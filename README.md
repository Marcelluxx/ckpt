# `ckpt` — *The State Saver & Context Restorer for AI coding sessions.*

<p align="center">
  <a href="https://github.com/Marcelluxx/ckpt/actions/workflows/tests.yml"><img src="https://github.com/Marcelluxx/ckpt/actions/workflows/tests.yml/badge.svg" alt="CI Status"></a>
  <a href="https://github.com/Marcelluxx/ckpt/releases"><img src="https://img.shields.io/github/v/release/Marcelluxx/ckpt?color=blue&logo=github" alt="GitHub Release"></a>
  <a href="https://pypi.org/project/ckpt/"><img src="https://img.shields.io/pypi/v/ckpt?color=green&logo=pypi" alt="PyPI Version"></a>
  <a href="https://github.com/Marcelluxx/ckpt/stargazers"><img src="https://img.shields.io/github/stars/Marcelluxx/ckpt?style=social" alt="GitHub Stars"></a>
  <a href="https://github.com/Marcelluxx/ckpt/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Marcelluxx/ckpt?color=lightgrey" alt="License"></a>
</p>

Are your AI coding sessions suffering from **context bloat** and **session amnesia**? 

When pair programming with AI agents or large language models (LLMs), transferring your current state after a context switch or break is painful. Dumping your entire directory tree or pasting endless lines of raw git diffs into chat windows consumes millions of expensive cloud tokens and confuses the LLM.

**`ckpt`** solves this by capturing and restoring development session states locally. It bundles your active git branch, latest commit, uncommitted changes, recent shell command history, and a high-density, **150-word AI-generated "Mental Map"** (summarizing what you are working on, key changes made, and next steps).

---

## ⚡ Quick Start

You can run `ckpt` instantly without installation using `uvx`, or install it permanently as a global CLI tool.

### Option A: Instant Run (via `uv`)
Run `ckpt` immediately on any machine where [Astral's `uv`](https://github.com/astral-sh/uv) is installed:

```bash
# Capture your current session checkpoint and generate an AI mental map
uvx --from ckpt ckpt save -m "Extracted middleware validation logic"

# Restore a prior state by its 8-character ID
uvx --from ckpt ckpt restore a1b2c3d4
```

### Option B: Global CLI Installation
Install `ckpt` permanently to your path:

```bash
# Install ckpt globally
uv tool install ckpt

# Initialize your AI provider (Ollama or Google Gemini)
ckpt setup

# Save your first checkpoint
ckpt save -m "Work in progress: authentication refactoring"

# Revert unstaged changes and restore prior session context
ckpt restore <checkpoint-id>
```

---

## 🏗️ Architecture

`ckpt` acts as a coordination bridge between your local shell environment, git tree, local/remote LLM intelligence, and your AI assistant:

```
    ┌──────────────────────────────────────────────────────────────┐
    │                     Developer Command Line                   │
    └──────────────────────────────┬───────────────────────────────┘
                                   │  ckpt save
                                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                          ckpt Engine                         │
    │  - Git Tree (diffs, branch, modified files)                  │
    │  - Shell History (~/.zsh_history, ~/.bash_history)           │
    └──────────────────────────────┬───────────────────────────────┘
                                   │  Prompt Payload
                                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                         LLM Provider                         │
    │  - Ollama (Local LLaMA-3 / Mistral)                          │
    │  - Google Gemini (API-driven Content Generation)             │
    └──────────────────────────────┬───────────────────────────────┘
                                   │  150-Word "Mental Map"
                                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                      Persistent Store                        │
    │  - Snapshot JSON: ~/.config/ckpt/snapshots/<id>.json         │
    │  - Strict Permissions: Read-Write Owner Only (0o600 / ACLs) │
    └──────────────────────────────────────────────────────────────┘
```

---

## 🔌 Model Context Protocol (MCP) Integration

`ckpt` ships with a built-in **Model Context Protocol (MCP)** server over standard input/output (`stdio`), allowing AI editors like **Cursor**, **Claude Desktop**, or **Claude Code** to programmatically query, list, and create checkpoints during a session.

### 1. Cursor Setup
Configure `ckpt` inside Cursor:
1. Open **Cursor Settings** -> **Features** -> **MCP**.
2. Click **+ Add New MCP Server**.
3. Fill out the dialog:
   - **Name**: `checkpoint`
   - **Type**: `command`
   - **Command**: `uvx --from ckpt ckpt-mcp`

### 2. Claude Desktop Setup
Add `ckpt` to your Claude Desktop configuration file:

* **macOS / Linux**: `~/.config/Claude/claude_desktop_config.json`
* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "checkpoint": {
      "command": "uvx",
      "args": [
        "--from",
        "ckpt",
        "ckpt-mcp"
      ]
    }
  }
}
```

### 3. Claude Code Setup
Install `ckpt-mcp` in your environment and run it via Claude Code's system rules:

```bash
# Register using Claude Code's system instructions
"Use the checkpoint MCP server tools ('save_snapshot', 'list_snapshots') to capture progress before complex changes and restore context."
```

---

## 🛡️ Privacy & Security (FAQ)

### Q: Does `ckpt` send my private code to the cloud?
**A:** By default, no! `ckpt` supports **Ollama** out of the box. If you configure a local Ollama instance (running LLaMA-3, Mistral, etc.), all your git diffs, histories, and mental maps are generated entirely on your local GPU/CPU. No external calls are made.

If you choose **Google Gemini** as your provider during `ckpt setup`, only the necessary git diff snippet (capped at 3,000 characters) and your recent command list are sent securely via TLS to Google AI Studio APIs to synthesize the summary.

### Q: How secure are my checkpoint files on disk?
**A:** Very secure. `ckpt` enforces strict file and folder permissions during save operations:
- **macOS / Linux**: Configuration folders are locked to `0o700` and files to `0o600` (readable/writeable by the owner only).
- **Windows**: The system explicitly uninherits ACL permissions and grants Full Control (`F`) exclusively to the active Windows username.

### Q: Can a compromised repository escape directory structures?
**A:** No. `ckpt` validates all snapshot IDs using strict regular expression guards (`^[a-f0-9]{1,64}$`) before executing any load, restore, or unlink command. Path traversal attempts like `../../etc/passwd` or `..\win.ini` are blocked instantly and raise a `CheckpointNotFoundError`.

---

## 📄 License
Licensed under the [MIT License](LICENSE).
