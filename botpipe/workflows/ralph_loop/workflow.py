"""Durable, imperative Ralph loop."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from botpipe import Artifact, Provider, Session, Worklist, current_run, workflow
from botpipe.workflows._reviews import save_review


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["accepted", "needs_rework"]
    summary: str = ""
    required_changes: list[str] = Field(default_factory=list)


PLAN = """
Read the supplied request and inspect the repository.
If a previous plan-review artifact is supplied, address every required change;
do not re-emit a rejected plan unchanged.

Write work.json with the complete implementation plan, ordered into independently
implementable items. Give each item a stable, unique id and acceptance checks.
Use this structure, with new items initially marked planned:
{
  "goal": "The requested outcome",
  "items": [
    {
      "id": "item-1",
      "title": "Short imperative title",
      "status": "planned",
      "goal": "What to implement",
      "acceptance_checks": ["What must be true"]
    }
  ]
}
""".strip()

REVIEW_PLAN = """
Verify the supplied work.json against the original request and repository.
Accept only if it fully covers the request, is ordered, and each item is
independently implementable with concrete acceptance checks.

Return a structured object whose verdict is accepted or needs_rework.
""".strip()

IMPLEMENT = """
Read the supplied work.json and current item's complete payload.
If a previous implementation-review artifact is supplied, address every blocking
finding before making unrelated changes.

Implement this item completely and correctly in the repository. Edit files,
add or update tests as needed, run validation, and fix failures.
""".strip()

REVIEW_IMPLEMENTATION = """
Independently verify the repository implementation for the supplied current item.
Do not rely on the producer's summary or claimed validation. Inspect work.json,
the item payload, repository diff, source, tests, artifacts, and command output.
Accept only if the item is correctly and completely implemented with no
remaining gaps against its goal and acceptance checks.

Return a structured decision with exact rework instructions if rejected.
""".strip()


@workflow(name="ralph_loop", version="1")
def ralph_loop(request: str):
    work = Artifact.json("work.json", required=True)
    plan_review = Artifact.md("plan_review.md", required=True)
    planner = Provider()
    plan_reviewer = planner.with_config(session=None)
    feedback: tuple[object, ...] = ()

    while True:
        plan = planner.run(PLAN, input=request, reads=feedback, writes=(work,))
        review = plan_reviewer.query(
            REVIEW_PLAN,
            input=request,
            reads=(plan.artifacts.work,),
            returns=ReviewDecision,
        )
        plan_review_path = save_review(str(current_run().folder / plan_review.path), review.value)
        if review.value.verdict == "accepted":
            break
        feedback = (plan_review_path,)

    items = Worklist.from_artifact(plan.artifacts.work, collection="items")
    for item in items:
        provider = planner.with_config(session=Session.work_item(item))
        reviewer = planner.with_config(session=None)
        item_review = Artifact.md(
            f"items/{item.dir_key}/implementation_review.md",
            required=True,
        )
        feedback = ()
        while True:
            provider.run(
                IMPLEMENT,
                input=item.payload,
                reads=(items.artifact, *feedback),
            )
            review = reviewer.query(
                REVIEW_IMPLEMENTATION,
                input=item.payload,
                reads=(items.artifact,),
                returns=ReviewDecision,
            )
            item_review_path = save_review(
                str(current_run().folder / item_review.path), review.value
            )
            if review.value.verdict == "accepted":
                items.complete(item)
                break
            feedback = (item_review_path,)

    return items.artifact


RalphLoop = ralph_loop

__all__ = ["RalphLoop", "ReviewDecision", "ralph_loop"]
