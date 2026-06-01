"""Unit tests for the ckpt snapshot layer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import pytest
from pytest_mock import MockerFixture

from ckpt.models import Checkpoint
from ckpt.snapshot import (
    GitCommandError,
    GitNotFoundError,
    _compute_checkpoint_id,
    _run_git,
    create_snapshot,
    get_current_branch,
    get_git_diff,
    get_last_commit_hash,
    get_modified_files,
    get_shell_history,
)


@pytest.fixture(autouse=True)
def mock_home_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Fixture that mocks Path.home() to point to a temporary test directory.

    This ensures no tests write to or read from the actual user's home folder.
    """
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Git Command Mock Tests
# ---------------------------------------------------------------------------


def test_run_git_success(mocker: MockerFixture) -> None:
    """Test successful execution of a git command."""
    mock_result = mocker.MagicMock()
    mock_result.stdout = "  feature/branch \n"
    mock_run = mocker.patch("subprocess.run", return_value=mock_result)

    output = _run_git("branch", "--show-current")

    assert output == "feature/branch"
    mock_run.assert_called_once_with(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
    )


def test_run_git_not_found(mocker: MockerFixture) -> None:
    """Test that GitNotFoundError is raised when git is not installed."""
    mocker.patch("subprocess.run", side_effect=FileNotFoundError())

    with pytest.raises(GitNotFoundError) as exc_info:
        _run_git("status")
    assert "git is not installed or not available on PATH" in str(exc_info.value)


def test_run_git_command_error(mocker: MockerFixture) -> None:
    """Test that GitCommandError is raised when a git command exits with a non-zero code."""
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(
            returncode=128, cmd=["git", "status"], stderr="fatal: not a git repository"
        ),
    )

    with pytest.raises(GitCommandError) as exc_info:
        _run_git("status")
    assert "git status failed (rc=128): fatal: not a git repository" in str(
        exc_info.value
    )


def test_get_current_branch(mocker: MockerFixture) -> None:
    """Test get_current_branch retrieves current branch."""
    mocker.patch("ckpt.snapshot._run_git", return_value="main")
    assert get_current_branch() == "main"


def test_get_last_commit_hash(mocker: MockerFixture) -> None:
    """Test get_last_commit_hash retrieves valid HEAD commit SHA."""
    mocker.patch(
        "ckpt.snapshot._run_git",
        return_value="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
    )
    assert get_last_commit_hash() == "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"


def test_get_last_commit_hash_empty_repo(mocker: MockerFixture) -> None:
    """Test get_last_commit_hash fallback to all zeros in a newly initialized git repo with no commits."""

    def mock_run(cmd: str, *args: str) -> str:
        if cmd == "rev-parse" and args == ("HEAD",):
            raise GitCommandError("rev-parse HEAD failed")
        elif cmd == "rev-parse" and args == ("--is-inside-work-tree",):
            return "true"
        return ""

    mocker.patch("ckpt.snapshot._run_git", side_effect=mock_run)
    assert get_last_commit_hash() == "0000000000000000000000000000000000000000"


def test_get_git_diff(mocker: MockerFixture) -> None:
    """Test get_git_diff retrieves diff output."""
    mocker.patch("ckpt.snapshot._run_git", return_value="diff content")
    assert get_git_diff() == "diff content\n"


def test_get_modified_files(mocker: MockerFixture) -> None:
    """Test get_modified_files parses file paths correctly."""
    mocker.patch(
        "ckpt.snapshot._run_git", return_value="src/main.py\ntests/test_main.py\n"
    )
    assert get_modified_files() == ["src/main.py", "tests/test_main.py"]

    # Empty case
    mocker.patch("ckpt.snapshot._run_git", return_value="")
    assert get_modified_files() == []


# ---------------------------------------------------------------------------
# Shell History Mock Tests
# ---------------------------------------------------------------------------


def test_shell_history_win32(mocker: MockerFixture, mock_home_dir: Path) -> None:
    """Test PSReadLine ConsoleHost history extraction on Windows platform."""
    mocker.patch("sys.platform", "win32")

    # Set up simulated AppData folder
    appdata = mock_home_dir / "AppData" / "Roaming"
    mocker.patch("os.environ", {"APPDATA": str(appdata)})

    # Write dummy PSReadLine history file
    ps_dir = appdata / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine"
    ps_dir.mkdir(parents=True, exist_ok=True)
    history_file = ps_dir / "ConsoleHost_history.txt"
    history_file.write_text(
        "cd ckpt\r\ngit status\r\npytest tests/\r\n", encoding="utf-8"
    )

    history = get_shell_history(limit=2)
    assert history == ["git status", "pytest tests/"]


