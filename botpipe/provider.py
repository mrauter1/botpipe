"""Configured provider operations with explicit, managed conversation continuity."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Mapping, Self, TypeVar, overload

from .errors import BotpipeError
from .models import Result
from .policy import Policy
from .prompts import Prompt
from .runtime import Botpipe, _CURRENT, _async_call, current_run, workflow
from .sessions import Session

if TYPE_CHECKING:
    from .decisions import DecisionAnswer, DecisionQuestion
    from .streaming import Stream

_INHERIT = object()
_DEFAULT = object()
T = TypeVar("T")
_CONFIG_FIELDS = frozenset({
    "instructions", "model", "effort", "workspace", "policy", "name",
    "timeout", "output_retries", "allow_commands", "settings",
})


def _freeze(value):
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Configuration keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, Path)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"Unsupported configuration value: {type(value).__name__}")


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _configuration(values):
    from .config import validate_non_secret_settings

    unknown = values.keys() - _CONFIG_FIELDS
    if unknown:
        raise TypeError(f"Unknown provider settings: {', '.join(sorted(unknown))}")
    values = dict(values)
    if "policy" in values:
        policy = values["policy"]
        values["policy"] = policy.to_dict() if isinstance(policy, Policy) else Policy.from_dict(policy).to_dict()
    if "allow_commands" in values:
        commands = values["allow_commands"]
        if isinstance(commands, (str, bytes)) or commands is None:
            raise TypeError("allow_commands must contain exact argv sequences")
        commands = tuple(commands)
        for command in commands:
            if isinstance(command, (str, bytes)) or not command or any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in command):
                raise ValueError("Each command grant must be a nonempty argument vector")
        values["allow_commands"] = tuple(tuple(command) for command in commands)
    retries = values.get("output_retries", 2)
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise ValueError("output_retries must be a nonnegative integer")
    timeout = values.get("timeout")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout must be finite and positive")
    for key in ("instructions", "model", "effort", "name"):
        if values.get(key) is not None and not isinstance(values[key], str):
            raise TypeError(f"{key} must be a string or None")
    validate_non_secret_settings(values)
    return _freeze(values)


@dataclass(eq=False)
class _Family:
    backend: str | None = None
    selected: dict | None = None
    runtime: Any = None
    lock: threading.RLock = field(default_factory=threading.RLock)


@dataclass
class _Conversation:
    value: Any = _DEFAULT
    lock: threading.Lock = field(default_factory=threading.Lock)


class Provider:
    """A lazily selected backend, immutable defaults, and a managed session.

    Reusing a provider continues its conversation. ``session=None`` makes calls
    independent; ``with_config`` retains the existing session unless replaced.
    """
    _backend: str | None = None

    def __init__(self, *, runtime: Botpipe | None = None, session=_INHERIT, **config: Any) -> None:
        if runtime is not None and not isinstance(runtime, Botpipe):
            raise TypeError("runtime must be a Botpipe instance")
        if session is not _INHERIT and session is not None and not isinstance(session, Session):
            raise TypeError("session must be a Session or None")
        self._runtime = runtime
        self._family = _Family(self._backend)
        self._conversation = _Conversation(_DEFAULT if session is _INHERIT else session)
        self._explicit_session = session is not _INHERIT
        self._config = _configuration(config)

    @property
    def config(self) -> Mapping[str, Any]:
        return self._config

    @property
    def session(self) -> Session | None:
        value = self._conversation.value
        return None if value is _DEFAULT else value

    @property
    def backend(self) -> str | None:
        return self._family.selected["name"] if self._family.selected else self._family.backend

    def with_config(self, *, session=_INHERIT, **changes: Any) -> Self:
        normalized = _configuration(changes)
        values = {**_plain(self._config), **_plain(normalized)}
        # Policy derivation must retain every enclosing restriction.
        if "policy" in changes:
            values["policy"] = Policy.resolve(self._config.get("policy"), changes["policy"]).to_dict()
        variant = object.__new__(type(self))
        variant._runtime = self._runtime
        variant._family = self._family
        variant._config = _configuration(values)
        variant._explicit_session = self._explicit_session if session is _INHERIT else True
        if session is _INHERIT:
            variant._conversation = self._conversation
        else:
            if session is not None and not isinstance(session, Session):
                raise TypeError("session must be a Session or None")
            variant._conversation = _Conversation(session)
        return variant

    def _runtime_for_call(self):
        ctx = _CURRENT.get()
        if ctx is not None:
            if self._runtime is not None and self._runtime is not ctx.client:
                raise BotpipeError("The provider is attached to another runtime; use the active runtime or an unattached provider")
            return ctx.client
        if self._runtime is not None:
            return self._runtime
        with self._family.lock:
            if self._family.runtime is None:
                from .config import load_config
                self._family.runtime = Botpipe(**load_config(self._config.get("workspace", ".")).client_kwargs())
            return self._family.runtime

    def _selection(self, runtime):
        from .config import ConfigurationError
        ctx = _CURRENT.get()
        family = self._family
        with family.lock:
            def choose():
                if family.selected is not None:
                    return dict(family.selected)
                recorded = ctx.journal.run(ctx.run_id) if ctx is not None else {}
                default_name = recorded.get("provider", runtime.provider_name)
                name = family.backend or default_name
                if not name:
                    raise ConfigurationError("No default provider configured; set default_provider in botpipe.toml or use an explicit provider constructor")
                config = dict(recorded.get("provider_config", runtime.provider_config)) if name == default_name else {}
                defaults = dict(recorded.get("provider_defaults", getattr(runtime, "provider_defaults", {}))) if name == default_name else {}
                return {"name": name, "config": config, "defaults": defaults}
            if ctx is not None:
                bindings = ctx._provider_family_bindings
                if family not in bindings:
                    bindings[family] = ctx.operation("provider_binding", {"backend": family.backend}, choose, retry_safe=True)
                selected = bindings[family]
            else:
                selected = choose()
            if family.selected is not None and family.selected != selected:
                raise BotpipeError("Provider family selection differs from the recorded backend; construct a new provider")
            family.selected = dict(selected)
            return runtime.resolve_adapter(selected["name"], selected["config"]), selected

    def _session_for_call(self, adapter, override):
        supports = getattr(getattr(adapter, "capabilities", None), "sessions", True)
        if not supports:
            if override is not _INHERIT or self._explicit_session:
                from .providers import CapabilityError
                raise CapabilityError(f"{adapter.name} does not support session arguments")
            return None
        if override is not _INHERIT:
            if override is not None and not isinstance(override, Session):
                raise TypeError("session must be a Session or None")
            return override
        with self._conversation.lock:
            if self._conversation.value is _DEFAULT:
                self._conversation.value = Session()
            return self._conversation.value

    def _invoke(self, operation, prompt=None, *, session=_INHERIT, **options):
        runtime = self._runtime_for_call()
        adapter, selection = self._selection(runtime)
        if operation == "decide":
            from .providers import CapabilityError
            if session is not _INHERIT or self._explicit_session:
                raise CapabilityError("Typed decisions do not support session arguments")
            if not getattr(getattr(adapter, "capabilities", None), "decisions", False):
                raise CapabilityError(f"{adapter.name} does not support typed decisions")
            selected_session = None
        else:
            selected_session = self._session_for_call(adapter, session)
        call_config = {key: options.pop(key) for key in tuple(options) if key in _CONFIG_FIELDS}
        defaults = selection.get("defaults", {})
        profile = {key: defaults[key] for key in ("model", "effort", "instructions") if defaults.get(key) is not None}
        if operation == "generate":
            profile["allow_commands"] = defaults.get("generate_allow_commands", ())
        profile_policy = {}
        if operation == "query" and defaults.get("query_read_roots") is not None:
            profile_policy["allow_read"] = defaults["query_read_roots"]
        config = {**profile, **_plain(self._config), **_plain(_configuration(call_config))}
        if operation == "decide":
            unsupported = config.keys() - {"model", "settings", "timeout", "name"}
            if unsupported:
                from .providers import CapabilityError
                raise CapabilityError(f"Typed decisions do not accept: {', '.join(sorted(unsupported))}")
            if "model" in config:
                config["settings"] = {**config.get("settings", {}), "model": config.pop("model")}
        else:
            config["policy"] = Policy.resolve(Policy.resolve(profile_policy, self._config.get("policy")), call_config.get("policy")).to_dict()
            for key in ("model", "effort"):
                if key in config:
                    config["policy"][key] = config.pop(key)
        spec = {"selection": selection, "session": selected_session, "operation": operation, "prompt": prompt, "options": {**config, **options}}
        if _CURRENT.get() is not None:
            return _execute_spec(spec, adapter=adapter)
        result = runtime.run(_standalone_operation, spec)
        if result.ok:
            return result.value
        failure = result.exception or BotpipeError(result.error or f"Provider operation is {result.status}")
        failure.run_id = result.run_id
        if not getattr(failure, "operation_id", None):
            operations = runtime.journal.operations(result.run_id)
            failure.operation_id = operations[-1]["id"] if operations else None
        raise failure

    @overload
    def generate(self, prompt: str | Prompt, *, returns: type[T], **options: Any) -> Result[T]: ...

    @overload
    def generate(self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any) -> Result[str]: ...

    def generate(self, prompt, *, input=None, reads=(), returns=str, session=_INHERIT, allow_commands=_INHERIT, **options):
        if "writes" in options:
            raise TypeError("generate() cannot declare writes; use run()")
        if allow_commands is not _INHERIT:
            options["allow_commands"] = allow_commands
        return self._invoke("generate", prompt, input=input, reads=reads, returns=returns, session=session, **options)

    @overload
    def query(self, prompt: str | Prompt, *, returns: type[T], **options: Any) -> Result[T]: ...

    @overload
    def query(self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any) -> Result[str]: ...

    def query(self, prompt, *, input=None, reads=(), returns=str, session=_INHERIT, **options):
        if "writes" in options or "allow_commands" in options:
            raise TypeError("query() does not accept writes or generation command grants")
        return self._invoke("query", prompt, input=input, reads=reads, returns=returns, session=session, **options)

    @overload
    def run(self, prompt: str | Prompt, *, returns: type[T], **options: Any) -> Result[T]: ...

    @overload
    def run(self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any) -> Result[str]: ...

    def run(self, prompt, *, input=None, reads=(), writes=(), returns=str, session=_INHERIT, **options):
        if "allow_commands" in options:
            raise TypeError("run() uses its execution policy, not generation command grants")
        return self._invoke("run", prompt, input=input, reads=reads, writes=writes, returns=returns, session=session, **options)

    def decide(self, *, state: Any, questions: Mapping[str, DecisionQuestion], **options: Any) -> Result[dict[str, DecisionAnswer]]:
        return self._invoke("decide", state=state, questions=questions, **options)

    @overload
    async def agenerate(self, prompt: str | Prompt, *, returns: type[T], **options: Any) -> Result[T]: ...

    @overload
    async def agenerate(self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any) -> Result[str]: ...

    async def agenerate(self, prompt, **options):
        return await _async_call(self.generate, prompt, **options)

    @overload
    async def aquery(self, prompt: str | Prompt, *, returns: type[T], **options: Any) -> Result[T]: ...

    @overload
    async def aquery(self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any) -> Result[str]: ...

    async def aquery(self, prompt, **options):
        return await _async_call(self.query, prompt, **options)

    @overload
    async def arun(self, prompt: str | Prompt, *, returns: type[T], **options: Any) -> Result[T]: ...

    @overload
    async def arun(self, prompt: str | Prompt, *, returns: type[str] = str, **options: Any) -> Result[str]: ...

    async def arun(self, prompt, **options):
        return await _async_call(self.run, prompt, **options)

    async def adecide(self, *, state: Any, questions: Mapping[str, DecisionQuestion], **options: Any) -> Result[dict[str, DecisionAnswer]]:
        return await _async_call(self.decide, state=state, questions=questions, **options)

    @overload
    def stream(self, prompt: str | Prompt, *, operation: Literal["generate", "query", "run"], returns: type[T], **options: Any) -> Stream[T]: ...

    @overload
    def stream(self, prompt: str | Prompt, *, operation: Literal["generate", "query", "run"], returns: type[str] = str, **options: Any) -> Stream[str]: ...

    def stream(self, prompt, *, operation, **options):
        if operation not in ("generate", "query", "run"):
            raise ValueError("stream operation must be generate, query, or run")
        from .streaming import start_stream

        runtime = self._runtime_for_call()
        return start_stream(
            self, prompt, operation=operation, options=options,
            cancel=lambda run_id, operation_id: runtime.cancel(run_id, operation_id),
        )

    @overload
    def astream(self, prompt: str | Prompt, *, operation: Literal["generate", "query", "run"], returns: type[T], **options: Any) -> Stream[T]: ...

    @overload
    def astream(self, prompt: str | Prompt, *, operation: Literal["generate", "query", "run"], returns: type[str] = str, **options: Any) -> Stream[str]: ...

    def astream(self, prompt, *, operation, **options):
        return self.stream(prompt, operation=operation, **options)

    def close(self) -> None:
        """Release this family's owned runtime, retaining its durable evidence.

        Derived configurations share ownership. An explicitly supplied runtime
        remains the caller's responsibility.
        """
        with self._family.lock:
            runtime = self._family.runtime
            if runtime is not None:
                runtime.close()
                self._family.runtime = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_) -> None:
        self.close()


class Codex(Provider):
    _backend = "codex"


class ClaudeCode(Provider):
    _backend = "claude"


class Pi(Provider):
    _backend = "pi"


class Jev(Provider):
    _backend = "jev"


def _execute_spec(spec, *, adapter=None):
    from .operations import execute_provider
    ctx = current_run()
    selected = spec["selection"]
    if adapter is None:
        adapter = ctx.client.resolve_adapter(selected["name"], selected["config"])
    if spec["operation"] == "decide":
        from .operations import execute_decision
        return execute_decision(adapter, provider_config=selected["config"], **spec["options"])
    options = dict(spec["options"])
    if spec["operation"] != "generate":
        options.pop("allow_commands", None)
    return execute_provider(
        adapter, spec["session"], spec["prompt"], operation=spec["operation"],
        affinity={
            "provider_config": selected["config"],
            "profile": selected.get("defaults", {}).get("profile"),
        },
        **options,
    )


@workflow(name="botpipe.operation")
def _standalone_operation(spec):
    return _execute_spec(spec)
