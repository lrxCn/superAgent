"""Reflection gate, evaluator, and revise strategies."""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Callable, Literal

from langchain_core.messages import MessageLikeRepresentation

from agent.config import load_config
from agent.llm import LLMClient, LLMRequest, create_siliconflow_llm
from agent.observability import NodeTracker, safe_summary
from agent.router import (
    HIGH_RISK_KEYWORDS,
    LOW_CONFIDENCE_THRESHOLD,
    REVIEW_KEYWORDS,
)
from agent.state import (
    AgentState,
    Evaluation,
    RoutePath,
    is_user_message,
    message_content_text,
)

EvaluationStatus = Literal["not_required", "pass", "fail"]
EvaluationResult = Evaluation
EvaluatorFn = Callable[[AgentState], EvaluationResult | Awaitable[EvaluationResult]]
ReviseFn = Callable[[AgentState], str]


REFLECTION_PATHS: frozenset[RoutePath] = frozenset(
    {"react_agent", "planner", "multi_agent_orchestrator", "fallback"}
)

FAILURE_MARKERS = ("NEEDS_REVISION", "INCOMPLETE_ANSWER")
MIN_ANSWER_LENGTH = 8
EVALUATOR_SYSTEM_PROMPT = (
    "You are SuperAgent's reflection evaluator. Judge whether the draft answer "
    "satisfies the user's request, respects safety constraints, and does not "
    "contain placeholders. Return JSON only with this exact shape: "
    '{"status":"PASS|FAIL","issues":["short machine-readable issue ids"],'
    '"suggestions":["specific revision guidance"]}. Use PASS only when no '
    "revision is needed."
)


@dataclass(frozen=True)
class ReflectionGateDecision:
    """Whether reflection should run and why."""

    enabled: bool
    reasons: list[str]
    skip_reason: str | None


def compute_reflection_gate(state: AgentState) -> ReflectionGateDecision:
    """Decide if the current output should enter the evaluator."""
    runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
    if not runtime_config.get("reflection_enabled", True):
        return ReflectionGateDecision(
            enabled=False,
            reasons=[],
            skip_reason="reflection_disabled",
        )

    if state.get("reflection_exhausted"):
        return ReflectionGateDecision(
            enabled=False,
            reasons=[],
            skip_reason="reflection_exhausted",
        )

    decision = state.get("intent_decision")
    path = decision["path"] if decision else None
    confidence = decision["confidence"] if decision else 1.0
    requires_reflection = decision["requires_reflection"] if decision else False
    normalized = _normalize(_latest_user_text(state))

    reasons: list[str] = []

    if path in REFLECTION_PATHS:
        reasons.append(f"path:{path}")
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        reasons.append(f"low_confidence:{confidence:.2f}")
    if _keyword_matches(normalized, HIGH_RISK_KEYWORDS):
        reasons.extend(
            f"high_risk:{match}"
            for match in _keyword_matches(normalized, HIGH_RISK_KEYWORDS)[:3]
        )
    if _keyword_matches(normalized, REVIEW_KEYWORDS):
        reasons.extend(
            f"user_review:{match}"
            for match in _keyword_matches(normalized, REVIEW_KEYWORDS)[:3]
        )
    if requires_reflection and not reasons:
        reasons.append("route_requires_reflection")

    if path == "direct_answer" and not reasons:
        return ReflectionGateDecision(
            enabled=False,
            reasons=[],
            skip_reason="direct_low_risk",
        )

    if not reasons:
        return ReflectionGateDecision(
            enabled=False,
            reasons=[],
            skip_reason="no_reflection_triggers",
        )

    return ReflectionGateDecision(enabled=True, reasons=reasons, skip_reason=None)


