"""Understand, build, test and independently review in a bounded repair loop."""

import sys
from pathlib import Path

from botpipe import Provider, Session, ask_human, current_run, provider_budget, workflow

from .contracts import Brief, Build, Review, WorkflowAuthorResult
from .guidance import load_authoring_guidance
from .params import Params
from .validation import prepare_candidate, validate_candidate, verify_candidate

UNDERSTAND = """Write the brief for the requested Botpipe workflow. Read the request
and relevant files. Explain who runs it, its purpose, and what done looks like.
Define material vague terms and distinguish requirements from chosen assumptions.
For every human gate, say what the person sees and what their answer changes.
Give concrete given/when/then scenarios, including realistic failures and exhaustion.
Ask only when a wrong assumption would materially change the design. Preserve the
original request and all clarification answers. Keep the brief concise."""

BUILD = """Build the workflow in the brief using the supplied Botpipe guides.
Write flow.py, workflow.toml and any needed assets under `package`, and behavioral
FakeProvider tests at `tests`. Test each brief scenario's consequences, including
human-answer use, feedback, failure and replay; merely copying answer text is not
proof it changes behavior. Use project context in this candidate workspace.
Run `check.argv` with `check.cwd` (an argument list, not a shell command). Read the
resulting transcript as the person running the workflow. Fix unusable questions,
lost decisions and incomplete handoffs. Transcript warnings are hints: transformed
values and earlier session context can be valid. Scripted tests do not prove live
model quality. Address feedback and its causes; preserve unaffected behavior and
avoid unrelated changes. If evidence corrects an assumption, return an updated
brief; preserve explicit requirements and surface material unresolved questions.
Return the actual flow.py:callable reference and concise implementation notes."""

REVIEW = """Independently decide whether this workflow serves the original request
and the person's clarification answers. Check the brief against those authorities.
Start with the test transcript: questions, answers, agent inputs and responses,
and observed test outcomes. Does the person have enough context to answer? Do their
choices reach the appropriate operation and change its behavior? Use source and
tests to investigate causes, missing scenarios, invalid assumptions and vacuous
assertions. Warnings about missing verbatim text are hints, not proof of lost data.
Inspect the validation evidence and distinguish scripted behavior from untested
live quality. You can inspect files, but cannot run tests or edit them in this
read-only review. Ship only if nothing material is wrong; otherwise give concrete
findings, including brief corrections when needed. Do not require unrelated work."""


@workflow(name="workflow_author", version="3")
def workflow_author(params: Params, request: str = "") -> WorkflowAuthorResult:
    with provider_budget(max_turns=params.max_provider_turns):
        run = current_run()
        root = prepare_candidate(str(run.workspace), str(run.folder / "candidate"), params.package_name)
        agent = Provider(workspace=root, instructions=load_authoring_guidance())
        author, reviewer = Session(), Session()
        context = {"request": request, "parameters": params.model_dump(mode="json"), "answers": []}
        brief = agent.run(UNDERSTAND, input=context, returns=Brief, session=author).value
        feedback, validation, reference = [], None, None
        package = f".botpipe/workflows/{params.package_name}"
        for round_ in range(1, params.max_rounds + 1):
            if brief.questions:
                answer = ask_human("Before building:\n- " + "\n- ".join(brief.questions))
                context["answers"].append({"questions": brief.questions, "answer": answer})
                brief = agent.run(UNDERSTAND, input={**context, "brief": brief.model_dump()},
                                  returns=Brief, session=author).value
                if brief.questions:
                    feedback = brief.questions
                    continue
            transcript = str(Path(root) / ".botpipe" / "transcripts" / f"round-{round_}.md")
            check = {"cwd": root, "argv": [sys.executable, "-m",
                     "botpipe.workflows.workflow_author.validation", params.package_name,
                     "--transcript", transcript]}
            reference, validation = None, None
            built = agent.run(BUILD, input={**context, "brief": brief.model_dump(),
                              "package": package, "tests": f"tests/runtime/test_{params.package_name}.py",
                              "check": check, "transcript": transcript, "feedback": feedback},
                              returns=Build, session=author).value
            brief = built.brief or brief
            if brief.questions:
                feedback = brief.questions
                continue
            validation = validate_candidate(root, params.package_name, built.reference, transcript,
                                            extra_argv=params.target_test_argv)
            if not validation.success:
                feedback = validation.errors
                continue
            reference = validation.reference
            review = agent.query(REVIEW, input={**context, "brief": brief.model_dump(),
                                 "package": package, "transcript": transcript,
                                 "validation": validation.model_dump(), "builder_notes": built.notes},
                                 returns=Review, session=reviewer).value
            feedback = review.findings
            if review.ship:
                verify_candidate(root, validation)
                return WorkflowAuthorResult(reference=reference, shipped=True, rounds=round_,
                                            findings=[], brief=brief, candidate_root=root, validation=validation)
        return WorkflowAuthorResult(reference=reference, shipped=False, rounds=params.max_rounds,
                                    findings=feedback, brief=brief, candidate_root=root, validation=validation)
