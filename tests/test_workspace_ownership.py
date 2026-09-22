from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from botpipe.errors import RunBusy
from botpipe.journal import Journal
from botpipe.workspace_ownership import WorkspaceCoordinator


def _journal(path: Path, run_id: str, *, unresolved: bool = False) -> Path:
    journal = Journal(path)
    journal.create_run({"run_id": run_id, "status": "running", "error": None})
    if unresolved:
        journal.begin(
            operation_id=f"{run_id}:op",
            run_id=run_id,
            scope="root",
            ordinal=0,
            kind="activity",
            name="effect",
            fingerprint="fingerprint",
            inputs={"$botpipe": "dict", "value": {}},
            limit=10,
        )
    journal.close()
    return path


def _provider_operations(path: Path, run_id: str, *operation_ids: str) -> Path:
    journal = Journal(path)
    journal.create_run({"run_id": run_id, "status": "running", "error": None})
    for ordinal, operation_id in enumerate(operation_ids):
        journal.begin(
            operation_id=operation_id,
            run_id=run_id,
            scope="root",
            ordinal=ordinal,
            kind="provider",
            name="effect",
            fingerprint=f"fingerprint:{operation_id}",
            inputs={"$botpipe": "dict", "value": {"writes": []}},
            limit=10,
        )
    journal.close()
    return path


def _claim_rows(coordinator: WorkspaceCoordinator) -> list[sqlite3.Row]:
    db = sqlite3.connect(coordinator.database)
    db.row_factory = sqlite3.Row
    try:
        return db.execute("SELECT * FROM claims ORDER BY workspace,token").fetchall()
    finally:
        db.close()


def test_default_registry_location_is_patchable_and_outside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "user-state"
    monkeypatch.setattr("botpipe.workspace_ownership.user_state_dir", lambda: state)

    coordinator = WorkspaceCoordinator()

    assert coordinator.registry_dir == state
    assert coordinator.database.parent == state
    assert not any(workspace.iterdir())


def test_large_live_directory_identity_is_not_persisted_as_sqlite_integer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    coordinator = WorkspaceCoordinator(tmp_path / "registry")
    canonical = str(workspace.resolve())
    large_identity = (2**100 + 1, 2**120 + 3)
    monkeypatch.setattr(
        "botpipe.workspace_ownership._canonical_directory",
        lambda path: (canonical, large_identity),
    )
    monkeypatch.setattr(coordinator, "_check_identity", lambda lease: None)

    with coordinator.claim(workspace, journal, "run", "write") as lease:
        assert lease._identity == large_identity
        db = sqlite3.connect(coordinator.database)
        try:
            columns = {
                row[1] for row in db.execute("PRAGMA table_info(claims)")
            }
        finally:
            db.close()
        assert columns.isdisjoint({"device", "inode"})


