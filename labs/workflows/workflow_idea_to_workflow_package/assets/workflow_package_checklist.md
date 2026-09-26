# Workflow package review checklist

Use this as review guidance, not as a mandatory document template.

- The generated package is `.botpipe/workflows/<package_name>/` with `flow.py` and `workflow.toml`.
- The user's selected request, terminal outcome, constraints, source evidence, and material assumptions remain recognizable end to end.
- Writable producer work and artifact destinations stay in the run-owned producer workspace; relative source reads resolve against the injected `source_workspace`.
- Each step has one coherent purpose, evidence boundary, work boundary, semantic handoff, acceptance condition, and recovery target.
- Python owns control flow; providers own judgments that require interpretation. There is no route table, graph compiler, or generic runner.
- Prompts exist only where needed. Each names its purpose, available evidence, stable obligations, semantic output, contradiction/assumption policy, and done criteria while leaving sound methods flexible.
- Independent review protects a material boundary rather than mirroring every producer.
- Complete declared artifacts are required for acceptance; pauses and redirects preserve only genuine available evidence and never fabricate placeholders.
- Diagrams clarify real branching or concurrency; linear procedures stay linear prose.
- Extra schemas, manifests, contracts, reports, prompts, and recursive-improvement stages exist only for a demonstrated runtime or consumer need.
- Evaluation compares actual generated source and prompts with the request and reviewed design, records only checks that ran, and separates proven from unproven outcomes.
- Evaluation rework changes only evaluation evidence; a source, prompt, behavior, proof, or design defect carries exact rejected-candidate evidence through redesign and a fresh build.
- The content manifest uses an explicit `<entry-file>.py:<callable>` reference and stays within the isolated package/test boundary.
