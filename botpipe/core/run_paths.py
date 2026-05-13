"""Internal run identity and filesystem layout values.

Not part of the public botpipe authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunPaths:
    root: Path
    task_folder: Path
    workflow_folder: Path
    run_folder: Path
    package_folder: Path
    request_file: Path
    task_request_file: Path | None
    run_meta_file: Path | None
    events_file: Path
    checkpoint_file: Path
    sessions_dir: Path
    trace_file: Path
    raw_dir: Path
    parent_file: Path | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "root",
            "task_folder",
            "workflow_folder",
            "run_folder",
            "package_folder",
            "request_file",
            "events_file",
            "checkpoint_file",
            "sessions_dir",
            "trace_file",
            "raw_dir",
        ):
            object.__setattr__(self, field_name, Path(getattr(self, field_name)))
        if self.task_request_file is not None:
            object.__setattr__(self, "task_request_file", Path(self.task_request_file))
        if self.run_meta_file is not None:
            object.__setattr__(self, "run_meta_file", Path(self.run_meta_file))
        if self.parent_file is not None:
            object.__setattr__(self, "parent_file", Path(self.parent_file))


@dataclass(frozen=True, slots=True)
class RunIdentity:
    task_id: str
    run_id: str
    workflow_name: str
    paths: RunPaths | None = None
