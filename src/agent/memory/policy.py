"""Memory write policies: candidate extraction, filtering, and stability checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.config import load_config
from agent.context_budget import HIGH_VALUE_MARKERS
from agent.reflection import FAILURE_MARKERS
from agent.router import HIGH_RISK_KEYWORDS
from agent.state import (
    AgentState,
    Evaluation,
    RuntimeConfig,
    is_user_message,
    message_content_text,
    message_role,
)

_SENSITIVE_CONTENT_PATTERN = re.compile(
    r"(password|passwd|token|secret|api[_-]?key|authorization|credential|"
    r"private[_-]?key|access[_-]?key|bearer\s+[a-z0-9._-]{8,}|"
    r"sk-[a-z0-9]{8,}|"
    r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----|"
    r"密码|密钥|凭证|秘钥)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+"
)
_TRANSIENT_MARKERS = (
    "fallback:",
    "i don't know",
    "unknown",
    "cannot answer",
    "无法回答",
    "暂不确定",
    "needs_revision",
    "incomplete_answer",
)
_PREFERENCE_MARKERS = (
    "preference:",
    "prefer:",
    "用户偏好",
    "偏好：",
    "偏好:",
)
_FACT_MARKERS = (
    "fact:",
    "remember:",
    "记住",
    "请记住",
)
_MIN_STABLE_LENGTH = 12
_MAX_CANDIDATES = 5


@dataclass(frozen=True)
class MemoryWriteCandidate:
    """A single long-term memory write candidate."""

    content: str
    source: str
    confidence: float
    category: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryWritePolicyResult:
    """Policy output consumed by the memory write node."""

    candidates: list[MemoryWriteCandidate]
    skipped: list[str]


def evaluate_write_policies(state: AgentState) -> MemoryWritePolicyResult:
    """Extract, filter, and stabilize memory write candidates."""
    skip_reason = memory_write_skip_reason(state)
    if skip_reason:
        return MemoryWritePolicyResult(candidates=[], skipped=[skip_reason])

    raw_candidates = _extract_candidates(state)
    eligible: list[MemoryWriteCandidate] = []
    skipped: list[str] = []

    for candidate in raw_candidates:
        sensitive_reason = sensitive_skip_reason(candidate.content)
        if sensitive_reason:
            skipped.append(f"{candidate.source}:{sensitive_reason}")
            continue
        if not is_stable_candidate(candidate, state):
            skipped.append(f"{candidate.source}:unstable")
            continue
        eligible.append(candidate)

    return MemoryWritePolicyResult(
        candidates=eligible[:_MAX_CANDIDATES],
        skipped=skipped,
    )


def memory_write_skip_reason(state: AgentState) -> str | None:
    """Return a global skip reason before candidate extraction."""
    runtime_config: RuntimeConfig = (
        state.get("runtime_config") or load_config().to_runtime_config()
    )
    if not runtime_config.get("memory_enabled", True):
        return "memory_disabled"

    evaluation = _current_evaluation(state)
    if evaluation.get("status") == "fail":
        return "evaluation_failed"
    if state.get("reflection_exhausted") and evaluation.get("status") == "fail":
        return "reflection_exhausted_unreliable"

    fallback_reason = state.get("fallback_reason")
    if fallback_reason and evaluation.get("status") == "fail":
        return "fallback_unreliable"

    return None


def sensitive_skip_reason(content: str) -> str | None:
    """Return a skip reason when content looks sensitive."""
    normalized = content.strip()
    if not normalized:
        return "empty_content"
    if _SENSITIVE_CONTENT_PATTERN.search(normalized):
        return "sensitive_content"
    if _SENSITIVE_VALUE_PATTERN.search(normalized):
        return "sensitive_assignment"
    if _looks_like_secret_token(normalized):
        return "secret_token"
    return None


def is_stable_candidate(candidate: MemoryWriteCandidate, state: AgentState) -> bool:
    """Return whether a candidate is stable enough for long-term storage."""
    content = candidate.content.strip()
    lowered = content.lower()

    if any(marker in lowered for marker in _TRANSIENT_MARKERS):
        return False
    if any(marker in content for marker in FAILURE_MARKERS):
        return False
    if len(content) < _MIN_STABLE_LENGTH and candidate.category not in {
        "preference",
        "explicit_fact",
    }:
        return False

    if candidate.category in {"preference", "explicit_fact", "agent_memory"}:
        return True

    if _is_high_value(content):
        return True

    evaluation = _current_evaluation(state)
    if evaluation.get("status") == "pass":
        return len(content) >= _MIN_STABLE_LENGTH

    if state.get("fallback_reason"):
        return False

    decision = state.get("intent_decision")
    path = decision["path"] if decision else None
    if path == "direct_answer" and evaluation.get("status") == "not_required":
        return _is_high_value(content) or candidate.confidence >= 0.8

    return candidate.confidence >= 0.75 and len(content) >= _MIN_STABLE_LENGTH


def _extract_candidates(state: AgentState) -> list[MemoryWriteCandidate]:
    candidates: list[MemoryWriteCandidate] = []
    thread_id = state.get("thread_id")
    user_id = state.get("user_id")
    group_id = state.get("group_id")
    run_id = state.get("run_id")
    base_metadata: dict[str, object] = {}
    if thread_id:
        base_metadata["thread_id"] = thread_id
    if user_id:
        base_metadata["user_id"] = user_id
    if group_id:
        base_metadata["group_id"] = group_id
    if run_id:
        base_metadata["run_id"] = run_id

    for message in state.get("messages", []):
        if not is_user_message(message):
            continue
        content = message_content_text(message).strip()
        if not content:
            continue
        category = _classify_user_content(content)
        if category is None:
            continue
        candidates.append(
            MemoryWriteCandidate(
                content=content,
                source="user_message",
                confidence=0.9 if category == "preference" else 0.85,
                category=category,
                metadata={**base_metadata, "role": message_role(message)},
            )
        )

    for result in state.get("agent_results", []):
        if result.get("role") != "memory_manager":
            continue
        output = result.get("output", "").strip()
        if not output:
            continue
        candidates.append(
            MemoryWriteCandidate(
                content=output,
                source=f"agent:{result.get('agent_name', 'memory_manager')}",
                confidence=float(result.get("confidence", 0.8)),
                category="agent_memory",
                metadata={**base_metadata, "agent_status": result.get("status")},
            )
        )

    for observation in state.get("observations", []):
        content = observation.get("content", "").strip()
        if not content or not _is_high_value(content):
            continue
        candidates.append(
            MemoryWriteCandidate(
                content=content,
                source=f"observation:{observation.get('source', 'unknown')}",
                confidence=0.7,
                category="observation",
                metadata={**base_metadata, "observation_error": observation.get("error")},
            )
        )

    final_answer = (state.get("final_answer") or "").strip()
    if final_answer and _should_consider_final_answer(state, final_answer):
        decision = state.get("intent_decision")
        candidates.append(
            MemoryWriteCandidate(
                content=final_answer,
                source="final_answer",
                confidence=_final_answer_confidence(state),
                category="final_answer",
                metadata={
                    **base_metadata,
                    "path": decision["path"] if decision else None,
                },
            )
        )

    return _dedupe_candidates(candidates)


def _should_consider_final_answer(state: AgentState, final_answer: str) -> bool:
    evaluation = _current_evaluation(state)
    if evaluation.get("status") == "fail":
        return False
    if any(keyword in final_answer.lower() for keyword in HIGH_RISK_KEYWORDS):
        return _has_explicit_memory_consent(state)
    if _is_high_value(final_answer):
        return True
    if evaluation.get("status") == "pass":
        return True
    return _has_explicit_memory_consent(state)


def _has_explicit_memory_consent(state: AgentState) -> bool:
    for message in state.get("messages", []):
        if not is_user_message(message):
            continue
        lowered = message_content_text(message).lower()
        if any(
            token in lowered
            for token in ("remember this", "save this", "记住", "保存到记忆", "写入记忆")
        ):
            return True
    return False


def _final_answer_confidence(state: AgentState) -> float:
    evaluation = _current_evaluation(state)
    if evaluation.get("status") == "pass":
        return 0.85
    if _has_explicit_memory_consent(state):
        return 0.8
    decision = state.get("intent_decision")
    return float(decision["confidence"]) if decision else 0.6


def _classify_user_content(content: str) -> str | None:
    lowered = content.lower()
    if any(marker in lowered for marker in _PREFERENCE_MARKERS):
        return "preference"
    if any(marker in lowered for marker in _FACT_MARKERS):
        return "explicit_fact"
    if _is_high_value(content):
        return "explicit_fact"
    return None


def _is_high_value(content: str) -> bool:
    lowered = content.strip().lower()
    return lowered.startswith(HIGH_VALUE_MARKERS)


def _looks_like_secret_token(content: str) -> bool:
    for token in content.split():
        cleaned = token.strip("`'\".,;")
        if len(cleaned) >= 24 and cleaned.isalnum():
            return True
        if cleaned.startswith("sk-") and len(cleaned) >= 12:
            return True
    return False


def _dedupe_candidates(candidates: list[MemoryWriteCandidate]) -> list[MemoryWriteCandidate]:
    seen: set[str] = set()
    deduped: list[MemoryWriteCandidate] = []
    for candidate in candidates:
        key = _normalize_key(candidate.content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _normalize_key(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())


def _current_evaluation(state: AgentState) -> Evaluation:
    return state.get("evaluation") or {
        "enabled": False,
        "status": "not_required",
        "issues": [],
        "suggestions": [],
    }