def build_gate_evaluation(
    gate: ReflectionGateDecision,
    *,
    reflection_round: int,
) -> EvaluationResult:
    """Materialize gate output into the shared evaluation state."""
    if gate.enabled:
        return {
            "enabled": True,
            "status": "not_required",
            "issues": [],
            "suggestions": [],
            "round": reflection_round,
            "requires_revision": False,
            "gate_reasons": gate.reasons,
            "skip_reason": None,
            "source": "rule",
            "model": None,
        }
    return {
        "enabled": False,
        "status": "not_required",
        "issues": [],
        "suggestions": [],
        "round": reflection_round,
        "requires_revision": False,
        "gate_reasons": [],
        "skip_reason": gate.skip_reason,
        "source": "rule",
        "model": None,
    }


def evaluate_output(state: AgentState) -> EvaluationResult:
    """Run a deterministic first-phase evaluator for stable tests."""
    gate = compute_reflection_gate(state)
    reflection_round = state.get("reflection_round", 0)
    answer = (state.get("final_answer") or "").strip()
    normalized_answer = _normalize(answer)
    issues: list[str] = []
    suggestions: list[str] = []

    if not answer:
        issues.append("empty_answer")
        suggestions.append("Provide a complete answer grounded in the available context.")
    if any(marker in answer for marker in FAILURE_MARKERS):
        issues.append("quality_marker")
        suggestions.append("Remove placeholder markers and answer the user directly.")
    if len(answer) < MIN_ANSWER_LENGTH:
        issues.append("answer_too_short")
        suggestions.append("Expand the answer with the key facts requested by the user.")
    if _keyword_matches(normalized_answer, HIGH_RISK_KEYWORDS) and not _has_safety_note(
        answer
    ):
        issues.append("high_risk_without_disclaimer")
        suggestions.append(
            "Add a brief safety disclaimer for high-risk topics and avoid unsafe instructions."
        )

    user_goal = _normalize(_latest_user_text(state))
    if user_goal and _looks_like_question(user_goal) and "?" not in answer and "？" not in answer:
        if not _answer_addresses_goal(user_goal, normalized_answer):
            issues.append("incomplete_coverage")
            suggestions.append("Address each part of the user's request explicitly.")

    status: EvaluationStatus = "fail" if issues else "pass"
    return {
        "enabled": gate.enabled,
        "status": status,
        "issues": issues,
        "suggestions": suggestions,
        "round": reflection_round,
        "requires_revision": status == "fail",
        "gate_reasons": gate.reasons,
        "skip_reason": gate.skip_reason,
        "source": "rule",
        "model": None,
    }


async def evaluate_output_with_llm(
    state: AgentState,
    *,
    llm_factory: Callable[[], LLMClient] = create_siliconflow_llm,
) -> EvaluationResult:
    """Run the default LLM-backed structured evaluator."""
    gate = compute_reflection_gate(state)
    reflection_round = state.get("reflection_round", 0)
    try:
        llm = llm_factory()
        result = await llm.generate(
            LLMRequest(messages=build_evaluator_messages(state), temperature=0.0)
        )
    except Exception:
        return evaluate_output(state)

    parsed = parse_evaluation_response(
        result.content,
        gate=gate,
        reflection_round=reflection_round,
        model=result.model,
    )
    if parsed is None:
        return evaluate_output(state)
    return parsed


