# 🛡️ `ckpt` — Checkpoint: The State Saver & Context Restorer for AI Coding Sessions

<p align="center">
  <a href="https://github.com/Marcelluxx/ckpt/actions/workflows/tests.yml"><img src="https://github.com/Marcelluxx/ckpt/actions/workflows/tests.yml/badge.svg" alt="CI Status"></a>
  <a href="https://github.com/Marcelluxx/ckpt/releases"><img src="https://img.shields.io/github/v/release/Marcelluxx/ckpt?color=9b5de5&logo=github" alt="GitHub Release"></a>
  <a href="https://pypi.org/project/ckpt-cli/"><img src="https://img.shields.io/pypi/v/ckpt-cli?color=00bbf9&logo=pypi" alt="PyPI Version"></a>
  <a href="https://github.com/Marcelluxx/ckpt/stargazers"><img src="https://img.shields.io/github/stars/Marcelluxx/ckpt?style=social" alt="GitHub Stars"></a>
  <a href="https://github.com/Marcelluxx/ckpt/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Marcelluxx/ckpt?color=lightgrey" alt="License"></a>
</p>

Are your AI coding sessions suffering from **context bloat**, **expensive token waste**, and **session amnesia**?

When pair programming with AI agents (like Claude Desktop, Cursor, or Claude Code) or using Large Language Models, switching tasks or taking breaks is a painful context loss. Pasting massive git diffs and directory structures into chat windows burns through your tokens and confuses the AI.

**`ckpt` (Checkpoint)** solves this. It captures your entire development session state locally in a lightweight JSON package: your active git branch, latest commit hash, working directory changes, recent shell history, and a high-density, **agent-generated "Mental Map"** summarizing the session context, changes made, and next steps.

Restoring your workspace or catching your AI agent up is now as simple as a single command or tool call!

---

## ⚡ 30-Second Quick Start (No Experience Required)

You don't need to be a terminal expert to start using `ckpt`. You can activate and use it instantly in less than 30 seconds!

### Step 1: Install `ckpt` globally
Run **one** of these commands in your terminal to install `ckpt` on your system:

```bash
# Using uv (Recommended - ultra-fast)
uv tool install ckpt-cli

# Or using pipx
pipx install ckpt-cli

# Or using standard pip
pip install ckpt-cli
```

### 🔄 How to Update `ckpt`
To upgrade `ckpt` to the latest version, run the command corresponding to the tool you used for installation:

```bash
# Using uv
uv tool upgrade ckpt-cli

# Or using pipx
pipx upgrade ckpt-cli

# Or using standard pip
pip install --upgrade ckpt-cli
```

If you are developing locally and want to install your own changes in editable mode:
```bash
pip install -e .
```


### Step 2: Initialize your AI Provider (Optional)
If you want `ckpt` to automatically generate high-quality mental maps using an LLM when used via the CLI, run:
```bash
ckpt setup
```
*(Choose between a local **Ollama** instance to keep 100% of your code offline, **Google Gemini** for lightning-fast cloud summaries, or **OpenRouter** to access any open/closed model).*

### Step 3: Start Checkpointing!
*   **Save your progress:**
    ```bash
    ckpt save -m "Refactored user authentication routes"
    ```
*   **Restore a previous state interactively:**
    ```bash
    ckpt restore
    ```
    *(Use the Arrow Keys to scroll through your checkpoints cleanly and press Enter to restore!)*

---

## 🚀 The "Zero-Click" Setup: Let Your AI Do It!

Because modern coding AI assistants (like Claude, Cursor, or Cline) have direct access to your local filesystem, **you don't even need to configure these JSON files yourself!** 

You can literally copy-paste one of the prompts below into your AI chat, and your AI assistant will automatically locate, parse, and update the configuration files on your operating system.

### 💬 Prompts to Copy-Paste Into Your AI Assistant:

