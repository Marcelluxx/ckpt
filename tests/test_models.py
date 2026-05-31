"""Unit tests for the Checkpoint Pydantic model."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from ckpt.models import Checkpoint


def test_checkpoint_defaults() -> None:
    """Test that default values are generated correctly when creating a Checkpoint."""
    checkpoint = Checkpoint(
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Initial commit description",
    )

    # Verify generated ID format (8 hex characters)
    assert len(checkpoint.id) == 8
    assert all(c in "0123456789abcdef" for c in checkpoint.id)

    # Verify generated timestamp is recent and timezone-aware (UTC)
    assert isinstance(checkpoint.timestamp, datetime)
    assert checkpoint.timestamp.tzinfo == timezone.utc

    # Verify default fields
    assert checkpoint.git_diff == ""
    assert checkpoint.history == []
    assert checkpoint.mental_map is None
    assert checkpoint.files_locked == []


def test_checkpoint_serialization_deserialization() -> None:
    """Test that the Checkpoint model serializes and deserializes JSON correctly."""
    # Deserialization from JSON string
    json_str = (
        '{"id": "a1b2c3d4", "timestamp": "2026-06-01T01:11:43Z", "branch": "feature/auth", '
        '"commit_hash": "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4", "message": "Implemented JWT middleware", '
        '"git_diff": "diff --git a/auth.py ...", "history": ["git add .", "pytest tests/"], '
        '"mental_map": "Working on auth flow; JWT validated, next: refresh tokens.", '
        '"files_locked": ["src/auth.py", "tests/test_auth.py"]}'
    )

    checkpoint = Checkpoint.model_validate_json(json_str)
    assert checkpoint.id == "a1b2c3d4"
    assert checkpoint.timestamp == datetime(2026, 6, 1, 1, 11, 43, tzinfo=timezone.utc)
    assert checkpoint.branch == "feature/auth"
    assert checkpoint.commit_hash == "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4"
    assert checkpoint.message == "Implemented JWT middleware"
    assert checkpoint.git_diff == "diff --git a/auth.py ..."
    assert checkpoint.history == ["git add .", "pytest tests/"]
    assert (
        checkpoint.mental_map
        == "Working on auth flow; JWT validated, next: refresh tokens."
    )
    assert checkpoint.files_locked == ["src/auth.py", "tests/test_auth.py"]

    # Serialization to JSON
    serialized = checkpoint.model_dump_json()
    deserialized_again = Checkpoint.model_validate_json(serialized)
    assert deserialized_again == checkpoint


@pytest.mark.parametrize(
    "invalid_id",
    [
        "a1b2c3d",  # 7 characters (too short)
        "a1b2c3d4e",  # 9 characters (too long)
        "a1b2c3dG",  # non-hex character 'G'
        "a1b2-3d4",  # special characters
        "",  # empty
    ],
)
def test_checkpoint_id_pattern_validation(invalid_id: str) -> None:
    """Test validation constraints on the checkpoint ID pattern."""
    with pytest.raises(ValidationError) as exc_info:
        Checkpoint(
            id=invalid_id,
            branch="main",
            commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
            message="Test invalid ID",
        )
    assert "id" in str(exc_info.value)


def test_checkpoint_required_fields() -> None:
    """Test that missing required fields trigger validation errors."""
    # Missing 'branch'
    with pytest.raises(ValidationError) as exc_info:
        Checkpoint(  # type: ignore[call-arg]
            commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
            message="Test missing branch",
        )
    assert "branch" in str(exc_info.value)

    # Missing 'commit_hash'
    with pytest.raises(ValidationError) as exc_info:
        Checkpoint(  # type: ignore[call-arg]
            branch="main",
            message="Test missing commit_hash",
        )
    assert "commit_hash" in str(exc_info.value)

    # Missing 'message'
    with pytest.raises(ValidationError) as exc_info:
        Checkpoint(  # type: ignore[call-arg]
            branch="main",
            commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        )
    assert "message" in str(exc_info.value)
