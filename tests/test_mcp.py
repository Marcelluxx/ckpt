"""Unit tests for the ckpt MCP server layer."""

from __future__ import annotations

from pathlib import Path
import pytest
from pytest_mock import MockerFixture

from ckpt.models import Checkpoint
from ckpt.store import ConfigError, LLMError
from ckpt.mcp_server import save_snapshot, list_snapshots, get_snapshot_by_id


@pytest.fixture(autouse=True)
def mock_home_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Fixture that mocks Path.home() to point to a temporary test directory."""
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_save_snapshot_success(mocker: MockerFixture) -> None:
    """Test save_snapshot tool successfully generates a mental map and saves checkpoint."""
    mock_checkpoint = Checkpoint(
        id="a1b2c3d4",
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Test checkpoint message",
        git_diff="some diff",
        history=["cmd1"],
    )

    # Mock the internal functions
    mocker.patch("ckpt.mcp_server.create_snapshot", return_value=mock_checkpoint)
    mock_generate = mocker.patch(
        "ckpt.mcp_server.generate_mental_map", return_value="This is a mental map"
    )
    mock_save = mocker.patch(
        "ckpt.mcp_server.save_checkpoint", return_value="/mock/path/a1b2c3d4.json"
    )

    # Call save_snapshot
    result = await save_snapshot("Test checkpoint message")

    assert "Checkpoint saved successfully" in result
    assert "ID:         a1b2c3d4" in result
    assert "Mental Map: Yes" in result

    # Assert generated mental map was added to the saved checkpoint
    mock_generate.assert_called_once_with("some diff", ["cmd1"])
    called_checkpoint = mock_save.call_args[0][0]
    assert called_checkpoint.mental_map == "This is a mental map"


@pytest.mark.asyncio
async def test_save_snapshot_llm_config_error(mocker: MockerFixture) -> None:
    """Test save_snapshot handles ConfigError during mental map generation gracefully."""
    mock_checkpoint = Checkpoint(
        id="a1b2c3d4",
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Test checkpoint message",
        git_diff="some diff",
        history=["cmd1"],
    )

    mocker.patch("ckpt.mcp_server.create_snapshot", return_value=mock_checkpoint)
    mocker.patch(
        "ckpt.mcp_server.generate_mental_map",
        side_effect=ConfigError("LLM not configured"),
    )
    mock_save = mocker.patch(
        "ckpt.mcp_server.save_checkpoint", return_value="/mock/path/a1b2c3d4.json"
    )

    result = await save_snapshot("Test checkpoint message")

    assert "Checkpoint saved successfully" in result
    assert "Mental Map: No" in result

    called_checkpoint = mock_save.call_args[0][0]
    assert called_checkpoint.mental_map is None


@pytest.mark.asyncio
async def test_save_snapshot_llm_error(mocker: MockerFixture) -> None:
    """Test save_snapshot handles LLMError during mental map generation gracefully."""
    mock_checkpoint = Checkpoint(
        id="a1b2c3d4",
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Test checkpoint message",
        git_diff="some diff",
        history=["cmd1"],
    )

    mocker.patch("ckpt.mcp_server.create_snapshot", return_value=mock_checkpoint)
    mocker.patch(
        "ckpt.mcp_server.generate_mental_map",
        side_effect=LLMError("Gemini call failed"),
    )
    mock_save = mocker.patch(
        "ckpt.mcp_server.save_checkpoint", return_value="/mock/path/a1b2c3d4.json"
    )

    result = await save_snapshot("Test checkpoint message")

    assert "Checkpoint saved successfully" in result
    assert "Mental Map: No" in result

    called_checkpoint = mock_save.call_args[0][0]
    assert called_checkpoint.mental_map is None


@pytest.mark.asyncio
async def test_save_snapshot_direct_mental_map(mocker: MockerFixture) -> None:
    """Test save_snapshot tool uses the provided mental map directly and skips LLM call."""
    mock_checkpoint = Checkpoint(
        id="a1b2c3d4",
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Test checkpoint message",
        git_diff="some diff",
        history=["cmd1"],
    )

    mocker.patch("ckpt.mcp_server.create_snapshot", return_value=mock_checkpoint)
    mock_generate = mocker.patch("ckpt.mcp_server.generate_mental_map")
    mock_save = mocker.patch(
        "ckpt.mcp_server.save_checkpoint", return_value="/mock/path/a1b2c3d4.json"
    )

    # Call save_snapshot passing a direct mental map
    result = await save_snapshot(
        "Test checkpoint message", mental_map="Directly provided mental map"
    )

    assert "Checkpoint saved successfully" in result
    assert "Mental Map: Yes" in result

    # Assert LLM generation was NOT called
    mock_generate.assert_not_called()

    # Assert provided mental map was applied
    called_checkpoint = mock_save.call_args[0][0]
    assert called_checkpoint.mental_map == "Directly provided mental map"


@pytest.mark.asyncio
async def test_list_snapshots(mocker: MockerFixture) -> None:
    """Test list_snapshots returns all saved checkpoints."""
    c1 = Checkpoint(
        id="11111111",
        branch="main",
        commit_hash="1111111111111111111111111111111111111111",
        message="First checkpoint",
    )
    mocker.patch("ckpt.mcp_server.list_checkpoints", return_value=[c1])

    result = await list_snapshots()
    assert "Found 1 checkpoint" in result
    assert "[11111111]" in result


@pytest.mark.asyncio
async def test_get_snapshot_by_id(mocker: MockerFixture) -> None:
    """Test get_snapshot_by_id returns checkpoint JSON or validation error."""
    # Test valid ID
    c1 = Checkpoint(
        id="11111111",
        branch="main",
        commit_hash="1111111111111111111111111111111111111111",
        message="First checkpoint",
    )
    mocker.patch("ckpt.mcp_server.load_checkpoint", return_value=c1)

    result = await get_snapshot_by_id("11111111")
    assert '"id": "11111111"' in result

    # Test invalid ID
    result_invalid = await get_snapshot_by_id("../../invalid")
    assert "[error] Invalid snapshot ID" in result_invalid
