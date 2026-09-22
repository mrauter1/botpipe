from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest

from scripts.extract_codex_windows import extract_windows_package


ENTRYPOINT = "codex-x86_64-pc-windows-msvc.exe"
REQUIRED_PACKAGE = [
    ("codex-code-mode-host.exe", b"host"),
    ("codex-command-runner.exe", b"runner"),
    ("codex-windows-sandbox-setup.exe", b"setup"),
    ("codex-resources/codex-command-runner.exe", b"runner"),
    ("codex-resources/codex-windows-sandbox-setup.exe", b"setup"),
    (
        "codex-package.json",
        json.dumps(
            {
                "target": "x86_64-pc-windows-msvc",
                "entrypoint": ENTRYPOINT,
            }
        ).encode(),
    ),
]


def _archive(path: Path, entries: list[tuple[str, bytes | None]]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, contents in entries:
            if contents is None:
                bundle.writestr(name.rstrip("/") + "/", b"")
            else:
                bundle.writestr(name, contents)
    return path


def test_extracts_current_nested_package_and_preserves_resources(tmp_path: Path):
    archive = _archive(
        tmp_path / "codex.zip",
        [
            ("bin/", None),
            ("codex-resources/", None),
            (ENTRYPOINT, b"codex"),
            *REQUIRED_PACKAGE,
            ("late-directory/item", b"nested"),
            ("late-directory/", None),
        ],
    )

    binary = extract_windows_package(archive, tmp_path / "install")

    assert binary.read_bytes() == b"codex"
    assert binary.name == ENTRYPOINT
    assert (
        binary.parent / "codex-resources/codex-command-runner.exe"
    ).read_bytes() == b"runner"
    assert json.loads((binary.parent / "codex-package.json").read_bytes()) == {
        "target": "x86_64-pc-windows-msvc",
        "entrypoint": ENTRYPOINT,
    }
    assert (binary.parent / "late-directory/item").read_bytes() == b"nested"


@pytest.mark.parametrize(
    "name",
    ["../escape", "/absolute", "C:/drive", "nested\\escape", "CON.txt", "name. "],
)
def test_rejects_traversal_absolute_and_ambiguous_windows_names(
    tmp_path: Path, name: str
):
    archive = _archive(
        tmp_path / "codex.zip",
        [(ENTRYPOINT, b"codex"), *REQUIRED_PACKAGE, (name, b"x")],
    )

    with pytest.raises(ValueError, match="archive entry"):
        extract_windows_package(archive, tmp_path / "install")


def test_rejects_case_collisions(tmp_path: Path):
    archive = _archive(
        tmp_path / "codex.zip",
        [
            (ENTRYPOINT, b"codex"),
            *REQUIRED_PACKAGE,
            ("Resources/item", b"first"),
            ("resources/ITEM", b"second"),
        ],
    )

    with pytest.raises(ValueError, match="case-colliding"):
        extract_windows_package(archive, tmp_path / "install")


def test_rejects_symlinks(tmp_path: Path):
    archive = tmp_path / "codex.zip"
    link = zipfile.ZipInfo("codex-resources/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(ENTRYPOINT, b"codex")
        for name, contents in REQUIRED_PACKAGE:
            bundle.writestr(name, contents)
        bundle.writestr(link, b"target")

    with pytest.raises(ValueError, match="unsupported"):
        extract_windows_package(archive, tmp_path / "install")


def test_requires_matching_package_metadata_and_helpers(tmp_path: Path):
    missing_helper = _archive(
        tmp_path / "missing-helper.zip",
        [(ENTRYPOINT, b"codex"), *REQUIRED_PACKAGE[:-2], REQUIRED_PACKAGE[-1]],
    )
    with pytest.raises(ValueError, match="missing required entries"):
        extract_windows_package(missing_helper, tmp_path / "missing-install")

    wrong_metadata = _archive(
        tmp_path / "wrong-metadata.zip",
        [
            (ENTRYPOINT, b"codex"),
            *REQUIRED_PACKAGE[:-1],
            (
                "codex-package.json",
                b'{"target":"aarch64-pc-windows-msvc","entrypoint":"wrong.exe"}',
            ),
        ],
    )
    with pytest.raises(ValueError, match="wrong target"):
        extract_windows_package(wrong_metadata, tmp_path / "metadata-install")
