"""Tests for scripts/ddd/promote.py (SP7).

All HTTP calls, file uploads, and review gates are mocked — no network, no
real sleeping, no canopy-web dependency.
"""
from __future__ import annotations

import html
from pathlib import Path

import pytest
import yaml

from scripts.ddd.schemas.models import RunState, Scene, UnifiedSpec, WhyBrief, SpineItem, Persona
from scripts.ddd.promote import build_docs_page, publish_artifact, promote


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_spec() -> UnifiedSpec:
    return UnifiedSpec(
        name="Smart Routing",
        narrative="Route smarter, not harder.",
        base_url="https://example.com",
        personas={
            "alice": Persona(
                name="Alice",
                role="Field worker",
                color="#2563eb",
                intro="Alice manages daily visits.",
            )
        },
        scenes=[
            Scene(
                persona="alice",
                title="Scene 1",
                show="Open the app and tap Routes.",
                concept_claim="Instantly see your optimised route for the day.",
                provenance="SP1",
            ),
            Scene(
                persona="alice",
                title="Scene 2",
                show="Tap Start to begin navigation.",
                concept_claim="Turn-by-turn navigation with live traffic.",
                provenance="SP2",
            ),
        ],
    )


def _make_why_brief() -> WhyBrief:
    return WhyBrief(
        feature="Smart Routing",
        problem="Field workers spend 40% of their day navigating inefficiently.",
        spine=[
            SpineItem(
                id="s1",
                claim="Route optimisation saves 2 hours per worker per day.",
                rationale="Internal pilot with 20 workers showed 1.8h average saving.",
            ),
            SpineItem(
                id="s2",
                claim="Live traffic avoids delays at peak hours.",
                rationale="Traffic API integration reduces average trip time by 12%.",
            ),
        ],
        gaps=[],
    )


# ---------------------------------------------------------------------------
# build_docs_page — content tests
# ---------------------------------------------------------------------------


