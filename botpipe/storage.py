"""Platform-aware flushing for atomic file publication."""

from __future__ import annotations

import os
from pathlib import Path


def sync_directory(path: Path) -> None:
    """Persist directory entries on POSIX; propagate genuine storage failures.

    Windows does not expose directory fsync through Python's file descriptors.
    Callers still flush file contents before atomic replacement there, but that
    does not promise the same power-loss durability for the directory entry.
    """
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
