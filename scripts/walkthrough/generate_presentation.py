"""Generate a self-contained HTML slideshow from walkthrough run data.

Usage:
    python -m tools.walkthrough.generate_presentation --input run_data.json --output output.html

No external template engine required — HTML is built with Python string formatting.
"""

import argparse
import html
import json
import os


def _render_stars(score, max_score=5):
    """Render Unicode star rating."""
    filled = "\u2605" * score  # ★
    empty = "\u2606" * (max_score - score)  # ☆
    return f'<span class="stars">{filled}{empty}</span> ({score}/{max_score})'


def _render_score_bar(score, max_score=5):
    """Render a visual score bar with stars."""
    if score >= 5:
        bar_color = "#059669"
    elif score >= 4:
        bar_color = "#2563eb"
    elif score >= 3:
        bar_color = "#d97706"
    else:
        bar_color = "#dc2626"
    pct = int((score / max_score) * 100)
    stars = _render_stars(score, max_score)
    return f"""<div class="score-bar-row">
  <div class="score-bar-bg"><div class="score-bar-fill" style="width:{pct}%;background:{bar_color};"></div></div>
  {stars}
</div>"""


def _render_title_slide(run_data):
    """Render the title slide HTML."""
    name = html.escape(run_data["name"])
    narrative = html.escape(run_data["narrative"])
    generated = html.escape(run_data["generated_at"][:10])
    scene_count = sum(1 for s in run_data["slides"] if s["type"] == "scene")
    persona_count = len(run_data["personas"])
    ai_count = sum(1 for s in run_data["slides"] if s.get("type") == "scene" and s.get("ai_evaluation"))

    # Partial-scope banner. When the run came from /canopy:walkthrough --scene <sel>
    # (or /canopy:ddd-run --scene <sel>), the sidecar carries `scenes_run` (the orig
    # 1-based spec indices that were actually rendered) and `scene_filter` (the raw
    # selector string). Render a banner so a viewer can't mistake a partial run for
    # a full-spec run — the deck still shows "Scene 2 of 10" on the scene slide, but
    # the title makes the scope explicit. Both fields are optional and absent on
    # legacy run-data, so this is fully backward-compatible.
    scenes_run = run_data.get("scenes_run")
    scene_filter = run_data.get("scene_filter")
    partial_banner = ""
    if scene_filter and scenes_run:
        # Look up the spec scene count from any scene slide's scene_total — that's
        # the count of scenes IN THE SPEC, not the count rendered.
        spec_total = next(
            (s.get("scene_total") for s in run_data["slides"]
             if s.get("type") == "scene" and s.get("scene_total")),
            scene_count,
        )
        indices = ", ".join(str(i) for i in scenes_run)
        sel_esc = html.escape(str(scene_filter))
        partial_banner = (
            f'<div class="partial-scope-banner">'
            f'<strong>Partial run</strong> &middot; <code>--scene {sel_esc}</code> '
            f'rendered scene(s) {indices} of {spec_total}. '
            f'Promotion requires a full-spec run.'
            f"</div>"
        )

    return f"""<div class="slide slide-title">
  <div class="title-accent-bar"></div>
  <div class="title-content">
    {partial_banner}
    <h1>{name}</h1>
    <p class="narrative">&#8220;{narrative}&#8221;</p>
    <p class="title-subtitle">Walkthrough Demo &mdash; {scene_count} scenes across {persona_count} personas</p>
    <hr class="title-divider">
    <p class="meta">Generated: {generated} &middot; {ai_count} AI features evaluated</p>
  </div>
</div>"""


def _render_persona_intro(persona_key, personas):
    """Render a persona introduction slide."""
    p = personas[persona_key]
    name = html.escape(p["name"])
    role = html.escape(p["role"])
    intro = html.escape(p["intro"])
    color = html.escape(p["color"])
    initials = "".join(w[0] for w in p["name"].split()[:2])
    return f"""<div class="slide slide-persona" style="background-color: {color}0d;">
  <div class="persona-card">
    <p class="persona-up-next">Up next:</p>
    <div class="persona-avatar" style="background-color: {color}">{initials}</div>
    <h2>{name}</h2>
    <p class="persona-role">{role}</p>
    <p class="persona-intro">{intro}</p>
  </div>
</div>"""


