"""Guard the PR's net production-source growth, excluding docs and tests."""

import os
import subprocess

base = os.environ.get("BOTPIPE_BASE_REF", "origin/main")
result = subprocess.run(
    [
        "git",
        "diff",
        "--numstat",
        f"{base}...HEAD",
        "--",
        "botpipe",
        "botpipe_optimizer",
        "labs",
        "tools",
    ],
    check=True,
    capture_output=True,
    text=True,
)
added = removed = 0
for line in result.stdout.splitlines():
    plus, minus, path = line.split("\t", 2)
    if path.endswith((".py", ".js", ".mjs", ".ts")) and plus != "-":
        added += int(plus)
        removed += int(minus)
net = added - removed
print(f"Production source: +{added} / -{removed}; net {net:+d} lines against {base}.")
if net > 4500:
    raise SystemExit(
        "Source growth exceeds the 4,500-line guardrail; simplify or document an explicit exception."
    )
