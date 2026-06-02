"""Unit tests for the ckpt CLI wrapper."""

from __future__ import annotations

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
