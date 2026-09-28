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
    return Provider().run("swap thumbnail text, feels clickbaity is visible here").value

def test_pause_then_resume(tmp_path):
    client = Botpipe(workspace=tmp_path, provider=FakeProvider([
        ProviderResponse("provider replied", "session-42"), "followup",
    ]))
    paused = client.run(task)
    assert paused.status == "awaiting_input"
    result = client.resume(paused.run_id, workflow=task, answer="swap thumbnail text, feels clickbaity")
    assert result.value == "provider repliedfollowupswap thumbnail text, feels clickbaity"
    other = Botpipe(workspace=tmp_path, provider=FakeProvider(["other result"]))
    assert other.run(unrelated).value == "other result"
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert "test_pause_then_resume — passed" in report
    assert "Your intent?" in report
    assert "swap thumbnail text, feels clickbaity" in report
    assert long_prompt in report
    assert "provider replied" in report and "other result" in report
    assert "Follow trace guidance" in report
    assert "Session key:" in report and "session-42" in report
    assert "Final value:" in report and "provider repliedfollowupswap thumbnail text, feels clickbaity" in report
    assert report.count("Warning: free-text answer not found verbatim") == 1
    assert 'for this run: ["swap thumbnail text, feels clickbaity"]' in report
    assert report.count("Follow trace guidance") == 1
    assert "Instructions: same as block 1." in report
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
    answer = Decision(decision="go", details={"reasons": ["nested detailed rationale", "nested detailed rationale"]})
    assert client.resume(waiting.run_id, workflow=structured, answer=answer).value == "go"
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert report.count("**answer**") == 2
    assert "Nullable?" in report and "Decision?" in report
    assert "null" in report and '"decision": "go"' in report
    assert "nested detailed rationale" in report
    assert report.count("Warning: no later provider prompt was recorded") == 1
    assert 'free-text answers ["nested detailed rationale"]' in report


def test_short_choices_still_recorded_without_free_text_warning(tmp_path):
    source = '''
from botpipe import Botpipe, ask_human, workflow
from botpipe.providers import FakeProvider

@workflow
def choice():
    return ask_human("Choice?")

def test_choices(tmp_path):
    for answer in ("select", "reject_all", "abandon", "two words"):
        workspace = tmp_path / answer
        workspace.mkdir()
        client = Botpipe(workspace=workspace, provider=FakeProvider([]))
        waiting = client.run(choice)
        assert client.resume(waiting.run_id, workflow=choice, answer=answer).value == answer
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert report.count("**answer**") == 4
    for answer in ("select", "reject_all", "abandon", "two words"):
        assert answer in report
    assert "Warning:" not in report


def test_forwarded_answer_and_changed_instructions_with_unset_session_id(tmp_path):
    source = '''
import json
from botpipe import Botpipe, Provider, ask_human, workflow
from botpipe.providers import FakeProvider

@workflow
def forwarded():
    answer = ask_human("What should change?")
    provider = Provider(instructions="Keep every instruction word")
    provider.run("First: " + answer)
    provider.run("Again: " + json.dumps(answer, ensure_ascii=True))
    Provider(instructions="New revised guidance").run("Third prompt with " + answer)
    provider.run("Fourth prompt with " + answer)
    return answer

@workflow
def escaped():
    answer = ask_human("Unicode note?")
    Provider().run("Escaped: " + json.dumps(answer, ensure_ascii=True))
    return answer

def test_forwarded(tmp_path):
    client = Botpipe(workspace=tmp_path, provider=FakeProvider(["first", "second", "third", "fourth"]))
    waiting = client.run(forwarded)
    assert client.resume(
        waiting.run_id, workflow=forwarded, answer="swap thumbnail text, feels clickbaity"
    ).status == "completed"

def test_escaped(tmp_path):
    client = Botpipe(workspace=tmp_path, provider=FakeProvider(["done"]))
    waiting = client.run(escaped)
    assert client.resume(
        waiting.run_id, workflow=escaped, answer="revise the café heading"
    ).status == "completed"
'''
    result, target = _pytest(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    report = target.read_text(encoding="utf-8")
    assert report.count("**prompt**") == 5
    assert report.count("session ID: `None`") == 5
    assert report.count("Keep every instruction word") == 1
    assert report.count("Instructions: same as block 1.") == 2
    assert report.count("New revised guidance") == 1
    assert "Instructions (block 2):" in report
    assert "First: swap thumbnail text, feels clickbaity" in report
    assert "Fourth prompt with swap thumbnail text, feels clickbaity" in report
    assert 'Escaped: "revise the caf\\u00e9 heading"' in report
    assert "Warning:" not in report


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
