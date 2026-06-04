"""Deterministic intent and complexity routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.state import (
    AgentState,
    IntentDecision,
    RoutePath,
    is_user_message,
    message_content_text,
)

LOW_CONFIDENCE_THRESHOLD = 0.72

CLARIFICATION_PATTERNS = (
    re.compile(r"^\s*$"),
    re.compile(r"^\s*(help|帮我|处理一下|搞一下|做一下|看看|fix it)\s*[。.!?？]?\s*$", re.I),
    re.compile(r"\b(this|that|it|thing)\b", re.I),
)
TOOL_KEYWORDS = (
    "search",
    "look up",
    "browse",
    "fetch",
    "download",
    "api",
    "mcp",
    "tool",
    "file",
    "read",
    "write",
    "execute",
    "run",
    "test",
    "shell",
    "terminal",
    "latest",
    "current",
    "today",
    "搜索",
    "查询",
    "联网",
    "浏览",
    "下载",
    "接口",
    "工具",
    "文件",
    "读取",
    "写入",
    "执行",
    "运行",
    "测试",
    "最新",
    "今天",
)
PLAN_KEYWORDS = (
    "plan",
    "roadmap",
    "architecture",
    "design",
    "implement",
    "build",
    "refactor",
    "migrate",
    "analyze",
    "debug",
    "investigate",
    "multi-step",
    "step by step",
    "方案",
    "计划",
    "架构",
    "设计",
    "实现",
    "开发",
    "重构",
    "迁移",
    "分析",
    "排查",
    "调试",
    "拆分",
    "步骤",
)
MULTI_AGENT_KEYWORDS = (
    "parallel",
    "concurrent",
    "multi-agent",
    "orchestrate",
    "researcher",
    "coder",
    "reviewer",
    "分工",
    "并行",
    "多 agent",
    "多-agent",
    "多智能体",
    "研究员",
    "开发者",
    "审查",
    "评审",
    "协作",
)
HIGH_RISK_KEYWORDS = (
    "delete database",
    "drop table",
    "production",
    "prod",
    "credential",
    "secret",
    "api key",
    "medical",
    "legal",
    "financial",
    "investment",
    "删除数据库",
    "删库",
    "生产环境",
    "凭证",
    "密钥",
    "医疗",
    "法律",
    "金融",
    "投资",
)
REVIEW_KEYWORDS = (
    "review",
    "check",
    "verify",
    "audit",
    "validate",
    "检查",
    "审核",
    "审查",
    "验证",
    "复核",
)


@dataclass(frozen=True)
class RouteCandidate:
    """Intermediate score for a route."""

    path: RoutePath
    reason: str
    confidence: float
    signals: list[str]


def route_intent(state: AgentState) -> IntentDecision:
    """Classify task intent and complexity using deterministic rules."""
    text = _latest_user_text(state)
    normalized = _normalize(text)
    candidates = [
        _fallback_candidate(text, normalized),
        _multi_agent_candidate(normalized),
        _planner_candidate(normalized),
        _react_candidate(normalized),
        _direct_candidate(normalized),
    ]
    best = max(candidates, key=lambda candidate: candidate.confidence)
    requires_reflection = _requires_reflection(
        path=best.path,
        confidence=best.confidence,
        normalized=normalized,
    )
    return {
        "path": best.path,
        "reason": best.reason,
        "confidence": best.confidence,
        "signals": best.signals,
        "requires_reflection": requires_reflection,
    }


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if is_user_message(message):
            return message_content_text(message)
    return ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _fallback_candidate(text: str, normalized: str) -> RouteCandidate:
    if any(pattern.search(text) for pattern in CLARIFICATION_PATTERNS):
        return RouteCandidate(
            path="fallback",
            reason="Input is underspecified and needs clarification before execution.",
            confidence=0.9,
            signals=["input_insufficient"],
        )
    high_risk_matches = _keyword_matches(normalized, HIGH_RISK_KEYWORDS)
    if high_risk_matches:
        return RouteCandidate(
            path="fallback",
            reason="High-risk request requires clarification or a safer execution boundary.",
            confidence=0.86,
            signals=[f"high_risk:{match}" for match in high_risk_matches[:3]],
        )
    return RouteCandidate(
        path="fallback",
        reason="No fallback risk signals matched.",
        confidence=0.0,
        signals=[],
    )


def _multi_agent_candidate(normalized: str) -> RouteCandidate:
    matches = _keyword_matches(normalized, MULTI_AGENT_KEYWORDS)
    if matches:
        return RouteCandidate(
            path="multi_agent_orchestrator",
            reason="Request mentions specialist roles, collaboration, or parallel work.",
            confidence=min(0.92, 0.78 + len(matches) * 0.04),
            signals=[f"multi_agent:{match}" for match in matches[:4]],
        )
    return RouteCandidate(
        path="multi_agent_orchestrator",
        reason="No multi-agent signals matched.",
        confidence=0.0,
        signals=[],
    )


def _planner_candidate(normalized: str) -> RouteCandidate:
    matches = _keyword_matches(normalized, PLAN_KEYWORDS)
    complexity = _complexity_signals(normalized)
    signals = [f"plan:{match}" for match in matches[:4]] + complexity
    if signals:
        confidence = 0.7 + min(0.22, len(signals) * 0.04)
        return RouteCandidate(
            path="planner",
            reason="Request appears to require multiple steps or implementation planning.",
            confidence=confidence,
            signals=signals,
        )
    return RouteCandidate(
        path="planner",
        reason="No planning complexity signals matched.",
        confidence=0.0,
        signals=[],
    )


def _react_candidate(normalized: str) -> RouteCandidate:
    matches = _keyword_matches(normalized, TOOL_KEYWORDS)
    if matches:
        return RouteCandidate(
            path="react_agent",
            reason="Request needs tools, files, execution, or external/current information.",
            confidence=min(0.9, 0.74 + len(matches) * 0.03),
            signals=[f"tool:{match}" for match in matches[:5]],
        )
    return RouteCandidate(
        path="react_agent",
        reason="No tool or external information signals matched.",
        confidence=0.0,
        signals=[],
    )


def _direct_candidate(normalized: str) -> RouteCandidate:
    word_count = len(normalized.split())
    if not normalized:
        confidence = 0.0
    elif word_count <= 14 and not _has_list_or_sequence(normalized) and normalized.count(",") <= 1:
        confidence = 0.82
    else:
        confidence = 0.68
    return RouteCandidate(
        path="direct_answer",
        reason="Request looks like a simple answerable prompt without tool or planning signals.",
        confidence=confidence,
        signals=["simple_question"] if confidence >= LOW_CONFIDENCE_THRESHOLD else ["ambiguous_direct"],
    )


def _keyword_matches(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if _keyword_matches_text(text, keyword)]


def _keyword_matches_text(text: str, keyword: str) -> bool:
    if keyword.isascii() and re.search(r"[a-z0-9]", keyword):
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return keyword in text


def _complexity_signals(text: str) -> list[str]:
    signals: list[str] = []
    if _has_list_or_sequence(text):
        signals.append("complexity:sequence")
    if len(text.split()) >= 40:
        signals.append("complexity:long_request")
    if any(separator in text for separator in (" and then ", " then ", "然后", "并且", "同时")):
        signals.append("complexity:multi_clause")
    return signals


def _has_list_or_sequence(text: str) -> bool:
    return bool(re.search(r"(^|\s)(1\.|2\.|3\.|- |\* )", text)) or "；" in text or ";" in text


def _requires_reflection(
    *,
    path: RoutePath,
    confidence: float,
    normalized: str,
) -> bool:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return True
    if path in {"react_agent", "planner", "multi_agent_orchestrator", "fallback"}:
        return True
    if _keyword_matches(normalized, HIGH_RISK_KEYWORDS):
        return True
    return bool(_keyword_matches(normalized, REVIEW_KEYWORDS))
