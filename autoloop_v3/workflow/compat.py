"""Compatibility normalization boundary.

The strict-core phase only needs a no-op normalizer. Legacy loader and workspace
drift handling land in later phases.
"""

from __future__ import annotations

from typing import Any


def normalize_workflow(workflow_cls: type[Any]) -> type[Any]:
    """Return the workflow class unchanged in the strict-core phase."""

    return workflow_cls

