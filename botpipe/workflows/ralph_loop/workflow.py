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
    item_verifier_session = Session.work_item(items)

    plan = produce_verify_step(
        session=plan_session,
        verifier_session=plan_verifier_session,
        producer_prompt=Prompt.inline(
            """
            Read {{ message }}. Inspect the repository.

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
            Md("plan_review", path="{{ workflow.folder }}/plan_review.md", required=True),
        ],
        routes={
            "accepted": Route.to(
                "implement",
                required_writes=["work", "plan_review"],
            ),
            "needs_rework": Route.to(
                "plan",
                required_writes=["plan_review"],
            ),
        },
    )

    implement = produce_verify_step(
        scope=items,
        session=item_session,
        verifier_session=item_verifier_session,
        requires=[plan.work],
        verifier_requires=[plan.work],
        producer_prompt=Prompt.inline(
            """
            Read work.json and the current item.

            Current item:
            - id: {{ item.id }}
            - title: {{ item.title }}
            - payload: {{ item.payload }}

            Implement this item completely and correctly in the repository.
            Edit files, add or update tests, run validation, and fix failures.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Verify the repository implementation for the current item.

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
                required_writes=["implementation_review"],
            ),
        },
    )

    entry = plan
