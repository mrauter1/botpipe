"""Transcript plugin integration tests using real pytest sessions."""

import os
import subprocess
import sys
from pathlib import Path

from botpipe.runtime import Botpipe


PLUGIN = "botpipe.workflows.workflow_author.transcript_plugin"
ROOT = Path(__file__).resolve().parents[1]


def _pytest(tmp_path, source, *, transcript=True):
    test_file = tmp_path / "test_generated.py"
    test_file.write_text(source, encoding="utf-8")
    target = tmp_path / "nested" / "trace.md"
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    if transcript:
        env["BOTPIPE_TRANSCRIPT"] = str(target)
    else:
        env.pop("BOTPIPE_TRANSCRIPT", None)
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", PLUGIN, "-q", str(test_file)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40,
    )
    return process, target


def test_records_human_pause_responses_full_prompt_and_run_scoped_warning(tmp_path):
    long_prompt = "begin " + "continuation " * 100 + " end"
    source = '''
from botpipe import Botpipe, Provider, Session, ask_human, workflow
from botpipe.providers import FakeProvider, ProviderResponse

@workflow
def task():
    answer = ask_human("Your intent?")
    provider = Provider(instructions="Follow trace guidance", session=Session.task("trace"))
    first = provider.run("begin " + "continuation " * 100 + " end").value
    second = provider.run("follow-up").value
    return first + second + answer

@workflow
def unrelated():
    return Provider().run("the exact secret phrase is visible here").value

def test_pause_then_resume(tmp_path):
    client = Botpipe(workspace=tmp_path, provider=FakeProvider([
        ProviderResponse("provider replied", "session-42"), "followup",
    ]))
    paused = client.run(task)
    assert paused.status == "awaiting_input"
    result = client.resume(paused.run_id, workflow=task, answer="the exact secret phrase")
    assert result.value == "provider repliedfollowupthe exact secret phrase"
    other = Botpipe(workspace=tmp_path, provider=FakeProvider(["other result"]))
    assert other.run(unrelated).value == "other result"
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert "test_pause_then_resume — passed" in report
    assert "Your intent?" in report
    assert "the exact secret phrase" in report
    assert long_prompt in report
    assert "provider replied" in report and "other result" in report
    assert "Follow trace guidance" in report
    assert "Session key:" in report and "session-42" in report
    assert "Final value:" in report and "provider repliedfollowupthe exact secret phrase" in report
    assert report.count("Warning: free-text answer not found verbatim") == 1
    assert "inspect transformed values/session context" in report


def test_records_genuine_failed_test_and_fake_provider_exception(tmp_path):
    source = '''
from botpipe import Botpipe, Provider, workflow
from botpipe.providers import FakeProvider

@workflow
def task():
    return Provider().run("question").value

def test_failure(tmp_path):
    client = Botpipe(workspace=tmp_path, provider=FakeProvider([RuntimeError("provider exploded")]))
    result = client.run(task)
    assert result.status == "failed"
    assert False, "genuine assertion failure"
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 1, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert "test_failure — failed" in report
    assert "question" in report
    assert "FakeProvider.run" in report and "provider exploded" in report


def test_resume_omitted_none_and_structured_answers(tmp_path):
    source = '''
from typing import Any
from pydantic import BaseModel
from botpipe import Botpipe, ask_human, workflow
from botpipe.providers import FakeProvider

class Decision(BaseModel):
    decision: str
    details: dict[str, list[str]]

@workflow
def nullable():
    return ask_human("Nullable?", returns=Any)

@workflow
def structured():
    return ask_human("Decision?", returns=Decision).decision

def test_answers(tmp_path):
    client = Botpipe(workspace=tmp_path, provider=FakeProvider([]))
    waiting = client.run(nullable)
    assert client.resume(waiting.run_id, workflow=nullable).status == "awaiting_input"
    assert client.resume(waiting.run_id, workflow=nullable, answer=None).status == "completed"
    waiting = client.run(structured)
    answer = Decision(decision="go", details={"reasons": ["nested rationale"]})
    assert client.resume(waiting.run_id, workflow=structured, answer=answer).value == "go"
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert report.count("**answer**") == 2
    assert "Nullable?" in report and "Decision?" in report
    assert "null" in report and '"decision": "go"' in report
    assert "nested rationale" in report
    assert report.count("Warning: no later provider prompt was recorded") == 1


def test_disabled_env_and_patch_lifecycle_between_pytest_main_calls(tmp_path):
    source = '''
def test_simple():
    assert True
'''
    result, target = _pytest(tmp_path, source, transcript=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not target.exists()

    test_file = tmp_path / "test_in_process.py"
    test_file.write_text(source, encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import os, pytest\n"
        "from botpipe.runtime import Botpipe\n"
        "from botpipe.providers import FakeProvider\n"
        "original = (Botpipe.run, Botpipe.resume, FakeProvider.run)\n"
        "assert pytest.main(['-p', '" + PLUGIN + "', '-q', '" + str(test_file) + "']) == 0\n"
        "assert (Botpipe.run, Botpipe.resume, FakeProvider.run) == original\n"
        "os.environ.pop('BOTPIPE_TRANSCRIPT')\n"
        "assert pytest.main(['-p', '" + PLUGIN + "', '-q', '" + str(test_file) + "']) == 0\n"
        "assert (Botpipe.run, Botpipe.resume, FakeProvider.run) == original\n",
        encoding="utf-8",
    )
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    env["BOTPIPE_TRANSCRIPT"] = str(target)
    process = subprocess.run(
        [sys.executable, str(driver)], cwd=tmp_path, env=env,
        text=True, capture_output=True, timeout=40,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert target.exists()
    assert target.read_text(encoding="utf-8").count("test_simple — passed") == 1
