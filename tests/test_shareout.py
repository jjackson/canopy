"""Tests for the shareout gather/post pipeline (deterministic parts only)."""
import datetime as dt
import json
from pathlib import Path

import pytest

from orchestrator import shareout


# ---------------------------------------------------------------------------
# resolve_range
# ---------------------------------------------------------------------------

TODAY = dt.date(2026, 6, 4)
YESTERDAY = dt.date(2026, 6, 3)


class TestResolveRange:
    def test_default_is_yesterday_single_day(self):
        assert shareout.resolve_range(None, None, None, today=TODAY) == (YESTERDAY, YESTERDAY)

    def test_days_window_ends_yesterday(self):
        # last 7 full days ending yesterday
        assert shareout.resolve_range(None, None, 7, today=TODAY) == (
            dt.date(2026, 5, 28),
            YESTERDAY,
        )

    def test_explicit_from_and_to(self):
        assert shareout.resolve_range("2026-06-01", "2026-06-02", None, today=TODAY) == (
            dt.date(2026, 6, 1),
            dt.date(2026, 6, 2),
        )

    def test_from_only_extends_to_yesterday(self):
        assert shareout.resolve_range("2026-06-01", None, None, today=TODAY) == (
            dt.date(2026, 6, 1),
            YESTERDAY,
        )

    def test_to_only_is_single_day(self):
        assert shareout.resolve_range(None, "2026-05-01", None, today=TODAY) == (
            dt.date(2026, 5, 1),
            dt.date(2026, 5, 1),
        )

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError):
            shareout.resolve_range("2026-06-05", "2026-06-01", None, today=TODAY)


# ---------------------------------------------------------------------------
# session_in_range
# ---------------------------------------------------------------------------


class TestSessionInRange:
    def _s(self, first, last):
        return {"first_ts": first, "last_ts": last}

    def test_session_within_window(self):
        s = self._s("2026-06-03T10:00:00Z", "2026-06-03T12:00:00Z")
        assert shareout.session_in_range(s, YESTERDAY, YESTERDAY)

    def test_session_outside_window(self):
        s = self._s("2026-06-01T10:00:00Z", "2026-06-01T12:00:00Z")
        assert not shareout.session_in_range(s, YESTERDAY, YESTERDAY)

    def test_session_spanning_into_window(self):
        s = self._s("2026-06-02T23:00:00Z", "2026-06-03T01:00:00Z")
        assert shareout.session_in_range(s, YESTERDAY, YESTERDAY)

    def test_missing_timestamps_excluded(self):
        assert not shareout.session_in_range({"first_ts": None, "last_ts": None}, YESTERDAY, YESTERDAY)


# ---------------------------------------------------------------------------
# gather
# ---------------------------------------------------------------------------


def _write_transcript(path: Path, prompts, ts="2026-06-03T10:00:00Z"):
    lines = [{"type": "last-prompt", "sessionId": path.stem}]
    for p in prompts:
        lines.append({"type": "user", "message": {"content": p}, "timestamp": ts})
    path.write_text("\n".join(json.dumps(line) for line in lines))


