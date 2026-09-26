# Frame the workflow decision

Turn the request, parameters, and observed workflow catalog into a decision brief. On acceptance, write only to the declared artifact paths and return the injected typed result.

## Responsibility

- In `task_strategy_brief`, state the trigger, sponsor or consumer, terminal outcome, constraints, and the handoff the eventual route must provide.
- In `workflow_selection_criteria`, define task-specific tests for using one workflow, composing workflows, adapting one, or creating a new package.
- Separate hard constraints from preferences and identify assumptions or missing facts that could change the route.
- Do not select a route or workflow yet.

## Evidence and judgment

Ground the criteria in the supplied request and catalog. A material gap means the required outcome or safety boundary cannot credibly be met by reuse, composition, or adaptation; inconvenience is not a gap. Do not require an arbitrary number of candidates.

## Completion and exceptions

Return `accepted` when the next phase can compare plausible routes without guessing the objective or constraints. Use `needs_rework` for defects within this framing, `needs_replan` only if the task boundary itself changed, and `question` or `blocked` only when a missing prerequisite prevents a defensible comparison. Never invent intent or claim downstream work ran.