def _render_scene_slide(slide, personas, slide_index, total_slides):
    """Render a scene slide with screenshot and optional AI evaluation."""
    persona = personas[slide["persona_key"]]
    p_name = html.escape(persona["name"])
    p_color = html.escape(persona["color"])
    title = html.escape(slide["title"])
    narration = html.escape(slide.get("narration", ""))

    # Progress bar percentage
    scene_slides_total = max(total_slides, 1)
    progress_pct = int((slide_index / scene_slides_total) * 100)

    # Scene counter: "Scene 2 of 10" using the ORIGINAL spec index + total.
    # The fields are 1-based and reflect the spec (not the rendered subset), so
    # a single-scene render for spec scene 2 still labels "Scene 2 of 10" — not
    # "Scene 1 of 1". This keeps a partial-run scene's identity stable: anyone
    # looking at the deck can see exactly which scene of the spec this is.
    scene_index_in_spec = slide.get("scene_index")
    scene_total_in_spec = slide.get("scene_total")
    if scene_index_in_spec and scene_total_in_spec:
        scene_counter_html = (
            f'<span class="scene-counter">Scene {scene_index_in_spec} '
            f"of {scene_total_in_spec}</span>"
        )
    else:
        scene_counter_html = ""

    # Screenshot or placeholder
    if slide.get("screenshot_b64"):
        img_html = f'<img src="data:image/png;base64,{slide["screenshot_b64"]}" alt="{title}" class="screenshot">'
    else:
        error_msg = html.escape(slide.get("error", "Screenshot not captured"))
        img_html = f'<div class="screenshot-placeholder"><p>{error_msg}</p></div>'

    # Context row: logged-in user and URL (both optional)
    logged_in_as = slide.get("logged_in_as")
    url = slide.get("url")
    context_parts = []
    if logged_in_as:
        context_parts.append(
            f'<span class="slide-context-user">Logged in as <strong>{html.escape(logged_in_as)}</strong></span>'
        )
    if url:
        url_esc = html.escape(url, quote=True)
        url_display = html.escape(url)
        context_parts.append(
            f'<a class="slide-context-url" href="{url_esc}" target="_blank" rel="noopener noreferrer">{url_display}</a>'
        )
    context_html = ""
    if context_parts:
        context_html = (
            '<div class="slide-context">'
            + '<span class="slide-context-sep"> &middot; </span>'.join(context_parts)
            + "</div>"
        )

    # AI evaluation card
    ai_html = ""
    if slide.get("ai_evaluation"):
        ai = slide["ai_evaluation"]
        stars = _render_stars(ai["score"], ai.get("max_score", 5))
        commentary = html.escape(ai["commentary"])
        ai_html = f"""<div class="ai-quality-card">
    <div class="ai-quality-header">&#10024; AI Quality {stars}</div>
    <p>{commentary}</p>
  </div>"""

    return f"""<div class="slide slide-scene" style="border-top: 3px solid {p_color};">
  <div class="slide-header">
    <span class="persona-badge" style="background-color: {p_color}">{p_name}</span>
    {scene_counter_html}
    <div class="slide-progress-bar"><div class="slide-progress-fill"
      style="width:{progress_pct}%;background:{p_color};"></div></div>
  </div>
  <h2>{title}</h2>
  {context_html}
  <div class="narration-box"><p class="narration">{narration}</p></div>
  {img_html}
  {ai_html}
</div>"""