class TestGather:
    def test_groups_by_repo_and_filters_by_date(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-Users-me-canopy"
        proj.mkdir(parents=True)
        # in-range session
        _write_transcript(proj / "s1.jsonl", ["build the shareout feed"], "2026-06-03T10:00:00Z")
        # out-of-range session (older)
        _write_transcript(proj / "s2.jsonl", ["old work"], "2026-05-01T10:00:00Z")

        repo_map = {"-Users-me-canopy": "jjackson/canopy"}
        corpus = shareout.gather(
            projects_dir=projects_dir,
            repo_map=repo_map,
            labels={},
            start=YESTERDAY,
            end=YESTERDAY,
            fetch_prs_fn=lambda *a, **k: [],
        )
        assert corpus["period"] == {"start": "2026-06-03", "end": "2026-06-03"}
        assert "jjackson/canopy" in corpus["projects"]
        sessions = corpus["projects"]["jjackson/canopy"]["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["prompts"] == ["build the shareout feed"]

    def test_prs_attached_per_repo(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-Users-me-canopy"
        proj.mkdir(parents=True)
        _write_transcript(proj / "s1.jsonl", ["work"], "2026-06-03T10:00:00Z")

        def fake_prs(repo, start, end, author="@me"):
            return [{"number": 1, "title": "Add feed", "url": "u", "state": "MERGED"}]

        corpus = shareout.gather(
            projects_dir=projects_dir,
            repo_map={"-Users-me-canopy": "jjackson/canopy"},
            labels={},
            start=YESTERDAY,
            end=YESTERDAY,
            fetch_prs_fn=fake_prs,
        )
        assert corpus["projects"]["jjackson/canopy"]["prs"][0]["number"] == 1

    def test_project_filter(self, tmp_path):
        projects_dir = tmp_path / "projects"
        for key, repo in [("-Users-me-canopy", "jjackson/canopy"), ("-Users-me-ace", "jjackson/ace")]:
            p = projects_dir / key
            p.mkdir(parents=True)
            _write_transcript(p / "s.jsonl", ["work"], "2026-06-03T10:00:00Z")
        repo_map = {"-Users-me-canopy": "jjackson/canopy", "-Users-me-ace": "jjackson/ace"}
        corpus = shareout.gather(
            projects_dir=projects_dir,
            repo_map=repo_map,
            labels={},
            start=YESTERDAY,
            end=YESTERDAY,
            project_filter="ace",
            fetch_prs_fn=lambda *a, **k: [],
        )
        assert list(corpus["projects"].keys()) == ["jjackson/ace"]


# ---------------------------------------------------------------------------
# build_post_payload
# ---------------------------------------------------------------------------


class TestBuildPostPayload:
    def _authoring(self):
        return {
            "period_start": "2026-06-03",
            "period_end": "2026-06-03",
            "author": "jjackson",
            "rollup": {"title": "Yesterday", "summary": "tl;dr", "content": "## Roll-up"},
            "projects": [
                {
                    "project_slug": "canopy",
                    "title": "Shareouts",
                    "summary": "s",
                    "content": "## What",
                    "links": [{"label": "PR #83", "url": "u"}],
                }
            ],
        }

    def test_rollup_has_null_slug_and_source_stamped(self):
        payload = shareout.build_post_payload(self._authoring(), source="canopy:shareout@T")
        items = payload["shareouts"]
        assert len(items) == 2
        rollup = items[0]
        assert rollup["project_slug"] is None
        assert rollup["source"] == "canopy:shareout@T"
        assert rollup["period_start"] == "2026-06-03"
        assert rollup["author"] == "jjackson"

    def test_project_item_carries_slug_and_links(self):
        payload = shareout.build_post_payload(self._authoring(), source="src")
        proj = payload["shareouts"][1]
        assert proj["project_slug"] == "canopy"
        assert proj["links"] == [{"label": "PR #83", "url": "u"}]
        assert proj["source"] == "src"

    def test_no_rollup_only_projects(self):
        a = self._authoring()
        a["rollup"] = None
        payload = shareout.build_post_payload(a, source="src")
        assert len(payload["shareouts"]) == 1
        assert payload["shareouts"][0]["project_slug"] == "canopy"


class TestResolveDefaultRange:
    def test_no_prior_shareout_falls_back_to_yesterday(self):
        assert shareout.resolve_default_range(None, today=TODAY) == (YESTERDAY, YESTERDAY)

    def test_continues_from_day_after_last_shareout(self):
        # last shareout ended 2026-05-31 → cover 2026-06-01 .. today (06-04)
        assert shareout.resolve_default_range(dt.date(2026, 5, 31), today=TODAY) == (
            dt.date(2026, 6, 1),
            TODAY,
        )

    def test_last_shareout_was_yesterday_covers_today(self):
        assert shareout.resolve_default_range(YESTERDAY, today=TODAY) == (TODAY, TODAY)

    def test_last_shareout_already_reaches_today_collapses_to_today(self):
        # already current (or somehow ahead) → today..today, never an inverted range
        assert shareout.resolve_default_range(TODAY, today=TODAY) == (TODAY, TODAY)
        assert shareout.resolve_default_range(dt.date(2026, 6, 9), today=TODAY) == (TODAY, TODAY)


class TestFetchLatestPeriodEnd:
    def test_parses_period_end_from_items(self, monkeypatch):
        import io
        payload = json.dumps({"items": [{"period_end": "2026-06-03"}], "total": 1}).encode()
        monkeypatch.setattr(shareout.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload))
        assert shareout.fetch_latest_period_end("https://x", "tok") == dt.date(2026, 6, 3)

    def test_empty_feed_returns_none(self, monkeypatch):
        import io
        monkeypatch.setattr(shareout.urllib.request, "urlopen",
                            lambda *a, **k: io.BytesIO(b'{"items": [], "total": 0}'))
        assert shareout.fetch_latest_period_end("https://x", "tok") is None

    def test_network_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("unreachable")
        monkeypatch.setattr(shareout.urllib.request, "urlopen", boom)
        assert shareout.fetch_latest_period_end("https://x", "tok") is None


class TestFillAllPrsFromCorpus:
    def _corpus(self):
        return {
            "period": {"start": "2026-06-03", "end": "2026-06-03"},
            "projects": {
                "jjackson/ace": {"prs": [
                    {"number": 685, "title": "auto-capture", "url": "u685", "state": "MERGED", "body": "x"},
                ]},
                "jjackson/canopy": {"prs": [
                    {"number": 124, "title": "auto-promote", "url": "u124", "state": "MERGED"},
                ]},
            },
        }

    def test_fills_by_repo_basename_match(self):
        authoring = {
            "period_start": "2026-06-03", "period_end": "2026-06-03",
            "projects": [
                {"project_slug": "ace", "title": "t", "content": "c"},
                {"project_slug": "canopy", "title": "t", "content": "c"},
            ],
        }
        shareout.fill_all_prs_from_corpus(authoring, self._corpus())
        ace = authoring["projects"][0]["all_prs"]
        assert ace == [{"number": 685, "title": "auto-capture", "url": "u685", "state": "MERGED"}]
        assert authoring["projects"][1]["all_prs"][0]["number"] == 124

    def test_does_not_overwrite_existing_all_prs(self):
        authoring = {
            "period_start": "2026-06-03", "period_end": "2026-06-03",
            "projects": [{"project_slug": "ace", "title": "t", "content": "c",
                          "all_prs": [{"number": 1, "title": "kept", "url": "u", "state": "OPEN"}]}],
        }
        shareout.fill_all_prs_from_corpus(authoring, self._corpus())
        assert authoring["projects"][0]["all_prs"][0]["title"] == "kept"

    def test_build_payload_passes_all_prs(self):
        authoring = {
            "period_start": "2026-06-03", "period_end": "2026-06-03", "author": "j",
            "projects": [{"project_slug": "ace", "title": "t", "content": "c",
                          "all_prs": [{"number": 685, "title": "x", "url": "u", "state": "MERGED"}]}],
        }
        payload = shareout.build_post_payload(authoring, source="src")
        assert payload["shareouts"][0]["all_prs"][0]["number"] == 685


def test_feed_url():
    assert shareout.feed_url("https://x.app/") == "https://x.app/shareouts"
