"""Native Windows readiness failures stop initialization before agent dispatch."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import botpipe.codex_appserver as appserver
from botpipe.capabilities import CapabilityError, CodexCapabilities


@pytest.mark.parametrize(
    ("platform", "has_method", "status", "blocked"),
    [
        ("nt", True, "ready", False),
        ("nt", True, "notConfigured", True),
        ("nt", True, "updateRequired", True),
        ("nt", True, "unexpected", True),
        ("nt", False, "notConfigured", False),
        ("posix", True, "notConfigured", False),
    ],
)
def test_windows_readiness_precedes_dispatch(
    monkeypatch, platform, has_method, status, blocked
):
    capabilities = CodexCapabilities(
        executable=sys.executable,
        version="fixture",
        identity="fixture",
        methods=frozenset({"windowsSandbox/readiness"} if has_method else ()),
    )
    adapter = appserver.CodexAppServerAdapter(
        sys.executable, capabilities=capabilities
    )
    containment = Mock(creation_kwargs={})
    monkeypatch.setattr(appserver.ProcessContainment, "create", lambda: containment)
    monkeypatch.setattr(appserver.subprocess, "Popen", Mock(return_value=Mock()))
    monkeypatch.setattr(appserver.threading, "Thread", Mock())
    monkeypatch.setattr(appserver, "os", SimpleNamespace(name=platform, environ=os.environ))
    rpc = Mock(return_value={"status": status})
    kill = Mock()
    monkeypatch.setattr(adapter, "_rpc", rpc)
    monkeypatch.setattr(adapter, "_send", Mock())
    monkeypatch.setattr(adapter, "_kill_transport", kill)

    if blocked:
        with pytest.raises(CapabilityError, match="Windows sandbox is not ready"):
            adapter._start()
        kill.assert_called_once()
    else:
        adapter._start()
        kill.assert_not_called()

    expected = ["initialize"]
    if platform == "nt" and has_method:
        expected.append("windowsSandbox/readiness")
        assert rpc.call_args.args[1] is None
    assert [call.args[0] for call in rpc.call_args_list] == expected
