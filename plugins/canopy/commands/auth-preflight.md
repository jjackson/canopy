---
description: Fast auth health check (gh, 1Password, AWS labs) before long deploy/workflow runs
allowed-tools: [Bash, Read]
---

# Auth Preflight

Probe `gh`, `op`, and (when labs work is likely) `aws --profile labs` and
report pass/fail with recovery commands. Run this before any long-running
deploy or workflow.

## Process

1. Invoke the `auth-preflight` skill
2. The skill runs `bash scripts/canopy-auth-preflight.sh` and reports
   one line per dependency plus a final summary