*   **For Claude Desktop:**
    > *"Please find my Claude Desktop configuration file on my system and add the checkpoint MCP server to it. Use the command 'uvx' with args ['--from', 'ckpt-cli', 'ckpt-mcp']."`*
*   **For VS Code (Cline / Roo Code):**
    > *"Please locate my Cline/Roo Code MCP settings JSON file under my VS Code AppData folder, and register the checkpoint MCP server using the 'uvx --from ckpt-cli ckpt-mcp' command."*
*   **For Cursor:**
    > *"Please add the checkpoint MCP server with command 'uvx --from ckpt-cli ckpt-mcp' to Cursor's global storage configuration file."*
*   **For Antigravity (Your Google Gemini Partner Agent):**
    > *"Installa ed attiva automaticamente il server MCP per il salvataggio dei checkpoint nel mio ambiente di lavoro."*

The AI assistant will find the file (e.g. `%APPDATA%\Claude\claude_desktop_config.json` on Windows, or `~/Library/Application Support/` on macOS), insert the `checkpoint` server block, and write the file. You will just need to approve the file write, and the tool is instantly active!

---

## 🔌 AI & Model Context Protocol (MCP) Integration

`ckpt` features a built-in **Model Context Protocol (MCP)** server. This allows AI assistants like **Cursor**, **Claude Desktop**, **Windsurf**, or **Claude Code** to programmatically save, list, and restore checkpoints in real-time.

> [!TIP]
> **The Direct Mental Map Hack (No API Key Required!)**
> When you pair `ckpt` with an AI agent in your editor, you don't even need to configure Ollama or Gemini!
> The AI agent already knows exactly what it has done. It will automatically pre-generate the **Mental Map** in memory and inject it directly into your checkpoint. This saves API costs, operates instantly, and uses the agent's live context perfectly!

### How to prompt your AI Agent to handle it
Once you have added `ckpt` to your AI editor (see configuration guides below), you can literally tell your AI agent:
*   *"Save a checkpoint of my current progress before you refactor this module."*
*   *"Can you show me the list of recent snapshots and restore the state from 10 minutes ago?"*
*   *"Use the checkpoint MCP server to save a snapshot before installing this library."*

---

## ⚙️ 1-Minute Configuration for AI Editors

Here is how to hook up `ckpt`'s MCP server to your favorite AI tools so they can use it automatically.

### 1. Cursor Setup
Configure `ckpt` inside Cursor to give your AI agent full snapshot powers:
1.  Open **Cursor Settings** -> **Features** -> **MCP**.
2.  Click **+ Add New MCP Server**.
3.  Fill out the dialog:
    *   **Name**: `checkpoint`
    *   **Type**: `command`
    *   **Command**: `uvx --from ckpt-cli ckpt-mcp`
4.  Click **Save**. You're done!

---

### 2. Claude Desktop Setup
Add `ckpt` to your Claude Desktop configuration file:
*   **macOS / Linux**: `~/.config/Claude/claude_desktop_config.json`
*   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the following block to the `mcpServers` section:
```json
{
  "mcpServers": {
    "checkpoint": {
      "command": "uvx",
      "args": [
        "--from",
        "ckpt-cli",
        "ckpt-mcp"
      ]
    }
  }
}
```

---

### 3. Windsurf Setup
Configure `ckpt` inside Windsurf:
1.  Open **Windsurf Settings** -> **Mcp**.
2.  Click **Add MCP Server**.
3.  Choose **Command** and configure it:
    *   **Name**: `checkpoint`
    *   **Command**: `uvx --from ckpt-cli ckpt-mcp`
4.  Save and enjoy automated state recovery!

---

### 4. Claude Code Setup
Install `ckpt-mcp` in your environment and register it using Claude Code's instructions:
```bash
# Register using Claude Code's system rules
"Use the checkpoint MCP server tools ('save_snapshot', 'list_snapshots') to capture progress before complex changes and restore context."
```

---

## 🏗️ Architecture Flow

`ckpt` coordinates your local terminal, Git workspace, and your AI assistant to form a cohesive, secure lifecycle:

```
    ┌──────────────────────────────────────────────────────────────┐
    │                Developer / AI Agent Interface                │
    └──────────────────────────────┬───────────────────────────────┘
                                   │  ckpt save / save_snapshot
                                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                          ckpt Engine                         │
    │  - Git Tree (Unified diffs, active branch, modified files)   │
    │  - Shell History (~/.zsh_history, PowerShell history, etc.)  │
    └──────────────────────────────┬───────────────────────────────┘
                                   │  In-Memory / LLM Payload
                                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                     Mental Map Generator                     │
    │  - DIRECT: Injected by AI agent directly in memory           │
    │  - LOCAL: Ollama (LLaMA-3 / Mistral)                         │
    │  - CLOUD: Google Gemini or OpenRouter (Capped at 3k chars)   │
    └──────────────────────────────┬───────────────────────────────┘
                                   │  JSON Metadata & Summary
                                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                      Persistent Store                        │
    │  - Snapshot Location: ~/.config/ckpt/snapshots/<id>.json     │
    │  - Linux/macOS Permissions: Locked to Owner only (0o600)    │
    │  - Windows Security: Uninherited ACLs with Full Control only │
    └──────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Security, Privacy & Safety

*   **100% Offline Capability:** By default, `ckpt` works entirely offline with local git metadata. If you choose Ollama as your LLM provider, all mental map generation occurs on your local machine. No code ever leaves your computer.
*   **Encrypted & Locked Configs:** Your checkpoint storage is secured with system-level permission controls (`0o600` on Unix and custom uninherited ACLs on Windows) to prevent unauthorized read access by other users or processes.
*   **Path-Traversal Protection:** Every checkpoint operation validates the input snapshot ID using a strict hexadecimal regex (`^[a-f0-9]{1,64}$`). Any attempt to pass directory traversal parameters (like `../../passwd`) is caught and blocked instantly.

---

## 📄 License

Licensed under the [MIT License](LICENSE).