class TestBuildDocsPage:
    def test_contains_video_url(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://example.com/hero.mp4")
        assert "https://example.com/hero.mp4" in result

    def test_contains_feature_name(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "Smart Routing" in result

    def test_contains_every_concept_claim(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        for scene in spec.scenes:
            assert scene.concept_claim in result, (
                f"concept_claim {scene.concept_claim!r} missing from HTML"
            )

    def test_contains_why_brief_problem(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        # May be HTML-escaped — check for escaped version
        assert "Field workers spend 40%" in result or html.escape(why.problem) in result

    def test_contains_section_headers(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "What you can do" in result
        assert "Why it works this way" in result

    def test_walkthrough_section_dropped(self):
        # The build-audience scene `show` walkthrough is NOT rendered on the user
        # docs page — the hero video is the walkthrough; the shows reference internal UI.
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "What the demo walks through" not in result

    def test_contains_spine_claims(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        for item in why.spine:
            assert item.claim in result or html.escape(item.claim) in result

    def test_xss_in_concept_claim_is_escaped(self):
        """Malicious concept_claim must not appear as raw HTML."""
        spec = _make_spec()
        spec.scenes[0].concept_claim = '<script>alert("xss")</script>'
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "<script>" not in result
        # The escaped version must be present (or entirely absent, but never raw)
        assert "&lt;script&gt;" in result or "alert" not in result

    def test_xss_in_show_is_escaped(self):
        spec = _make_spec()
        spec.scenes[0].show = '<img src=x onerror=alert(1)>'
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "<img src=x onerror=alert(1)>" not in result

    def test_xss_in_why_problem_is_escaped(self):
        spec = _make_spec()
        why = _make_why_brief()
        why.problem = '<script>bad()</script>'
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "<script>" not in result

    def test_xss_in_spine_rationale_is_escaped(self):
        spec = _make_spec()
        why = _make_why_brief()
        why.spine[0].rationale = '<b onmouseover="evil()">text</b>'
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert 'onmouseover="evil()"' not in result

    def test_is_valid_html_structure(self):
        """Smoke-check: has DOCTYPE, html, head, body tags."""
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "<head>" in result
        assert "<body>" in result

    def test_share_page_url_uses_iframe(self):
        """URLs containing /w/ (canopy-web viewer) should embed as iframe."""
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://canopy.example.com/w/abc123?t=tok")
        assert "<iframe" in result

    def test_plain_mp4_url_uses_video_tag(self):
        """Direct .mp4 URLs should embed as <video>."""
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://cdn.example.com/video.mp4")
        assert "<video" in result

    def test_data_uri_video_uses_video_tag(self):
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "data:video/mp4;base64,AAAA")
        assert "<video" in result

    def test_no_external_css_or_js_deps(self):
        """The page must be self-contained — no external stylesheet or script src."""
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        # Allow <script> tags (for inline JS) but not <script src="http...
        import re
        external_scripts = re.findall(r'<script[^>]+src=["\']https?://', result)
        external_css = re.findall(r'<link[^>]+href=["\']https?://', result)
        assert not external_scripts, f"External script srcs found: {external_scripts}"
        assert not external_css, f"External CSS links found: {external_css}"

    def test_scenes_in_order(self):
        """Scene concept_claims should appear in the same order as spec.scenes."""
        spec = _make_spec()
        why = _make_why_brief()
        result = build_docs_page(spec, why, "https://x.test/v.mp4")
        pos0 = result.index(spec.scenes[0].concept_claim)
        pos1 = result.index(spec.scenes[1].concept_claim)
        assert pos0 < pos1, "Scenes must appear in spec order"


# ---------------------------------------------------------------------------
# publish_artifact — HTTP injection tests
# ---------------------------------------------------------------------------


class TestPublishArtifact:
    def _mock_post(self, *, wid="art123", share_token="tok99"):
        """Return a fake _post callable that records call args."""
        calls: list[dict] = []

        def fake_post(url, pat, fields, filename, content_type, file_bytes):
            calls.append(
                dict(
                    url=url,
                    pat=pat,
                    fields=fields,
                    filename=filename,
                    content_type=content_type,
                    file_bytes=file_bytes,
                )
            )
            return {"id": wid, "share_token": share_token}

        fake_post.calls = calls
        return fake_post

    def test_returns_hosted_url(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        mock = self._mock_post(wid="abc", share_token="s1")
        url = publish_artifact(
            "<html>hi</html>",
            kind="html",
            title="Test doc",
            base_url="https://canopy.test",
            _post=mock,
        )
        assert "abc" in url
        assert url.startswith("https://canopy.test/w/")

    def test_posts_to_walkthroughs_endpoint(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        mock = self._mock_post()
        publish_artifact(
            b"video bytes",
            kind="video",
            title="Hero",
            base_url="https://canopy.test",
            _post=mock,
        )
        assert mock.calls[0]["url"] == "https://canopy.test/api/walkthroughs/"

    def test_html_kind_sets_correct_content_type(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        mock = self._mock_post()
        publish_artifact(
            "<html></html>",
            kind="html",
            title="Doc",
            base_url="https://canopy.test",
            _post=mock,
        )
        assert mock.calls[0]["content_type"] == "text/html"

    def test_video_kind_sets_correct_content_type(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        mock = self._mock_post()
        publish_artifact(
            b"\x00\x00",
            kind="video",
            title="Vid",
            base_url="https://canopy.test",
            _post=mock,
        )
        assert mock.calls[0]["content_type"] == "video/mp4"

    def test_invalid_kind_raises(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        with pytest.raises(ValueError, match="kind"):
            publish_artifact("x", kind="pdf", title="bad", _post=self._mock_post())

    def test_str_content_encoded_as_utf8(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        mock = self._mock_post()
        publish_artifact(
            "héllo",
            kind="html",
            title="enc",
            base_url="https://canopy.test",
            _post=mock,
        )
        assert mock.calls[0]["file_bytes"] == "héllo".encode("utf-8")

    def test_includes_share_token_in_url_when_present(self, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        mock = self._mock_post(wid="xyz", share_token="mytok")
        url = publish_artifact(
            b"data",
            kind="video",
            title="v",
            base_url="https://canopy.test",
            _post=mock,
        )
        assert "mytok" in url

    def test_url_without_share_token(self, monkeypatch):
        """When server returns no share_token, URL still works (no ?t= param)."""
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")

        def fake_post(url, pat, fields, filename, content_type, file_bytes):
            return {"id": "noshare"}  # no share_token key

        url = publish_artifact(
            b"data",
            kind="video",
            title="v",
            base_url="https://canopy.test",
            _post=fake_post,
        )
        assert url == "https://canopy.test/w/noshare"
        assert "?" not in url


# ---------------------------------------------------------------------------
# promote — orchestration tests
# ---------------------------------------------------------------------------


def _write_run_fixtures(tmp_ddd: Path, run_id: str):
    """Write minimal run_state.yaml, unified_spec.yaml, why_brief.yaml."""
    run_dir = tmp_ddd / "runs" / run_id
    run_dir.mkdir(parents=True)

    spec = _make_spec()
    why = _make_why_brief()

    # run_state.yaml
    state = RunState(run_id=run_id, feature="Smart Routing", phase="converged")
    (run_dir / "run_state.yaml").write_text(
        yaml.dump(state.model_dump(), default_flow_style=False, allow_unicode=True)
    )

    # unified_spec.yaml
    (run_dir / "unified_spec.yaml").write_text(
        yaml.dump(spec.model_dump(), default_flow_style=False, allow_unicode=True)
    )

    # why_brief.yaml
    (run_dir / "why_brief.yaml").write_text(
        yaml.dump(why.model_dump(), default_flow_style=False, allow_unicode=True)
    )

    return run_dir


class TestPromote:
    @pytest.fixture()
    def tmp_run(self, tmp_path, monkeypatch):
        """Set up a tmp DDD dir, a run, and a dummy video file."""
        import scripts.ddd.runstate as rs
        import scripts.ddd.promote as pm

        # Point _resolve_ddd_dir to tmp_path
        monkeypatch.setattr(rs, "_resolve_ddd_dir", lambda: tmp_path)
        monkeypatch.setattr(pm, "_resolve_ddd_dir", lambda: tmp_path)

        run_id = "smart-routing-2026-01-01-001"
        run_dir = _write_run_fixtures(tmp_path, run_id)

        # Dummy video file
        video_file = tmp_path / "hero.mp4"
        video_file.write_bytes(b"\x00\x01\x02\x03")

        return {"run_id": run_id, "run_dir": run_dir, "video_path": str(video_file), "ddd": tmp_path}

    def _make_uploader(self, calls_store: list) -> object:
        """Return a fake _upload callable that records calls and returns fake URLs."""
        counter = {"n": 0}

        def fake_upload(
            content, *, kind, title, base_url=None, token=None,
            run_id=None, feature=None, role=None,
        ):
            counter["n"] += 1
            url = f"https://canopy.test/w/fake-{kind}-{counter['n']}"
            calls_store.append({
                "kind": kind, "title": title, "content_len": len(content), "url": url,
                "run_id": run_id, "feature": feature, "role": role,
            })
            return url

        return fake_upload

    def _make_gate(self, choice: str):
        """Return a gate callable that returns *choice* immediately."""
        gate_calls: list[dict] = []

        def fake_gate(review_request, base_url, token):
            gate_calls.append({"gate": review_request.gate, "run_id": review_request.run_id})
            return choice

        fake_gate.calls = gate_calls
        return fake_gate

    def test_publish_returns_docs_url(self, tmp_run, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("publish")

        url = promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        assert url.startswith("https://canopy.test/w/")
        # Both video and html must have been uploaded
        kinds = [c["kind"] for c in upload_calls]
        assert "video" in kinds
        assert "html" in kinds

    def test_publish_sets_phase_promoted(self, tmp_run, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("publish")

        promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        # Reload from disk and check phase
        import scripts.ddd.runstate as rs
        state = rs.load(tmp_run["run_id"])
        assert state.phase == "promoted"

    def test_hold_does_not_upload_html(self, tmp_run, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("hold")

        result = promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        assert result == ""
        # Video upload may still happen (gate is post-video), but HTML must NOT be uploaded
        html_uploads = [c for c in upload_calls if c["kind"] == "html"]
        assert html_uploads == [], "HTML must not be uploaded when gate returns 'hold'"

    def test_hold_leaves_phase_unchanged(self, tmp_run, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("hold")

        promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        import scripts.ddd.runstate as rs
        state = rs.load(tmp_run["run_id"])
        assert state.phase == "converged", "Phase must stay 'converged' when gate returns 'hold'"

    def test_gate_receives_external_release_gate(self, tmp_run, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("publish")

        promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        assert len(gate.calls) == 1
        assert gate.calls[0]["gate"] == "external_release"

    def test_video_url_embedded_in_docs_html(self, tmp_run, monkeypatch):
        """The HTML uploaded must contain the video URL returned by the video upload."""
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("publish")

        promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        video_upload = next(c for c in upload_calls if c["kind"] == "video")
        html_upload = next(c for c in upload_calls if c["kind"] == "html")

        # DDD-run grouping: promoted artifacts carry run_id/feature + their role.
        assert video_upload["role"] == "hero_video"
        assert html_upload["role"] == "docs"
        assert video_upload["run_id"] == tmp_run["run_id"]
        assert html_upload["run_id"] == tmp_run["run_id"]
        assert video_upload["feature"] and html_upload["feature"]

        # The HTML content (bytes) should contain the video URL
        # upload content_len > 0 is checked; to check URL we need to capture bytes
        # Re-run with a more detailed mock to capture the HTML bytes
        html_bytes_store: list[bytes] = []

        def capturing_upload(
            content, *, kind, title, base_url=None, token=None,
            run_id=None, feature=None, role=None,
        ):
            if kind == "html":
                html_bytes_store.append(content if isinstance(content, bytes) else content.encode("utf-8"))
                return "https://canopy.test/w/html-99"
            return "https://canopy.test/w/video-88"

        promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=capturing_upload,
            _gate=self._make_gate("publish"),
        )

        assert html_bytes_store, "HTML was not uploaded"
        html_content = html_bytes_store[0].decode("utf-8")
        # The video URL embedded in the HTML is whatever video upload returned
        assert "https://canopy.test/w/video-88" in html_content

    def test_auto_approve_bypasses_gate(self, tmp_run, monkeypatch):
        """auto_approve_for_test=True should skip _gate entirely."""
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)

        gate_called = []

        def should_not_be_called(*args, **kwargs):
            gate_called.append(True)
            return "hold"

        url = promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=should_not_be_called,
            auto_approve_for_test=True,
        )

        assert not gate_called, "Gate must not be called when auto_approve_for_test=True"
        assert url  # Should return docs URL

    def test_gate_run_id_matches(self, tmp_run, monkeypatch):
        monkeypatch.setenv("CANOPY_WEB_PAT", "test-pat")
        upload_calls: list[dict] = []
        uploader = self._make_uploader(upload_calls)
        gate = self._make_gate("publish")

        promote(
            tmp_run["run_id"],
            video_path=tmp_run["video_path"],
            base_url="https://canopy.test",
            _upload=uploader,
            _gate=gate,
        )

        assert gate.calls[0]["run_id"] == tmp_run["run_id"]
