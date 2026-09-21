# Ralph Loop

`ralph_loop(request)` plans a repository change into stable work items. A
separate reviewer must accept the plan. Each item then uses a persistent
work-item session for implementation and independent review, repeating until
accepted. Accepted items are durably completed in the versioned worklist.

The workflow returns the final immutable `work.json` artifact handle.
