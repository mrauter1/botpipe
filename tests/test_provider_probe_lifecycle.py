from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from botpipe.capabilities import CapabilityStatus, CodexCapabilities
from botpipe.policy import Policy
from botpipe.providers import CodexProvider, ProviderRequest, ProviderTimeoutError


def _request(tmp_path: Path, *, deadline: float | None = None) -> ProviderRequest:
    return ProviderRequest(
        operation_id="attempt",
        operation_key="logical",
        prompt="work",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(),
        artifacts={},
        timeout=1,
        deadline=deadline,
    )


class StrictAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.disposed = False
        self.probes = 0
        self.dispose_error: str | None = None
        self.capabilities = CodexCapabilities(
            executable=sys.executable,
            version="fixture",
            identity=name,
            methods=frozenset(),
            presets={
                preset: CapabilityStatus(True)
                for preset in ("run", "query", "generate")
            },
        )

    def probe(self, *, deadline=None):
        if self.disposed:
            raise AssertionError("disposed adapter was reused")
        self.probes += 1
        return self.capabilities

    def dispose(self) -> None:
        if self.dispose_error is not None:
            raise RuntimeError(self.dispose_error)
        self.disposed = True

    def close(self) -> None:
        self.disposed = True


def test_successive_factory_owners_do_not_reuse_disposed_probe_adapter(tmp_path: Path) -> None:
    created: list[StrictAdapter] = []

    def factory() -> StrictAdapter:
        adapter = StrictAdapter(f"adapter-{len(created)}")
        created.append(adapter)
        return adapter

    provider = CodexProvider(adapter_factory=factory)
    request = _request(tmp_path)

    for expected in range(3):
        assert provider.validate_request(request).identity == f"adapter-{expected}"
        owner = provider._adapter_for(request)
        assert owner is created[expected]
        provider.release_operation("logical")

    assert len(created) == 3
    assert all(adapter.disposed for adapter in created)
    assert provider._probe_adapter is None
    assert provider._factory_probe_available is False


def test_direct_probe_is_serialized_with_owner_disposal(tmp_path: Path) -> None:
    probe_started = threading.Event()
    finish_probe = threading.Event()
    dispose_started = threading.Event()

    class BlockingAdapter(StrictAdapter):
        def probe(self, *, deadline=None):
            result = super().probe(deadline=deadline)
            if self.probes == 2:
                probe_started.set()
                assert finish_probe.wait(5)
                assert not self.disposed
            return result

        def dispose(self) -> None:
            dispose_started.set()
            super().dispose()

    adapter = BlockingAdapter("adapter-0")
    provider = CodexProvider(adapter_factory=lambda: adapter)
    request = _request(tmp_path)
    provider.validate_request(request)
    assert provider._adapter_for(request) is adapter

    probe_errors: list[BaseException] = []
    release_errors: list[BaseException] = []

    def probe() -> None:
        try:
            provider.probe()
        except BaseException as exc:
            probe_errors.append(exc)

    def release() -> None:
        try:
            provider.release_operation("logical")
        except BaseException as exc:
            release_errors.append(exc)

    probe_thread = threading.Thread(target=probe)
    release_thread = threading.Thread(target=release)
    probe_thread.start()
    assert probe_started.wait(5)
    release_thread.start()
    assert not dispose_started.wait(0.1)
    finish_probe.set()
    probe_thread.join(5)
    release_thread.join(5)

    assert not probe_thread.is_alive()
    assert not release_thread.is_alive()
    assert probe_errors == []
    assert release_errors == []
    assert adapter.disposed


def test_validate_request_deadline_includes_owner_lock_wait(tmp_path: Path) -> None:
    adapter = StrictAdapter("adapter")
    provider = CodexProvider(adapter=adapter)
    request = _request(tmp_path, deadline=time.monotonic() + 0.05)
    errors: list[BaseException] = []

    provider._owner_lock.acquire()
    try:
        worker = threading.Thread(
            target=lambda: _capture_error(errors, provider.validate_request, request)
        )
        worker.start()
        worker.join(2)
    finally:
        provider._owner_lock.release()

    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], ProviderTimeoutError)
    assert "capability probe timed out" in str(errors[0])
    assert adapter.probes == 0


def test_failed_disposal_keeps_factory_owner_and_probe_reference(tmp_path: Path) -> None:
    adapter = StrictAdapter("adapter")
    adapter.dispose_error = "cleanup unverified"
    provider = CodexProvider(adapter_factory=lambda: adapter)
    request = _request(tmp_path)

    provider.validate_request(request)
    assert provider._adapter_for(request) is adapter
    with pytest.raises(RuntimeError, match="cleanup unverified"):
        provider.release_operation("logical")

    assert provider._owners["logical"] is adapter
    assert provider._probe_adapter is adapter
    assert provider._factory_probe_available is False
    assert provider.validate_request(request) is adapter.capabilities


def _capture_error(errors, function, *args) -> None:
    try:
        function(*args)
    except BaseException as exc:
        errors.append(exc)
