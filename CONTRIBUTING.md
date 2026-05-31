# Contributing to `ckpt`

First of all, thank you for taking the time to contribute to `ckpt`! We welcome community contributions to help improve state snapshotting and developer productivity.

---

## 🛠️ Development Setup

We use [Astral's `uv`](https://github.com/astral-sh/uv) to manage our environment and dependencies.

1. **Fork and Clone the Repository**
2. **Initialize the Environment**:
   ```bash
   # Synchronize the virtual environment and all development tools
   uv sync --all-groups
   ```
3. **Activate the Environment**:
   ```bash
   # Activate local virtual environment
   .venv/Scripts/activate      # Windows (PowerShell)
   source .venv/bin/activate   # macOS / Linux
   ```

---

## 🧑‍💻 Code Guidelines

To keep the codebase maintainable and safe, we enforce strict standards:

* **Style & Formatting**: We follow PEP 8 standard formatting rules. Run our linter and formatter using `ruff` prior to committing:
  ```bash
  uv run ruff check       # Run linter checks
  uv run ruff format      # Format the code base
  ```
* **Strict Type Hints**: Every function and module must be strictly type-annotated. Run type checking using `mypy`:
  ```bash
  uv run mypy ckpt/
  ```
* **Testing Requirements**: We use `pytest` for all automation assertions. If you introduce a feature or modify a module, you **must write accompanying unit tests**:
  ```bash
  uv run pytest           # Run full suite
  ```

---

## 🐚 Extending Shell History Parsers

One of the best ways to contribute is by writing a custom shell history parser (e.g., for **Fish**, **NuShell**, or custom PowerShell installations).

### How history extraction works in `ckpt`
All history loading resides inside `ckpt/snapshot.py` under the function `get_shell_history()`.

1. **Locate the Shell**: Add your shell pattern matching within `get_shell_history()` using the `SHELL` environment variable or checking system configurations.
2. **Implement file reading**: Leverage `_read_history_file(path, limit)` to safely read and decode lines using multiple fallback encodings without loading the entire file into memory.
3. **Clean Metadata (If needed)**: If your shell stores metadata timestamps (like Zsh's `: <timestamp>:<duration>;`), write a regex-based helper (like `_clean_zsh_history`) to strip the extra fields.

#### Example: Implementing a Fish history parser
```python
def get_shell_history(limit: int = 5) -> list[str]:
    # ... inside get_shell_history ...
    shell = os.environ.get("SHELL", "")
    if "fish" in shell:
        fish_history = Path.home() / ".local" / "share" / "fish" / "fish_history"
        if fish_history.is_file():
            # Fish history is stored in YAML format. Read, clean, and extract
            lines = _read_history_file(fish_history, limit * 4) # Read extra lines due to multi-line YAML
            # Parse YAML commands matching '- cmd: ' prefix
            commands = [line.replace("- cmd:", "").strip() for line in lines if line.startswith("- cmd:")]
            return commands[-limit:]
```

---

## 🐛 Reporting Bugs & Requesting Features

* **Bugs**: Before creating an issue, verify that it isn't already reported. Include details like your OS version, Python version, configuration (Ollama/Gemini), and the stack trace.
* **Features**: Clearly describe the proposed capability, explain why it would benefit developers, and present a sample usage workflow.
