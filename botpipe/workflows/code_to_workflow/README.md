# Code To Workflow

`code_to_workflow` reads the current workspace, captures bounded source and trace evidence, and asks Codex to produce a runnable Botpipe workflow under `.botpipe/workflows/<generated_workflow_name>/`.

The workflow exposes only one optional parameter, `generated_workflow_name`. All source scope, behavior focus, and validation intent should be described in the run message.
