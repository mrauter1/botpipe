"""Safely extract the official Codex Windows package used by native CI."""

from __future__ import annotations

import json
import shutil
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath


_WINDOWS_DEVICES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_WINDOWS_FORBIDDEN = frozenset('<>:"|?*')


def _safe_parts(name: str) -> tuple[str, ...]:
    if not name or "\\" in name or name.startswith("/"):
        raise ValueError(f"unsafe Codex archive entry: {name!r}")
    raw_parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise ValueError(f"unsafe Codex archive entry: {name!r}")
    path = PurePosixPath(name)
    parts = path.parts
    if not parts:
        raise ValueError(f"unsafe Codex archive entry: {name!r}")
    for part in parts:
        stem = part.split(".", 1)[0].rstrip(" .").casefold()
        if (
            part.endswith((".", " "))
            or stem in _WINDOWS_DEVICES
            or any(character in _WINDOWS_FORBIDDEN for character in part)
            or any(ord(character) < 32 for character in part)
        ):
            raise ValueError(f"ambiguous Windows archive entry: {name!r}")
    return parts


def extract_windows_package(
    archive: Path,
    destination: Path,
    *,
    entrypoint: str = "codex-x86_64-pc-windows-msvc.exe",
) -> Path:
    """Extract and validate the complete official Windows package."""
    destination.mkdir(parents=True, exist_ok=True)
    planned: list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]] = []
    paths: dict[tuple[str, ...], tuple[tuple[str, ...], bool]] = {}
    explicit_paths: set[tuple[str, ...]] = set()
    entries: dict[tuple[str, ...], zipfile.ZipInfo] = {}

    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            parts = _safe_parts(member.filename)
            is_directory = member.is_dir()
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type not in (0, stat.S_IFDIR if is_directory else stat.S_IFREG):
                raise ValueError(
                    f"unsupported Codex archive entry: {member.filename!r}"
                )
            folded = tuple(
                unicodedata.normalize("NFC", part).casefold() for part in parts
            )
            for index in range(1, len(folded) + 1):
                key = folded[:index]
                spelling = parts[:index]
                is_path_directory = index < len(folded) or is_directory
                previous = paths.get(key)
                if previous is not None:
                    previous_spelling, previous_is_directory = previous
                    if previous_spelling != spelling:
                        raise ValueError(
                            f"case-colliding Codex archive entry: {member.filename!r}"
                        )
                    if not previous_is_directory or not is_path_directory:
                        raise ValueError(
                            f"archive path collides with a file: {member.filename!r}"
                        )
                else:
                    paths[key] = (spelling, is_path_directory)
            if folded in explicit_paths:
                raise ValueError(
                    f"duplicate Codex archive entry: {member.filename!r}"
                )
            explicit_paths.add(folded)
            planned.append((member, parts, is_directory))
            if not is_directory:
                entries[parts] = member

        required = {
            (entrypoint,),
            ("codex-package.json",),
            ("codex-code-mode-host.exe",),
            ("codex-command-runner.exe",),
            ("codex-windows-sandbox-setup.exe",),
            ("codex-resources", "codex-command-runner.exe"),
            ("codex-resources", "codex-windows-sandbox-setup.exe"),
        }
        missing = required.difference(entries)
        if missing:
            raise ValueError(
                f"Codex package is missing required entries: {sorted(missing)!r}"
            )
        metadata_member = entries[("codex-package.json",)]
        if metadata_member.file_size > 1_000_000:
            raise ValueError("Codex package metadata is unreasonably large")
        try:
            metadata = json.loads(bundle.read(metadata_member))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Codex package metadata is invalid") from exc
        target = entrypoint.removeprefix("codex-").removesuffix(".exe")
        if not isinstance(metadata, dict) or metadata.get("target") != target:
            raise ValueError("Codex package metadata has the wrong target")
        if metadata.get("entrypoint") != entrypoint:
            raise ValueError("Codex package metadata has the wrong entrypoint")

        for member, parts, is_directory in planned:
            target = destination.joinpath(*parts)
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)

    return destination / entrypoint
