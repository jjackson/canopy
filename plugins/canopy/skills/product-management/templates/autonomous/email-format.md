# Working-backwards email — format

Sent at the end of each `/canopy:pm-autonomous` sprint. The body is generated programmatically from the cycle log and screenshot directory — NOT freehand-written. This keeps the email honest: no inventing wins, no hand-waving past failures.

## Hard rules (every release-notes email)

These are non-negotiable. Violating any of them ships an email that looks amateur and erodes trust in the autonomous cycle.

1. **HTML body, never raw markdown.** The body is rendered to HTML and sent via the sender skill's `--body-html` flag (or equivalent). Recipients open this in Gmail / Outlook / Apple Mail — those clients render HTML; they show literal `##`, `**`, `-` characters when handed markdown. Always include a brief plain-text fallback for `--body` so non-HTML clients see something readable.
2. **PM-grade visual design, not dev-tool aesthetic.** Typographic hierarchy over bordered boxes. Restrained accent palette (one brand color, neutrals for everything else). Hero images per highlight. No literal `*` or `**` as section markers — those belong in markdown drafts, never in the rendered HTML. The reference is "Linear / Stripe / Vercel changelog" — not "GitHub issue body". See the canonical layout below.
3. **Screenshots from prod, never localhost.** Drive the deployed app via the configured `headless_browser_skill` and authenticate via the project's automation login (e.g. `/auth/e2e-login/` for ace-web). Localhost screenshots show port numbers, dev banners, and seeded fake data — recipients spot it instantly and lose trust. Some surfaces may not be reachable in prod (e.g. when a global fallback masks a "disconnected" branch as the canonical e2e user) — describe those textually rather than substituting a localhost shot.
4. **Inline images via persistent https URLs, not `cid:` references and not data: URIs.** Most `gog gmail send`-style CLIs produce `multipart/mixed` when given attachments, which means `cid:` refs in the HTML do not resolve and Gmail shows broken-image icons in the body. Data URIs are stripped in many clients. The reliable pattern: commit the screenshots to a stable branch on the project's repo (e.g. `pm-assets/<sprint-slug>`) and reference them in `<img src>` via `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` URLs. The branch is permanent so the email URLs keep resolving forever.
5. **Every feature highlight is clickable in three places: title, hero image, AND the explicit "Try it" CTA.** A small "Try it on labs →" link buried at the bottom of each card is not enough — recipients scan; they shouldn't have to hunt for the click target. Wrap each highlight's `<h2>` AND the `<img>` in `<a href="<TRY-IT-URL>">` (with `text-decoration:none` so styling is preserved). The standalone "Try it" CTA stays as a stronger explicit affordance. This matches the Linear / Stripe / Vercel changelog pattern.
6. **Internal notes belong in a small footer**, separated by a divider — not a top-level section heading. The recipient is a stakeholder, not a maintainer; engineering metadata is a footnote, not a chapter.
7. **Pre-send rendering pass (Phase E.4 gate).** Before invoking the sender skill, render the final `email.html` via the configured `headless_browser_skill` and screenshot at desktop (1280px) and mobile (375px) widths. This is a sanity check — does it actually look like a release-notes email when a real browser draws it? Save the rendered shots under the sprint screenshots dir as `email-rendered-{desktop,mobile}.png`. If anything looks off (broken image, wrap regression, palette wreck), fix the HTML and re-render before sending.

Save the rendered body to `$EMAIL_WORKDIR/email.html` (the temp working dir created at the start of Phase E) before sending. The rendered HTML and screenshots also get committed to the `pm-assets/<sprint-slug>` branch on the project's repo — that branch is the only persistent home. Nothing email-specific persists in `$CANOPY_PM_DIR`; the run log under `$CANOPY_PM_DIR/runs/<sprint-slug>.md` captures the highlights (Phase D) for future cycles to consult.

## Subject

```
<email.subject_prefix> What's new — <theme summary>
```

Theme summary is 2-5 words and comes from the surviving highlights, not from `theme_detection.lens_rotation`. Avoid "Release notes — …— YYYY-MM-DD" boilerplate; it's redundant with the email date and feels procedural.

## Layout

The HTML body uses a centered ~640px container with a brand bar, hero, per-highlight blocks, and a small footer. Each highlight block has: title (linked), 1-2 sentence body, hero screenshot (linked), italic caption, "Try it" CTA. Sections are separated by hairline dividers, NOT by `<hr>` rules or repeated borders.

