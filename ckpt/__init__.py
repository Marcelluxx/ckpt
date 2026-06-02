"""ckpt — A CLI utility for capturing and restoring development session checkpoints."""

import importlib.metadata

try:
    __version__ = importlib.metadata.version("ckpt-cli")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.2.0"
