Update the remaining workflow prompt-body documentation and tests to match the shipped route model.

Required changes:

- Replace the retired `Reserved routes` wording in workflow prompt bodies under `workflows/**/prompts/*.md`.
- Prompt bodies must describe `question` as the only default runtime control route.
- Prompt bodies must describe authored `blocked` and `failed` as ordinary application routes, not framework-default or reserved routes.
- Remove any prompt-body wording that explicitly lists `question`, `blocked`, and `failed` as the reserved/default route set.
- Update the runtime prompt-package tests that currently assert phrases like `Reserved routes are only` or `Use reserved routes only`.
- Add regression coverage so prompt-body route wording is guarded centrally, not only through `docs/workflows/*.md` and prompt `README.md`.

Acceptance checks:

- No workflow prompt body under `workflows/**/prompts/*.md` contains `Reserved routes`.
- No workflow prompt body describes `blocked` or `failed` as default framework routes.
- Representative prompt-package runtime tests pass after asserting the new wording.
- Shared baseline coverage fails if prompt bodies reintroduce the retired reserved-route wording.
