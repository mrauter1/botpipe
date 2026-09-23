"""Installed Codex capability discovery.

The adapter derives its contract from the executable it will run.  There is no
version allow-list: a release is usable when its generated protocol describes
the methods and fields Botpipe needs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CapabilityError(RuntimeError):
    """The installed Codex cannot faithfully enforce a requested contract."""


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    available: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CodexCapabilities:
    executable: str
    version: str
    identity: str
    methods: frozenset[str]
    features: tuple[dict[str, Any], ...] = ()
    supports_turn_sandbox: bool = False
    supports_interrupt: bool = False
    supports_output_schema: bool = False
    supports_dynamic_tools: bool = False
    supports_tool_config: bool = False
    supports_mcp_config: bool = False
    supports_effort: bool = False
    supports_instructions: bool = False
    supports_strict_workspace_roots: bool = False
    presets: Mapping[str, CapabilityStatus] = field(default_factory=dict)
    item_types: frozenset[str] = frozenset()

    @property
    def probe_hash(self) -> str:
        return self.identity

    def require(self, preset: str) -> None:
        status = self.presets.get(preset)
        if status is None:
            raise CapabilityError(f"unknown Codex preset {preset!r}")
        if not status.available:
            raise CapabilityError(status.reason or f"preset {preset!r} is unavailable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "executable": self.executable,
            "version": self.version,
            "probe_hash": self.probe_hash,
            "methods": sorted(self.methods),
            "features": [dict(item) for item in self.features],
            "supports_turn_sandbox": self.supports_turn_sandbox,
            "supports_interrupt": self.supports_interrupt,
            "supports_output_schema": self.supports_output_schema,
            "supports_dynamic_tools": self.supports_dynamic_tools,
            "supports_tool_config": self.supports_tool_config,
            "supports_mcp_config": self.supports_mcp_config,
            "supports_effort": self.supports_effort,
            "supports_instructions": self.supports_instructions,
            "supports_strict_workspace_roots": self.supports_strict_workspace_roots,
            "presets": {
                name: value.to_dict() for name, value in sorted(self.presets.items())
            },
            "item_types": sorted(self.item_types),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CodexCapabilities:
        return cls(
            executable=str(value["executable"]),
            version=str(value["version"]),
            identity=str(value["probe_hash"]),
            methods=frozenset(map(str, value.get("methods", ()))),
            features=tuple(dict(item) for item in value.get("features", ())),
            supports_turn_sandbox=bool(value.get("supports_turn_sandbox")),
            supports_interrupt=bool(value.get("supports_interrupt")),
            supports_output_schema=bool(value.get("supports_output_schema")),
            supports_dynamic_tools=bool(value.get("supports_dynamic_tools")),
            supports_tool_config=bool(value.get("supports_tool_config")),
            supports_mcp_config=bool(value.get("supports_mcp_config")),
            supports_effort=bool(value.get("supports_effort")),
            supports_instructions=bool(value.get("supports_instructions")),
            supports_strict_workspace_roots=bool(
                value.get("supports_strict_workspace_roots")
            ),
            presets={
                str(name): CapabilityStatus(
                    bool(status.get("available")), status.get("reason")
                )
                for name, status in value.get("presets", {}).items()
            },
            item_types=frozenset(map(str, value.get("item_types", ()))),
        )


_CORE_METHODS = frozenset(
    {"initialize", "thread/start", "thread/resume", "turn/start", "turn/interrupt"}
)
_PROBE_FORMAT = 7


def _method_names(document: Mapping[str, Any]) -> frozenset[str]:
    names: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            properties = value.get("properties")
            if isinstance(properties, Mapping):
                method = properties.get("method")
                if isinstance(method, Mapping):
                    enum = method.get("enum")
                    if isinstance(enum, list):
                        names.update(item for item in enum if isinstance(item, str))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    return frozenset(names)


def _property_schemas(root: Path, relative: str) -> dict[str, Any]:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
        properties = value.get("properties", {})
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        raise CapabilityError(
            f"Codex schema is unreadable at {relative}: {exc}"
        ) from exc
    if not isinstance(properties, Mapping):
        raise CapabilityError(f"Codex schema {relative} has no request properties")
    return {str(key): value for key, value in properties.items()}


def _thread_item_types(root: Path) -> frozenset[str]:
    try:
        document = json.loads(
            (root / "v2" / "ItemCompletedNotification.json").read_text(encoding="utf-8")
        )
        variants = document["definitions"]["ThreadItem"]["oneOf"]
        return frozenset(
            item
            for variant in variants
            for item in variant.get("properties", {}).get("type", {}).get("enum", ())
            if isinstance(item, str)
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CapabilityError(f"Codex item schema is unreadable: {exc}") from exc


def _config_shape(root: Path) -> tuple[frozenset[str], bool]:
    try:
        document = json.loads(
            (root / "v2" / "ConfigReadResponse.json").read_text(encoding="utf-8")
        )
        config = document["definitions"]["Config"]
        properties = config["properties"]
        return frozenset(map(str, properties)), config.get(
            "additionalProperties"
        ) is True
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CapabilityError(f"Codex config schema is unreadable: {exc}") from exc


def _workspace_write_fields(root: Path) -> frozenset[str]:
    try:
        document = json.loads(
            (root / "v2" / "TurnStartParams.json").read_text(encoding="utf-8")
        )
        variants = document["definitions"]["SandboxPolicy"]["oneOf"]
        for variant in variants:
            properties = variant.get("properties", {})
            if properties.get("type", {}).get("enum") == ["workspaceWrite"]:
                return frozenset(map(str, properties))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CapabilityError(f"Codex sandbox schema is unreadable: {exc}") from exc
    return frozenset()


def _accepts(
    schema: Any, *, primitive: str | None = None, ref: str | None = None
) -> bool:
    """Conservative shape check for the small request surface we emit."""
    if not isinstance(schema, Mapping):
        return False
    if ref and schema.get("$ref", "").endswith("/" + ref):
        return True
    kind = schema.get("type")
    if primitive and (
        kind == primitive or isinstance(kind, list) and primitive in kind
    ):
        return True
    for key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(key)
        if isinstance(variants, list) and any(
            _accepts(value, primitive=primitive, ref=ref) for value in variants
        ):
            return True
    return False


def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    timeout: float,
    deadline: float | None = None,
) -> str:
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("Codex capability probe timed out")
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **env},
        )
    except subprocess.TimeoutExpired as exc:
        if deadline is not None:
            raise TimeoutError("Codex capability probe timed out") from exc
        raise CapabilityError(
            f"Codex capability probe failed ({' '.join(command)}): {exc}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise CapabilityError(
            f"Codex capability probe failed ({' '.join(command)}): {exc}"
        ) from exc
    return result.stdout


def _feature_inventory(
    executable: str, env: Mapping[str, str], deadline: float | None = None
) -> tuple[dict[str, Any], ...]:
    try:
        output = _run(
            (executable, "features", "list"), env=env, timeout=10, deadline=deadline
        )
    except CapabilityError:
        return ()
    features: list[dict[str, Any]] = []
    for line in output.splitlines():
        match = re.match(r"^(\S+)\s+(.+?)\s+(true|false)$", line.strip())
        if match:
            features.append(
                {
                    "name": match.group(1),
                    "stage": match.group(2).strip().replace(" ", "_"),
                    "enabled": match.group(3) == "true",
                }
            )
    if output.strip() and not features:
        return ()
    return tuple(sorted(features, key=lambda item: item["name"]))


def probe_codex(
    executable: str | os.PathLike[str],
    *,
    env: Mapping[str, str] | None = None,
    state_dir: Path | None = None,
    deadline: float | None = None,
) -> CodexCapabilities:
    """Probe one installed executable, caching by resolved path, size and mtime."""
    environment = {str(k): str(v) for k, v in (env or {}).items()}
    raw = os.fspath(executable)
    located = (
        shutil.which(raw)
        if not Path(raw).is_absolute() and Path(raw).parent == Path(".")
        else None
    )
    try:
        path = Path(located or raw).expanduser().resolve(strict=True)
    except OSError as exc:
        raise CapabilityError(
            f"Codex executable {raw!r} is unavailable: {exc}. "
            "Install Codex or configure codex.path to an executable."
        ) from exc
    stat = path.stat()
    install_key = hashlib.sha256(
        f"{_PROBE_FORMAT}\0{path}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
    ).hexdigest()
    cache_root = (
        state_dir
        or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        / "botpipe"
        / "codex-probes"
    )
    cache_path = cache_root / f"{install_key}.json"
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        capabilities = CodexCapabilities.from_dict(cached)
        if capabilities.executable == str(path):
            return capabilities
    except (OSError, ValueError, KeyError, TypeError):
        pass

    version = _run(
        (str(path), "--version"), env=environment, timeout=10, deadline=deadline
    ).strip()
    if not version:
        raise CapabilityError("Codex --version returned no version")
    features = _feature_inventory(str(path), environment, deadline)
    with tempfile.TemporaryDirectory(prefix="botpipe-codex-schema-") as temporary:
        root = Path(temporary)
        _run(
            (
                str(path),
                "app-server",
                "generate-json-schema",
                "--experimental",
                "--out",
                str(root),
            ),
            env=environment,
            timeout=30,
            deadline=deadline,
        )
        try:
            protocol_bytes = (
                root / "codex_app_server_protocol.schemas.json"
            ).read_bytes()
            protocol = json.loads(protocol_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise CapabilityError(f"Codex protocol schema probe failed: {exc}") from exc
        methods = _method_names(protocol)
        missing_methods = sorted(_CORE_METHODS - methods)
        thread_start = _property_schemas(root, "v2/ThreadStartParams.json")
        thread_resume = _property_schemas(root, "v2/ThreadResumeParams.json")
        turn_start = _property_schemas(root, "v2/TurnStartParams.json")
        item_types = _thread_item_types(root)
        missing_fields: list[str] = []
        for filename, actual, required in (
            ("ThreadStartParams", thread_start, {"cwd", "sandbox", "config"}),
            ("ThreadResumeParams", thread_resume, {"threadId", "cwd", "sandbox"}),
            (
                "TurnStartParams",
                turn_start,
                {"threadId", "input", "sandboxPolicy"},
            ),
        ):
            missing_fields.extend(
                f"{filename}.{name}" for name in sorted(required - actual.keys())
            )
        if missing_methods or missing_fields:
            parts = []
            if missing_methods:
                parts.append("methods: " + ", ".join(missing_methods))
            if missing_fields:
                parts.append("fields: " + ", ".join(missing_fields))
            raise CapabilityError(
                "Codex app-server lacks required protocol " + "; ".join(parts)
            )
        incompatible = []
        checks = (
            ("ThreadStartParams.cwd", thread_start["cwd"], "string", None),
            ("ThreadStartParams.config", thread_start["config"], "object", None),
            (
                "ThreadStartParams.sandbox",
                thread_start["sandbox"],
                "string",
                "SandboxMode",
            ),
            ("ThreadResumeParams.threadId", thread_resume["threadId"], "string", None),
            ("TurnStartParams.threadId", turn_start["threadId"], "string", None),
            ("TurnStartParams.input", turn_start["input"], "array", None),
            (
                "TurnStartParams.sandboxPolicy",
                turn_start["sandboxPolicy"],
                "object",
                "SandboxPolicy",
            ),
        )
        for label, schema, primitive, ref in checks:
            if not _accepts(schema, primitive=primitive, ref=ref):
                incompatible.append(label)
        if incompatible:
            raise CapabilityError(
                "Codex app-server request fields have incompatible shapes: "
                + ", ".join(incompatible)
            )
        config_properties, open_config = _config_shape(root)
        workspace_write_fields = _workspace_write_fields(root)
        schema_digest = hashlib.sha256(protocol_bytes).hexdigest()

    supports_sandbox = "sandboxPolicy" in turn_start
    supports_output = "outputSchema" in turn_start
    supports_dynamic = "dynamicTools" in thread_start
    supports_strict_roots = "writableRoots" in workspace_write_fields
    supports_tool_config = bool(features) and "web_search" in config_properties
    supports_mcp = (
        "mcpServerStatus/list" in methods
        and open_config
        and _accepts(thread_start.get("config"), primitive="object")
        and _accepts(thread_resume.get("config"), primitive="object")
    )
    identity = hashlib.sha256(
        json.dumps(
            {
                "install": install_key,
                "version": version,
                "schema": schema_digest,
                "features": features,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    statuses = {
        "run": CapabilityStatus(
            supports_sandbox and supports_strict_roots,
            None
            if supports_sandbox and supports_strict_roots
            else "per-turn sandbox or strict writable roots are unavailable",
        ),
        "query": CapabilityStatus(
            supports_sandbox and supports_tool_config and supports_mcp,
            None
            if supports_sandbox and supports_tool_config and supports_mcp
            else "read-only sandbox or native tool/MCP controls are unavailable",
        ),
        "generate": CapabilityStatus(
            supports_sandbox and supports_tool_config and supports_mcp,
            None
            if supports_sandbox and supports_tool_config and supports_mcp
            else "exact generation needs per-turn sandbox and native tool/MCP controls",
        ),
    }
    result = CodexCapabilities(
        executable=str(path),
        version=version,
        identity=identity,
        methods=methods,
        features=features,
        supports_turn_sandbox=supports_sandbox,
        supports_interrupt="turn/interrupt" in methods,
        supports_output_schema=supports_output,
        supports_dynamic_tools=supports_dynamic,
        supports_tool_config=supports_tool_config,
        supports_mcp_config=supports_mcp,
        supports_effort="effort" in turn_start,
        supports_instructions=(
            "developerInstructions" in thread_start
            and "developerInstructions" in thread_resume
        ),
        supports_strict_workspace_roots=supports_strict_roots,
        presets=statuses,
        item_types=item_types,
    )
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_temporary = cache_path.with_suffix(".tmp")
        cache_temporary.write_text(
            json.dumps(result.to_dict(), sort_keys=True), encoding="utf-8"
        )
        os.replace(cache_temporary, cache_path)
    except OSError:
        pass
    return result


__all__ = [
    "CapabilityError",
    "CapabilityStatus",
    "CodexCapabilities",
    "probe_codex",
]
