import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from botpipe.native_tools import ToolObservation
from botpipe.tool_evidence import ToolEvidence, ToolEvidenceError


def request(tmp_path, *, attempt=1):
    return SimpleNamespace(receipt_dir=tmp_path, operation_id="op/../one", attempt=attempt)


def test_manifest_is_exact_immutable_and_reusable_before_dispatch(tmp_path):
    first = ToolEvidence(request(tmp_path), "pinned-v1")
    manifest = first.prepare({"grant-1": {"grant_id": "one", "argv": ["git", "status"]}})
    expected = manifest.read_bytes()
    second = ToolEvidence(request(tmp_path), "pinned-v1")
    second.prepare([{"argv": ["git", "status"], "grant_id": "one"}])
    assert manifest.read_bytes() == expected
    with pytest.raises(ToolEvidenceError, match="manifest changed"):
        second.prepare([])
    assert manifest.read_bytes() == expected


def test_receipts_survive_new_recorder_and_prevent_attempt_restart(tmp_path):
    evidence = ToolEvidence(request(tmp_path), "pinned-v1")
    evidence.prepare()
    observation = ToolObservation("read", {"path": "a.txt"}, "exact output",
                                  identity={"sha256": "abc"})
    path = evidence.record(observation)
    record = json.loads(path.read_text())
    assert record["observation"] == observation.to_record()
    assert record["operation_id"] == "op/../one"
    assert record["attempt"] == 1 and record["sequence"] == 1
    assert record["profile"] == "pinned-v1" and record["timestamp"]
    evidence.prepare()  # The active recorder can recheck its manifest.
    with pytest.raises(ToolEvidenceError, match="requires native recovery"):
        ToolEvidence(request(tmp_path), "pinned-v1").prepare()
    ToolEvidence(request(tmp_path, attempt=2), "pinned-v1").prepare()
    assert path.read_text() and len(list(tmp_path.iterdir())) == 2


def test_concurrent_observations_have_unique_contiguous_receipts(tmp_path):
    evidence = ToolEvidence(request(tmp_path), "pinned-v1")
    evidence.prepare()
    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(lambda i: evidence.record(
            ToolObservation("read", {"index": i}, str(i))), range(24)))
    records = [json.loads(path.read_text()) for path in paths]
    assert sorted(item["sequence"] for item in records) == list(range(1, 25))
    assert {item["observation"]["output"] for item in records} == {str(i) for i in range(24)}
    assert not list(evidence.directory.glob(".pending-*"))


def test_budgets_and_write_failure_block_delivery_without_overwriting(tmp_path, monkeypatch):
    evidence = ToolEvidence(request(tmp_path), "pinned-v1", max_observations=1)
    observation = ToolObservation("read", {}, "result")
    with pytest.raises(ToolEvidenceError, match="prepare"):
        evidence.record(observation)
    evidence.prepare()
    path = evidence.record(observation)
    expected = path.read_bytes()
    with pytest.raises(ToolEvidenceError, match="count budget"):
        evidence.record(observation)
    assert path.read_bytes() == expected

    bounded = ToolEvidence(request(tmp_path, attempt=2), "pinned-v1", max_bytes=1024)
    bounded.prepare()
    with pytest.raises(ToolEvidenceError, match="byte budget"):
        bounded.record(ToolObservation("read", {}, "x" * 1024))
    assert not list(bounded.directory.glob("observation-*"))

    def fail(*_):
        raise OSError("disk unavailable")

    monkeypatch.setattr("botpipe.tool_evidence.os.link", fail)
    with pytest.raises(ToolEvidenceError, match="could not be persisted") as error:
        bounded.record(observation)
    assert isinstance(error.value.__cause__, OSError)
    assert "disk unavailable" in str(error.value.__cause__)
    assert not list(bounded.directory.glob("observation-*"))
    assert not list(bounded.directory.glob(".pending-*"))


def test_racing_recorders_cannot_replace_receipts(tmp_path):
    first = ToolEvidence(request(tmp_path), "pinned-v1")
    second = ToolEvidence(request(tmp_path), "pinned-v1")
    first.prepare()
    second.prepare()
    path = first.record(ToolObservation("read", {}, "first"))
    with pytest.raises(ToolEvidenceError, match="already exists"):
        second.record(ToolObservation("read", {}, "second"))
    assert json.loads(path.read_text())["observation"]["output"] == "first"


def test_non_durable_envelopes_and_observations_fail_with_evidence_error(tmp_path):
    evidence = ToolEvidence(request(tmp_path), "pinned-v1")
    with pytest.raises(ToolEvidenceError, match="durable JSON") as envelope_error:
        evidence.prepare([{"value": float("nan")}])
    assert isinstance(envelope_error.value.__cause__, ValueError)

    evidence.prepare()

    class InvalidObservation:
        def to_record(self):
            return {"output": object()}

    with pytest.raises(ToolEvidenceError, match="durable JSON") as observation_error:
        evidence.record(InvalidObservation())
    assert isinstance(observation_error.value.__cause__, TypeError)
    assert not list(evidence.directory.glob("observation-*"))
