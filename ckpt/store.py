"""Persistent storage layer for ckpt checkpoints.

Manages reading, writing, listing, and deleting Checkpoint JSON files
inside ``~/.config/ckpt/snapshots/``.  Also handles LLM configuration
(``~/.config/ckpt/config.json``) and async mental-map generation via
Ollama or Google Gemini.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import sys
from pathlib import Path

import httpx

from ckpt.models import Checkpoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class StoreError(Exception):
    """Base exception for storage-layer failures."""


class CheckpointNotFoundError(StoreError):
    """Raised when a checkpoint ID does not match any stored file."""


class ConfigError(StoreError):
    """Raised when the LLM configuration is missing or invalid."""


class LLMError(StoreError):
    """Raised when the LLM API call fails or returns an unusable response."""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_DIR_MODE = 0o700
"""Permissions for newly created configuration directories."""

_FILE_MODE = 0o600
"""Permissions for newly created configuration / snapshot files."""


def _config_dir() -> Path:
    """Return the root configuration directory for ckpt.

    On Windows ``~/.config`` may not exist, so we create it if needed.

    Returns:
        ``~/.config/ckpt`` as an absolute :class:`Path`.
    """
    return Path.home() / ".config" / "ckpt"


def _snapshots_dir() -> Path:
    """Return the directory where checkpoint JSON files are stored.

    Returns:
        ``~/.config/ckpt/snapshots`` as an absolute :class:`Path`.
    """
    return _config_dir() / "snapshots"


def _config_file() -> Path:
    """Return the path to the LLM configuration JSON file.

    Returns:
        ``~/.config/ckpt/config.json`` as an absolute :class:`Path`.
    """
    return _config_dir() / "config.json"


def _secure_mkdir(path: Path) -> None:
    """Create a directory with strict permissions, including parents.

    Args:
        path: Directory path to create.
    """
    path.mkdir(parents=True, exist_ok=True)
    # On POSIX systems enforce restrictive mode; on Windows this is a no-op.
    if sys.platform != "win32":
        path.chmod(_DIR_MODE)


def _secure_write(path: Path, data: str) -> None:
    """Write *data* to *path* with restrictive file permissions.

    Args:
        path: Target file path.
        data: UTF-8 string content to write.
    """
    _secure_mkdir(path.parent)
    path.write_text(data, encoding="utf-8")
    if sys.platform != "win32":
        path.chmod(_FILE_MODE)


# ---------------------------------------------------------------------------
# Checkpoint CRUD
# ---------------------------------------------------------------------------


def save_checkpoint(checkpoint: Checkpoint) -> Path:
    """Persist a checkpoint to disk as a JSON file.

    The file is written to ``~/.config/ckpt/snapshots/<id>.json``.

    Args:
        checkpoint: The :class:`Checkpoint` instance to save.

    Returns:
        The absolute :class:`Path` of the written file.

    Raises:
        StoreError: If the write operation fails.
    """
    target = _snapshots_dir() / f"{checkpoint.id}.json"
    try:
        _secure_write(target, checkpoint.model_dump_json(indent=2))
    except OSError as exc:
        raise StoreError(f"Failed to write checkpoint {checkpoint.id}: {exc}") from exc

    logger.info("Checkpoint saved → %s", target)
    return target


def load_checkpoint(checkpoint_id: str) -> Checkpoint:
    """Load a checkpoint from disk by its 8-character ID.

    Args:
        checkpoint_id: The unique identifier of the checkpoint.

    Returns:
        A reconstructed :class:`Checkpoint` instance.

    Raises:
        CheckpointNotFoundError: If no file matches the given ID.
        StoreError: If the file exists but cannot be parsed.
    """
    target = _snapshots_dir() / f"{checkpoint_id}.json"
    if not target.is_file():
        raise CheckpointNotFoundError(
            f"No checkpoint found with id '{checkpoint_id}'"
        )

    try:
        raw = target.read_text(encoding="utf-8")
        return Checkpoint.model_validate_json(raw)
    except Exception as exc:
        raise StoreError(
            f"Failed to parse checkpoint '{checkpoint_id}': {exc}"
        ) from exc


def list_checkpoints() -> list[Checkpoint]:
    """Return all stored checkpoints, sorted newest-first.

    Returns:
        A list of :class:`Checkpoint` instances ordered by descending
        timestamp.
    """
    snap_dir = _snapshots_dir()
    if not snap_dir.is_dir():
        return []

    checkpoints: list[Checkpoint] = []
    for path in snap_dir.glob("*.json"):
        try:
            raw = path.read_text(encoding="utf-8")
            checkpoints.append(Checkpoint.model_validate_json(raw))
        except Exception:
            logger.warning("Skipping corrupt checkpoint file: %s", path.name)

    checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
    return checkpoints


def delete_checkpoint(checkpoint_id: str) -> None:
    """Delete a checkpoint file by ID.

    Args:
        checkpoint_id: The unique identifier of the checkpoint.

    Raises:
        CheckpointNotFoundError: If no file matches the given ID.
    """
    target = _snapshots_dir() / f"{checkpoint_id}.json"
    if not target.is_file():
        raise CheckpointNotFoundError(
            f"No checkpoint found with id '{checkpoint_id}'"
        )
    target.unlink()
    logger.info("Checkpoint deleted: %s", checkpoint_id)


# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """Read the LLM configuration from ``~/.config/ckpt/config.json``.

    Expected schema::

        {
            "provider": "ollama" | "gemini",
            "model": "<model-name>",
            "api_key": "<key>"          // required for gemini only
        }

    Returns:
        A dictionary with configuration values.

    Raises:
        ConfigError: If the file is missing or malformed.
    """
    path = _config_file()
    if not path.is_file():
        raise ConfigError(
            "LLM not configured. Run `ckpt setup` to configure a provider."
        )
    try:
        raw = path.read_text(encoding="utf-8")
        config = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Invalid config file: {exc}") from exc

    if "provider" not in config:
        raise ConfigError("Config missing required key 'provider'.")

    return config


def save_config(config: dict) -> Path:
    """Write the LLM configuration to disk with secure permissions.

    Args:
        config: Dictionary matching the expected config schema.

    Returns:
        The absolute path of the written config file.
    """
    path = _config_file()
    _secure_write(path, json.dumps(config, indent=2))
    logger.info("Config saved → %s", path)
    return path


# ---------------------------------------------------------------------------
# LLM mental-map generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a senior software engineer assistant. Given a git diff and "
    "recent command history from a developer session, produce a dense, "
    "structured Markdown summary (max 150 words) called a **Mental Map**. "
    "It must include:\n"
    "- **Context**: what the developer is working on.\n"
    "- **Changes**: key modifications made.\n"
    "- **Next Steps**: likely follow-up actions.\n"
    "Be concise, use bullet points, and avoid filler."
)


def _build_user_prompt(diff: str, history: list[str]) -> str:
    """Assemble the user-facing prompt sent to the LLM.

    Args:
        diff: Raw git diff output (may be empty).
        history: Recent shell commands.

    Returns:
        A formatted prompt string.
    """
    diff_section = diff[:3000] if diff else "(no uncommitted changes)"
    history_section = "\n".join(history) if history else "(no recent commands)"
    return (
        f"## Git Diff\n```\n{diff_section}\n```\n\n"
        f"## Recent Commands\n```\n{history_section}\n```\n\n"
        "Generate the Mental Map now."
    )


async def _generate_mental_map_ollama(
    diff: str,
    history: list[str],
    model: str,
) -> str:
    """Call the Ollama local API to generate a mental map.

    Args:
        diff: Raw git diff.
        history: Recent shell commands.
        model: Ollama model name (e.g. ``"llama3"``).

    Returns:
        The generated mental map as a Markdown string.

    Raises:
        LLMError: If the HTTP request fails or response is invalid.
    """
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": _build_user_prompt(diff, history),
        "system": _SYSTEM_PROMPT,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Ollama API request failed: {exc}"
            ) from exc

    try:
        return resp.json()["response"]
    except (KeyError, json.JSONDecodeError) as exc:
        raise LLMError(f"Unexpected Ollama response format: {exc}") from exc


async def _generate_mental_map_gemini(
    diff: str,
    history: list[str],
    model: str,
    api_key: str,
) -> str:
    """Call the Google Gemini API to generate a mental map.

    Args:
        diff: Raw git diff.
        history: Recent shell commands.
        model: Gemini model name (e.g. ``"gemini-2.0-flash"``).
        api_key: Google AI Studio API key.

    Returns:
        The generated mental map as a Markdown string.

    Raises:
        LLMError: If the HTTP request fails or response is invalid.
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{_SYSTEM_PROMPT}\n\n{_build_user_prompt(diff, history)}"}
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 400,
            "temperature": 0.4,
        },
    }
    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini API request failed: {exc}") from exc

    try:
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LLMError(f"Unexpected Gemini response format: {exc}") from exc


