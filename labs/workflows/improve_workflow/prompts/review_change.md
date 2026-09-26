Independently inspect the candidate source against the original baseline, the
reviewed proposal, and the frozen diagnostic assessment. Check correctness,
scope, simplicity, preserved behavior, and the criteria fixed before implementation.
Use the supplied execution results as evidence; identify relevant gaps instead
of treating passing checks as proof of everything. This turn is inspection-only;
the workflow has already run the configured executable checks in isolation.

Accept when the change implements the proposal without known blocking defects.
Otherwise return concrete required changes. Do not infer measured improvement
from the implementation or the producer's explanation; the comparison is owned
by the deterministic evaluator.