def build_evaluator_messages(state: AgentState) -> list[MessageLikeRepresentation]:
    """Build the structured reflection evaluator prompt."""
    answer = (state.get("final_answer") or "").strip()
    gate = _current_evaluation(state)
    gate_reasons = gate.get("gate_reasons") or compute_reflection_gate(state).reasons
    observations = state.get("observations", [])[-4:]
    observation_lines = [
        f"- {item['source']}: {safe_summary(item['content'], max_chars=300)}"
        for item in observations
        if item.get("content")
    ]
    user_content = "\n\n".join(
        [
            f"User request:\n{_latest_user_text(state) or 'none'}",
            f"Reflection triggers:\n{', '.join(gate_reasons) if gate_reasons else 'none'}",
            "Recent observations:\n"
            + ("\n".join(observation_lines) if observation_lines else "none"),
            f"Draft answer:\n{answer or 'none'}",
        ]
    )
    return [
        {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_evaluation_response(
    raw: str,
    *,
    gate: ReflectionGateDecision,
    reflection_round: int,
    model: str | None = None,
) -> EvaluationResult | None:
    """Parse LLM evaluator JSON into the shared evaluation shape."""
    payload = _extract_json_object(raw)
    if payload is None:
        return None

    status = _parse_evaluation_status(payload.get("status"))
    if status is None:
        return None

    issues = _string_list(payload.get("issues"))
    suggestions = _string_list(payload.get("suggestions"))
    if status == "pass":
        issues = []
    elif not issues:
        issues = ["llm_quality_review_failed"]
    if status == "fail" and not suggestions:
        suggestions = ["Revise the answer to address the evaluator's quality concerns."]

    return {
        "enabled": gate.enabled,
        "status": status,
        "issues": issues,
        "suggestions": suggestions,
        "round": reflection_round,
        "requires_revision": status == "fail",
        "gate_reasons": gate.reasons,
        "skip_reason": gate.skip_reason,
        "source": "llm",
        "model": model,
    }


def _current_evaluation(state: AgentState) -> Evaluation:
    """Return the current evaluation payload with stable defaults."""
    return state.get("evaluation") or {
        "enabled": False,
        "status": "not_required",
        "issues": [],
        "suggestions": [],
        "source": "rule",
        "model": None,
    }


def revise_output(state: AgentState) -> str:
    """Apply deterministic fixes from evaluator feedback."""
    answer = (state.get("final_answer") or "").strip()
    evaluation = _current_evaluation(state)
    issues = evaluation.get("issues", [])
    suggestions = evaluation.get("suggestions", [])
    revised = answer

    if "empty_answer" in issues:
        revised = "Revised answer: the runtime could not recover enough context to answer fully."
    if "quality_marker" in issues:
        for marker in FAILURE_MARKERS:
            revised = revised.replace(marker, "").strip()
        if not revised:
            revised = "Revised answer after quality review."
    if "answer_too_short" in issues and len(revised) < MIN_ANSWER_LENGTH:
        revised = f"{revised} Additional detail added after quality review."
    if "high_risk_without_disclaimer" in issues and not _has_safety_note(revised):
        revised = (
            f"{revised}\n\nSafety note: verify high-risk guidance with qualified professionals "
            "before acting."
        )
    if "incomplete_coverage" in issues:
        user_goal = _latest_user_text(state)
        revised = f"{revised}\n\nCoverage note: addressed user request -> {user_goal}".strip()

    review_notes = [
        note
        for note in issues
        if note
        and note
        not in {
            "empty_answer",
            "quality_marker",
            "answer_too_short",
            "high_risk_without_disclaimer",
            "incomplete_coverage",
        }
    ]
    if review_notes:
        revised = (
            f"{revised}\n\nQuality review focus: {', '.join(review_notes)}."
        ).strip()

    for suggestion in suggestions:
        if suggestion and suggestion not in revised:
            revised = f"{revised}\n{suggestion}".strip()

    return revised.strip()


def choose_reflection_path(state: AgentState) -> Literal["evaluator", "memory_write"]:
    """Route from reflection gate to evaluator or memory write."""
    evaluation = _current_evaluation(state)
    if evaluation.get("enabled"):
        return "evaluator"
    return "memory_write"


def choose_evaluator_path(
    state: AgentState,
) -> Literal["memory_write", "revise", "fallback"]:
    """Route evaluator output to pass, revise, or fallback."""
    evaluation = _current_evaluation(state)
    status = evaluation.get("status", "not_required")
    if status != "fail":
        return "memory_write"

    runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
    reflection_round = state.get("reflection_round", 0)
    max_rounds = runtime_config.get("reflection_max_rounds", 1)
    if reflection_round < max_rounds:
        return "revise"
    return "fallback"


def _has_safety_note(answer: str) -> bool:
    lowered = answer.lower()
    return any(
        token in lowered
        for token in (
            "safety note",
            "verify",
            "qualified professional",
            "disclaimer",
            "安全",
            "免责声明",
        )
    )


def _looks_like_question(text: str) -> bool:
    return "?" in text or "？" in text or text.startswith(("what", "how", "why", "explain"))


def _answer_addresses_goal(user_goal: str, normalized_answer: str) -> bool:
    tokens = [token for token in re.split(r"\W+", user_goal) if len(token) >= 5]
    if not tokens:
        return True
    hits = sum(1 for token in tokens if token in normalized_answer)
    return hits >= min(2, len(tokens))


@dataclass
class ReflectionGateNode:
    """Graph node that decides whether reflection should run."""

    async def __call__(self, state: AgentState) -> AgentState:
        """Write gate decision into graph state."""
        tracker = NodeTracker(state, "reflection_gate", event="reflection")
        gate = compute_reflection_gate(state)
        reflection_round = state.get("reflection_round", 0)
        return tracker.finish(
            {"evaluation": build_gate_evaluation(gate, reflection_round=reflection_round)},
            summary=(
                f"reflection_enabled={gate.enabled} "
                f"reasons={safe_summary(gate.reasons or gate.skip_reason or '', max_chars=120)}"
            ),
            status="skipped" if not gate.enabled else "completed",
        )


@dataclass
class EvaluatorNode:
    """Graph node that evaluates the current final answer."""

    evaluator: EvaluatorFn | None = None
    llm_factory: Callable[[], LLMClient] = create_siliconflow_llm

    async def __call__(self, state: AgentState) -> AgentState:
        """Evaluate the current answer and record PASS/FAIL."""
        tracker = NodeTracker(state, "evaluator", event="reflection")
        if self.evaluator is not None:
            result = await _call_evaluator(self.evaluator, state)
        else:
            result = await evaluate_output_with_llm(state, llm_factory=self.llm_factory)
        return tracker.finish(
            {"evaluation": result},
            summary=f"evaluation_status={result.get('status', 'not_required')}",
            status="failed" if result.get("status") == "fail" else "completed",
        )


@dataclass
class ReviseNode:
    """Graph node that revises the answer after a failed evaluation."""

    reviser: ReviseFn | None = None

    async def __call__(self, state: AgentState) -> AgentState:
        """Revise the answer after a failed evaluation."""
        tracker = NodeTracker(state, "revise", event="reflection")
        reflection_round = state.get("reflection_round", 0) + 1
        revised_answer = (self.reviser or revise_output)(state)
        return tracker.finish(
            {
                "final_answer": revised_answer,
                "reflection_round": reflection_round,
            },
            summary=f"revision_round={reflection_round} answer_chars={len(revised_answer)}",
        )


def create_reflection_gate_node() -> ReflectionGateNode:
    """Create the reflection gate graph node."""
    return ReflectionGateNode()


def create_evaluator_node(
    evaluator: EvaluatorFn | None = None,
    llm_client: LLMClient | None = None,
) -> EvaluatorNode:
    """Create the evaluator graph node."""
    if llm_client is not None:
        return EvaluatorNode(evaluator=evaluator, llm_factory=lambda: llm_client)
    return EvaluatorNode(evaluator=evaluator)


def create_revise_node(reviser: ReviseFn | None = None) -> ReviseNode:
    """Create the revise graph node."""
    return ReviseNode(reviser=reviser)


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if is_user_message(message):
            return message_content_text(message)
    return ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _keyword_matches(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if _keyword_matches_text(text, keyword)]


def _keyword_matches_text(text: str, keyword: str) -> bool:
    if keyword.isascii() and re.search(r"[a-z0-9]", keyword):
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return keyword in text


async def _call_evaluator(
    evaluator: EvaluatorFn,
    state: AgentState,
) -> EvaluationResult:
    result = evaluator(state)
    if inspect.isawaitable(result):
        return await result
    return result


def _extract_json_object(raw: str) -> dict[str, object] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_evaluation_status(value: object) -> EvaluationStatus | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"pass", "passed", "ok"}:
        return "pass"
    if normalized in {"fail", "failed", "needs_revision", "revise"}:
        return "fail"
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [
            safe_summary(str(item).strip(), max_chars=200)
            for item in value
            if str(item).strip()
        ]
    if isinstance(value, str) and value.strip():
        return [safe_summary(value.strip(), max_chars=200)]
    return []