async def generate_mental_map(diff: str, history: list[str]) -> str:
    """Generate an AI mental map using the configured LLM provider.

    Reads the provider selection from ``~/.config/ckpt/config.json`` and
    dispatches to the appropriate backend (Ollama or Gemini).

    Args:
        diff: Raw git diff output.
        history: Recent shell commands.

    Returns:
        A Markdown-formatted mental map string.

    Raises:
        ConfigError: If the LLM is not configured.
        LLMError: If the API call fails.
    """
    config = load_config()
    provider = config["provider"]
    model = config.get("model", "llama3")

    if provider == "ollama":
        return await _generate_mental_map_ollama(diff, history, model)
    elif provider == "gemini":
        api_key = config.get("api_key", "")
        if not api_key:
            raise ConfigError("Gemini requires an 'api_key' in config.json.")
        return await _generate_mental_map_gemini(diff, history, model, api_key)
    else:
        raise ConfigError(f"Unknown LLM provider: '{provider}'")


def generate_mental_map_sync(diff: str, history: list[str]) -> str:
    """Synchronous wrapper around :func:`generate_mental_map`.

    Manages the async event loop boundary so callers (e.g. Typer commands)
    do not need to handle ``asyncio`` directly.

    Args:
        diff: Raw git diff output.
        history: Recent shell commands.

    Returns:
        A Markdown-formatted mental map string.
    """
    return asyncio.run(generate_mental_map(diff, history))
