from pathlib import Path
from orchestrator.run_log import create_run_entry, save_run, load_run, get_last_run_ts

class TestCreateRunEntry:
    def test_returns_dict(self):
        run = create_run_entry()
        assert isinstance(run, dict)

    def test_has_started_ts(self):
        run = create_run_entry()
        assert "started" in run

    def test_has_empty_results(self):
        run = create_run_entry()
        assert run["transcripts_analyzed"] == 0
        assert run["observations_created"] == 0
        assert run["proposals_generated"] == 0
        assert run["proposals_implemented"] == 0

class TestSaveAndLoad:
    def test_round_trip(self, tmp_path):
        run = create_run_entry()
        run["transcripts_analyzed"] = 3
        path = save_run(run, tmp_path)
        loaded = load_run(path)
        assert loaded["transcripts_analyzed"] == 3

    def test_filename_includes_timestamp(self, tmp_path):
        run = create_run_entry()
        path = save_run(run, tmp_path)
        assert "run-" in path.name

class TestGetLastRunTs:
    def test_no_runs_returns_none(self, tmp_path):
        assert get_last_run_ts(tmp_path) is None

    def test_returns_latest_started_ts(self, tmp_path):
        run1 = create_run_entry()
        run1["started"] = "2026-03-20T10:00:00"
        save_run(run1, tmp_path)
        run2 = create_run_entry()
        run2["started"] = "2026-03-20T14:00:00"
        save_run(run2, tmp_path)
        assert get_last_run_ts(tmp_path) == "2026-03-20T14:00:00"
