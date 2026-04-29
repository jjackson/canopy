# Working-backwards email — format

Sent at the end of each `/canopy:pm-autonomous` sprint. The body is generated programmatically from the cycle log and screenshot directory — NOT freehand-written. This keeps the email honest: no inventing wins, no hand-waving past failures.

Save the rendered body to `$CANOPY_PM_DIR/sent-emails/<YYYY-MM-DD-theme-slug>/email.md` before sending.

## Subject

```
<email.subject_prefix> Release notes — <theme summary> — <YYYY-MM-DD>
```

Theme summary is 2-5 words; come from the surviving highlights, not from `theme_detection.lens_rotation`.

## Body

```markdown
# What's new in <product>

> 2-3 sentence customer pitch — what's better today than yesterday, framed as the value to the user / LLO / contributor. No PR numbers, no jargon.

## Highlights

- **<Feature 1>** — One sentence. Why it matters to you.

  ![<feature-1 screenshot>](screenshots/feature-1-after.png)

  *Try it:* one-line instruction with a clickable URL.

- **<Feature 2>** — …

  ![<feature-2 walkthrough>](screenshots/feature-2-walkthrough.png)

  *Try it:* …

(3-6 highlights; one per shipped item or grouped if they tell one story. Every "Try it" highlight has at least one screenshot from the dogfood pass.)

## Walkthrough

> Optional: if multiple features compose into a single user journey, embed a 2-4 panel sequence showing the journey end-to-end.

---

## * Internal notes

**Sprint summary:** <theme>, <N PRs>, <X cycles>, <Y minutes wall-clock>.

**What shipped (engineering view):**

| PR  | Lens                | Title                       | Self-review verdict   |
|-----|---------------------|-----------------------------|-----------------------|
| #143 | user-value         | …                           | "would defend in CR"  |
| #144 | adoption-blockers  | …                           | "would defend in CR"  |

**Self-review blocks (proposals dropped before PR):**
- `<title>` — blocked on Q3 ("can't name what a senior would object to" → blind spot suspected in <area>)
- `<title>` — blocked on Q5 ("hesitated on vacation-test")

**Deploy / health:**
- N deploys, all green
- (or: "deploy-X failed at <step>, fixed forward in PR#Y, see cycle log")

**What I'd do next** (suggestion, not commitment):
- One or two specific lenses or surfaces with the most untapped value.

---

## ** Canopy self-improvement notes

Process improvements I made to the `canopy:product-management` skill this sprint (separately committed PRs to `jjackson/canopy`):

- **<insight>** — link to canopy PR#Z. What changed and why.
- **<insight>** — …

If no canopy improvements this sprint, this section says "No new universal lessons this sprint."
```

## Sender invocation

Invoke `email.sender_skill` with:

- `subject` (string)
- `body_markdown` (the rendered file above)
- `attachments` (list of absolute paths, one per screenshot referenced in the body)

If the configured sender skill does not support attachments, log that limitation in the run log and send body-only — the recipient can browse the repo to see screenshots. Do NOT block on attachment support; the email is still worth sending.

## Stuck-state alternative

If the sprint never converged on a passable email (Phase D failed three critique passes), send a minimal alternative body:

```markdown
# Sprint <date> — no release notes this time

The autonomous PM sprint did not converge on something worth shipping in customer voice today. Cycle log: `~/.canopy/pm/<project>/runs/<file>.md`. The next sprint will scout against <suggested lens> first.

Why this happened (one paragraph):
<the actual reason from the run log — self-review blocks, repeated CI red, etc.>
```

This is a feature, not a failure mode. The whole point of the email-and-stop loop is to refuse to ship weak content.
