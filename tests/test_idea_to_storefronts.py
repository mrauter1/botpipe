"""Regression coverage for the One Idea, Many Storefronts lab workflow."""

from __future__ import annotations

import itertools
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from botpipe import Botpipe
from botpipe.discovery import discover_workflows, resolve_workflow
from botpipe.providers import FakeProvider
from labs.workflows.idea_to_storefronts.flow import Idea, idea_to_storefronts


_DECODER = json.JSONDecoder()


def _prompt_json(request, heading: str) -> Any:
    """Decode the first JSON value after a prompt heading.

    Provider prompts can append more sections after the value, so splitting at a
    blank line is unsafe for strings containing newlines.  ``raw_decode`` is the
    same parsing strategy a real provider-side adapter needs here.
    """

    marker = f"\n\n{heading}\n"
    tail = request.prompt.split(marker, 1)[1].lstrip()
    return _DECODER.raw_decode(tail)[0]


def _input(request) -> dict[str, Any]:
    if "\n\nInput:\n" not in request.prompt:
        return {}
    return _prompt_json(request, "Input:")


def _reads(request) -> dict[str, Path]:
    heading = "Read these immutable input artifacts:"
    if f"\n\n{heading}\n" not in request.prompt:
        return {}
    return {
        item["name"]: Path(item["path"])
        for item in _prompt_json(request, heading)
    }


