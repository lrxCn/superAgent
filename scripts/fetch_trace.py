#!/usr/bin/env python3
"""Fetch a LangSmith trace by trace_id and save it as JSON.

Usage:
    uv run python scripts/fetch_trace.py <trace_id> [--project PROJECT]
    uv run python scripts/fetch_trace.py --latest [--project PROJECT]

The trace is saved to .langsmith_traces/<trace_id>.json (gitignored).
Requires LANGSMITH_API_KEY in environment or .env.
"""
from __future__ import annotations

import argparse
import json
import os
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


def default_project_name() -> str:
    """Resolve LangSmith project from env, matching runtime observability defaults."""
    return (
        os.getenv("LANGCHAIN_PROJECT")
        or os.getenv("LANGSMITH_PROJECT")
        or "SUPER_AGENT"
    )


def resolve_latest_trace_id(project: str | None = None) -> str:
    """Return trace_id of the most recent root run in the given project."""
    from langsmith import Client

    project_name = project or default_project_name()
    client = Client()
    runs = list(
        client.list_runs(
            project_name=project_name,
            is_root=True,
            limit=1,
        )
    )
    if not runs:
        sys.stderr.write(f"ERROR: No root runs found in project={project_name}\n")
        sys.exit(1)

    latest = runs[0]
    trace_id = getattr(latest, "trace_id", None) or latest.id
    sys.stdout.write(
        f"Latest trace: {trace_id} "
        f"(name={getattr(latest, 'name', '?')}, "
        f"start_time={getattr(latest, 'start_time', '?')}, "
        f"status={getattr(latest, 'status', '?')})\n"
    )
    return str(trace_id)


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
    parser.add_argument(
        "trace_id",
        nargs="?",
        default=None,
        help="The trace ID to fetch (omit when using --latest)",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Fetch the most recent root run in the project",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="LangSmith project name (default: LANGCHAIN_PROJECT / SUPER_AGENT)",
    )
    args = parser.parse_args()

    if args.latest and args.trace_id:
        parser.error("Use either --latest or trace_id, not both")
    if not args.latest and not args.trace_id:
        parser.error("Provide trace_id or --latest")

    trace_id = resolve_latest_trace_id(args.project) if args.latest else args.trace_id
    fetch_trace(trace_id, args.project)


if __name__ == "__main__":
    main()