def _render_summary_slide(slide, run_data):
    """Render the summary slide with scores, issues, and comparison."""
    duration = int(run_data.get("duration_seconds", 0))
    mins, secs = divmod(duration, 60)
    completed = slide["scenes_completed"]
    total = slide["scenes_total"]
    generated = html.escape(run_data["generated_at"][:16].replace("T", " "))

    # Verdict headline based on average AI score
    ai_scores_list = slide.get("ai_scores", [])
    verdict_html = ""
    if ai_scores_list:
        avg = sum(s["score"] for s in ai_scores_list) / len(ai_scores_list)
        if avg >= 4:
            verdict_html = '<p class="verdict verdict-green">Demo Ready &#10003;</p>'
        elif avg >= 3:
            verdict_html = '<p class="verdict verdict-amber">Needs Polish</p>'
        else:
            verdict_html = '<p class="verdict verdict-red">Needs Work</p>'

    # AI scores with visual bars
    scores_html = ""
    for ai in ai_scores_list:
        feature = html.escape(ai["feature"])
        bar = _render_score_bar(ai["score"], ai.get("max_score", 5))
        flag = ' <span class="focus-flag">&larr; needs work</span>' if ai["score"] <= 3 else ""
        scores_html += f"<li><span class='score-feature'>{feature}</span>{bar}{flag}</li>\n"

    # Issues
    issues_html = ""
    for issue in slide.get("issues", []):
        icon = "&#9888;" if issue["severity"] == "warning" else "&#10007;"
        desc = html.escape(issue["description"])
        issues_html += f'<li class="issue-{issue["severity"]}">{icon} Scene {issue["scene"]}: {desc}</li>\n'

    # Previous run comparison
    prev_html = ""
    prev = slide.get("previous_run")
    if prev:
        prev_date = html.escape(prev["generated_at"][:16].replace("T", " "))
        prev_html = f'<h3>Previous Run ({prev_date})</h3><ul class="comparison">'
        prev_scores = {s["feature"]: s["score"] for s in prev.get("ai_scores", [])}
        for ai in ai_scores_list:
            feat = ai["feature"]
            prev_score = prev_scores.get(feat)
            if prev_score is not None:
                if ai["score"] > prev_score:
                    arrow = f'<span class="arrow-up">&#8593;</span> {feat}: {prev_score}&rarr;{ai["score"]}'
                elif ai["score"] < prev_score:
                    arrow = f'<span class="arrow-down">&#8595;</span> {feat}: {prev_score}&rarr;{ai["score"]}'
                else:
                    arrow = f"= {feat}: unchanged"
                prev_html += f"<li>{arrow}</li>"
        prev_html += "</ul>"

    scenes_badge = f'<span class="scenes-badge">Scenes: {completed}/{total} completed</span>'

    return f"""<div class="slide slide-summary">
  <h2>Walkthrough Summary</h2>
  <p class="meta">Run: {generated} | Duration: {mins}m {secs:02d}s</p>
  {scenes_badge}
  {verdict_html}
  {"<h3>AI Quality Scores</h3><ul>" + scores_html + "</ul>" if scores_html else ""}
  {"<h3>Issues Found</h3><ul>" + issues_html + "</ul>" if issues_html else ""}
  {prev_html}
</div>"""


