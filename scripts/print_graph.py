#!/usr/bin/env python3
"""Print the compiled SuperAgent LangGraph as Mermaid and copy it to the clipboard."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

NODE_DECLARATION = re.compile(r"^([A-Za-z0-9_]+)\(([^()<>]+)\)$")


def repo_root() -> Path:
    """Return the repository root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def add_import_roots(root: Path) -> None:
    """Ensure agent imports resolve when running as a standalone script."""
    for path in (root, root / "src"):
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


def to_compatible_mermaid(mermaid: str) -> str:
    """Strip LangGraph HTML labels and classDef syntax for common renderers."""
    lines = ["flowchart TD"]
    for raw_line in mermaid.splitlines():
        line = raw_line.strip().rstrip(";")
        if not line or line == "---":
            continue
        if line.startswith(("config:", "flowchart:", "curve:", "graph ", "classDef ")):
            continue
        if line.startswith("__start__("):
            lines.append("    start_node([START])")
            continue
        if line.startswith("__end__("):
            lines.append("    end_node([END])")
            continue

        line = line.replace("__start__", "start_node").replace("__end__", "end_node")
        node_match = NODE_DECLARATION.match(line)
        if node_match:
            node_id, label = node_match.groups()
            lines.append(f'    {node_id}["{label}"]')
        else:
            lines.append(f"    {line}")
    return "\n".join(lines) + "\n"


def render_mermaid() -> str:
    """Compile the runtime graph and return Mermaid text."""
    add_import_roots(repo_root())
    from agent.graph import build_graph

    return to_compatible_mermaid(build_graph().get_graph().draw_mermaid())


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard."""
    encoded = text.encode("utf-8")
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=encoded, check=True)
        return
    if sys.platform == "win32":
        subprocess.run(["clip"], input=text.encode("utf-16le"), check=True)
        return
    if shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=encoded, check=True)
        return
    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=encoded,
            check=True,
        )
        return
    raise RuntimeError("未找到剪贴板工具（macOS: pbcopy；Linux: wl-copy / xclip）")


def main() -> int:
    """Print Mermaid to stdout and copy the same content to the clipboard."""
    output = render_mermaid()
    sys.stdout.write(output)
    try:
        copy_to_clipboard(output)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.stderr.write(f"警告：未能复制到剪贴板（{exc}）\n")
        return 1
    sys.stderr.write("已复制 Mermaid 到剪贴板\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
