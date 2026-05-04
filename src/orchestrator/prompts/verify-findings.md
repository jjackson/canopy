You are verifying whether canopy session-review proposals have already been
shipped between when they were generated and now. For each proposal, decide
one of four verdicts based on the evidence corpus provided.

## Evidence corpus

Recent commits on `origin/main` (last 14 days):

```
{commits}
```

CHANGELOG.md head (top 200 lines, may be empty):

```
{changelog}
```

Code-level grep results for symbols mentioned in the proposals:

```
{grep_results}
```

## Proposals to verify

{proposals_yaml}

## Output

Return a YAML list with one entry per input proposal, in the same order.
Each entry MUST have:

```yaml
- id: <proposal-id (12 hex chars, exactly as in the input)>
  verdict: shipped | partial | open | unverifiable
  evidence: <one-line excerpt from commits/changelog/grep that justifies>
  shipped_at: <commit-sha if verdict==shipped, else null>
  shipped_in_version: <version from CHANGELOG section header if visible, else null>
```

## Verdict rules

- **shipped**: a commit AND/OR changelog entry describes the proposed fix
  end-to-end, AND code-level grep confirms the new behavior is currently in
  the tree. Cite the commit sha and the matching line.
- **partial**: SOME of the fix shipped — a different solution was chosen for
  the same root issue, OR one of N affected files was updated, OR the
  intent shipped but the proposal's specific symbol is absent. Cite what
  shipped and what didn't.
- **open**: no commit/changelog hits AND grep confirms the original symptom
  is still present. Evidence is the absence of relevant commits since the
  proposal date.
- **unverifiable**: action is too vague to grep for (e.g. "improve error
  reporting" with no symbol named), OR the evidence corpus is insufficient
  (no commits, no CHANGELOG, no grep hits in either direction). State why.

Every non-`open` verdict MUST cite specific evidence. A verdict without
specific evidence is inadmissible — fall back to `unverifiable`.

Output ONLY the YAML list. No prose, no markdown fences.
