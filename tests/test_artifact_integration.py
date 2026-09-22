"""Artifact durability across the real session and workflow operation ledger."""

from __future__ import annotations

import json
from pathlib import Path

from botpipe import Artifact, Botpipe, Policy, Provider, Worklist, ask_human, workflow
from botpipe.providers import FakeProvider
from botpipe.recovery import Stopped


def test_session_snapshots_raw_binary_reads(tmp_path):
    content = b"\x00\xff\x80raw input"
    source = tmp_path / "input.bin"
    source.write_bytes(content)
    observed = []

    def inspect_request(request):
        declarations = json.loads(
            request.prompt.split("Read these immutable input artifacts:\n")[1]
        )
        observed.append(Path(declarations[0]["path"]).read_bytes())
        return "read"

    @workflow
    def reader():
        return Provider().run("Read input", reads=["input.bin"]).value

    provider = FakeProvider([inspect_request])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(reader)
    assert result.ok, result.error
    assert observed == [content]


def test_relative_raw_reads_resolve_from_effective_provider_workspace(tmp_path):
    target = tmp_path / "candidate"
    target.mkdir()
    (tmp_path / "input.txt").write_text("wrong root")
    (target / "input.txt").write_text("candidate input")
    observed = []

    def inspect_request(request):
        observed.append(request.reads[0].read_text())
        return "read"

    @workflow
    def reader():
        return Provider(session=None).run(
            "Read candidate input",
            workspace=target,
            reads=["input.txt"],
        ).value

    provider = FakeProvider([inspect_request])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(reader)

    assert result.ok, result.error
    assert observed == ["candidate input"]


