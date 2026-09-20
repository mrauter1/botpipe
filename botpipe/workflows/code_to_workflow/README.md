# Code to Workflow

`code_to_workflow(request, generated_workflow_name=...)` captures a bounded
source manifest and trace corpus, distills observable behavior, designs an
imperative durable workflow, builds it, validates coverage and discovery, and
publishes a receipt.

Each stage has an independent typed verifier. Local rework repeats the current
stage; design failures return to behavior distillation; build failures can
return to design with the build review as explicit feedback.
