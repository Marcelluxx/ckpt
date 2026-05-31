"""Pydantic v2 domain models for ckpt session checkpoints.

This module defines the core data schema used to persist and restore
a developer's session state, including git context, uncommitted changes,
recent command history, and an optional LLM-generated mental map.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _generate_id() -> str:
    """Generate an 8-character unique hash identifier.

    Produces a truncated SHA-256 digest derived from a UUID4, providing
    sufficient uniqueness for session-scoped checkpoint identifiers.

    Returns:
        An 8-character lowercase hexadecimal string.
    """
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:8]


def _utc_now() -> datetime:
    """Return the current UTC-aware datetime.

    Returns:
        A timezone-aware ``datetime`` anchored to UTC.
    """
    return datetime.now(timezone.utc)


class Checkpoint(BaseModel):
    """A snapshot of a development session state.

    Each checkpoint captures the full context needed to understand and
    restore a point-in-time view of the developer's working environment,
    including git metadata, uncommitted diffs, shell history, and an
    optional AI-generated summary of intent.

    Attributes:
        id: An 8-character unique hash identifying the checkpoint.
        timestamp: UTC-aware datetime when the checkpoint was created.
        branch: The name of the active git branch at capture time.
        commit_hash: The SHA hash of the last git commit at capture time.
        message: A human- or AI-provided description of the session state.
        git_diff: Raw output of uncommitted changes (e.g. ``git diff``).
        history: A list of recent shell commands executed by the developer.
        mental_map: An optional LLM-generated summary of the developer's
            current intent and reasoning context.
        files_locked: Paths of files modified since the last commit.
    """

    id: str = Field(
        default_factory=_generate_id,
        pattern=r"^[a-f0-9]{8}$",
        description="8-character unique hash identifying the checkpoint.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="UTC-aware datetime when the checkpoint was created.",
    )
    branch: str = Field(
        ...,
        description="Name of the active git branch at capture time.",
    )
    commit_hash: str = Field(
        ...,
        description="SHA hash of the last git commit at capture time.",
    )
    message: str = Field(
        ...,
        description="Human- or AI-provided description of the session state.",
    )
    git_diff: str = Field(
        default="",
        description="Raw output of uncommitted changes (e.g. git diff).",
    )
    history: list[str] = Field(
        default_factory=list,
        description="Recent shell commands executed by the developer.",
    )
    mental_map: str | None = Field(
        default=None,
        description="Optional LLM-generated summary of developer intent.",
    )
    files_locked: list[str] = Field(
        default_factory=list,
        description="Paths of files modified since the last commit.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "a1b2c3d4",
                    "branch": "feature/auth",
                    "commit_hash": "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
                    "message": "Implemented JWT middleware",
                    "git_diff": "diff --git a/auth.py ...",
                    "history": ["git add .", "pytest tests/"],
                    "mental_map": "Working on auth flow; JWT validated, next: refresh tokens.",
                    "files_locked": ["src/auth.py", "tests/test_auth.py"],
                }
            ]
        }
    }
