"""Packaged Ralph-loop workflow."""

from __future__ import annotations

from pydantic import BaseModel

from botpipe import FINISH, Md, Prompt, Route, Session, Workflow, Worklist, produce_verify_step
from botpipe.core import Artifact


class RalphLoop(Workflow):
    """Plan a repository change into work items, then implement each item."""

    name = "ralph_loop"

    class Input(BaseModel):
        request: str

    work = Artifact.json(
        "{{ workflow.folder }}/work.json",
        name="work",
        required=True,
    )
    plan_review = Md(
        "plan_review",
        path="{{ workflow.folder }}/plan_review.md",
        required=False,
    )

    items = Worklist.from_artifact(
        name="item",
        artifact=work,
        collection="items",
        item_id="id",
        title="title",
        status="status",
    )

    plan_session = Session.run()
    plan_verifier_session = Session.run()
    item_session = Session.work_item(items)

    plan = produce_verify_step(
        session=plan_session,
        verifier_session=plan_verifier_session,
        reads=[plan_review],
        producer_prompt=Prompt.inline(
            """
            Read {{ message }}. Inspect the repository.

            If plan_review.md exists, read it first. If it contains
            `needs_rework` or required rework, update work.json to address
            every listed issue. Do not re-emit the prior plan unchanged.

            Review path:
            {{ workflow.folder }}/plan_review.md

            Write work.json with a complete implementation plan decomposed into
            independently implementable items.

            Shape:
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
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify work.json.

            Accept only if it fully covers {{ message }}, is ordered, and
            each item is independently implementable with acceptance checks.

            Write plan_review.md with the decision and required rework, if any.
            """.strip()
        ),
        producer_writes=[work],
        verifier_writes=[
            plan_review,
        ],
        routes={
            "accepted": Route.to(
                "implement",
                required_writes=["work", "plan_review"],
            ),
            "needs_rework": Route.to(
                "plan",
                handoff=(
                    "The verifier rejected the plan. Read "
                    "{{ workflow.folder }}/plan_review.md and address every "
                    "required rework item before rewriting work.json."
                ),
                required_writes=["plan_review"],
            ),
        },
    )

    implement = produce_verify_step(
        scope=items,
        session=item_session,
        requires=[plan.work],
        verifier_requires=[plan.work],
        producer_prompt=Prompt.inline(
            """
            Read work.json and the current item.

            Current item:
            - id: {{ item.id }}
            - title: {{ item.title }}
            - payload: {{ item.payload }}

            If implementation_review.md exists for the current item, read it
            first. If it contains NEEDS_REWORK or blocking findings, address
            every listed finding before making unrelated changes.

            Review path:
            {{ workflow.folder }}/items/{{ item.dir_key }}/implementation_review.md

            Implement this item completely and correctly in the repository.
            Edit files, add or update tests, run validation, and fix failures.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify the repository implementation for the current item.

            Independently verify the repository state. Do not rely on the
            producer's summary or claimed validation. Inspect source, tests,
            artifacts, and command output yourself.

            Check work.json, the item payload, repo diff, source files, tests,
            and relevant command output.

            Accept only if the item is correctly and completely implemented
            with no remaining gaps.

            Write implementation_review.md with the decision and exact rework
            instructions if rejected.
            """.strip()
        ),
        verifier_writes=[
            Md(
                "implementation_review",
                path="{{ workflow.folder }}/items/{{ item.dir_key }}/implementation_review.md",
                required=True,
            ),
        ],
        routes={
            "accepted": Route.complete_and_advance(
                "implement",
                exhausted=FINISH,
                required_writes=["implementation_review"],
            ),
            "needs_rework": Route.to(
                "implement",
                handoff=(
                    "The verifier rejected item {{ item.id }}. Read "
                    "{{ workflow.folder }}/items/{{ item.dir_key }}/implementation_review.md "
                    "and address every required change before continuing."
                ),
                required_writes=["implementation_review"],
            ),
        },
    )

    entry = plan
