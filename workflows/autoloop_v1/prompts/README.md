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
- Reserved routes remain available for `question`, `blocked`, and `failed`.

## Verifier Payloads

- Verifier payloads should justify the chosen route and cite the required artifacts when relevant.