CSS_STYLES = """
/* Geist Variable from Google Fonts — matches canopy-web aesthetic */
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@100..900&family=Geist+Mono:wght@100..900&display=swap');

/* Dark-mode shadcn-style tokens (OKLCH). Default is dark; override
   with .light on the body to force light mode. */
:root {
  --background: #0a0a0a;
  --foreground: #fafafa;
  --card: #0a0a0a;
  --card-foreground: #fafafa;
  --muted: #171717;
  --muted-foreground: #a1a1aa;
  --border: #262626;
  --primary: #fafafa;
  --primary-foreground: #0a0a0a;
  --accent: #262626;
  --accent-foreground: #fafafa;
  --success: #10b981;
  --success-subtle: #052e22;
  --warning: #f59e0b;
  --warning-subtle: #3b2706;
  --danger: #ef4444;
  --danger-subtle: #3b0f0f;
  --info: #60a5fa;
  --info-subtle: #0c1f3a;

  --radius: 10px;
}

body.light {
  --background: #fafafa;
  --foreground: #0a0a0a;
  --card: #ffffff;
  --card-foreground: #0a0a0a;
  --muted: #f4f4f5;
  --muted-foreground: #52525b;
  --border: #e5e7eb;
  --primary: #18181b;
  --primary-foreground: #fafafa;
  --accent: #f4f4f5;
  --accent-foreground: #18181b;
  --success: #059669;
  --success-subtle: #ecfdf5;
  --warning: #d97706;
  --warning-subtle: #fffbeb;
  --danger: #dc2626;
  --danger-subtle: #fef2f2;
  --info: #2563eb;
  --info-subtle: #eff6ff;
}

/* Reset and base */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  background: var(--background);
}

body {
  font-family: 'Geist', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-feature-settings: "cv11", "ss01", "ss03";
  font-size: 16px;
  line-height: 1.6;
  color: var(--foreground);
  background: var(--background);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

code, pre, .font-mono {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
}

/* Slide system */
#presentation {
  width: 100%;
  min-height: 100vh;
}

.slide {
  display: none;
  max-width: 960px;
  margin: 0 auto;
  padding: 3rem 2rem 6rem;
  background: var(--background);
}

.slide.active {
  display: block;
  animation: fadeIn 0.25s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Scene slides get more room for screenshots */
.slide-scene {
  max-width: 1180px;
  padding-top: 2rem;
}

/* Typography */
h1 {
  font-size: 3rem;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 1rem;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

h2 {
  font-size: 1.875rem;
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 0.75rem;
  letter-spacing: -0.02em;
}

h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--foreground);
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  letter-spacing: -0.01em;
}

p {
  margin-bottom: 0.75rem;
  color: var(--muted-foreground);
}

ul {
  list-style: none;
  padding-left: 0;
  margin-bottom: 1rem;
}

ul li {
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--border);
  color: var(--muted-foreground);
}

/* Title slide */
.slide-title {
  display: none;
  align-items: flex-start;
  justify-content: center;
  flex-direction: column;
  min-height: 100vh;
  padding: 0;
  position: relative;
  overflow: hidden;
}

.slide-title.active {
  display: flex;
}

.title-accent-bar {
  width: 100%;
  height: 4px;
  background: linear-gradient(90deg, var(--info), var(--success));
  flex-shrink: 0;
}

.title-content {
  padding: 4rem 3rem 3rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  flex: 1;
  max-width: 880px;
}

.title-divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 2rem 0 1rem;
  max-width: 640px;
}

.slide-title .narrative {
  font-size: 1.25rem;
  color: var(--muted-foreground);
  margin: 1rem 0 0;
  max-width: 720px;
  line-height: 1.5;
  font-style: normal;
}

.title-subtitle {
  font-size: 0.95rem;
  color: var(--muted-foreground);
  font-weight: 500;
  margin-top: 1rem;
  margin-bottom: 0;
}

.slide-title .meta {
  font-size: 0.8rem;
  color: var(--muted-foreground);
  opacity: 0.7;
  margin-top: 0.5rem;
  margin-bottom: 0;
}

/* Persona slides */
.slide-persona {
  display: none;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  min-height: 100vh;
  text-align: center;
  background: var(--background);
}

.slide-persona.active {
  display: flex;
}

.persona-card {
  max-width: 560px;
  padding: 3rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: calc(var(--radius) * 1.6);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
}

.persona-avatar {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  color: #ffffff;
  font-size: 1.75rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1.25rem;
  letter-spacing: -0.02em;
}

.persona-up-next {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted-foreground);
  opacity: 0.7;
  margin-bottom: 1rem;
}

.persona-role {
  font-size: 1rem;
  color: var(--muted-foreground);
  font-weight: 500;
  margin-bottom: 1.25rem;
}

.persona-intro {
  font-size: 1.05rem;
  color: var(--muted-foreground);
  line-height: 1.7;
}

/* Scene slides */
.slide-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.persona-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  color: #ffffff;
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
  letter-spacing: 0.01em;
}

.slide-progress-bar {
  flex: 1;
  height: 2px;
  background: var(--muted);
  border-radius: 9999px;
  overflow: hidden;
  min-width: 60px;
}

.slide-progress-fill {
  height: 100%;
  border-radius: 9999px;
  transition: width 0.3s ease;
}

.slide-context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin-top: -0.25rem;
  margin-bottom: 1rem;
  font-size: 0.8rem;
  color: var(--muted-foreground);
}

.slide-context-user strong {
  color: var(--foreground);
  font-weight: 600;
}

.slide-context-url {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  color: var(--info);
  text-decoration: none;
  word-break: break-all;
}

.slide-context-url:hover {
  text-decoration: underline;
}

.slide-context-sep {
  color: var(--border);
}

.narration-box {
  background: var(--muted);
  border-left: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
}

.narration {
  font-size: 1rem;
  color: var(--muted-foreground);
  margin-bottom: 0;
  line-height: 1.6;
}

/* Screenshot */
.screenshot {
  width: 100%;
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  border: 1px solid var(--border);
  display: block;
  margin: 1rem 0;
}

.screenshot-placeholder {
  background: var(--muted);
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 1rem 0;
  padding: 2rem;
  text-align: center;
  color: var(--muted-foreground);
  font-size: 0.95rem;
}

/* AI quality card */
.ai-quality-card {
  border-left: 3px solid var(--info);
  background: var(--info-subtle);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: 1rem 1.25rem;
  margin-top: 1.5rem;
}

.ai-quality-header {
  font-weight: 600;
  color: var(--foreground);
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
}

.ai-quality-card p {
  color: var(--muted-foreground);
  font-size: 0.9rem;
  line-height: 1.6;
}

/* Stars */
.stars {
  color: var(--warning);
  font-size: 1.05em;
  letter-spacing: 0.05em;
}

/* Focus flag */
.focus-flag {
  color: var(--danger);
  font-size: 0.8rem;
  font-weight: 500;
}

/* Issues */
.issue-warning {
  color: var(--warning);
}

.issue-error {
  color: var(--danger);
}

.issue-info {
  color: var(--info);
}

/* Summary slide */
.verdict {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0.75rem 0 1.5rem;
  letter-spacing: -0.02em;
}

.verdict-green {
  color: var(--success);
}

.verdict-amber {
  color: var(--warning);
}

.verdict-red {
  color: var(--danger);
}

.scenes-badge {
  display: inline-block;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: 9999px;
  padding: 0.2rem 0.75rem;
  font-size: 0.8rem;
  color: var(--muted-foreground);
  font-weight: 500;
  margin-bottom: 0.75rem;
}

/* Scene counter — "Scene 2 of 10" on each scene slide header, next to
   the persona badge. Uses spec indices (not deck-slide indices), so a
   partial-run deck for spec scene 2 still reads "Scene 2 of 10". */
.scene-counter {
  display: inline-block;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: 9999px;
  padding: 0.2rem 0.65rem;
  font-size: 0.78rem;
  color: var(--muted-foreground);
  font-weight: 500;
  margin-left: 0.5rem;
}

/* Partial-scope banner on the title slide — only renders when scenes_run
   + scene_filter are set on the run-data sidecar (i.e. the run came from
   /canopy:walkthrough --scene or /canopy:ddd-run --scene). Makes "this is
   a partial run, not a promotable full pass" visible at a glance. */
.partial-scope-banner {
  display: block;
  background: rgba(217, 119, 6, 0.08);
  border: 1px solid var(--warning);
  border-radius: 0.5rem;
  padding: 0.5rem 0.85rem;
  margin: 0 0 1.25rem 0;
  font-size: 0.85rem;
  color: var(--warning);
}
.partial-scope-banner code {
  background: rgba(217, 119, 6, 0.15);
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  font-size: 0.8rem;
}

.score-feature {
  display: block;
  font-weight: 500;
  color: var(--foreground);
  margin-bottom: 0.25rem;
  font-size: 0.95rem;
}

.score-bar-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.25rem;
}

.score-bar-bg {
  flex: 1;
  height: 6px;
  background: var(--muted);
  border-radius: 4px;
  overflow: hidden;
  min-width: 80px;
  max-width: 200px;
}

.score-bar-fill {
  height: 100%;
  border-radius: 4px;
}

/* Summary slide comparison */
.comparison li {
  color: var(--muted-foreground);
}

.arrow-up {
  color: var(--success);
  font-weight: 600;
}

.arrow-down {
  color: var(--danger);
  font-weight: 600;
}

/* Summary slide */
.slide-summary {
  padding-bottom: 8rem;
}

.slide-summary .meta {
  font-size: 0.875rem;
  color: var(--muted-foreground);
  margin-bottom: 0.5rem;
}

/* Navigation controls */
#nav-progress-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: var(--muted);
  z-index: 99;
}

#nav-progress-bar-fill {
  height: 100%;
  background: var(--foreground);
  transition: width 0.2s ease;
}

#nav-controls {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 9999px;
  padding: 0.5rem 1.25rem;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  z-index: 100;
}

#nav-controls button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--foreground);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  transition: background 0.15s;
}

#nav-controls button:hover {
  background: var(--accent);
}

#nav-progress {
  font-size: 0.8rem;
  color: var(--muted-foreground);
  min-width: 60px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

#nav-slide-title {
  font-size: 0.8rem;
  color: var(--muted-foreground);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

#theme-toggle {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--muted-foreground);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  transition: background 0.15s;
}

#theme-toggle:hover {
  background: var(--accent);
}

/* Print styles */
@media print {
  body {
    background: white;
    color: #0a0a0a;
  }

  #nav-controls,
  #nav-progress-bar {
    display: none;
  }

  .slide {
    display: block !important;
    opacity: 1 !important;
    page-break-after: always;
    min-height: auto;
    border: none;
    padding: 2rem;
    background: white;
  }

  .slide:last-child {
    page-break-after: avoid;
  }

  .screenshot {
    max-width: 100%;
    box-shadow: none;
    border: 1px solid #e5e7eb;
  }
}
"""

