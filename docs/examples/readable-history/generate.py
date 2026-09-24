"""Regenerate the checked-in readable run using only public Botpipe APIs."""

from __future__ import annotations

import shutil
from pathlib import Path

from botpipe import Botpipe, Provider, activity, ask_human, workflow
from botpipe.providers import FakeProvider


ROOT = Path(__file__).resolve().parent
calls = 0


@activity(retry_safe=False)
def uncertain_publish():
    global calls
    calls += 1
    raise SystemExit("simulated crash after an external publish")


@workflow
def readable_example(request: str):
    number = Provider().run(
        "Return the requested integer.",
        returns=int,
        output_retries=1,
        session=None,
    ).value
    approval = ask_human("Approve the generated integer?")
    receipt = uncertain_publish()
    return {"request": request, "number": number, "approval": approval, "receipt": receipt}


def main():
    shutil.rmtree(ROOT / "tasks", ignore_errors=True)
    shutil.rmtree(ROOT / "sessions", ignore_errors=True)
    provider = FakeProvider(["not an integer", "7"])
    with Botpipe(ROOT, state_dir=ROOT, provider=provider) as client:
        first = client.run(
            readable_example,
            "Prepare the readable history example.",
            task_id="readable-task",
            run_id="readable-run",
        )
        assert first.status == "awaiting_input"
        try:
            client.resume(
                first.run_id,
                workflow=readable_example,
                answer="approved",
            )
        except SystemExit:
            pass
        interrupted = client.resume(first.run_id, workflow=readable_example)
        assert interrupted.status == "interrupted"
        operation = next(
            row
            for row in client.journal.operations(first.run_id)
            if row["kind"] == "activity"
        )
        client.resolve(first.run_id, operation["id"], fail=True)
        assert client.journal.run(first.run_id)["status"] == "failed"


if __name__ == "__main__":
    main()
