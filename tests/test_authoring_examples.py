from __future__ import annotations

import re
from pathlib import Path

from botpipe import Artifact, Botpipe
from botpipe.providers import FakeProvider


def test_authoring_rework_example_is_runnable_and_uses_separate_sessions(
    tmp_path: Path,
) -> None:
    document = Path("docs/authoring.md").read_text(encoding="utf-8")
    [source] = re.findall(r"```python\n(.*?)```", document, flags=re.DOTALL)
    namespace: dict[str, object] = {}
    # Execute the repository's own example to catch documentation/API drift.
    exec(compile(source, "docs/authoring.md", "exec"), namespace)  # noqa: S102

    provider = FakeProvider(
        [
            {"summary": "first attempt"},
            {"accepted": False, "findings": ["missing test"]},
            {"summary": "fixed", "checks_claimed": ["pytest"]},
            {"accepted": True, "checks_run": ["pytest"]},
        ]
    )
    result = Botpipe(tmp_path, provider=provider).run(
        namespace["implement"],
        "Make the change",
        task_id="authoring-docs",
        run_id="bounded-review",
    )

    assert result.status == "completed"
    assert result.value.accepted is True
    assert [call.preset for call in provider.calls] == ["run"] * 4
    assert provider.calls[0].session_key == provider.calls[2].session_key
    assert provider.calls[1].session_key == provider.calls[3].session_key
    assert provider.calls[0].session_key != provider.calls[1].session_key
    assert "missing test" in provider.calls[2].prompt


def test_sdk_replay_example_resumes_without_another_provider_call(
    tmp_path: Path,
) -> None:
    document = Path("docs/sdk.md").read_text(encoding="utf-8")
    source = re.findall(r"```python\n(.*?)```", document, flags=re.DOTALL)[-1]
    namespace: dict[str, object] = {"tmp_path": tmp_path}

    exec(compile(source, "docs/sdk.md", "exec"), namespace)  # noqa: S102

    backend = namespace["backend"]
    assert isinstance(backend, FakeProvider)
    assert len(backend.calls) == 1


def test_sdk_artifact_key_and_optionality_examples_match_the_api() -> None:
    optional = Artifact.md("evidence-brief.md")
    named = Artifact.md("evidence-brief.md", name="evidence_brief", required=True)

    assert optional.name == "evidence-brief"
    assert optional.required is False
    assert named.name == "evidence_brief"
    assert named.required is True
