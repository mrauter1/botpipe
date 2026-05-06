# Autoloop-v1 Prompts

Package-local prompts for the Autoloop-v1 workflow live in this directory.

## Shared README Boundary

Keep the common runtime contract wording aligned with the active workflow prompt READMEs.

## Keep In Each Prompt

- Treat declared artifacts as governed output surfaces, not an exclusive allow-list.
- Provider raw output is runtime telemetry, not an authoritative contract surface.

## Step Surface

- Respect readable inputs and required inputs separately.
- Use the workflow-authored prompt as the task-specific instruction body.

## Route Surface

- route metadata supplies route summaries and any route-specific required writes.
- treat helper routes as ordinary compiled routes with conventional defaults rather than a separate control-routing subsystem.
- default `question` and `blocked` helper routes are interactive-only; default `failed` remains provider-visible in full-auto mode unless the workflow overrides or suppresses it.
- use `outcome.route_fields.questions` for question routes and nullable `outcome.route_fields.reason` for blocked or failed routes.

## Verifier Payloads

- Verifier payloads should justify the chosen route and cite the required artifacts when relevant.
