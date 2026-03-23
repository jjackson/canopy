# Scout Prompt Template

Use this template when prompting Claude Code for the scout phase.

```
Explore this project.

Before starting: Read `.claude/pm/context.md` for project context — especially "What Matters Most".

Before starting: Read `.claude/pm/learnings.md` — do NOT re-propose any closed or rejected items listed there.

Read CLAUDE.md first. Then:
1. git log --oneline -20 (understand recent momentum)
2. Run the test suite: {test_command}
3. Check for TODO.md, open issues, or known gaps
4. Through the lens of [{lens}], find the top 5 improvement opportunities

For each, provide: Title, What (specific files), Why it matters, Effort (S/M/L), How to validate, Risk.

Focus on changes that are concrete, testable, and can ship independently.
Do NOT suggest vague refactors or "add more tests everywhere." Be specific.
Check what already exists before proposing additions — verify current state.
For any finding you believe is a bug or broken behavior: try to write a failing test
that demonstrates the problem. If you can write one, include it. If you can't, explain why.
```