JS_NAVIGATION = """
(function () {
  var slides = document.querySelectorAll('.slide');
  var totalSlides = slides.length;
  var currentSlide = 0;

  function showSlide(n) {
    if (totalSlides === 0) return;
    // Clamp index
    if (n < 0) n = 0;
    if (n >= totalSlides) n = totalSlides - 1;

    // Deactivate all slides
    for (var i = 0; i < totalSlides; i++) {
      slides[i].classList.remove('active');
    }

    // Activate target slide (CSS animation handles the fade)
    slides[n].classList.add('active');
    currentSlide = n;

    // Update progress indicator
    var progress = document.getElementById('nav-progress');
    if (progress) {
      progress.textContent = (currentSlide + 1) + ' / ' + totalSlides;
    }

    // Update slide title in nav
    var titleEl = document.getElementById('nav-slide-title');
    if (titleEl) {
      var h2 = slides[n].querySelector('h2');
      var h1 = slides[n].querySelector('h1');
      titleEl.textContent = (h2 && h2.textContent) || (h1 && h1.textContent) || '';
    }

    // Update bottom progress bar
    var barFill = document.getElementById('nav-progress-bar-fill');
    if (barFill) {
      barFill.style.width = Math.round(((currentSlide + 1) / totalSlides) * 100) + '%';
    }

    // Scroll to top of slide
    window.scrollTo(0, 0);
  }

  function prevSlide() {
    showSlide(currentSlide - 1);
  }

  function nextSlide() {
    showSlide(currentSlide + 1);
  }

  // Keyboard navigation
  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      nextSlide();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      prevSlide();
    }
  });

  // Build bottom progress bar
  var progressBar = document.createElement('div');
  progressBar.id = 'nav-progress-bar';
  var progressBarFill = document.createElement('div');
  progressBarFill.id = 'nav-progress-bar-fill';
  progressBar.appendChild(progressBarFill);
  document.body.appendChild(progressBar);

  // Build nav controls
  var nav = document.createElement('div');
  nav.id = 'nav-controls';

  var prevBtn = document.createElement('button');
  prevBtn.textContent = '\\u2190';
  prevBtn.title = 'Previous slide (ArrowLeft)';
  prevBtn.addEventListener('click', prevSlide);

  var progress = document.createElement('span');
  progress.id = 'nav-progress';

  var slideTitle = document.createElement('span');
  slideTitle.id = 'nav-slide-title';

  var nextBtn = document.createElement('button');
  nextBtn.textContent = '\\u2192';
  nextBtn.title = 'Next slide (ArrowRight)';
  nextBtn.addEventListener('click', nextSlide);

  // Theme toggle: dark is the default, user can flip to light
  var themeBtn = document.createElement('button');
  themeBtn.id = 'theme-toggle';
  themeBtn.title = 'Toggle light/dark (T)';
  var updateThemeIcon = function () {
    themeBtn.textContent = document.body.classList.contains('light') ? '\\u263C' : '\\u263D';
  };
  updateThemeIcon();
  var toggleTheme = function () {
    document.body.classList.toggle('light');
    try {
      localStorage.setItem('walkthrough-theme',
        document.body.classList.contains('light') ? 'light' : 'dark');
    } catch (e) {}
    updateThemeIcon();
  };
  themeBtn.addEventListener('click', toggleTheme);
  document.addEventListener('keydown', function (e) {
    if (e.key === 't' || e.key === 'T') {
      toggleTheme();
    }
  });
  // Restore saved theme (default dark)
  try {
    if (localStorage.getItem('walkthrough-theme') === 'light') {
      document.body.classList.add('light');
      updateThemeIcon();
    }
  } catch (e) {}

  nav.appendChild(prevBtn);
  nav.appendChild(progress);
  nav.appendChild(slideTitle);
  nav.appendChild(nextBtn);
  nav.appendChild(themeBtn);
  document.body.appendChild(nav);

  // Initialize
  showSlide(0);
})();
"""


