"""Model Context Protocol (MCP) server for ckpt.

Exposes checkpoint operations as MCP tools so that AI agents (e.g.
Claude Desktop, Cursor, or any MCP-compatible host) can save, list,
and inspect development session snapshots programmatically.

The server is built on the official Anthropic ``FastMCP`` SDK and
communicates over **stdio** transport by default.
"""

from __future__ import annotations

import asyncio
import logging
import re

from mcp.server.fastmcp import FastMCP

from ckpt.snapshot import SnapshotError, create_snapshot
from ckpt.store import (
    CheckpointNotFoundError,
    StoreError,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("checkpoint")

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_SAFE_ID_RE = re.compile(r"^[a-f0-9]{1,64}$")
"""Regex enforcing that snapshot IDs are pure lowercase hex — no path
traversal characters (``../``, ``\\``, ``/``) or shell metacharacters."""


def _validate_snapshot_id(snapshot_id: str) -> str:
    """Sanitise and validate a snapshot ID against path-traversal attacks.

    Args:
        snapshot_id: The raw ID string received from the caller.

    Returns:
        The validated, stripped ID.

    Raises:
        ValueError: If the ID contains illegal characters or patterns.
    """
    cleaned = snapshot_id.strip()
    if not _SAFE_ID_RE.match(cleaned):
        raise ValueError(
            f"Invalid snapshot ID '{cleaned}'. "
            "IDs must contain only lowercase hexadecimal characters (a-f, 0-9)."
        )
    return cleaned


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_snapshots() -> str:
    """List all saved checkpoints.

    Scans ``~/.config/ckpt/snapshots/`` and returns a formatted summary
    of every available checkpoint including its ID, timestamp, branch,
    and message.

    Returns:
        A human-readable, newline-separated list of checkpoints, or a
        message indicating that none exist.
    """
    try:
        loop = asyncio.get_running_loop()
        checkpoints = await loop.run_in_executor(None, list_checkpoints)
    except StoreError as exc:
        return f"[error] Failed to list checkpoints: {exc}"

    if not checkpoints:
        return "No checkpoints found. Use `save_checkpoint` to create one."

    lines: list[str] = [f"Found {len(checkpoints)} checkpoint(s):\n"]
    for cp in checkpoints:
        ts = cp.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"  [{cp.id}]  {ts}  |  branch: {cp.branch}  |  {cp.message}")
    return "\n".join(lines)


@mcp.tool()
async def get_snapshot_by_id(snapshot_id: str) -> str:
    """Fetch the full JSON contents of a checkpoint by its ID.

    The ID is validated against path-traversal patterns before any
    filesystem access.

    Args:
        snapshot_id: The 8-character hexadecimal checkpoint ID.

    Returns:
        The raw JSON representation of the checkpoint, or an error
        message if the ID is invalid or the checkpoint does not exist.
    """
    try:
        safe_id = _validate_snapshot_id(snapshot_id)
    except ValueError as exc:
        return f"[error] {exc}"

    try:
        loop = asyncio.get_running_loop()
        checkpoint = await loop.run_in_executor(None, load_checkpoint, safe_id)
    except CheckpointNotFoundError:
        return f"[error] No checkpoint found with id '{safe_id}'."
    except StoreError as exc:
        return f"[error] Failed to load checkpoint: {exc}"

    return checkpoint.model_dump_json(indent=2)


@mcp.tool()
async def save_snapshot(message: str) -> str:
    """Capture the current development session state as a new checkpoint.

    Programmatically executes the snapshot logic: reads the active git
    branch, latest commit, uncommitted diff, modified files, and recent
    shell history, then persists the result to disk.

    Args:
        message: A description of the current session state or intent.

    Returns:
        A confirmation string containing the generated checkpoint ID
        and storage path, or an error message on failure.
    """
    if not message or not message.strip():
        return "[error] A non-empty message is required."

    try:
        loop = asyncio.get_running_loop()
        checkpoint = await loop.run_in_executor(None, create_snapshot, message.strip())
    except SnapshotError as exc:
        return f"[error] Snapshot capture failed: {exc}"

    try:
        path = await loop.run_in_executor(None, save_checkpoint, checkpoint)
    except StoreError as exc:
        return f"[error] Failed to persist checkpoint: {exc}"

    return (
        f"Checkpoint saved successfully.\n"
        f"  ID:     {checkpoint.id}\n"
        f"  Branch: {checkpoint.branch}\n"
        f"  Commit: {checkpoint.commit_hash[:8]}\n"
        f"  Files:  {len(checkpoint.files_locked)} modified\n"
        f"  Path:   {path}"
    )


# ---------------------------------------------------------------------------
# MCP prompt template
# ---------------------------------------------------------------------------


@mcp.prompt()
def checkpoint_guidance() -> str:
    """System instructions for AI agents on using the checkpoint tools.

    Returns a structured prompt explaining when and how to use
    ``save_snapshot``, ``list_snapshots``, and ``get_snapshot_by_id``.
    """
    return (
        "You have access to a local checkpoint system via the following tools:\n\n"
        "1. **save_snapshot(message)** -- Capture the current development session\n"
        "   state (git branch, commit, diff, modified files, shell history) as a\n"
        "   persistent checkpoint. Call this tool:\n"
        "   - Before starting a complex refactoring or risky code change.\n"
        "   - After completing a meaningful unit of work.\n"
        "   - When the developer explicitly asks to save progress.\n"
        "   Always provide a concise but descriptive message summarising the\n"
        "   session intent (e.g. 'Pre-refactor: auth module extraction').\n\n"
        "2. **list_snapshots()** -- Retrieve a summary of all saved checkpoints.\n"
        "   Use this to help the developer locate a prior state or to verify\n"
        "   that a checkpoint was saved successfully.\n\n"
        "3. **get_snapshot_by_id(snapshot_id)** -- Fetch the full JSON details\n"
        "   of a specific checkpoint. Use this to inspect the exact diff,\n"
        "   modified files, or session history of a previous state.\n\n"
        "General guidelines:\n"
        "- Proactively suggest saving a checkpoint before destructive operations.\n"
        "- When restoring context after a break, list snapshots and summarise\n"
        "  the most recent one to help the developer regain focus.\n"
        "- Never fabricate checkpoint IDs; always use `list_snapshots` first."
    )


# ---------------------------------------------------------------------------
# Server launcher
# ---------------------------------------------------------------------------


def run_server() -> None:
    """Launch the MCP server over stdio transport.

    All exceptions during transport are caught and logged to prevent
    raw tracebacks from leaking into the stdio stream.
    """
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("MCP server stopped by user.")
    except Exception as exc:
        logger.critical("MCP server crashed: %s", exc, exc_info=True)


if __name__ == "__main__":
    run_server()
