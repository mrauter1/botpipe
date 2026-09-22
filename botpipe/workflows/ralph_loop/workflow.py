"""Durable, imperative Ralph loop."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from botpipe import Artifact, Provider, Session, Worklist, workflow


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["accepted", "needs_rework"]


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

Write plan_review.md with your decision and exact required rework, if any.
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

Write implementation_review.md at its declared item-specific path, including
your decision and exact rework instructions if rejected. Return a structured
object whose verdict is accepted or needs_rework.
""".strip()


@workflow(name="ralph_loop", version="1")
def ralph_loop(request: str):
    work = Artifact.json("work.json", required=True)
    plan_review = Artifact.md("plan_review.md", required=True)
    planner = Provider()
    plan_reviewer = planner.with_config(session=None)
    feedback = ()

    while True:
        plan = planner.run(PLAN, input=request, reads=feedback, writes=(work,))
        review = plan_reviewer.run(
            REVIEW_PLAN,
            input=request,
            reads=(plan.artifacts.work,),
            writes=(plan_review,),
            returns=ReviewDecision,
        )
        if review.value.verdict == "accepted":
            break
        feedback = (review.artifacts.plan_review,)

    items = Worklist.from_artifact(plan.artifacts.work, collection="items")
    for item in items:
        provider = planner.with_config(session=Session.work_item(item))
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
            review = provider.run(
                REVIEW_IMPLEMENTATION,
                input=item.payload,
                reads=(items.artifact,),
                writes=(item_review,),
                returns=ReviewDecision,
            )
            if review.value.verdict == "accepted":
                items.complete(item)
                break
            feedback = (review.artifacts.implementation_review,)

    return items.artifact


RalphLoop = ralph_loop

__all__ = ["RalphLoop", "ReviewDecision", "ralph_loop"]
