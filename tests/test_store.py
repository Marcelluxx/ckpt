"""Unit tests for the ckpt storage layer."""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from pytest_mock import MockerFixture

from ckpt.models import Checkpoint
from ckpt.store import (
    CheckpointNotFoundError,
    ConfigError,
    LLMError,
    _config_dir,
    _config_file,
    _secure_mkdir,
    _secure_write,
    _snapshots_dir,
    delete_checkpoint,
    generate_mental_map,
    generate_mental_map_sync,
    list_checkpoints,
    load_checkpoint,
    load_config,
    save_checkpoint,
    save_config,
)


@pytest.fixture(autouse=True)
def mock_home_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Fixture that mocks Path.home() to point to a temporary test directory.

    This ensures no tests write to or read from the actual user's home folder.
    """
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    return tmp_path


def test_path_helpers(mock_home_dir: Path) -> None:
    """Verify that path helpers point to directories inside the mocked home directory."""
    expected_config_dir = mock_home_dir / ".config" / "ckpt"
    expected_snapshots_dir = expected_config_dir / "snapshots"
    expected_config_file = expected_config_dir / "config.json"

    assert _config_dir() == expected_config_dir
    assert _snapshots_dir() == expected_snapshots_dir
    assert _config_file() == expected_config_file


def test_save_and_load_checkpoint(mock_home_dir: Path) -> None:
    """Test that a checkpoint can be successfully saved and loaded."""
    checkpoint = Checkpoint(
        id="a1b2c3d4",
        branch="main",
        commit_hash="e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        message="Saved checkpoint test",
    )

    # Save
    saved_path = save_checkpoint(checkpoint)
    assert saved_path == _snapshots_dir() / "a1b2c3d4.json"
    assert saved_path.is_file()

    # Load
    loaded = load_checkpoint("a1b2c3d4")
    assert loaded == checkpoint


def test_load_checkpoint_not_found() -> None:
    """Test that loading a non-existent checkpoint raises CheckpointNotFoundError."""
    with pytest.raises(CheckpointNotFoundError) as exc_info:
        load_checkpoint("00000000")
    assert "No checkpoint found with id '00000000'" in str(exc_info.value)


@pytest.mark.parametrize(
    "hazardous_id",
    [
        "../../etc/passwd",
        r"..\win.ini",
        "snapshot/../../etc",
        "a1b2c3d4/../config",
        "; rm -rf /",
        "id with spaces",
        "a1b2c3d4e",  # 9 chars (fails ID regex)
    ],
)
def test_directory_traversal_protection(hazardous_id: str) -> None:
    """Verify that directory traversal attempts raise CheckpointNotFoundError."""
    # Test loading
    with pytest.raises(CheckpointNotFoundError) as exc_info:
        load_checkpoint(hazardous_id)
    assert "No checkpoint found with id" in str(exc_info.value)

    # Test deleting
    with pytest.raises(CheckpointNotFoundError) as exc_info:
        delete_checkpoint(hazardous_id)
    assert "No checkpoint found with id" in str(exc_info.value)


def test_list_and_delete_checkpoints() -> None:
    """Test that list_checkpoints lists checkpoints sorted newest-first, and delete_checkpoint unlinks them."""
    # Empty case
    assert list_checkpoints() == []

    c1 = Checkpoint(
        id="11111111",
        branch="main",
        commit_hash="1111111111111111111111111111111111111111",
        message="First checkpoint",
    )
    c2 = Checkpoint(
        id="22222222",
        branch="main",
        commit_hash="2222222222222222222222222222222222222222",
        message="Second checkpoint",
    )

    save_checkpoint(c1)
    save_checkpoint(c2)

    # Order is based on c.timestamp descending
    all_checkpoints = list_checkpoints()
    assert len(all_checkpoints) == 2
    assert all_checkpoints[0].timestamp >= all_checkpoints[1].timestamp

    # Delete
    delete_checkpoint("11111111")
    remaining = list_checkpoints()
    assert len(remaining) == 1
    assert remaining[0].id == "22222222"

    # Delete again should raise error
    with pytest.raises(CheckpointNotFoundError):
        delete_checkpoint("11111111")


def test_config_crud() -> None:
    """Test loading, saving, and validation of LLM configuration."""
    # Config does not exist
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "LLM not configured" in str(exc_info.value)

    # Save config
    config_data = {
        "provider": "ollama",
        "model": "llama3",
    }
    config_path = save_config(config_data)
    assert config_path == _config_file()
    assert config_path.is_file()

    # Load and verify
    loaded = load_config()
    assert loaded == config_data

    # Save invalid config (missing provider)
    invalid_config = {"model": "llama3"}
    save_config(invalid_config)
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "Config missing required key 'provider'" in str(exc_info.value)

    # Malformed JSON config
    _config_file().write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "Invalid config file" in str(exc_info.value)


def test_secure_mkdir_non_win32(mocker: MockerFixture, mock_home_dir: Path) -> None:
    """Test that _secure_mkdir applies permissions and chmod on POSIX/Linux systems."""
    mocker.patch("sys.platform", "linux")
    mock_chmod = mocker.patch("pathlib.Path.chmod")

    test_dir = mock_home_dir / ".config" / "ckpt" / "snapshots"
    _secure_mkdir(test_dir)

    assert test_dir.is_dir()
    # verify chmod was called for config dir and snapshots dir (both 0o700)
    assert mock_chmod.call_count >= 2
    mock_chmod.assert_any_call(0o700)


def test_secure_write_posix(mocker: MockerFixture, mock_home_dir: Path) -> None:
    """Test _secure_write POSIX flow where files are opened with strict permission bits."""
    mocker.patch("sys.platform", "linux")
    mock_open_os = mocker.patch("os.open", return_value=123)
    mock_fdopen = mocker.patch("os.fdopen")

    test_file = mock_home_dir / ".config" / "ckpt" / "test_posix.json"
    _secure_write(test_file, "{}")

    # verify os.open called with target file, flags O_WRONLY|O_CREAT|O_TRUNC, and 0o600
    mock_open_os.assert_called_once_with(
        test_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    mock_fdopen.assert_called_once_with(123, "w", encoding="utf-8")


def test_secure_write_win32(mocker: MockerFixture, mock_home_dir: Path) -> None:
    """Test _secure_write Windows flow where we write standard file and apply icacls permission restriction."""
    mocker.patch("sys.platform", "win32")
    mocker.patch("os.environ", {"USERNAME": "test_win_user"})
    mock_subprocess_run = mocker.patch("subprocess.run")

    test_file = mock_home_dir / ".config" / "ckpt" / "test_win.json"
    _secure_write(test_file, "windows_data")

    # Check file written successfully
    assert test_file.read_text(encoding="utf-8") == "windows_data"

    # Verify icacls was invoked with correct arguments
    mock_subprocess_run.assert_called_once()
    args = mock_subprocess_run.call_args[0][0]
    assert args[0] == "icacls"
    assert args[1] == str(test_file)
    assert "/grant:r" in args
    assert "test_win_user:(F)" in args


# ---------------------------------------------------------------------------
# LLM Async API Mock Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_mental_map_ollama(mocker: MockerFixture) -> None:
    """Test mental map generation using Ollama provider with mocked httpx.AsyncClient."""
    save_config({"provider": "ollama", "model": "mistral"})

    # Mock response object from httpx
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "Ollama mental map response"}

    # Mock AsyncClient.post context manager and response
    mock_post = mocker.patch("httpx.AsyncClient.post", return_value=mock_response)

    result = await generate_mental_map("diff", ["cmd1", "cmd2"])

    assert result == "Ollama mental map response"
    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    assert call_args[0] == "http://localhost:11434/api/generate"
    assert call_kwargs["json"]["model"] == "mistral"


@pytest.mark.asyncio
async def test_generate_mental_map_gemini(mocker: MockerFixture) -> None:
    """Test mental map generation using Gemini provider with mocked httpx.AsyncClient."""
    save_config(
        {"provider": "gemini", "model": "gemini-3.1-flash-lite", "api_key": "secret_key"}
    )

    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Gemini mental map response"}]}}]
    }

    mock_post = mocker.patch("httpx.AsyncClient.post", return_value=mock_response)

    result = await generate_mental_map("diff", ["cmd1", "cmd2"])

    assert result == "Gemini mental map response"
    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    assert "generativelanguage.googleapis.com" in call_args[0]
    assert call_kwargs["headers"]["x-goog-api-key"] == "secret_key"


@pytest.mark.asyncio
async def test_generate_mental_map_gemini_missing_key() -> None:
    """Test Gemini provider raises ConfigError if api_key is missing."""
    save_config({"provider": "gemini", "model": "gemini-3.1-flash-lite"})
    with pytest.raises(ConfigError) as exc_info:
        await generate_mental_map("diff", [])
    assert "Gemini requires an 'api_key'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_mental_map_unknown_provider() -> None:
    """Test that an unknown LLM provider raises ConfigError."""
    save_config({"provider": "unsupported_provider"})
    with pytest.raises(ConfigError) as exc_info:
        await generate_mental_map("diff", [])
    assert "Unknown LLM provider" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_mental_map_http_failure(mocker: MockerFixture) -> None:
    """Test LLMError is raised when httpx fails."""
    save_config({"provider": "ollama"})

    import httpx

    mocker.patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.HTTPStatusError(
            "API Error", request=mocker.MagicMock(), response=mocker.MagicMock()
        ),
    )

    with pytest.raises(LLMError) as exc_info:
        await generate_mental_map("diff", [])
    assert "Ollama API request failed" in str(exc_info.value)


def test_generate_mental_map_sync_wrapper(mocker: MockerFixture) -> None:
    """Test that the synchronous wrapper correctly runs the async function."""
    mock_generate = mocker.patch(
        "ckpt.store.generate_mental_map", return_value="Sync Wrapper Output"
    )

    # Case 1: No running event loop
    result = generate_mental_map_sync("diff", ["cmd"])
    assert result == "Sync Wrapper Output"
    mock_generate.assert_called_once_with("diff", ["cmd"])
