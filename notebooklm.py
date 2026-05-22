"""
notebooklm.py — Wrapper around the `nlm` CLI (notebooklm-mcp-cli).
All NotebookLM operations go through here.
"""

import os
import re
import asyncio
import subprocess
from typing import Optional


def _nlm_path() -> str:
    return os.getenv("NLM_PATH", "nlm")


async def _run(args: list[str]) -> tuple[int, str, str]:
    """Run an nlm CLI command asynchronously. Returns (returncode, stdout, stderr)."""
    cmd = [_nlm_path()] + args
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def create_notebook(name: str) -> Optional[str]:
    """
    Create a new NotebookLM notebook and return its ID.
    Example: nlm notebook create "B2B Sales Insights"
    Returns the notebook ID string, or None if failed.
    """
    code, out, err = await _run(["notebook", "create", name, "--json"])
    if code != 0:
        # Fallback: try without --json flag (older versions)
        code, out, err = await _run(["notebook", "create", name])

    if code != 0:
        print(f"[NLM] Failed to create notebook '{name}': {err}")
        return None

    # Try to extract notebook ID from JSON output first
    try:
        import json
        data = json.loads(out)
        return data.get("id") or data.get("notebook_id") or str(data)
    except Exception:
        pass

    # Fallback: extract from plain text output
    # nlm typically prints something like: "Created notebook: abc123"
    match = re.search(r"['\"]?([a-zA-Z0-9_-]{10,})['\"]?", out)
    if match:
        return match.group(1)

    return out if out else None


async def add_source(notebook_id: str, url: str) -> bool:
    """
    Add a YouTube URL as a source to a NotebookLM notebook.
    Example: nlm source add <notebook_id> --url "https://youtube.com/watch?v=..."
    Returns True on success.
    """
    code, out, err = await _run(["source", "add", notebook_id, "--url", url])
    if code != 0:
        print(f"[NLM] Failed to add source {url}: {err}")
        return False
    return True


async def list_notebooks() -> list[dict]:
    """
    List all NotebookLM notebooks.
    Returns a list of {id, name} dicts.
    """
    code, out, err = await _run(["notebook", "list", "--json"])
    if code != 0:
        # Try plain text
        code, out, err = await _run(["notebook", "list"])
        if code != 0:
            return []
        # Parse plain text lines
        notebooks = []
        for line in out.splitlines():
            line = line.strip()
            if line:
                notebooks.append({"id": line, "name": line})
        return notebooks

    try:
        import json
        data = json.loads(out)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


async def is_nlm_available() -> bool:
    """Check if nlm CLI is installed and authenticated."""
    code, out, err = await _run(["--version"])
    return code == 0
