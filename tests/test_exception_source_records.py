from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def _run(script: Path, source_root: Path):
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(source_root), str(Path(__file__).resolve().parents[1]))
        ),
    }
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_exception_class_source_drift_blocks_before_answer_checkpoint(tmp_path):
    (tmp_path / "workspace").mkdir()
    package = tmp_path / "owned"
    package.mkdir()
    (package / "__init__.py").write_text("")
    errors = package / "errors.py"
    errors.write_text(
        "class Failure(Exception):\n"
        "    @property\n"
        "    def outcome(self): return 'original'\n"
    )
    (package / "workflow.py").write_text(
        "from botpipe import activity, ask, workflow\n"
        "@activity\n"
        "def fail():\n"
        "    from owned.errors import Failure\n"
        "    raise Failure('failed')\n"
        "@workflow\n"
        "def job():\n"
        "    try: fail()\n"
        "    except Exception as error:\n"
        "        ask('continue?')\n"
        "        return error.outcome\n"
    )
    start = tmp_path / "start.py"
    start.write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe('workspace', provider=FakeProvider([])) as client:\n"
        "    print(client.run(job, run_id='source').status)\n"
    )
    resume = tmp_path / "resume.py"
    resume.write_text(
        "from botpipe import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "from owned.workflow import job\n"
        "with Botpipe('workspace', provider=FakeProvider([])) as client:\n"
        "    client.resume('source', workflow=job, answer='yes')\n"
    )

    first = _run(start, tmp_path)
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "awaiting_input"
    errors.write_text(errors.read_text().replace("'original'", "'edited'"))

    replay = _run(resume, tmp_path)
    assert replay.returncode != 0
    assert "ReplayMismatch" in replay.stderr
    assert "Source for durable type owned.errors:Failure changed" in replay.stderr

    db = sqlite3.connect(tmp_path / "workspace" / ".botpipe" / "state.sqlite3")
    response = db.execute(
        "SELECT response FROM operations WHERE run_id='source' AND kind='input'"
    ).fetchone()[0]
    db.close()
    assert "answer" not in json.loads(response)


def test_exception_and_inherited_slot_owner_have_type_source_records(tmp_path):
    from botpipe import Botpipe, activity, workflow
    from botpipe.providers import FakeProvider

    class BaseFailure(Exception):
        __slots__ = ("code",)

        def __init__(self, code):
            self.code = code
            super().__init__("failed")

    class Failure(BaseFailure):
        pass

    @activity
    def fail():
        raise Failure(7)

    @workflow
    def job():
        fail()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        failed = client.run(job, run_id="exception-record")
        assert failed.status == "failed"
        error = client.journal.operations(failed.run_id)[0]["error"]

    assert error["exception_type"]["$botpipe"] == "capsule"
    assert error["exception_type"]["value"]["$botpipe"] == "type"
    slot = next(item for item in error["slots"] if item["name"] == "code")
    assert slot["owner_type"]["$botpipe"] == "capsule"
    assert slot["owner_type"]["value"]["$botpipe"] == "type"


@pytest.mark.parametrize("missing", [True, False])
def test_missing_exception_type_evidence_blocks_before_writes(tmp_path, missing):
    from botpipe import Botpipe, activity, ask, workflow
    from botpipe.errors import ActivityFailed, ReplayMismatch
    from botpipe.providers import FakeProvider

    class LegacyFailure(Exception):
        def __init__(self):
            self.unsupported = object()
            super().__init__("legacy")

    @activity
    def fail():
        raise LegacyFailure()

    @workflow
    def job():
        try:
            fail()
        except ActivityFailed:
            ask("continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="missing-evidence")
        operations = client.journal.operations(paused.run_id)
        failed = next(record for record in operations if record["status"] == "failed")
        waiting = next(record for record in operations if record["status"] == "waiting")
        error = failed["error"]
        if missing:
            error.pop("exception_type")
        else:
            error["exception_type"] = None
        with client.journal.transaction() as db:
            db.execute(
                "UPDATE operations SET error=? WHERE id=?",
                (json.dumps(error), failed["id"]),
            )
        before_run = client.journal.run(paused.run_id)
        before_response = client.journal.get(waiting["id"])["response"]

        with pytest.raises(ReplayMismatch, match="exception type"):
            client.resume(
                paused.run_id, workflow=job, answer="yes", max_operations=2000
            )

        assert client.journal.run(paused.run_id) == before_run
        assert client.journal.get(waiting["id"])["response"] == before_response
