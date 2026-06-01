"""System state capture logic for ckpt.

This module provides safe subprocess wrappers for querying git metadata,
shell history readers for Bash and Zsh, and the top-level factory
function :func:`create_snapshot` that assembles a fully populated
:class:`~ckpt.models.Checkpoint` instance.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
from collections import deque
from pathlib import Path

from ckpt.models import Checkpoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SnapshotError(Exception):
    """Base exception for all snapshot capture failures."""


class GitNotFoundError(SnapshotError):
    """Raised when the ``git`` binary is not found on the system PATH."""


class GitCommandError(SnapshotError):
    """Raised when a git subprocess exits with a non-zero return code."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DIFF_SNIPPET_LIMIT = 2048
"""Maximum number of characters from the diff used for ID hashing."""


def _run_git(*args: str) -> str:
    """Execute a git command and return its stripped stdout.

    Args:
        *args: Positional arguments forwarded to ``git`` (e.g.
            ``"branch"``, ``"--show-current"``).

    Returns:
        The captured stdout with leading/trailing whitespace removed.

    Raises:
        GitNotFoundError: If the ``git`` executable is absent from PATH.
        GitCommandError: If the command exits with a non-zero code.
    """
    cmd = ["git", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        logger.error("git binary not found on PATH")
        raise GitNotFoundError("git is not installed or not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        logger.error("git command failed: %s — %s", cmd, stderr)
        raise GitCommandError(
            f"git {' '.join(args)} failed (rc={exc.returncode}): {stderr}"
        ) from exc

    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Git queries
# ---------------------------------------------------------------------------


def get_current_branch() -> str:
    """Return the name of the currently checked-out git branch.

    Returns:
        The branch name (e.g. ``"main"`` or ``"feature/auth"``).

    Raises:
        GitNotFoundError: If git is not installed.
        GitCommandError: If the command fails (e.g. not a git repository).
    """
    return _run_git("branch", "--show-current")


def get_last_commit_hash() -> str:
    """Return the full SHA-1 hash of the latest commit.

    Returns:
        A 40-character hexadecimal commit hash, or a fallback hash of all zeros
        for newly initialized repositories that have no commits yet.

    Raises:
        GitNotFoundError: If git is not installed.
        GitCommandError: If the command fails for a reason other than an empty repository.
    """
    try:
        return _run_git("rev-parse", "HEAD")
    except GitCommandError as exc:
        # Check if we are inside a git repository but it has no commits yet
        try:
            is_inside = _run_git("rev-parse", "--is-inside-work-tree")
            if is_inside == "true":
                return "0000000000000000000000000000000000000000"
        except Exception:
            pass
        raise exc


def get_git_diff() -> str:
    """Return the unified diff of all uncommitted working-tree changes.

    Returns:
        The raw ``git diff`` output, or an empty string if the tree is
        clean.

    Raises:
        GitNotFoundError: If git is not installed.
        GitCommandError: If the command fails.
    """
    diff = _run_git("diff")
    if diff and not diff.endswith("\n"):
        diff += "\n"
    return diff


def get_modified_files() -> list[str]:
    """Return the list of file paths with uncommitted modifications.

    Returns:
        A list of relative file paths reported by ``git diff --name-only``.
        Empty when the working tree is clean.

    Raises:
        GitNotFoundError: If git is not installed.
        GitCommandError: If the command fails.
    """
    output = _run_git("diff", "--name-only")
    if not output:
        return []
    return output.splitlines()


# ---------------------------------------------------------------------------
# Shell history
# ---------------------------------------------------------------------------

_ZSH_META_RE = re.compile(r"^:\s*\d+:\d+;")
"""Regex matching Zsh extended-history metadata prefixes (e.g. ``: 1700000000:0;``)."""


def _read_history_file(path: Path, limit: int) -> list[str]:
    """Read the last *limit* non-empty lines from a history file.

    Maintains a low memory footprint by streaming lines from the file
    and maintaining only the trailing lines in a double-ended queue.
    Attempts multiple common encodings to cleanly parse history on various
    operating systems (including Windows PowerShell UTF-16).

    Args:
        path: Absolute path to the history file.
        limit: Maximum number of history entries to return.

    Returns:
        A list of the most recent commands, oldest first.
    """
    encodings = ["utf-8", "utf-16", "locale", "cp1252"]
    for enc in encodings:
        try:
            encoding_name = sys.getdefaultencoding() if enc == "locale" else enc
            with path.open("r", encoding=encoding_name, errors="replace") as f:
                raw_lines = f.readlines()
                cleaned_lines = []
                for line in raw_lines:
                    line = line.replace("\x00", "").strip()
                    if line:
                        cleaned_lines.append(line)
                if cleaned_lines:
                    tail = deque(cleaned_lines, maxlen=limit)
                    return [line.rstrip("\r\n") for line in tail]
        except (UnicodeDecodeError, PermissionError):
            continue
        except OSError as exc:
            logger.warning("Could not read history file %s with %s: %s", path, enc, exc)
            return []
    return []


def _clean_zsh_history(lines: list[str]) -> list[str]:
    """Strip Zsh extended-history metadata from each line.

    Zsh history entries may be prefixed with ``: <timestamp>:<duration>;``.
    This function removes that prefix, yielding the raw command text.

    Args:
        lines: Raw lines read from ``~/.zsh_history``.

    Returns:
        Cleaned command strings with metadata stripped.
    """
    cleaned: list[str] = []
    for line in lines:
        line = _ZSH_META_RE.sub("", line).strip()
        if line:
            cleaned.append(line)
    return cleaned


def get_shell_history(limit: int = 5) -> list[str]:
    """Retrieve the most recent shell commands from the user's history file.

    The function inspects the ``$SHELL`` environment variable to determine
    the active shell. Supported shells:

    * **Zsh** — reads ``~/.zsh_history`` and strips extended-history
      metadata timestamps.
    * **Bash** — reads ``~/.bash_history`` as-is.

    On Windows, it checks the PowerShell PSReadLine history file.
    On Windows or when ``$SHELL`` is unset, the function falls back to
    checking both well-known history files in order of preference.

    Args:
        limit: Maximum number of recent commands to return.  Defaults to 5.

    Returns:
        A list of the most recent shell commands (oldest first).
        Returns an empty list if no history can be located.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            ps_history = (
                Path(appdata)
                / "Microsoft"
                / "Windows"
                / "PowerShell"
                / "PSReadLine"
                / "ConsoleHost_history.txt"
            )
            if ps_history.is_file():
                lines = _read_history_file(ps_history, limit)
                if lines:
                    return lines[-limit:]

    home = Path.home()
    shell = os.environ.get("SHELL", "")

    # Determine which history file(s) to try, in priority order.
    candidates: list[tuple[Path, bool]]
    if "zsh" in shell:
        candidates = [(home / ".zsh_history", True)]
    elif "bash" in shell:
        candidates = [(home / ".bash_history", False)]
    else:
        # Unknown or unset (common on Windows if not PowerShell) — try both.
        candidates = [
            (home / ".zsh_history", True),
            (home / ".bash_history", False),
        ]

    for path, is_zsh in candidates:
        if not path.is_file():
            logger.debug("History file not found: %s", path)
            continue

        lines = _read_history_file(path, limit)
        if is_zsh:
            lines = _clean_zsh_history(lines)
        if lines:
            return lines[-limit:]

    logger.info("No shell history found; returning empty list")
    return []


# ---------------------------------------------------------------------------
# Snapshot factory
# ---------------------------------------------------------------------------


def _compute_checkpoint_id(branch: str, commit_hash: str, diff: str) -> str:
    """Derive a deterministic 8-character ID from session context.

    The hash is computed from the concatenation of the branch name,
    commit hash, and the first :data:`_DIFF_SNIPPET_LIMIT` characters of
    the diff output.  This produces a stable, reproducible identifier for
    the same logical state.

    Args:
        branch: Active git branch name.
        commit_hash: Latest commit SHA.
        diff: Raw ``git diff`` output.

    Returns:
        An 8-character lowercase hexadecimal digest.
    """
    payload = f"{branch}:{commit_hash}:{diff[:_DIFF_SNIPPET_LIMIT]}"
    return hashlib.sha256(payload.encode()).hexdigest()[:8]


def create_snapshot(message: str) -> Checkpoint:
    """Capture the current development session state as a Checkpoint.

    Queries git for the active branch, latest commit, uncommitted diff,
    and modified file list, then reads recent shell history and assembles
    a :class:`~ckpt.models.Checkpoint`.

    Args:
        message: A human- or AI-provided description of the session state.

    Returns:
        A fully populated :class:`~ckpt.models.Checkpoint` instance.

    Raises:
        GitNotFoundError: If git is not installed.
        GitCommandError: If any git query fails (e.g. not inside a repo).
    """
    branch = get_current_branch()
    commit_hash = get_last_commit_hash()
    diff = get_git_diff()
    modified = get_modified_files()
    history = get_shell_history()

    checkpoint_id = _compute_checkpoint_id(branch, commit_hash, diff)

    logger.info(
        "Snapshot captured — id=%s branch=%s commit=%s files=%d",
        checkpoint_id,
        branch,
        commit_hash[:8],
        len(modified),
    )

    return Checkpoint(
        id=checkpoint_id,
        branch=branch,
        commit_hash=commit_hash,
        message=message,
        git_diff=diff,
        history=history,
        files_locked=modified,
    )
