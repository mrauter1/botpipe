from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop.core.context import Context
from autoloop.core.errors import WorkflowExecutionError
from autoloop.core.stores import InMemorySessionStore
from autoloop.core.worklists import Selector, Worklist


class _State(BaseModel):
    pass


def _context(tmp_path: Path, **workflow_params: object) -> Context:
    return Context(
        task_id="task-1",
        run_id="run-1",
        workflow_name="selector-workflow",
        task_folder=tmp_path / "task",
        workflow_folder=tmp_path / "task" / "wf_selector_workflow",
        run_folder=tmp_path / "run",
        package_folder=tmp_path / "package",
        state=_State(),
        session_store=InMemorySessionStore(),
        workflow_params=workflow_params,
    )


def _worklist() -> Worklist[dict[str, str]]:
    return Worklist.from_items(
        name="phase",
        items=(
            {"id": "p1", "title": "Phase 1"},
            {"id": "p2", "title": "Phase 2"},
            {"id": "p3", "title": "Phase 3"},
            {"id": "p4", "title": "Phase 4"},
            {"id": "p5", "title": "Phase 5"},
        ),
        selector=Selector(
            item_param="phase",
            start_param="from_phase",
            end_param="to_phase",
            mode_param="phase_mode",
            allowed_modes=("all", "single", "up_to", "from_to"),
        ),
    )


def test_selector_default_all_selects_all_items(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path))
    assert selection.mode == "all"
    assert selection.explicit is False
    assert [item.id for item in selection.items] == ["p1", "p2", "p3", "p4", "p5"]


def test_selector_all_rejects_item_param(tmp_path: Path) -> None:
    with pytest.raises(
        WorkflowExecutionError,
        match=r"worklist 'phase' selector mode 'all' does not accept parameter 'phase' with value 'p3'",
    ):
        _worklist().initial_selection(_context(tmp_path, phase="p3"))


def test_selector_all_rejects_start_param(tmp_path: Path) -> None:
    with pytest.raises(
        WorkflowExecutionError,
        match=r"worklist 'phase' selector mode 'all' does not accept parameter 'from_phase' with value 'p2'",
    ):
        _worklist().initial_selection(_context(tmp_path, from_phase="p2"))


def test_selector_all_rejects_end_param(tmp_path: Path) -> None:
    with pytest.raises(
        WorkflowExecutionError,
        match=r"worklist 'phase' selector mode 'all' does not accept parameter 'to_phase' with value 'p4'",
    ):
        _worklist().initial_selection(_context(tmp_path, to_phase="p4"))


def test_selector_single_with_item_selects_one_item(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="single", phase="p3"))
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p3"]


def test_selector_single_without_item_selects_first_item(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="single"))
    assert selection.explicit is False
    assert [item.id for item in selection.items] == ["p1"]


def test_selector_up_to_with_item_selects_prefix(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="up_to", phase="p3"))
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p1", "p2", "p3"]


def test_selector_up_to_with_end_param_selects_prefix(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="up_to", to_phase="p3"))
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p1", "p2", "p3"]


def test_selector_up_to_without_bound_selects_all(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="up_to"))
    assert selection.explicit is False
    assert [item.id for item in selection.items] == ["p1", "p2", "p3", "p4", "p5"]


def test_selector_from_to_with_start_and_end_selects_inclusive_range(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(
        _context(tmp_path, phase_mode="from_to", from_phase="p2", to_phase="p4")
    )
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p2", "p3", "p4"]


def test_selector_from_to_with_only_start_selects_suffix(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="from_to", from_phase="p2"))
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p2", "p3", "p4", "p5"]


def test_selector_from_to_with_only_end_selects_prefix(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="from_to", to_phase="p4"))
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p1", "p2", "p3", "p4"]


def test_selector_from_to_uses_item_param_as_end_bound(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="from_to", phase="p4"))
    assert selection.explicit is True
    assert [item.id for item in selection.items] == ["p1", "p2", "p3", "p4"]


def test_selector_from_to_without_bounds_selects_all(tmp_path: Path) -> None:
    selection = _worklist().initial_selection(_context(tmp_path, phase_mode="from_to"))
    assert selection.explicit is False
    assert [item.id for item in selection.items] == ["p1", "p2", "p3", "p4", "p5"]


def test_selector_from_to_start_after_end_fails(tmp_path: Path) -> None:
    with pytest.raises(
        WorkflowExecutionError,
        match=r"worklist 'phase' selector mode 'from_to' has invalid range",
    ):
        _worklist().initial_selection(
            _context(tmp_path, phase_mode="from_to", from_phase="p4", to_phase="p2")
        )


def test_selector_unknown_item_fails_with_known_ids(tmp_path: Path) -> None:
    with pytest.raises(
        WorkflowExecutionError,
        match=r"worklist 'phase' selector mode 'single' parameter 'phase' references unknown item id 'px'; known ids: p1, p2, p3, p4, p5",
    ):
        _worklist().initial_selection(_context(tmp_path, phase_mode="single", phase="px"))


def test_selector_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(
        WorkflowExecutionError,
        match=r"worklist 'phase' selector parameter 'phase_mode' received invalid mode 'range'; allowed modes: all, single, up_to, from_to",
    ):
        _worklist().initial_selection(_context(tmp_path, phase_mode="range"))


def test_selector_rejects_duplicate_allowed_modes() -> None:
    with pytest.raises(ValueError, match=r"duplicate mode 'single'"):
        Selector(allowed_modes=("all", "single", "single"))


def test_selector_rejects_default_mode_not_allowed() -> None:
    with pytest.raises(ValueError, match="Selector.default_mode must be included in allowed_modes"):
        Selector(default_mode="single", allowed_modes=("all",))