def generate(run_data, output_path):
    """Generate HTML slideshow and JSON sidecar from run data."""
    slides_html_parts = []
    personas = run_data["personas"]
    total_slides = len(run_data["slides"])
    seen_personas = set()
    slide_index = 0

    for slide in run_data["slides"]:
        slide_index += 1
        if slide["type"] == "title":
            slides_html_parts.append(_render_title_slide(run_data))
        elif slide["type"] == "persona_intro":
            seen_personas.add(slide["persona_key"])
            slides_html_parts.append(_render_persona_intro(slide["persona_key"], personas))
        elif slide["type"] == "scene":
            slides_html_parts.append(_render_scene_slide(slide, personas, slide_index, total_slides))
        elif slide["type"] == "summary":
            slides_html_parts.append(_render_summary_slide(slide, run_data))

    slides_html = "\n".join(slides_html_parts)
    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(run_data["name"])}</title>
<style>{CSS_STYLES}</style>
</head>
<body>
<div id="presentation">{slides_html}</div>
<script>{JS_NAVIGATION}</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    # Write JSON sidecar for run history comparison
    sidecar_path = os.path.splitext(output_path)[0] + ".json"
    summary_slide = next((s for s in run_data["slides"] if s["type"] == "summary"), {})
    sidecar = {
        "name": run_data["name"],
        "generated_at": run_data["generated_at"],
        "duration_seconds": run_data["duration_seconds"],
        "scenes_completed": summary_slide.get("scenes_completed", 0),
        "scenes_total": summary_slide.get("scenes_total", 0),
        "ai_scores": summary_slide.get("ai_scores", []),
        "issues": summary_slide.get("issues", []),
    }
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate walkthrough HTML presentation")
    parser.add_argument("--input", required=True, help="Path to JSON run data")
    parser.add_argument("--output", required=True, help="Path to write HTML")
    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        run_data = json.load(f)

    generate(run_data, args.output)


if __name__ == "__main__":
    main()
