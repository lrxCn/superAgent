from agent.state import AgentState, IntentDecision, RuntimeConfig


def test_agent_state_accepts_minimum_runtime_contract() -> None:
    runtime_config: RuntimeConfig = {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }
    decision: IntentDecision = {
        "path": "direct_answer",
        "reason": "unit test",
        "confidence": 1.0,
    }
    state: AgentState = {
        "messages": [{"role": "user", "content": "hello"}],
        "runtime_config": runtime_config,
        "memory_context": {
            "short_term": [],
            "long_term": [],
            "entities": [],
            "errors": [],
        },
        "context_budget": {
            "estimated_tokens": 1,
            "max_tokens": 4096,
            "compressed": False,
            "summary": None,
        },
        "intent_decision": decision,
        "plan": {"steps": [], "status": "not_started"},
        "current_step": None,
        "mcp_sessions": [],
        "tool_calls": [],
        "observations": [],
        "agent_results": [],
        "evaluation": {
            "enabled": False,
            "status": "not_required",
            "issues": [],
            "suggestions": [],
        },
        "fallback_reason": None,
        "memory_write_result": {
            "status": "skipped",
            "reason": "unit test",
        },
        "final_answer": "hello",
    }

    expected_fields = {
        "messages",
        "runtime_config",
        "memory_context",
        "context_budget",
        "intent_decision",
        "plan",
        "current_step",
        "mcp_sessions",
        "tool_calls",
        "observations",
        "agent_results",
        "evaluation",
        "fallback_reason",
        "memory_write_result",
        "final_answer",
    }
    assert expected_fields.issubset(state.keys())
