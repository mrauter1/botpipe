from __future__ import annotations

import shutil

import pytest

from botpipe import codec


def _capsule(owners):
    return {
        "$botpipe": "capsule",
        "version": 1,
        "sources": {},
        "owners": owners,
        "value": None,
    }


def test_explicit_anchor_is_not_an_owner(tmp_path):
    anchor = tmp_path / "workspace"
    owner_file = tmp_path / "source" / "workflow.py"
    owner_directory = tmp_path / "shared"
    anchor.mkdir()
    owner_file.parent.mkdir()
    owner_file.write_text("# workflow\n")
    owner_directory.mkdir()

    with codec.source_identity((owner_file, owner_directory), anchor=anchor):
        encoded = codec.encode({"plain": 1}, record_owners=True)

    assert encoded["owners"] == {
        "schema": "botpipe.source-owners.v2",
        "anchor_kind": "directory",
        "boundaries": [
            {"kind": "file", "relative": "../source/workflow.py"},
            {"kind": "directory", "relative": "../shared"},
        ],
    }
    assert codec.recorded_source_boundaries(encoded, root_boundary=anchor) == (
        owner_file,
        owner_directory,
    )


def test_source_owners_relocate_from_independent_file_anchor(tmp_path):
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    anchor = original / "run.py"
    owner = original / "owned" / "workflow.py"
    owner.parent.mkdir(parents=True)
    anchor.write_text("# runner\n")
    owner.write_text("# workflow\n")

    with codec.source_identity(owner, anchor=anchor):
        encoded = codec.encode(None, record_owners=True)
    assert encoded["owners"]["anchor_kind"] == "file"
    assert encoded["owners"]["boundaries"] == [
        {"kind": "file", "relative": "owned/workflow.py"}
    ]

    shutil.copytree(original, relocated)
    shutil.rmtree(original)
    assert codec.recorded_source_boundaries(
        encoded, root_boundary=relocated / "run.py"
    ) == (relocated / "owned" / "workflow.py",)


def test_empty_owners_do_not_emit_an_owner_capsule(tmp_path):
    anchor = tmp_path / "anchor"
    anchor.mkdir()
    expected = codec.encode({"plain": 1})

    with codec.source_identity((), anchor=anchor):
        assert codec.encode({"plain": 1}, record_owners=True) == expected


def test_nested_and_suppressed_source_identity_restore_anchor(tmp_path):
    outer_anchor = tmp_path / "outer-anchor"
    outer_owner = tmp_path / "outer.py"
    inner_anchor = tmp_path / "inner-anchor"
    inner_owner = tmp_path / "inner.py"
    outer_anchor.mkdir()
    inner_anchor.mkdir()
    outer_owner.write_text("# outer\n")
    inner_owner.write_text("# inner\n")
    plain = codec.encode(None)

    with codec.source_identity(outer_owner, anchor=outer_anchor):
        outer_before = codec.encode(None, record_owners=True)
        with codec.source_identity(inner_owner, anchor=inner_anchor):
            inner = codec.encode(None, record_owners=True)
        with codec.without_source_identity():
            assert codec.encode(None, record_owners=True) == plain
        outer_after = codec.encode(None, record_owners=True)

    assert outer_after == outer_before
    assert codec.recorded_source_boundaries(
        outer_after, root_boundary=outer_anchor
    ) == (outer_owner,)
    assert codec.recorded_source_boundaries(inner, root_boundary=inner_anchor) == (
        inner_owner,
    )


def test_owner_record_rejects_anchor_kind_drift_and_duplicate_owners(tmp_path):
    anchor = tmp_path / "anchor"
    owner = anchor / "owner.py"
    anchor.mkdir()
    owner.write_text("# owner\n")
    duplicated = _capsule(
        {
            "schema": "botpipe.source-owners.v2",
            "anchor_kind": "directory",
            "boundaries": [
                {"kind": "file", "relative": "owner.py"},
                {"kind": "file", "relative": "owner.py"},
            ],
        }
    )
    with pytest.raises(TypeError, match="ambiguous"):
        codec.recorded_source_boundaries(duplicated, root_boundary=anchor)

    wrong_kind = {
        **duplicated,
        "owners": {**duplicated["owners"], "anchor_kind": "file"},
    }
    with pytest.raises(TypeError, match="anchor kind changed"):
        codec.recorded_source_boundaries(wrong_kind, root_boundary=anchor)


def test_owner_locator_rejects_symlink_traversal(tmp_path):
    anchor = tmp_path / "anchor"
    target = tmp_path / "target"
    anchor.mkdir()
    target.mkdir()
    (target / "owner.py").write_text("# owner\n")
    link = anchor / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    encoded = _capsule(
        {
            "schema": "botpipe.source-owners.v2",
            "anchor_kind": "directory",
            "boundaries": [
                {"kind": "file", "relative": "linked/owner.py"},
            ],
        }
    )

    with pytest.raises(TypeError, match="traverses a symlink"):
        codec.recorded_source_boundaries(encoded, root_boundary=anchor)
