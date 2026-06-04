#!/usr/bin/env python3
"""Fetch a LangSmith trace by trace_id and save it as JSON.

Usage:
    uv run python scripts/fetch_trace.py <trace_id> [--project PROJECT]

The trace is saved to .langsmith_traces/<trace_id>.json (gitignored).
Requires LANGSMITH_API_KEY in environment or .env.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TRACE_DIR = PROJECT_ROOT / ".langsmith_traces"


def _run_to_dict(run: object) -> dict:
    """Convert a langsmith Run object to a JSON-serializable dict."""
    if hasattr(run, "model_dump"):
        return run.model_dump(mode="json")
    if hasattr(run, "dict"):
        return run.dict()
    return dict(run)


def fetch_trace(trace_id: str, project: str | None = None) -> Path:
    """Fetch all runs in a trace tree and save as a single JSON file.

    Returns the path to the saved file.
    """
    from langsmith import Client

    client = Client()

    # list_runs with trace_id returns the full tree
    kwargs: dict = {"trace_id": trace_id}
    if project:
        kwargs["project_name"] = project

    runs = list(client.list_runs(**kwargs))

    if not runs:
        # Fallback: try read_run on the trace_id itself
        try:
            root = client.read_run(trace_id, load_child_runs=True)
            runs = [root]
            # read_run with load_child_runs may attach children via .child_runs
            if hasattr(root, "child_runs") and root.child_runs:
                runs.extend(root.child_runs)
        except Exception as exc:
            sys.stderr.write(f"ERROR: No runs found for trace_id={trace_id}: {exc}\n")
            sys.exit(1)

    # Sort by start_time for readability
    runs.sort(key=lambda r: getattr(r, "start_time", None) or "")

    output = {
        "trace_id": trace_id,
        "run_count": len(runs),
        "runs": [_run_to_dict(r) for r in runs],
    }

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TRACE_DIR / f"{trace_id}.json"
    out_path.write_text(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    sys.stdout.write(f"Saved {len(runs)} runs to {out_path}\n")
    return out_path


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Fetch a LangSmith trace and save as JSON")
    parser.add_argument("trace_id", help="The trace ID to fetch")
    parser.add_argument("--project", default=None, help="LangSmith project name (optional)")
    args = parser.parse_args()

    fetch_trace(args.trace_id, args.project)


if __name__ == "__main__":
    main()
