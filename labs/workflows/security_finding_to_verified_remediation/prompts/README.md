# Prompt map

The investigation child workflow first supplies a reviewed evidence pack.

- `assessment_producer.md` determines exploitability and security acceptance criteria; `assessment_reviewer.md` challenges scope and threat reasoning.
- `remediation_producer.md` designs safe implementation and proof; `remediation_reviewer.md` gates fix relevance, validation strength, rollout, and rollback.
- `closure_producer.md` packages the reviewed plan and outstanding closure obligations.

Independent review stays on the two security judgments that can change risk. Final packaging has no extra reviewer and cannot claim implementation or closure.

The parent and investigation child share one typed declared-evidence intake. Security prompts use those immutable handles and keep subsequent live discoveries distinct.
An `accepted` producer result requires every declared artifact. If a missing prerequisite makes responsible work impossible, `question` or `blocked` may pause without creating all outputs; never manufacture placeholder evidence merely to satisfy destinations.
