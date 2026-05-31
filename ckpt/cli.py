"""Typer CLI application for ckpt.

Provides three commands:

- ``ckpt save``    — capture a session snapshot with optional LLM mental map.
- ``ckpt restore`` — reload a checkpoint and display its mental map.
- ``ckpt setup``   — interactive wizard to configure the LLM provider.
"""

from __future__ import annotations

import subprocess
import sys

import typer

from ckpt.snapshot import (
    GitCommandError,
    GitNotFoundError,
    SnapshotError,
    create_snapshot,
)
from ckpt.store import (
    CheckpointNotFoundError,
    ConfigError,
    LLMError,
    StoreError,
    generate_mental_map_sync,
    load_checkpoint,
    save_checkpoint,
    save_config,
)

app = typer.Typer(
    name="ckpt",
    help="Capture and restore development session checkpoints.",
    add_completion=False,
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _abort(message: str, code: int = 1) -> None:
    """Print an error message in red and exit.

    Args:
        message: User-facing error string.
        code: Process exit code.
    """
    typer.secho(f"[X] {message}", fg=typer.colors.RED, bold=True, err=True)
    raise typer.Exit(code=code)


def _success(message: str) -> None:
    """Print a success message in green.

    Args:
        message: User-facing success string.
    """
    typer.secho(f"[OK] {message}", fg=typer.colors.GREEN, bold=True)


def _info(message: str) -> None:
    """Print an informational message in cyan.

    Args:
        message: User-facing info string.
    """
    typer.secho(f"[*] {message}", fg=typer.colors.CYAN)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def save(
    message: str = typer.Option(
        "",
        "--message",
        "-m",
        help="Description of the current session state.",
    ),
) -> None:
    """Capture the current session state as a checkpoint.

    Takes a snapshot of the git branch, commit, diff, modified files, and
    shell history.  If an LLM provider is configured, a Mental Map summary
    is generated and attached.
    """
    # --- Message prompt -------------------------------------------------
    if not message:
        message = typer.prompt("Describe this checkpoint")

    # --- Snapshot --------------------------------------------------------
    try:
        checkpoint = create_snapshot(message)
    except GitNotFoundError:
        _abort("git is not installed or not on PATH.")
    except GitCommandError as exc:
        _abort(f"git error: {exc}")
    except SnapshotError as exc:
        _abort(f"Snapshot failed: {exc}")

    # --- Mental map (best-effort) ----------------------------------------
    try:
        _info("Generating mental map via LLM...")
        mental_map = generate_mental_map_sync(
            checkpoint.git_diff, checkpoint.history
        )
        checkpoint = checkpoint.model_copy(update={"mental_map": mental_map})
        _success("Mental map generated.")
    except ConfigError:
        typer.secho(
            "[!] LLM not configured -- skipping mental map. "
            "Run `ckpt setup` to enable.",
            fg=typer.colors.YELLOW,
        )
    except LLMError as exc:
        typer.secho(
            f"[!] LLM call failed -- skipping mental map: {exc}",
            fg=typer.colors.YELLOW,
        )

    # --- Persist ----------------------------------------------------------
    try:
        path = save_checkpoint(checkpoint)
    except StoreError as exc:
        _abort(f"Could not save checkpoint: {exc}")

    _success(f"Checkpoint [{checkpoint.id}] saved -> {path}")
    typer.secho(
        f"   branch: {checkpoint.branch}  |  "
        f"commit: {checkpoint.commit_hash[:8]}  |  "
        f"files: {len(checkpoint.files_locked)}",
        fg=typer.colors.BRIGHT_BLACK,
    )


@app.command()
def restore(
    checkpoint_id: str = typer.Argument(
        ...,
        help="8-character ID of the checkpoint to restore.",
    ),
) -> None:
    """Restore a saved checkpoint by its ID.

    Applies the stored git diff in reverse to revert unstaged changes,
    then prints the AI-generated Mental Map if available.
    """
    # --- Load -------------------------------------------------------------
    try:
        checkpoint = load_checkpoint(checkpoint_id)
    except CheckpointNotFoundError:
        _abort(f"No checkpoint found with id '{checkpoint_id}'.")
    except StoreError as exc:
        _abort(f"Failed to load checkpoint: {exc}")

    _info(
        f"Restoring [{checkpoint.id}] "
        f"from {checkpoint.timestamp:%Y-%m-%d %H:%M:%S UTC}"
    )

    # --- Revert unstaged changes via `git checkout -- .` ------------------
    try:
        subprocess.run(
            ["git", "checkout", "--", "."],
            check=True,
            capture_output=True,
            text=True,
        )
        _success("Unstaged changes reverted.")
    except FileNotFoundError:
        _abort("git is not installed or not on PATH.")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        _abort(f"git checkout failed: {stderr}")

    # --- Apply stored diff ------------------------------------------------
    if checkpoint.git_diff:
        try:
            subprocess.run(
                ["git", "apply", "--allow-empty"],
                input=checkpoint.git_diff,
                check=True,
                capture_output=True,
                text=True,
            )
            _success("Stored diff re-applied.")
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            typer.secho(
                f"[!] Could not re-apply diff: {stderr}",
                fg=typer.colors.YELLOW,
            )

    # --- Display mental map -----------------------------------------------
    if checkpoint.mental_map:
        typer.echo()
        typer.secho("Mental Map", fg=typer.colors.MAGENTA, bold=True)
        typer.secho("-" * 40, fg=typer.colors.BRIGHT_BLACK)
        typer.echo(checkpoint.mental_map)
        typer.secho("-" * 40, fg=typer.colors.BRIGHT_BLACK)
    else:
        typer.secho(
            "[*] No mental map attached to this checkpoint.",
            fg=typer.colors.BRIGHT_BLACK,
        )

    typer.echo()
    _success(f"Checkpoint [{checkpoint.id}] restored.")


@app.command()
def setup() -> None:
    """Interactive wizard to configure the LLM provider.

    Guides the user through selecting Ollama or Gemini, specifying a model
    name, and securely inputting an API key when required.
    """
    typer.secho("--- ckpt LLM Setup ---", fg=typer.colors.CYAN, bold=True)
    typer.echo()

    # --- Provider selection -----------------------------------------------
    typer.echo("Select your LLM provider:")
    typer.secho("  [1]  Ollama   (local, no API key)", fg=typer.colors.GREEN)
    typer.secho("  [2]  Gemini   (Google AI Studio)", fg=typer.colors.BLUE)
    typer.echo()

    choice = typer.prompt("Enter choice", type=int, default=1)

    if choice == 1:
        provider = "ollama"
        default_model = "llama3"
    elif choice == 2:
        provider = "gemini"
        default_model = "gemini-2.0-flash"
    else:
        _abort("Invalid choice. Please enter 1 or 2.")
        return  # unreachable, keeps type checker happy

    # --- Model name -------------------------------------------------------
    model = typer.prompt("Model name", default=default_model)

    # --- API key (Gemini only) --------------------------------------------
    config: dict[str, str] = {
        "provider": provider,
        "model": model,
    }

    if provider == "gemini":
        api_key = typer.prompt(
            "Google AI Studio API key",
            hide_input=True,
        )
        if not api_key.strip():
            _abort("API key cannot be empty.")
        config["api_key"] = api_key.strip()

    # --- Persist ----------------------------------------------------------
    try:
        path = save_config(config)
    except StoreError as exc:
        _abort(f"Could not save config: {exc}")

    typer.echo()
    _success(f"Configuration saved -> {path}")
    typer.secho(
        f"   provider: {provider}  |  model: {model}",
        fg=typer.colors.BRIGHT_BLACK,
    )