def test_completed_raw_read_does_not_require_live_file_on_resume(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("initial contents")

    @workflow
    def reader():
        value = Provider().run("Read input", reads=["input.txt"]).value
        ask_human("Continue?")
        return value

    provider = FakeProvider(["read"])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(reader)
        assert paused.status == "awaiting_input", paused.error
        source.unlink()
        resumed = client.resume(paused.run_id, workflow=reader, answers={client.pending(paused.run_id)[0]["operation_id"]: "yes"})
    assert resumed.ok, resumed.error
    assert resumed.value == "read"
    assert len(provider.calls) == 1


def test_raw_read_denied_by_authored_scope_never_dispatches_provider(tmp_path):
    (tmp_path / "secret.txt").write_text("must remain unread")

    @workflow
    def reader():
        return Provider(session=None).generate(
            "Read input",
            reads=["secret.txt"],
            policy=Policy(allow_read=("allowed",)),
        ).value

    provider = FakeProvider(["must not dispatch"])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(reader)

    assert result.status == "failed"
    assert "allow_read" in result.error
    assert provider.calls == []


def test_committed_raw_snapshot_replays_under_tighter_live_read_ceiling(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("initial contents")

    @workflow
    def reader():
        value = Provider(session=None).generate(
            "Read input", reads=["input.txt"]
        ).value
        ask_human("Continue?")
        return value

    provider = FakeProvider(["read"])
    with Botpipe(
        tmp_path,
        provider=provider,
        policy=Policy(allow_read=(".",)),
    ) as first:
        paused = first.run(reader)
        assert paused.status == "awaiting_input", paused.error
        [pending] = first.pending(paused.run_id)

    source.unlink()
    replay_provider = FakeProvider([])
    with Botpipe(
        tmp_path,
        provider=replay_provider,
        policy=Policy(allow_read=()),
    ) as tighter:
        resumed = tighter.resume(
            paused.run_id,
            workflow=reader,
            answers={pending["operation_id"]: "yes"},
        )

    assert resumed.ok, resumed.error
    assert resumed.value == "read"
    assert len(provider.calls) == 1
    assert replay_provider.calls == []


def test_capture_published_before_operation_finish_survives_crash(
    tmp_path, monkeypatch
):
    def write(request):
        request.artifacts["result"].write_text("provider version")
        return "written"

    @workflow
    def writer():
        return (
            Provider()
            .run("Write report", writes=[Artifact.text("result.txt", required=True)])
            .artifacts.result
        )

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        finish = client.journal.finish
        failed_once = []

        def interrupt_after_capture(operation_id, result):
            if (
                client.journal.get(operation_id)["kind"] == "provider"
                and not failed_once
            ):
                failed_once.append(True)
                raise KeyboardInterrupt()
            return finish(operation_id, result)

        monkeypatch.setattr(client.journal, "finish", interrupt_after_capture)
        paused = client.run(writer)
        assert paused.status == "interrupted", paused.error
        # Later mutable output cannot replace the already published capture.
        provider.calls[0].artifacts["result"].write_text("changed after capture")
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.ok, resumed.error
    assert resumed.value.read_text() == "provider version"
    assert len(provider.calls) == 1


def test_provider_response_is_recorded_before_artifact_validation(tmp_path):
    def invalid(request):
        request.artifacts["result"].write_text("not json")
        return "raw provider reply"

    @workflow
    def writer():
        return Provider().run(
            "Write JSON",
            writes=[Artifact.json("result.json", required=True)],
            output_retries=0,
        )

    with Botpipe(tmp_path, provider=FakeProvider([invalid])) as client:
        failed = client.run(writer)
        operations = client.inspect(failed.run_id)["operations"]
    assert failed.status == "failed"
    provider_row = next(row for row in operations if row["kind"] == "provider")
    assert provider_row["response"]["text"] == "raw provider reply"
    assert provider_row["status"] == "failed"


def test_explicit_provider_retry_requires_new_artifact_outputs(tmp_path):
    class ConfirmedStoppedProvider(FakeProvider):
        def recover(self, request):
            return Stopped("the interrupted fake attempt is confirmed stopped")

    def uncertain(request):
        request.artifacts["result"].write_text("uncertain old attempt")
        raise KeyboardInterrupt()

    @workflow
    def writer():
        return Provider().run(
            "Write report",
            writes=[Artifact.text("result.txt", required=True)],
            output_retries=0,
        )

    provider = ConfirmedStoppedProvider([uncertain, "retry forgot its file"])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer)
        assert paused.status == "interrupted", paused.error
        operation = next(
            row
            for row in client.inspect(paused.run_id)["operations"]
            if row["kind"] == "provider"
        )
        client.resolve(paused.run_id, operation["id"], retry=True)
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.status == "failed"
    assert "Required artifact was not written" in resumed.error
    assert len(provider.calls) == 2


def test_worklist_alias_and_latest_artifact_are_visible_after_resume(tmp_path):
    def write_plan(request):
        request.artifacts["work"].write_text(
            json.dumps(
                {
                    "items": [
                        {"id": "a", "title": "First", "status": "pending"},
                        {"id": "b", "title": "Second", "status": "pending"},
                    ]
                }
            )
        )
        return "planned"

    @workflow
    def plan():
        response = Provider().run(
            "Create work", writes=[Artifact.json("work.json", required=True)]
        )
        work = Worklist.from_artifact(response.artifacts.work)
        for item in work:
            work.complete(item)
            if item.id == "a":
                ask_human("Continue?")
        return work.artifact

    provider = FakeProvider([write_plan])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(plan)
        assert paused.status == "awaiting_input", paused.error
        source = provider.calls[0].artifacts["work"]
        assert [item["status"] for item in json.loads(source.read_text())["items"]] == [
            "completed",
            "pending",
        ]
        resumed = client.resume(paused.run_id, workflow=plan, answers={client.pending(paused.run_id)[0]["operation_id"]: "yes"})
        inspected = client.inspect(paused.run_id)
    assert resumed.ok, resumed.error
    assert [item["status"] for item in resumed.value.read_json()["items"]] == [
        "completed",
        "completed",
    ]
    assert json.loads(source.read_text()) == resumed.value.read_json()
    assert any(
        handle.digest == resumed.value.digest for handle in resumed.artifacts.values()
    )
    assert any(
        record["digest"] == resumed.value.digest
        for record in inspected["artifacts"].values()
    )
    assert len(provider.calls) == 1


def test_raw_read_publication_recovers_before_ledger_finish(tmp_path, monkeypatch):
    source = tmp_path / "input.txt"
    source.write_text("original observation")
    observed = []

    def inspect_request(request):
        declarations = json.loads(
            request.prompt.split("Read these immutable input artifacts:\n")[1]
        )
        observed.append(Path(declarations[0]["path"]).read_text())
        return "read"

    @workflow
    def reader():
        return Provider().run("Read input", reads=["input.txt"]).value

    provider = FakeProvider([inspect_request])
    with Botpipe(tmp_path, provider=provider) as client:
        finish = client.journal.finish
        interrupted = []

        def interrupt_read(operation_id, result):
            if client.journal.get(operation_id)["kind"] == "read" and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt()
            return finish(operation_id, result)

        monkeypatch.setattr(client.journal, "finish", interrupt_read)
        paused = client.run(reader)
        assert paused.status == "interrupted", paused.error
        source.unlink()
        resumed = client.resume(paused.run_id, workflow=reader)
    assert resumed.ok, resumed.error
    assert observed == ["original observation"]
    assert len(provider.calls) == 1


def test_parallel_isolated_artifacts_recover_independently(tmp_path, monkeypatch):
    from botpipe import parallel

    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "input.txt").write_text("shared observation")
    (right / "input.txt").write_text("shared observation")

    def write(request):
        request.artifacts["report"].write_text(request.workspace.name)
        return "written"

    @workflow
    def writer():
        return parallel(
            lambda: (
                Provider()
                .run(
                    "Write left",
                    workspace=left,
                    reads=["input.txt"],
                    writes=[Artifact.text("report.txt", required=True)],
                )
                .artifacts.report
            ),
            lambda: (
                Provider()
                .run(
                    "Write right",
                    workspace=right,
                    reads=["input.txt"],
                    writes=[Artifact.text("report.txt", required=True)],
                )
                .artifacts.report
            ),
        )

    provider = FakeProvider([write, write])
    with Botpipe(tmp_path, provider=provider) as client:
        finish = client.journal.finish
        interrupted = []

        def interrupt_first_provider(operation_id, result):
            if (
                client.journal.get(operation_id)["kind"] == "provider"
                and not interrupted
            ):
                interrupted.append(True)
                raise KeyboardInterrupt()
            return finish(operation_id, result)

        monkeypatch.setattr(client.journal, "finish", interrupt_first_provider)
        paused = client.run(writer)
        assert paused.status == "interrupted", paused.error
        assert len(provider.calls) == 2
        (left / "input.txt").unlink()
        (right / "input.txt").unlink()
        for request in provider.calls:
            request.artifacts["report"].unlink()
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.ok, resumed.error
    assert [handle.read_text() for handle in resumed.value] == ["left", "right"]
    assert len(provider.calls) == 2
    assert resumed.value[0].path != resumed.value[1].path
