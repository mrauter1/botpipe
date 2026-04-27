# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: compatibility-docs-cleanup
- Phase Directory Key: compatibility-docs-cleanup
- Phase Title: Compatibility Migration And Cleanup
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `Workflow_Instructions.md:65-71`, `Workflow_Instructions.md:272-277`, `Workflow_Instructions.md:334-339`, `Workflow_Instructions.md:441`
  The public doc scrub is incomplete: this repo-root authoring guide still teaches `route_contracts` and “concrete route contracts” as the runtime/provider contract even though this phase is supposed to retire RouteContract-based public authoring. A reader following that file will still author against the deprecated vocabulary, so AC-1 is not met even though `docs/` was cleaned. Minimal fix: either migrate `Workflow_Instructions.md` to the new `route_infos` / `route_required_outputs` / route-metadata vocabulary, or explicitly demote/move it out of the public-authoring surface and widen the doc validation scan so this class of drift cannot recur.