def _write(request, name: str, content: str) -> None:
    path = request.artifacts[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ideas(batch: int = 1, *, duplicate_evidence: bool = False) -> dict[str, Any]:
    ideas = []
    for index in range(5):
        link = f"https://example.org/item/{batch}-{index}"
        evidence = [link, link] if duplicate_evidence else [link]
        ideas.append(
            {
                "question": f"Question {batch}-{index}?",
                "evidence": evidence,
                "gap": f"Gap {batch}-{index}",
                "product": f"Product {batch}-{index}",
                "risk_flags": [],
            }
        )
    return {"ideas": ideas, "target_language": "English", "notes": "researched"}


class StorefrontProvider:
    """Dynamic fake for a workflow whose stage 3/4 call order is concurrent."""

    def __init__(
        self,
        *,
        research_reviews: list[dict[str, Any]] | None = None,
        product_formats: list[str] | None = None,
        reject_compliance: dict[str, int] | None = None,
        reject_reviews: dict[str, int] | None = None,
    ) -> None:
        self.requests: list[Any] = []
        self.records: list[tuple[str, dict[str, Any], Any]] = []
        self.research_reviews = list(research_reviews or [])
        self.product_formats = list(product_formats or ["guide"])
        self.reject_compliance = Counter(reject_compliance or {})
        self.reject_reviews = Counter(reject_reviews or {})
        self.research_batches = 0
        self.product_builds = 0
        self.package_builds = Counter()

    def _record(self, kind: str, request, data: dict[str, Any]) -> None:
        self.records.append((kind, data, request))

    def calls(self, kind: str) -> list[tuple[dict[str, Any], Any]]:
        return [(data, request) for found, data, request in self.records if found == kind]

    def __call__(self, request):
        self.requests.append(request)
        data = _input(request)
        artifacts = set(request.artifacts)

        if artifacts == {"research"}:
            self.research_batches += 1
            batch = _ideas(self.research_batches)
            _write(request, "research", json.dumps(batch, indent=2))
            self._record("research_producer", request, data)
            return batch

        if artifacts & {"long_video", "short_1", "short_2", "short_3", "hooks"}:
            token = " ".join(f"word{index}" for index in range(1300))
            for name in artifacts:
                if name == "long_video":
                    content = f"ANGLE {data.get('angle')} NOTES {data.get('creator_notes')} {token}"
                elif name.startswith("short_"):
                    content = " ".join([f"{name}-spoken"] * 160)
                else:
                    content = f"hooks problem first; notes={data.get('creator_notes')}"
                _write(request, name, content)
            self._record("script_producer", request, data)
            return "scripts written"

        if artifacts == {"listing"}:
            self.product_builds += 1
            index = min(self.product_builds - 1, len(self.product_formats) - 1)
            product_format = self.product_formats[index]
            product_dir = Path(data["product_dir"])
            product_dir.mkdir(parents=True, exist_ok=True)
            (product_dir / f"{product_format}.md").write_text(
                f"product build {self.product_builds}; notes={data.get('creator_notes')}",
                encoding="utf-8",
            )
            _write(
                request,
                "listing",
                f"listing build {self.product_builds}; format={product_format}; "
                f"notes={data.get('creator_notes')}",
            )
            self._record("product_producer", request, data)
            return {"format": product_format, "price_usd": 9}

        if artifacts == {"package"}:
            platform = data["platform"]
            self.package_builds[platform] += 1
            consumed = {
                name: path.read_text(encoding="utf-8")
                for name, path in _reads(request).items()
            }
            _write(
                request,
                "package",
                json.dumps(
                    {
                        "platform": platform,
                        "build": self.package_builds[platform],
                        "angle": data.get("angle"),
                        "off_limits": data.get("off_limits"),
                        "creator_notes": data.get("creator_notes"),
                        "consumed": consumed,
                    },
                    indent=2,
                ),
            )
            self._record("package_producer", request, {**data, "_consumed": consumed})
            return "package written"

        if artifacts == {"learnings"}:
            _write(request, "learnings", "repeat evidence; drop nothing; test one new hook")
            self._record("learnings", request, data)
            return "learnings written"

        if artifacts:
            for name in artifacts:
                _write(request, name, f"aid {name}")
            self._record("recording_helper", request, data)
            return "aids written"

        schema_properties = (request.output_schema or {}).get("properties", {})
        if "checks" in schema_properties:
            self._record("research_reviewer", request, data)
            if self.research_reviews:
                return self.research_reviews.pop(0)
            checks = []
            for idea_index, idea in enumerate(data["ideas"], start=1):
                for url in idea["evidence"]:
                    checks.append(
                        {
                            "idea_number": idea_index,
                            "url": str(url),
                            "supported": True,
                            "detail": "The fetched source supports the stated audience problem.",
                        }
                    )
            return {"checks": checks}

        if "accepted" in schema_properties:
            platform = data.get("platform")
            if platform:
                self._record("compliance_reviewer", request, data)
                if self.reject_compliance[platform] > 0:
                    self.reject_compliance[platform] -= 1
                    return {
                        "accepted": False,
                        "findings": [f"{platform} package remains noncompliant"],
                        "checks_run": ["platform checklist"],
                        "checks_unavailable": [],
                    }
            elif "product_dir" in data:
                self._record("product_reviewer", request, data)
                if self.reject_reviews["product"] > 0:
                    self.reject_reviews["product"] -= 1
                    return {
                        "accepted": False,
                        "findings": ["The product sample is not concrete enough."],
                        "checks_run": ["sample exercise"],
                        "checks_unavailable": [],
                    }
            else:
                self._record("script_reviewer", request, data)
                if self.reject_reviews["scripts"] > 0:
                    self.reject_reviews["scripts"] -= 1
                    return {
                        "accepted": False,
                        "findings": ["The opening is not concrete enough."],
                        "checks_run": ["script criteria"],
                        "checks_unavailable": [],
                    }
            return {
                "accepted": True,
                "findings": [],
                "checks_run": ["all criteria"],
                "checks_unavailable": [],
            }

        raise AssertionError(f"unrecognized provider request: {request.prompt[:200]}")


def _provider(fake: StorefrontProvider) -> FakeProvider:
    return FakeProvider(itertools.repeat(fake))


def _recordings_from_question(question: str) -> Path:
    match = re.search(r"([^'\[\], ]+)/long_video\.<ext>", question)
    assert match, question
    return Path(match.group(1))


def _answer_gate1() -> dict[str, Any]:
    return {
        "selection": "select",
        "idea_number": 1,
        "angle": "Lead with the creator's field-tested method and concrete tradeoffs.",
        "off_limits": "Do not promise guaranteed revenue.",
    }


def _drive_to_gate3(client: Botpipe, provider: FakeProvider, tmp_path: Path):
    result = client.run(
        idea_to_storefronts,
        "English-language solo creator systems",
        run_id="storefront-run",
        task_id="storefront-task",
    )
    assert result.status == "awaiting_input", result.error
    assert "Ranked ideas" in result.pending_input["question"]
    result = client.resume(result.run_id, workflow=idea_to_storefronts, answer=_answer_gate1())
    assert result.status == "awaiting_input", result.error
    question = result.pending_input["question"]
    assert "Expected recording files" in question
    recordings = _recordings_from_question(question)
    recordings.mkdir(parents=True, exist_ok=True)
    for stem in ("long_video", "short_1", "short_2", "short_3"):
        (recordings / f"{stem}.mp4").write_bytes(b"recorded")
    result = client.resume(
        result.run_id,
        workflow=idea_to_storefronts,
        answer={"recorded": True},
    )
    assert result.status == "awaiting_input", result.error
    assert "Every piece still open" in result.pending_input["question"]
    return result


def _finish(client: Botpipe, result, approvals: list[str] | None = None):
    if approvals is None:
        approvals = [
            "long_video",
            "short_1",
            "short_2",
            "short_3",
            "product",
            "youtube_package",
            "tiktok_package",
            "kdp_package",
            "etsy_or_hotmart_package",
        ]
    result = client.resume(
        result.run_id,
        workflow=idea_to_storefronts,
        answer={"approve": approvals},
    )
    assert result.status == "awaiting_input", result.error
    assert "About 7 days" in result.pending_input["question"]
    return client.resume(
        result.run_id,
        workflow=idea_to_storefronts,
        answer={"listing_views": 20, "sales": 1, "agent_cost_this_run": 2.5},
    )


def _assert_notes_contract(records, expected: list[str]) -> None:
    assert records
    for data, _request in records:
        assert data["creator_notes"] == expected
        assert all(note in data["findings"] for note in expected)


def _piece_is_shown(question: str, piece: str) -> bool:
    return f"'piece': '{piece}'" in question


def test_discovery_resolves_storefront_name_and_alias():
    root = Path(__file__).parents[1]
    entry = next(item for item in discover_workflows(root) if item.name == "idea_to_storefronts")
    assert entry.aliases == ("storefronts",)
    assert resolve_workflow("idea_to_storefronts", root).fn is idea_to_storefronts.fn
    assert resolve_workflow("storefronts", root).fn is idea_to_storefronts.fn


def test_idea_evidence_requires_http_urls_and_deduplicates():
    idea = Idea(
        question="What works?",
        evidence=["https://example.org/a", "https://example.org/a", "http://example.org/b"],
        gap="A gap",
        product="A guide",
    )
    assert [str(url) for url in idea.evidence] == [
        "https://example.org/a",
        "http://example.org/b",
    ]
    with pytest.raises(ValidationError):
        Idea(question="What works?", evidence=["not a URL"], gap="A gap", product="A guide")


def test_happy_path_carries_constraints_and_replays_without_provider_calls(tmp_path):
    fake = StorefrontProvider()
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        gate3 = _drive_to_gate3(client, provider, tmp_path)
        completed = _finish(client, gate3)
        assert completed.ok, completed.error
        before_replay = len(provider.calls)
        replayed = client.resume(completed.run_id, workflow=idea_to_storefronts)

    assert replayed.ok
    assert replayed.value == completed.value
    assert len(provider.calls) == before_replay
    assert {item.platform for item in completed.value.platform_packages} == {
        "youtube",
        "tiktok",
        "kdp",
        "etsy_or_hotmart",
    }

    for kind in ("script_producer", "product_producer", "package_producer"):
        for data, _request in fake.calls(kind):
            assert data["angle"].startswith("Lead with")
            assert data["off_limits"] == "Do not promise guaranteed revenue."
            assert data["creator_notes"] == []
    for kind in ("script_reviewer", "product_reviewer", "compliance_reviewer"):
        for data, _request in fake.calls(kind):
            assert data["angle"].startswith("Lead with")
            assert data["off_limits"] == "Do not promise guaranteed revenue."
            assert data["creator_notes"] == []
    research_calls = fake.calls("research_producer")
    review_calls = fake.calls("research_reviewer")
    assert len(research_calls) == len(review_calls) == 1
    assert research_calls[0][1].policy.network.value == "full"
    assert review_calls[0][1].policy.network.value == "full"
    assert review_calls[0][1].policy.sandbox_mode.value == "read_only"
    assert research_calls[0][1].session_key
    assert review_calls[0][1].session_key is None


def test_gate3_batches_upstream_rework_then_rebuilds_each_package_once(tmp_path):
    fake = StorefrontProvider()
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        gate3 = _drive_to_gate3(client, provider, tmp_path)
        baseline = len(fake.records)
        revised = client.resume(
            gate3.run_id,
            workflow=idea_to_storefronts,
            answer={
                "approve": ["short_1", "short_2", "short_3", "tiktok_package"],
                "notes": {
                    "long_video": "Make the opening more concrete.",
                    "product": "Add a worked example.",
                    "youtube_package": "Keep the title factual.",
                },
            },
        )
        assert revised.status == "awaiting_input", revised.error
        question = revised.pending_input["question"]
        assert not _piece_is_shown(question, "short_1")
        assert not _piece_is_shown(question, "short_2")
        assert not _piece_is_shown(question, "short_3")
        assert _piece_is_shown(question, "youtube_package")
        assert _piece_is_shown(question, "tiktok_package")

        new_records = fake.records[baseline:]
        kinds = [kind for kind, _data, _request in new_records]
        last_source = max(index for index, kind in enumerate(kinds) if kind in {"script_reviewer", "product_reviewer"})
        first_package = min(index for index, kind in enumerate(kinds) if kind == "package_producer")
        assert last_source < first_package
        assert Counter(
            data["platform"]
            for kind, data, _request in new_records
            if kind == "package_producer"
        ) == Counter({"youtube": 1, "tiktok": 1, "kdp": 1, "etsy_or_hotmart": 1})

        _assert_notes_contract(
            [(data, request) for kind, data, request in new_records if kind in {"script_producer", "script_reviewer"}],
            ["Make the opening more concrete."],
        )
        _assert_notes_contract(
            [(data, request) for kind, data, request in new_records if kind in {"product_producer", "product_reviewer"}],
            ["Add a worked example."],
        )
        youtube = [
            (data, request)
            for kind, data, request in new_records
            if kind in {"package_producer", "compliance_reviewer"}
            and data.get("platform") == "youtube"
        ]
        _assert_notes_contract(youtube, ["Keep the title factual."])

        completed = _finish(client, revised)
        assert completed.ok, completed.error
        replay_call_count = len(provider.calls)
        replayed = client.resume(completed.run_id, workflow=idea_to_storefronts)
        assert replayed.ok
        assert len(provider.calls) == replay_call_count
    assert "Make the opening more concrete." in Path(
        completed.value.script_paths["long_video"]
    ).read_text(encoding="utf-8")
    assert "Add a worked example." in Path(completed.value.product.listing_path).read_text(
        encoding="utf-8"
    )
    for package in completed.value.platform_packages:
        content = (Path(package.package_dir) / "package.md").read_text(encoding="utf-8")
        assert "Make the opening more concrete." in content
        assert "Add a worked example." in content


def test_direct_package_note_retains_unrelated_approvals(tmp_path):
    fake = StorefrontProvider()
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        gate3 = _drive_to_gate3(client, provider, tmp_path)
        revised = client.resume(
            gate3.run_id,
            workflow=idea_to_storefronts,
            answer={
                "approve": [
                    "long_video",
                    "short_1",
                    "short_2",
                    "short_3",
                    "product",
                    "tiktok_package",
                    "kdp_package",
                    "etsy_or_hotmart_package",
                ],
                "notes": {"youtube_package": "Use a less absolute title."},
            },
        )
        assert revised.status == "awaiting_input", revised.error
        question = revised.pending_input["question"]
        assert _piece_is_shown(question, "youtube_package")
        assert not _piece_is_shown(question, "tiktok_package")
        assert not _piece_is_shown(question, "long_video")
        assert fake.package_builds == Counter(
            {"youtube": 2, "tiktok": 1, "kdp": 1, "etsy_or_hotmart": 1}
        )
        completed = _finish(client, revised, ["youtube_package"])
    assert completed.ok, completed.error


def test_package_note_survives_later_upstream_rebuild(tmp_path):
    fake = StorefrontProvider()
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        gate3 = _drive_to_gate3(client, provider, tmp_path)
        after_package = client.resume(
            gate3.run_id,
            workflow=idea_to_storefronts,
            answer={"notes": {"youtube_package": "Keep the title factual."}},
        )
        assert after_package.status == "awaiting_input", after_package.error
        before = len(fake.calls("package_producer"))
        after_source = client.resume(
            gate3.run_id,
            workflow=idea_to_storefronts,
            answer={"notes": {"long_video": "State the tradeoff in sentence one."}},
        )
        assert after_source.status == "awaiting_input", after_source.error
        rebuilt = fake.calls("package_producer")[before:]
        youtube = [data for data, _request in rebuilt if data["platform"] == "youtube"]
        assert len(youtube) == 1
        assert youtube[0]["creator_notes"] == ["Keep the title factual."]
        completed = _finish(client, after_source)
    assert completed.ok, completed.error


def test_product_format_change_recomputes_platforms_and_removes_kdp(tmp_path):
    fake = StorefrontProvider(product_formats=["guide", "checklist"])
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        gate3 = _drive_to_gate3(client, provider, tmp_path)
        revised = client.resume(
            gate3.run_id,
            workflow=idea_to_storefronts,
            answer={
                "approve": ["long_video", "short_1", "short_2", "short_3"],
                "notes": {"product": "This should be a compact checklist."},
            },
        )
        assert revised.status == "awaiting_input", revised.error
        assert not _piece_is_shown(revised.pending_input["question"], "kdp_package")
        completed = _finish(
            client,
            revised,
            ["product", "youtube_package", "tiktok_package", "etsy_or_hotmart_package"],
        )
    assert completed.ok, completed.error
    assert completed.value.product.format == "checklist"
    product_files = {
        path.name for path in Path(completed.value.product.product_dir).iterdir() if path.is_file()
    }
    assert product_files == {"checklist.md"}
    prior_product_reads = {
        path.read_text(encoding="utf-8")
        for path in _reads(fake.calls("product_producer")[1][1]).values()
    }
    assert any("format=guide" in text for text in prior_product_reads)
    assert any("product build 1" in text for text in prior_product_reads)
    for data, _request in fake.calls("package_producer")[-3:]:
        consumed = "\n".join(data["_consumed"].values())
        assert "format=checklist" in consumed
        assert "product build 2" in consumed
        assert "format=guide" not in consumed
        assert "product build 1" not in consumed
    assert {item.platform for item in completed.value.platform_packages} == {
        "youtube",
        "tiktok",
        "etsy_or_hotmart",
    }


def test_product_format_change_adds_kdp_for_guide(tmp_path):
    fake = StorefrontProvider(product_formats=["checklist", "guide"])
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        gate3 = _drive_to_gate3(client, provider, tmp_path)
        assert fake.package_builds["kdp"] == 0
        revised = client.resume(
            gate3.run_id,
            workflow=idea_to_storefronts,
            answer={
                "approve": ["long_video", "short_1", "short_2", "short_3"],
                "notes": {"product": "Expand this into a guide."},
            },
        )
        assert revised.status == "awaiting_input", revised.error
        assert _piece_is_shown(revised.pending_input["question"], "kdp_package")
        assert fake.package_builds["kdp"] == 1
        completed = _finish(
            client,
            revised,
            [
                "product",
                "youtube_package",
                "tiktok_package",
                "kdp_package",
                "etsy_or_hotmart_package",
            ],
        )
    assert completed.ok, completed.error
    assert completed.value.product.format == "guide"
    assert "kdp" in {item.platform for item in completed.value.platform_packages}


def test_deliberately_dropped_platform_stays_dropped_after_product_rebuild(tmp_path):
    fake = StorefrontProvider(reject_compliance={"kdp": 3}, product_formats=["guide", "guide"])
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=400) as client:
        result = client.run(
            idea_to_storefronts,
            "English-language solo creator systems",
            run_id="dropped-platform",
            task_id="dropped-platform",
        )
        result = client.resume(result.run_id, workflow=idea_to_storefronts, answer=_answer_gate1())
        recordings = _recordings_from_question(result.pending_input["question"])
        recordings.mkdir(parents=True, exist_ok=True)
        for stem in ("long_video", "short_1", "short_2", "short_3"):
            (recordings / f"{stem}.mov").write_bytes(b"recorded")
        result = client.resume(result.run_id, workflow=idea_to_storefronts, answer={"recorded": True})
        assert "Stage 6 kdp package" in result.pending_input["question"]
        result = client.resume(
            result.run_id,
            workflow=idea_to_storefronts,
            answer={"action": "abandon"},
        )
        assert "Every piece still open" in result.pending_input["question"]
        assert not _piece_is_shown(result.pending_input["question"], "kdp_package")
        kdp_builds = fake.package_builds["kdp"]
        result = client.resume(
            result.run_id,
            workflow=idea_to_storefronts,
            answer={"notes": {"product": "Add a stronger example."}},
        )
        assert result.status == "awaiting_input", result.error
        assert not _piece_is_shown(result.pending_input["question"], "kdp_package")
        assert fake.package_builds["kdp"] == kdp_builds