def test_shell_history_zsh(mocker: MockerFixture, mock_home_dir: Path) -> None:
    """Test Zsh history extraction and metadata cleaning on Unix systems."""
    mocker.patch("sys.platform", "linux")
    mocker.patch("os.environ", {"SHELL": "/bin/zsh"})

    # Write dummy Zsh history file with metadata prefixes
    zsh_file = mock_home_dir / ".zsh_history"
    zsh_file.write_text(
        ": 1700000000:0;echo 'hello'\n: 1700000001:0;git add .\n: 1700000002:0;git commit -m \"feat\"\n",
        encoding="utf-8",
    )

    history = get_shell_history(limit=2)
    assert history == ["git add .", 'git commit -m "feat"']


def test_shell_history_bash(mocker: MockerFixture, mock_home_dir: Path) -> None:
    """Test Bash history extraction on Unix systems."""
    mocker.patch("sys.platform", "linux")
    mocker.patch("os.environ", {"SHELL": "/bin/bash"})

    # Write dummy Bash history file
    bash_file = mock_home_dir / ".bash_history"
    bash_file.write_text("mkdir test_dir\ncd test_dir\nls -lh\n", encoding="utf-8")

    history = get_shell_history(limit=2)
    assert history == ["cd test_dir", "ls -lh"]


def test_shell_history_fallback_both(
    mocker: MockerFixture, mock_home_dir: Path
) -> None:
    """Test fallback when shell is unset, testing both well-known files."""
    mocker.patch("sys.platform", "linux")
    mocker.patch("os.environ", {})  # SHELL not set

    # With only bash history existing
    bash_file = mock_home_dir / ".bash_history"
    bash_file.write_text("ls\npwd\n", encoding="utf-8")

    history = get_shell_history(limit=5)
    assert history == ["ls", "pwd"]

    # If zsh history exists, it should prioritize zsh (first candidate)
    zsh_file = mock_home_dir / ".zsh_history"
    zsh_file.write_text(": 1700000000:0;whoami\n", encoding="utf-8")

    history = get_shell_history(limit=5)
    assert history == ["whoami"]


def test_shell_history_empty_fallback(mocker: MockerFixture) -> None:
    """Test when no shell history files are found or env is empty."""
    mocker.patch("sys.platform", "linux")
    mocker.patch.dict(os.environ, {}, clear=True)
    history = get_shell_history()
    assert history == []


# ---------------------------------------------------------------------------
# Snapshot Engine Assembly Tests
# ---------------------------------------------------------------------------


def test_compute_checkpoint_id() -> None:
    """Verify deterministic 8-character ID generation from git context."""
    branch = "feature/auth"
    commit = "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"
    diff = "diff --git a/auth.py ..."

    id1 = _compute_checkpoint_id(branch, commit, diff)
    id2 = _compute_checkpoint_id(branch, commit, diff)
    assert id1 == id2
    assert len(id1) == 8

    # Changing diff should change hash
    id3 = _compute_checkpoint_id(branch, commit, "different diff")
    assert id1 != id3


def test_create_snapshot(mocker: MockerFixture) -> None:
    """Test create_snapshot orchestrates git queries, shell history, and yields a valid Checkpoint."""
    mocker.patch("ckpt.snapshot.get_current_branch", return_value="feature/auth")
    mocker.patch(
        "ckpt.snapshot.get_last_commit_hash",
        return_value="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
    )
    mocker.patch("ckpt.snapshot.get_git_diff", return_value="git diff sample")
    mocker.patch(
        "ckpt.snapshot.get_modified_files", return_value=["auth.py", "test_auth.py"]
    )
    mocker.patch("ckpt.snapshot.get_shell_history", return_value=["git diff", "pytest"])

    checkpoint = create_snapshot(message="Implemented JWT")

    assert isinstance(checkpoint, Checkpoint)
    assert checkpoint.branch == "feature/auth"
    assert checkpoint.commit_hash == "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"
    assert checkpoint.git_diff == "git diff sample"
    assert checkpoint.files_locked == ["auth.py", "test_auth.py"]
    assert checkpoint.history == ["git diff", "pytest"]
    assert checkpoint.message == "Implemented JWT"

    # Verify ID is correctly derived
    expected_id = _compute_checkpoint_id(
        "feature/auth", "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4", "git diff sample"
    )
    assert checkpoint.id == expected_id
