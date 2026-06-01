"""Unit tests for the interactive terminal selection menu and relative time formatting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ckpt.models import Checkpoint
from ckpt.menu import format_relative_time, select_checkpoint_interactive


def test_format_relative_time() -> None:
    """Test format_relative_time with different timedelta offsets."""
    now = datetime.now(timezone.utc)

    # 1. Just now
    assert format_relative_time(now - timedelta(seconds=10)) == "just now"
    assert format_relative_time(now - timedelta(seconds=59)) == "just now"
    
    # Clock drift / slight future
    assert format_relative_time(now + timedelta(seconds=2)) == "just now"

    # 2. Minutes ago
    assert format_relative_time(now - timedelta(minutes=1)) == "1 minute ago"
    assert format_relative_time(now - timedelta(minutes=5)) == "5 minutes ago"
    assert format_relative_time(now - timedelta(minutes=59)) == "59 minutes ago"

    # 3. Hours ago
    assert format_relative_time(now - timedelta(minutes=60)) == "1 hour ago"
    assert format_relative_time(now - timedelta(hours=3)) == "3 hours ago"
    assert format_relative_time(now - timedelta(hours=23, minutes=59)) == "23 hours ago"

    # 4. Days ago
    assert format_relative_time(now - timedelta(hours=24)) == "1 day ago"
    assert format_relative_time(now - timedelta(days=5)) == "5 days ago"
    assert format_relative_time(now - timedelta(days=365)) == "365 days ago"


def test_select_checkpoint_interactive_empty() -> None:
    """Test that an empty checkpoint list returns None immediately."""
    assert select_checkpoint_interactive([]) is None


def test_select_checkpoint_interactive_select(mocker: MockerFixture) -> None:
    """Test successful checkpoint selection using arrow keys and enter."""
    # Create mock checkpoints
    now = datetime.now(timezone.utc)
    cp1 = Checkpoint(
        id="a1b2c3d4",
        timestamp=now - timedelta(minutes=5),
        branch="main",
        commit_hash="1111111111111111111111111111111111111111",
        message="Message 1",
    )
    cp2 = Checkpoint(
        id="e5f6a7b8",
        timestamp=now - timedelta(hours=2),
        branch="feature/auth",
        commit_hash="2222222222222222222222222222222222222222",
        message="Message 2",
    )

    # Mock keypress sequence: "down", then "enter"
    mock_keypress = mocker.patch("ckpt.menu._get_keypress")
    mock_keypress.side_effect = ["down", "enter"]

    # Mock stdout to avoid writing ANSI sequences to terminal during test run
    mock_write = mocker.patch("sys.stdout.write")
    mocker.patch("sys.stdout.flush")

    selected_id = select_checkpoint_interactive([cp1, cp2])

    assert selected_id == "e5f6a7b8"
    assert mock_keypress.call_count == 2
    mock_write.assert_called()


def test_select_checkpoint_interactive_cancel(mocker: MockerFixture) -> None:
    """Test graceful cancellation of interactive selection via escape key."""
    now = datetime.now(timezone.utc)
    cp1 = Checkpoint(
        id="a1b2c3d4",
        timestamp=now,
        branch="main",
        commit_hash="1111111111111111111111111111111111111111",
        message="Message 1",
    )

    # Mock keypress: "escape"
    mock_keypress = mocker.patch("ckpt.menu._get_keypress")
    mock_keypress.side_effect = ["escape"]

    mocker.patch("sys.stdout.write")
    mocker.patch("sys.stdout.flush")

    selected_id = select_checkpoint_interactive([cp1])

    assert selected_id is None
