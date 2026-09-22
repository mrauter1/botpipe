from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from botpipe.config import ConfigurationError, discover_config, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def _workflow_file(tmp_path: Path) -> Path:
    path = tmp_path / "flows.py"
    path.write_text(
        "from botpipe import activity, ask_human, workflow\n\n"
        "@workflow\n"
        "def echo(message: str) -> str:\n"
        "    return message.upper()\n\n"
        "@workflow\n"
        "def approval() -> str:\n"
        "    return ask_human('Ship it?', returns=str)\n\n"
        "@activity(retry_safe=False)\n"
        "def external_effect() -> str:\n"
        "    raise KeyboardInterrupt()\n\n"
        "@workflow\n"
        "def interrupted() -> str:\n"
        "    return external_effect()\n",
        encoding="utf-8",
    )
    return path


def _cli(
    tmp_path: Path, *arguments: str, expected: int = 0
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT), env.get("PYTHONPATH")))
    )
    completed = subprocess.run(
        [sys.executable, "-m", "botpipe.cli", *arguments, "--workspace", str(tmp_path)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert completed.returncode == expected, completed.stderr
    return completed


def test_cli_subprocess_run_list_show_and_logs(tmp_path: Path) -> None:
    workflow = _workflow_file(tmp_path)
    completed = _cli(
        tmp_path,
        "run",
        f"{workflow}:echo",
        "hello",
        "--task-id",
        "echo-task",
        "--provider",
        "codex",
        "--provider-config",
        '{"command":["codex","exec"]}',
        "--policy",
        '{"network":"none","model":"unit-model"}',
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "completed"
    assert result["value"] == "HELLO"

    listed = json.loads(_cli(tmp_path, "runs", "list", "--task-id", "echo-task").stdout)
    assert [record["run_id"] for record in listed] == [result["run_id"]]

    shown = json.loads(
        _cli(
            tmp_path,
            "runs",
            "show",
            result["run_id"],
            "--provider",
            "codex",
            "--provider-config",
            '{"command":["codex","exec"]}',
            "--policy",
            '{"network":"none","model":"unit-model"}',
        ).stdout
    )
    assert shown["run"]["status"] == "completed"
    assert shown["run"]["provider_config"] == {"command": ["codex", "exec"]}
    assert shown["run"]["policy"] == {"model": "unit-model", "network": "none"}
    assert shown["observed_graph"]["complete_static_topology"] is False
    events = [
        json.loads(line)
        for line in _cli(tmp_path, "runs", "logs", result["run_id"]).stdout.splitlines()
    ]
    assert [event["event"] for event in events] == [
        "execution_revision",
        "execution_revision",
    ]
    assert [event["data"]["phase"] for event in events] == ["start", "end"]


def test_cli_subprocess_answers_human_input(tmp_path: Path) -> None:
    workflow = _workflow_file(tmp_path)
    first = json.loads(_cli(tmp_path, "run", f"{workflow}:approval", expected=4).stdout)
    assert first["status"] == "awaiting_input"
    assert first["pending_input"]["question"] == "Ship it?"

    resumed = json.loads(
        _cli(
            tmp_path,
            "answer",
            first["run_id"],
            first["pending_input"]["operation_id"],
            "yes",
            "--workflow",
            f"{workflow}:approval",
            "--max-operations",
            "1005",
            "--timeout",
            "4000",
        ).stdout
    )
    assert resumed["status"] == "completed"
    assert resumed["value"] == "yes"
    shown = json.loads(_cli(tmp_path, "runs", "show", first["run_id"]).stdout)
    assert shown["run"]["max_operations"] == 1005
    assert shown["run"]["timeout"] == 4000


def test_cli_subprocess_requires_explicit_interrupted_resolution(
    tmp_path: Path,
) -> None:
    workflow = _workflow_file(tmp_path)
    first = json.loads(
        _cli(tmp_path, "run", f"{workflow}:interrupted", expected=5).stdout
    )
    assert first["status"] == "interrupted"
    shown = json.loads(_cli(tmp_path, "runs", "show", first["run_id"]).stdout)
    operation_id = shown["operations"][0]["id"]

    resumed = json.loads(
        _cli(
            tmp_path,
            "resolve",
            first["run_id"],
            operation_id,
            "--response",
            '"already-created"',
            "--workflow",
            f"{workflow}:interrupted",
        ).stdout
    )
    assert resumed["status"] == "completed"
    assert resumed["value"] == "already-created"


def test_config_file_discovery_and_explicit_precedence(tmp_path: Path) -> None:
    config_file = tmp_path / "botpipe.toml"
    config_file.write_text(
        'default_provider = "claude"\ndefault_profile = "review"\nmax_operations = 25\ntimeout = 90\n'
        '[policy]\nnetwork = "none"\n'
        '[providers.claude]\nmodel = "configured"\n'
        '[providers.claude.profiles.review]\neffort = "medium"\n',
        encoding="utf-8",
    )
    assert discover_config(tmp_path) == config_file

    config = load_config(
        tmp_path,
        provider="codex",
        provider_config={"effort": "high"},
        max_operations=30,
    )
    assert config.default_provider == "codex"
    assert config.selection is not None
    assert config.selection.options == {"effort": "high"}
    assert config.policy == {"network": "none"}
    assert config.max_operations == 30
    assert config.timeout == 90

    config_file.write_text("unknown = true\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unknown configuration keys"):
        load_config(tmp_path)


def test_cli_resumes_file_workflow_and_typed_values_in_new_process(tmp_path: Path):
    source = tmp_path / "typed_flow.py"
    source.write_text("""from pathlib import Path
from pydantic import BaseModel
from botpipe import activity, ask_human, current_run, workflow

class Draft(BaseModel):
    title: str

@activity
def prepare():
    path = current_run().workspace / 'effects.txt'
    with path.open('a') as stream:
        stream.write('prepared\\n')
    return Draft(title='Saved typed result')

@workflow
def approval():
    draft = prepare()
    if draft.title in {'first', 'second', 'third', 'fourth', 'fifth'}:
        raise ValueError('Unexpected title')
    answer = ask_human('Approve?', returns=bool)
    return {'title': draft.title, 'approved': answer}
""")
    first = json.loads(_cli(tmp_path, "run", f"{source}:approval", expected=4).stdout)
    assert first["status"] == "awaiting_input"
    resumed = json.loads(
        _cli(
            tmp_path,
            "answer",
            first["run_id"],
            first["pending_input"]["operation_id"],
            "true",
        ).stdout
    )
    assert resumed["status"] == "completed"
    assert resumed["value"] == {"title": "Saved typed result", "approved": True}
    assert (tmp_path / "effects.txt").read_text() == "prepared\n"
