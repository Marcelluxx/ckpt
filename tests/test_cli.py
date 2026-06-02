"""Unit tests for the ckpt CLI wrapper."""

from __future__ import annotations

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from ckpt import __version__
from ckpt.cli import app

runner = CliRunner()


def test_cli_version_long() -> None:
    """Test that `ckpt --version` prints the correct version and exits."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"ckpt version {__version__}" in result.stdout


def test_cli_version_short() -> None:
    """Test that `ckpt -v` prints the correct version and exits."""
    result = runner.invoke(app, ["-v"])
    assert result.exit_code == 0
    assert f"ckpt version {__version__}" in result.stdout


def test_cli_help_contains_version() -> None:
    """Test that running the command or requesting help displays the version."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert f"v{__version__}" in result.stdout


def test_cli_restore_safety_cancel(mocker: MockerFixture) -> None:
    """Test that restore aborts if there are uncommitted changes and user declines warning."""
    from ckpt.models import Checkpoint
    from datetime import datetime, timezone

    mock_cp = Checkpoint(
        id="a1b2c3d4",
        timestamp=datetime.now(timezone.utc),
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Test checkpoint",
        git_diff="dummy diff",
    )

    mocker.patch("ckpt.cli.load_checkpoint", return_value=mock_cp)

    # Mock subprocess.run to simulate uncommitted changes (git diff returns status code 1)
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 1

    # Mock typer.confirm to return False (cancel)
    mocker.patch("typer.confirm", return_value=False)

    result = runner.invoke(app, ["restore", "a1b2c3d4"])
    assert result.exit_code == 0
    assert "Restoration cancelled." in result.stdout


def test_cli_restore_success(mocker: MockerFixture) -> None:
    """Test that restore succeeds when no changes are present and applies changes properly."""
    from ckpt.models import Checkpoint
    from datetime import datetime, timezone

    mock_cp = Checkpoint(
        id="a1b2c3d4",
        timestamp=datetime.now(timezone.utc),
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Test checkpoint",
        git_diff="dummy diff",
    )

    mocker.patch("ckpt.cli.load_checkpoint", return_value=mock_cp)

    # Mock subprocess.run to return code 0 (no changes)
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value.returncode = 0

    result = runner.invoke(app, ["restore", "a1b2c3d4"])
    assert result.exit_code == 0
    assert "Uncommitted changes cleared." in result.stdout
    assert "Checked out base commit e5f6a7b8." in result.stdout
    assert "Stored diff re-applied." in result.stdout
    assert "Checkpoint [a1b2c3d4] restored." in result.stdout