def test_canonical_alias_and_component_overlap_conflicts(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    root.mkdir()
    child.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable")
    first = _journal(tmp_path / "first.sqlite3", "one")
    second = _journal(tmp_path / "second.sqlite3", "two")
    owner = WorkspaceCoordinator(registry)
    contender = WorkspaceCoordinator(registry)

    with owner.claim(root, first, "one", "write"):
        with pytest.raises(RunBusy, match="overlap"):
            with contender.claim(alias, second, "two", "read"):
                pass
        with pytest.raises(RunBusy, match="overlap"):
            with contender.claim(child, first, "one", "write"):
                pass


def test_readers_coexist_but_writer_conflicts_in_both_tree_orders(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    root.mkdir()
    child.mkdir()
    first = _journal(tmp_path / "first.sqlite3", "one")
    second = _journal(tmp_path / "second.sqlite3", "two")
    a = WorkspaceCoordinator(registry)
    b = WorkspaceCoordinator(registry)

    with a.claim(root, first, "one", "read"):
        with b.claim(child, second, "two", "read"):
            pass
        with pytest.raises(RunBusy):
            with b.claim(child, second, "two", "write"):
                pass

    with a.claim(child, first, "one", "write"):
        with pytest.raises(RunBusy):
            with b.claim(root, second, "two", "write"):
                pass


def test_explicit_live_ancestor_delegates_but_not_sibling_writer(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    child.mkdir(parents=True)
    journal = _journal(tmp_path / "state.sqlite3", "run")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(root, journal, "run", "write") as root_lease:
        with pytest.raises(RunBusy):
            with coordinator.claim(child, journal, "run", "write"):
                pass
        with coordinator.claim(
            child, journal, "run", "write", parent=root_lease
        ) as child_lease:
            with pytest.raises(RunBusy):
                with coordinator.claim(
                    child, journal, "run", "write", parent=root_lease
                ):
                    pass
            child_lease.validate()
        with coordinator.claim(
            root, journal, "run", "read", parent=root_lease
        ):
            pass
        with pytest.raises(RunBusy, match="no longer active"):
            child_lease.validate()


def test_explicit_live_descendant_can_expand_its_claim(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    sibling = root / "sibling"
    child.mkdir(parents=True)
    sibling.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    foreign = _journal(tmp_path / "foreign.sqlite3", "foreign")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(child, journal, "run", "write") as child_lease:
        with coordinator.claim(
            root, journal, "run", "read", parent=child_lease
        ):
            with pytest.raises(RunBusy):
                with WorkspaceCoordinator(registry).claim(
                    sibling, foreign, "foreign", "write"
                ):
                    pass
        with coordinator.claim(
            root, journal, "run", "write", parent=child_lease
        ):
            pass


@pytest.mark.parametrize("mode", ["read", "write"])
def test_descendant_delegation_does_not_exempt_foreign_sibling(
    tmp_path: Path, mode: str
) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    sibling = root / "sibling"
    child.mkdir(parents=True)
    sibling.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    foreign = _journal(tmp_path / "foreign.sqlite3", "foreign")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(child, journal, "run", "write") as child_lease:
        with WorkspaceCoordinator(registry).claim(
            sibling, foreign, "foreign", "write"
        ):
            with pytest.raises(RunBusy, match="active"):
                with coordinator.claim(
                    root,
                    journal,
                    "run",
                    mode,
                    parent=child_lease,
                ):
                    pass


def test_unrelated_supplied_parents_are_ignored(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(left, journal, "run", "write") as left_lease:
        with coordinator.claim(
            right, journal, "run", "write", parent=(left_lease,)
        ):
            pass


def test_read_parent_cannot_delegate_write(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    child = tmp_path / "work" / "child"
    child.mkdir(parents=True)
    journal = _journal(tmp_path / "state.sqlite3", "run")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(child.parent, journal, "run", "read") as lease:
        with pytest.raises(RunBusy, match="read lease"):
            with coordinator.claim(
                child, journal, "run", "write", parent=lease
            ):
                pass


def test_unresolved_orphan_fences_foreign_and_requires_same_run_recovery(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    workspace = tmp_path / "work"
    workspace.mkdir()
    original = _journal(tmp_path / "original.sqlite3", "run", unresolved=True)
    foreign = _journal(tmp_path / "foreign.sqlite3", "run")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(workspace, original, "run", "write"):
        pass
    old_token = _claim_rows(coordinator)[0]["token"]

    with pytest.raises(RunBusy, match="unresolved effects"):
        with coordinator.claim(workspace, foreign, "run", "write"):
            pass
    with pytest.raises(RunBusy, match="unresolved effects"):
        with coordinator.claim(workspace, original, "run", "write"):
            pass

    with coordinator.claim(
        workspace, original, "run", "write", recovery=True
    ) as recovered:
        assert recovered.token != old_token
        with pytest.raises(RunBusy, match="active"):
            with WorkspaceCoordinator(registry).claim(
                workspace, foreign, "run", "read"
            ):
                pass
    assert [row["token"] for row in _claim_rows(coordinator)] == [recovered.token]


def test_recovery_only_replaces_overlapping_same_run_claims(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run", unresolved=True)
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(left, journal, "run", "write"):
        pass
    with coordinator.claim(right, journal, "run", "write"):
        pass
    before = {Path(row["workspace"]): row["token"] for row in _claim_rows(coordinator)}

    with coordinator.claim(left, journal, "run", "write", recovery=True):
        during = {
            Path(row["workspace"]): row["token"] for row in _claim_rows(coordinator)
        }
        assert during[right] == before[right]
        assert during[left] != before[left]


def test_narrow_root_recovery_retains_then_replaces_same_run_ancestor(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    child.mkdir(parents=True)
    journal = _journal(tmp_path / "state.sqlite3", "run", unresolved=True)
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(root, journal, "run", "write") as old_root:
        pass

    with coordinator.claim(
        child, journal, "run", "write", recovery=True
    ) as child_lease:
        rows = {
            Path(row["workspace"]): row["token"] for row in _claim_rows(coordinator)
        }
        assert rows == {root: old_root.token, child: child_lease.token}

        with coordinator.claim(
            root,
            journal,
            "run",
            "write",
            parent=child_lease,
            recovery=True,
        ) as recovered_root:
            rows = {
                Path(row["workspace"]): row["token"] for row in _claim_rows(coordinator)
            }
            assert rows == {
                root: recovered_root.token,
                child: child_lease.token,
            }
            assert recovered_root.token != old_root.token


def test_narrow_recovery_does_not_exempt_active_or_foreign_ancestor(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    child = root / "child"
    child.mkdir(parents=True)
    own = _journal(tmp_path / "own.sqlite3", "run", unresolved=True)
    foreign = _journal(tmp_path / "foreign.sqlite3", "foreign", unresolved=True)
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(root, own, "run", "write"):
        with pytest.raises(RunBusy, match="active"):
            with WorkspaceCoordinator(registry).claim(
                child, own, "run", "write", recovery=True
            ):
                pass

    # Replace the settled same-run setup with a foreign unresolved orphan.
    own_journal = Journal(own)
    own_journal.finish("run:op", {"finished": True})
    own_journal.close()
    with coordinator.claim(root, foreign, "foreign", "write"):
        pass
    with pytest.raises(RunBusy, match="unresolved effects"):
        with coordinator.claim(child, own, "run", "write", recovery=True):
            pass


def test_root_recovery_retains_operation_claim_for_matching_replay(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    root = tmp_path / "work"
    target = root / "target"
    independent = tmp_path / "independent"
    target.mkdir(parents=True)
    independent.mkdir()
    journal = _provider_operations(
        tmp_path / "state.sqlite3", "run", "provider:a", "provider:b"
    )
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(
        target,
        journal,
        "run",
        "write",
        operation_id="provider:a",
    ) as old_provider:
        pass

    with coordinator.claim(
        root, journal, "run", "write", recovery=True
    ) as root_lease:
        rows = {row["operation_id"]: row for row in _claim_rows(coordinator)}
        assert rows["provider:a"]["token"] == old_provider.token
        assert rows[None]["token"] == root_lease.token

        with pytest.raises(RunBusy, match="unresolved effects"):
            with coordinator.claim(
                target,
                journal,
                "run",
                "write",
                parent=root_lease,
                recovery=True,
                operation_id="provider:b",
            ):
                pass

        with coordinator.claim(
            independent,
            journal,
            "run",
            "write",
            parent=root_lease,
            recovery=True,
            operation_id="provider:b",
        ):
            pass

        with coordinator.claim(
            target,
            journal,
            "run",
            "write",
            parent=root_lease,
            recovery=True,
            operation_id="provider:a",
        ) as recovered_provider:
            rows = {Path(row["workspace"]): row for row in _claim_rows(coordinator)}
            assert rows[target]["token"] == recovered_provider.token
            assert recovered_provider.token != old_provider.token
            assert rows[target]["operation_id"] == "provider:a"


def test_broader_operation_claim_survives_narrow_root_recovery(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    target = tmp_path / "work"
    root = target / "child-root"
    root.mkdir(parents=True)
    journal = _provider_operations(tmp_path / "state.sqlite3", "run", "provider")
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(
        target,
        journal,
        "run",
        "write",
        operation_id="provider",
    ) as old_provider:
        pass

    with coordinator.claim(
        root, journal, "run", "write", recovery=True
    ) as root_lease:
        rows = {Path(row["workspace"]): row for row in _claim_rows(coordinator)}
        assert rows[target]["token"] == old_provider.token
        assert rows[root]["operation_id"] is None
        with coordinator.claim(
            target,
            journal,
            "run",
            "write",
            parent=root_lease,
            recovery=True,
            operation_id="provider",
        ) as recovered:
            rows = {Path(row["workspace"]): row for row in _claim_rows(coordinator)}
            assert rows[target]["token"] == recovered.token
            assert recovered.token != old_provider.token


def test_operation_settlement_releases_only_its_own_claim(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    journal_path = _provider_operations(
        tmp_path / "state.sqlite3", "run", "provider:a", "provider:b"
    )
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(
        left,
        journal_path,
        "run",
        "write",
        operation_id="provider:a",
    ):
        pass
    with coordinator.claim(
        right,
        journal_path,
        "run",
        "write",
        operation_id="provider:b",
    ):
        pass

    journal = Journal(journal_path)
    journal.finish("provider:a", {"finished": True})
    journal.close()
    assert Journal.foreign_has_unresolved_effects(
        journal_path, "run", "provider:a"
    ) is False
    assert Journal.foreign_has_unresolved_effects(
        journal_path, "run", "provider:b"
    ) is True
    assert Journal.foreign_has_unresolved_effects(
        journal_path, "run", "missing"
    ) is True

    foreign = _journal(tmp_path / "foreign.sqlite3", "foreign")
    with WorkspaceCoordinator(registry).claim(
        left, foreign, "foreign", "write"
    ):
        rows = _claim_rows(coordinator)
        assert {row["operation_id"] for row in rows} == {None, "provider:b"}


def test_settled_target_retires_inactive_dynamic_reads_only(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry"
    target = tmp_path / "target"
    dynamic_read = tmp_path / "dynamic-read"
    active_read = tmp_path / "active-read"
    unrelated = tmp_path / "unrelated"
    for path in (target, dynamic_read, active_read, unrelated):
        path.mkdir()
    journal_path = _provider_operations(
        tmp_path / "state.sqlite3", "run", "provider:a", "provider:b"
    )
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(
        dynamic_read,
        journal_path,
        "run",
        "read",
        operation_id="provider:a",
    ) as stale_read:
        pass
    with coordinator.claim(
        unrelated,
        journal_path,
        "run",
        "write",
        operation_id="provider:b",
    ) as unrelated_owner:
        pass

    target_context = coordinator.claim(
        target,
        journal_path,
        "run",
        "write",
        operation_id="provider:a",
    )
    target_context.__enter__()
    active_context = coordinator.claim(
        active_read,
        journal_path,
        "run",
        "read",
        operation_id="provider:a",
    )
    active_lease = active_context.__enter__()
    target_closed = False
    try:
        journal = Journal(journal_path)
        journal.finish("provider:a", {"finished": True})
        journal.close()

        target_context.__exit__(None, None, None)
        target_closed = True
        rows = _claim_rows(coordinator)
        assert {row["token"] for row in rows} == {
            active_lease.token,
            unrelated_owner.token,
        }
        assert stale_read.token not in {row["token"] for row in rows}
    finally:
        if not target_closed:
            target_context.__exit__(None, None, None)
        active_context.__exit__(None, None, None)


def test_unknown_registry_is_rejected_without_mutation(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    registry.mkdir()
    database = registry / "workspace-ownership.sqlite3"
    db = sqlite3.connect(database)
    db.execute("CREATE TABLE unrelated(value TEXT)")
    db.execute("INSERT INTO unrelated VALUES ('keep')")
    db.commit()
    db.close()
    before = database.read_bytes()

    with pytest.raises(ValueError, match="Incompatible workspace ownership"):
        WorkspaceCoordinator(registry)

    assert database.read_bytes() == before


@pytest.mark.parametrize("invalid", ["missing", "malformed"])
def test_missing_or_invalid_orphan_journal_is_conservative(
    tmp_path: Path, invalid: str
) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    journal = tmp_path / "owner.sqlite3"
    if invalid == "malformed":
        journal.write_text("not sqlite", encoding="utf-8")
    registry = tmp_path / "registry"
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(workspace, journal, "run", "read"):
        pass
    assert len(_claim_rows(coordinator)) == 1
    with pytest.raises(RunBusy, match="unresolved effects"):
        with coordinator.claim(
            workspace,
            _journal(tmp_path / "other.sqlite3", "other"),
            "other",
            "write",
        ):
            pass


def test_unresolved_reader_is_retained_but_does_not_block_readers(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run", unresolved=True)
    registry = tmp_path / "registry"
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(workspace, journal, "run", "read"):
        pass
    with WorkspaceCoordinator(registry).claim(workspace, journal, "run", "read"):
        pass
    assert len(_claim_rows(coordinator)) == 2
    with pytest.raises(RunBusy):
        with coordinator.claim(workspace, journal, "run", "write"):
            pass


def test_settled_claim_is_removed_on_release_and_safe_orphan_is_collected(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    settled = _journal(tmp_path / "settled.sqlite3", "settled")
    registry = tmp_path / "registry"
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(workspace, settled, "settled", "write"):
        assert len(_claim_rows(coordinator)) == 1
    assert _claim_rows(coordinator) == []

    missing = tmp_path / "missing.sqlite3"
    with coordinator.claim(workspace, missing, "missing", "write"):
        pass
    _journal(missing, "missing")
    with coordinator.claim(workspace, settled, "settled", "write"):
        rows = _claim_rows(coordinator)
        assert len(rows) == 1
        assert rows[0]["run_id"] == "settled"


def test_writer_is_released_only_after_effect_is_finalized(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    path = _journal(tmp_path / "state.sqlite3", "run", unresolved=True)
    registry = tmp_path / "registry"
    coordinator = WorkspaceCoordinator(registry)

    with coordinator.claim(workspace, path, "run", "write"):
        pass
    assert len(_claim_rows(coordinator)) == 1

    journal = Journal(path)
    journal.finish("run:op", {"artifact": "finalized"})
    journal.close()
    other = _journal(tmp_path / "other.sqlite3", "other")
    with coordinator.claim(workspace, other, "other", "write"):
        assert [row["run_id"] for row in _claim_rows(coordinator)] == ["other"]


def test_directory_replacement_invalidates_and_retains_claim(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    coordinator = WorkspaceCoordinator(tmp_path / "registry")

    with pytest.raises(RunBusy, match="changed while claim"):
        with coordinator.claim(workspace, journal, "run", "write") as lease:
            workspace.rename(tmp_path / "old-work")
            workspace.mkdir()
            with pytest.raises(RunBusy, match="replaced"):
                lease.validate()
    assert len(_claim_rows(coordinator)) == 1


def test_atomic_race_admits_one_overlapping_writer(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    registry = tmp_path / "registry"
    count = 8
    # Race claim admission, without making registry initialization a barrier peer.
    coordinators = [
        WorkspaceCoordinator(registry, busy_timeout=0.2) for _ in range(count)
    ]
    barrier = threading.Barrier(count)
    all_attempted = threading.Event()
    guard = threading.Lock()
    outcomes: list[str] = []

    def contend(index: int) -> None:
        coordinator = coordinators[index]
        barrier.wait(timeout=30)
        try:
            with coordinator.claim(workspace, journal, "run", "write"):
                with guard:
                    outcomes.append(f"won:{index}")
                    if len(outcomes) == count:
                        all_attempted.set()
                assert all_attempted.wait(30)
        except RunBusy:
            with guard:
                outcomes.append(f"busy:{index}")
                if len(outcomes) == count:
                    all_attempted.set()

    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(contend, index) for index in range(count)]
        try:
            for future in futures:
                future.result(timeout=30)
        finally:
            barrier.abort()

    assert sum(outcome.startswith("won:") for outcome in outcomes) == 1
    assert sum(outcome.startswith("busy:") for outcome in outcomes) == count - 1


def test_registry_busy_wait_is_bounded(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    journal = _journal(tmp_path / "state.sqlite3", "run")
    coordinator = WorkspaceCoordinator(tmp_path / "registry", busy_timeout=0.05)
    blocker = sqlite3.connect(coordinator.database, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        with pytest.raises(RunBusy, match="registry is busy"):
            with coordinator.claim(workspace, journal, "run", "write"):
                pass
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert time.monotonic() - started < 1
