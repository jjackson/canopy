# Implement Prompt Template

Use this template when prompting Claude Code for the implementation phase.
Delegate to superpowers skills for planning, TDD, and branch management — don't reinvent those workflows.

```
Implement: {title}

Branch: {prefix}/{slug}

What to do:
{spec}

Acceptance criteria:
{validation}

Constraints:
- Follow existing patterns (check CLAUDE.md)
- Include tests for new behavior
- Don't modify unrelated code
- Keep the PR small and reviewable

Steps:
1. Create branch: git checkout -b {prefix}/{slug}
2. Use /test-driven-development to write failing tests first, then implement
3. Run: {test_command}
4. Run /simplify to clean up code reuse, quality, and efficiency issues
5. If validation fails, fix and re-run. If you can't fix after 2 attempts, report what's failing and stop.
6. Use /verification-before-completion before claiming done
7. Use /create-pr to commit, push, and open the PR
8. Report: what changed, test results, anything surprising
```