Reference template (concrete colors / fonts can be tuned per project; structure is the contract):

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#f6f7f9;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f6f7f9;">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.06);overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1f2937;">

        <!-- Brand bar: dark strip with product name + date -->
        <tr><td style="padding:20px 32px;background:#0f172a;color:#fff;">
          <table role="presentation" width="100%"><tr>
            <td style="font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#94a3b8;"><PRODUCT> · release notes</td>
            <td align="right" style="font-size:13px;color:#94a3b8;"><Month Day, Year></td>
          </tr></table>
        </td></tr>

        <!-- Hero: single sharp headline + 1-2 sentence value pitch -->
        <tr><td style="padding:36px 32px 8px;">
          <h1 style="margin:0 0 12px;font-size:26px;line-height:1.25;color:#0f172a;font-weight:700;"><HEADLINE></h1>
          <p style="margin:0;font-size:16px;line-height:1.6;color:#475569;"><VALUE PITCH (1-2 sentences max — recipients absorb this in 5s)></p>
        </td></tr>

        <!-- Repeat per highlight. Note: title AND hero image both wrap in
             <a href="<TRY-IT-URL>"> per Hard rule #5 — recipients scan and
             expect every visible element to be clickable. Use text-decoration:none
             on both anchors so the styling stays clean. -->
        <tr><td style="padding:28px 32px 0;">
          <h2 style="margin:0 0 8px;font-size:18px;font-weight:600;">
            <a href="<TRY-IT-URL>" style="color:#0f172a;text-decoration:none;"><FEATURE TITLE></a>
          </h2>
          <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#334155;"><FEATURE BODY></p>
          <a href="<TRY-IT-URL>" style="text-decoration:none;display:block;">
            <img src="https://raw.githubusercontent.com/<OWNER>/<REPO>/pm-assets/<SPRINT-SLUG>/<PATH>/feature-after.png"
                 alt="<DESCRIPTIVE ALT>"
                 width="576"
                 style="display:block;width:100%;max-width:576px;height:auto;border:1px solid #e2e8f0;border-radius:8px;margin:0 0 8px;">
          </a>
          <p style="margin:0 0 18px;font-size:13px;color:#64748b;font-style:italic;">After: <CAPTION>.</p>
          <p style="margin:0 0 4px;font-size:14px;">
            <a href="<TRY-IT-URL>" style="color:#4338ca;text-decoration:none;font-weight:500;">Try it on labs →</a>
          </p>
        </td></tr>
        <tr><td style="padding:28px 32px 0;"><div style="height:1px;background:#e2e8f0;"></div></td></tr>
        <!-- ... more highlights ... -->

        <!-- Footer: small grey type, divider above, internal notes here -->
        <tr><td style="padding:36px 32px 32px;">
          <div style="height:1px;background:#e2e8f0;margin-bottom:20px;"></div>
          <p style="margin:0 0 8px;font-size:13px;color:#64748b;">
            <strong style="color:#475569;">Sprint internals.</strong> <CYCLE COUNT> autonomous cycle, <PR COUNT> bundled PR(s) (<a href="<PR-URL>" style="color:#4338ca;text-decoration:none;">#<N></a>), gates green, deploy verified.
          </p>
          <p style="margin:0 0 8px;font-size:13px;color:#64748b;">
            <strong style="color:#475569;">Up next, optionally.</strong> <CARRYOVER OR NEXT-CYCLE HINT>
          </p>
          <p style="margin:0;font-size:12px;color:#94a3b8;">Sent automatically by the autonomous PM cycle. Reply to opt out.</p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
```

Adapt copy and palette per project; do NOT skip the brand bar / hero / per-highlight image / footer divider structure, and do NOT skip the title-and-image anchors per Hard rule #5.

## Sender invocation

The sender skill is invoked with:

- `subject` (string) — see "Subject" above
- `body_html` (string) — the rendered HTML above, read from `$EMAIL_WORKDIR/email.html`
- `body_text` (string) — a one-paragraph plain-text fallback. Generic "please view as HTML" is fine; this is just for HTML-stripped clients
- `attachments` (optional list) — generally **omitted** when images are hosted via raw.githubusercontent.com URLs (the recommended path). Only attach if the sender skill explicitly supports `multipart/related` and you've embedded `cid:` refs (rare).

If the sender skill does not support an HTML body, log that limitation in the run log and send a minimal plain-text alternative — but flag this as a process bug to fix before the next sprint, NOT a per-cycle workaround.

## Image hosting (Phase E preconditions)

Before invoking the sender skill, the cycle MUST have:

1. Captured screenshots from prod (per Hard rule #3) into `$EMAIL_WORKDIR/screenshots/` (the Phase E temp working dir).
2. Committed those screenshots to a persistent branch on the **project's** git remote (the project being PM'd, not canopy itself) — by convention `pm-assets/<sprint-slug>`. Push without opening a PR; the branch is asset hosting, not a code change. Note: this is the *project repo's* origin, not the user-space `$CANOPY_PM_DIR`.
3. Verified each `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` URL returns HTTP 200 (curl -I).
4. Substituted those URLs into the `<img src>` attributes of `email.html` (the rendered file), and re-saved.

Without those four steps, the email will ship with broken images.

## Self-review (Phase E.4 pre-send + Phase E.5 post-send)

The email is the only customer-facing output of the cycle. The user's delight depends on it being good. So the cycle bookends sending with two render-and-look passes:

**E.4 — pre-send rendering (gate):**

1. Render `email.html` via `headless_browser_skill` at 1280×800 (desktop) and 375×812 (mobile).
2. Screenshot both, save as `$EMAIL_WORKDIR/screenshots/email-rendered-{desktop,mobile}.png`. They'll be pushed to the `pm-assets/<sprint-slug>` branch alongside the prod feature shots.
3. Look at the screenshots and answer the **structural checklist** (Hard-rule violations — must all PASS):
   - Do all hero images load? (Hosted https URLs return 200 — verify with curl too.)
   - Does every highlight title look like a link? (Hard rule #5: title + image must wrap in `<a>`.)
   - Is the headline a sharp single sentence, not a paragraph?
   - Does the visual hierarchy match Linear/Stripe/Vercel — typographic, not boxed?
   - Mobile: does the brand-bar text wrap awkwardly? Are images full-bleed?

   Then answer the **common-issues checklist** (visual-quality risks surfaced from real post-send critiques — flag and fix when they apply):
   - **Hero pitch length** — is the value pitch ≤ 2 punchy sentences? Three sentences reads like a lede paragraph and buries the headline. (Source: 2026-04-28-first-chat-path E.5.)
   - **Screenshot framing** — do the screenshots feel embedded, or pasted-in? Full dark-themed app shots against a light email background jar visually. Two fixes: (a) crop tighter to the new feature surface, OR (b) wrap each `<img>` in a soft frame/shadow so it reads as a figure, not a foreign object.
   - **One highlight = one image (or an honest composite)** — if the body text describes three branches/states/variants, a single screenshot showing one of them misleads. Either show a 3-up composite or rewrite the body to focus on the surface actually shown.
   - **Heavy `<code>` runs** — long literal strings rendered as inline `<code>` at body font size are too dense. Pull-quote a long literal onto its own line. In the footer, multiple inline `<code>` chunks in one sentence is noise; plain text reads better at footer scale.
   - **Sign-off line** — there should be a one-line human-feeling sign-off (e.g. `— ACE autonomous PM, on behalf of the Dimagi ACE team`) before the boilerplate "Sent automatically..." footer, otherwise the footer feels impersonal.
   - **Mobile brand-bar wrap** — at 375px, long product names (`ACE WEB · RELEASE NOTES`) wrap onto two lines. Either shorten (`ACE · RELEASE NOTES`) or stack the date below explicitly with deliberate spacing.
4. If any **structural** check fails, fix the HTML and re-render — these are gate-blocking. If any **common-issue** check flags, fix when cheap (most are 1-2 line tweaks); if a fix would derail the send and the email is otherwise strong, log the issue under E.5 and carry it to the next cycle. Do NOT send a "good enough" version on structural issues — Send is the closing of the cycle, not a thing to rush.

**E.5 — post-send self-critique (learning):**

After invoking the sender skill, the cycle does NOT stop at "sent". It writes a short critique into the run log naming 2-4 concrete improvement ideas, ranked by impact. The email is already in the recipient's inbox, so improvements feed the *next* cycle (and the canopy template, if structural). Critique against three filters:

- **Visual quality:** Linear/Stripe/Vercel changelog, or GitHub issue body? Spacing, typography, color, hierarchy.
- **Communication clarity:** as a recipient who didn't write this, does the value land in the first 5 seconds? Is the headline a sentence-level statement?
- **Technical correctness:** all images load; CTAs link to the right URL; dark-mode renders OK if the recipient client uses dark theme.

Surface the critique to the user as the closing message of the cycle. The sender skill ID, message ID, and screenshot file paths must all be in the closing message — the user should be able to see exactly what they sent and what you'd improve, without scrolling back through the cycle output.

## Stuck-state alternative

If the sprint never converged on a passable email (Phase D failed three critique passes), send a minimal alternative body — still HTML, still in the same template shell, but with no highlights and a single "no release notes this time" paragraph:

```html
<!-- Use the same shell. Replace the hero + highlights region with: -->
<tr><td style="padding:36px 32px;">
  <h1 style="margin:0 0 12px;font-size:24px;color:#0f172a;">Sprint <DATE> — no release notes this time</h1>
  <p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#475569;">
    The autonomous PM sprint did not converge on something worth shipping in customer voice today.
    The next sprint will scout against <SUGGESTED LENS> first.
  </p>
  <p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#64748b;">
    <strong>Why:</strong> <ACTUAL REASON FROM RUN LOG — self-review blocks, CI red, etc.>
  </p>
  <p style="margin:0;font-size:13px;color:#94a3b8;">
    Cycle log: <code>$CANOPY_PM_DIR/runs/<FILE>.md</code>.
  </p>
</td></tr>
```

This is a feature, not a failure mode. The whole point of the email-and-stop loop is to refuse to ship weak content.
