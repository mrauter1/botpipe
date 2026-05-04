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
- `question` is the only default runtime control route, and provider contracts hide it in full-auto mode.
- If a workflow authors `blocked` or `failed`, treat them as ordinary application routes rather than framework defaults.

## Verifier Payloads

- Verifier payloads should justify the chosen route and cite the required artifacts when relevant.
