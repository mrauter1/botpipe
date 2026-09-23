"""Prompt origin follows application composition, including SDK-only branches."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import botpipe


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("callback", ["lambda", "partial"])
def test_parallel_prompt_uses_nearest_application_source(tmp_path, nested, callback):
    for package in ("application", "child"):
        (tmp_path / package).mkdir()
        (tmp_path / package / "__init__.py").write_text("")
    (tmp_path / "prompt.md").write_text("wrong workspace prompt")
    (tmp_path / "application/prompt.md").write_text("application prompt")
    (tmp_path / "child/prompt.md").write_text("child prompt")
    expression = (
        'lambda: session.run(Prompt.file("prompt.md"), sandbox="read-only")'
        if callback == "lambda"
        else 'partial(session.run, Prompt.file("prompt.md"), sandbox="read-only")'
    )
    body = (
        "from functools import partial\n"
        "from botpipe import Policy, Prompt, Provider, Session, parallel, workflow\n"
        "@workflow\n"
        "def job():\n"
        "    session = Provider()\n"
        ""
        f"    return parallel({expression})[0].value\n"
    )
    source = "child" if nested else "application"
    (tmp_path / source / "workflow.py").write_text(body)
    if nested:
        (tmp_path / "application/workflow.py").write_text(
            "from botpipe import workflow\n"
            "from child.workflow import job as child\n"
            "@workflow\n"
            "def job(): return child()\n"
        )
    script = tmp_path / "run.py"
    script.write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from application.workflow import job\n"
        "provider = FakeProvider(['done'])\n"
        "with Botpipe('.', provider=provider) as client:\n"
        "    result = client.run(job)\n"
        "    assert result.ok, result.error\n"
        "    assert result.value == 'done'\n"
        f"    assert provider.calls[0].prompt == {source + ' prompt'!r}\n"
        "    replay = client.resume(result.run_id, workflow=job)\n"
        "    assert replay.ok, replay.error\n"
        "    assert replay.value == 'done'\n"
        "    assert len(provider.calls) == 1\n"
    )
    sdk = Path(botpipe.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(sdk), str(tmp_path)))}
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
