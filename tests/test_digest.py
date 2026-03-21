from pathlib import Path
from orchestrator.digest import generate_digest
from orchestrator.run_log import create_run_entry, save_run
from orchestrator.observations import create_observation, save_observation
from orchestrator.proposals import create_proposal, save_proposal


class TestGenerateDigest:
    def test_returns_string(self, tmp_path):
        result = generate_digest(tmp_path)
        assert isinstance(result, str)

    def test_empty_state_produces_header(self, tmp_path):
        result = generate_digest(tmp_path)
        assert "Orchestrator Digest" in result

    def test_includes_run_summary(self, tmp_path):
        runs_dir = tmp_path / "runs"
        run = create_run_entry()
        run["transcripts_analyzed"] = 3
        save_run(run, runs_dir)
        result = generate_digest(tmp_path)
        assert "3" in result

    def test_includes_pending_observations(self, tmp_path):
        obs_dir = tmp_path / "observations"
        save_observation(
            create_observation("gap", "Missing training tool", "high", "s1"),
            obs_dir,
        )
        result = generate_digest(tmp_path)
        assert "training tool" in result.lower()

    def test_writes_to_file(self, tmp_path):
        generate_digest(tmp_path, write=True)
        assert (tmp_path / "digest.md").exists()