def test_bounded_loop_retry_notes_reach_extra_round_producer_and_reviewer(tmp_path):
    fake = StorefrontProvider(reject_reviews={"product": 3})
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=250) as client:
        result = client.run(
            idea_to_storefronts,
            "English-language solo creator systems",
            run_id="bounded-retry",
            task_id="bounded-retry",
        )
        result = client.resume(
            result.run_id,
            workflow=idea_to_storefronts,
            answer=_answer_gate1(),
        )
        assert result.status == "awaiting_input", result.error
        assert "Stage 4 product" in result.pending_input["question"]
        assert "3 straight rounds were rejected" in result.pending_input["question"]
        result = client.resume(
            result.run_id,
            workflow=idea_to_storefronts,
            answer={"action": "retry_with_notes", "notes": "Use a real sample row."},
        )
    assert result.status == "awaiting_input", result.error
    assert "Expected recording files" in result.pending_input["question"]
    producers = fake.calls("product_producer")
    reviewers = fake.calls("product_reviewer")
    assert len(producers) == len(reviewers) == 4
    assert "Use a real sample row." in producers[-1][0]["findings"]
    assert "Use a real sample row." in reviewers[-1][0]["findings"]
    assert producers[0][1].session_key == producers[-1][1].session_key


@pytest.mark.parametrize("bad_review", ["unsupported", "missing"])
def test_research_review_repairs_unsupported_or_missing_evidence_in_same_session(
    tmp_path, bad_review
):
    checks = [
        {
            "idea_number": index,
            "url": f"https://example.org/item/1-{index - 1}",
            "supported": True,
            "detail": "supports the idea",
        }
        for index in range(1, 6)
    ]
    if bad_review == "unsupported":
        checks[2] = {**checks[2], "supported": False, "detail": "The page does not support the claim."}
    else:
        checks.pop()
    fake = StorefrontProvider(research_reviews=[{"checks": checks}])
    provider = _provider(fake)
    with Botpipe(tmp_path, provider=provider, max_operations=200) as client:
        result = client.run(
            idea_to_storefronts,
            "English-language solo creator systems",
            run_id=f"repair-{bad_review}",
            task_id=f"repair-{bad_review}",
        )
    assert result.status == "awaiting_input", result.error
    assert "Ranked ideas" in result.pending_input["question"]
    producers = fake.calls("research_producer")
    assert len(producers) == 2
    assert producers[0][1].session_key == producers[1][1].session_key
    repair_input = producers[1][0]
    feedback = json.dumps(repair_input, sort_keys=True)
    if bad_review == "unsupported":
        assert "does not support" in feedback
        assert "item/1-2" in feedback
    else:
        assert "exactly once" in feedback.lower()
        assert "item/1-4" in feedback


def test_research_review_exhaustion_fails_before_gate1_with_actionable_findings(tmp_path):
    # Each research round uses a fresh batch URL, so generate the three matching replies.
    reviews = []
    for batch in range(1, 4):
        reviews.append(
            {
                "checks": [
                    {
                        "idea_number": index,
                        "url": f"https://example.org/item/{batch}-{index - 1}",
                        "supported": False,
                        "detail": f"Source {index} lacks evidence for the claimed gap.",
                    }
                    for index in range(1, 6)
                ]
            }
        )
    fake = StorefrontProvider(research_reviews=reviews)
    with Botpipe(tmp_path, provider=_provider(fake), max_operations=100) as client:
        result = client.run(
            idea_to_storefronts,
            "English-language solo creator systems",
            run_id="research-exhausted",
            task_id="research-exhausted",
        )
    assert result.status == "failed"
    assert "lacks evidence" in result.error
    assert "item/3-" in result.error
    assert len(fake.calls("research_producer")) == 3
    assert not result.pending_input
