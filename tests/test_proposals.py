from pathlib import Path
import pytest
from orchestrator.proposals import (
    create_proposal, save_proposal, load_proposal,
    list_proposals, update_proposal_status,
)

class TestCreateProposal:
    def test_returns_dict(self):
        p = create_proposal(proposal_type="new_tool", action="Create generate_training_manual tool", target_repo="~/emdash-projects/connect-labs", ownership="self", motivation="No tool for training materials", observation_id="obs-abc")
        assert isinstance(p, dict)

    def test_has_required_fields(self):
        p = create_proposal(proposal_type="new_tool", action="Create generate_training_manual tool", target_repo="~/emdash-projects/connect-labs", ownership="self", motivation="No tool for training materials", observation_id="obs-abc")
        assert p["type"] == "new_tool"
        assert p["action"] == "Create generate_training_manual tool"
        assert p["target_repo"] == "~/emdash-projects/connect-labs"
        assert p["ownership"] == "self"
        assert p["status"] == "pending"

    def test_has_id_and_date(self):
        p = create_proposal("new_tool", "test", "~/repo", "self", "why", "obs-1")
        assert "id" in p
        assert "created" in p

    def test_complexity_defaults_to_medium(self):
        p = create_proposal("new_tool", "test", "~/repo", "self", "why", "obs-1")
        assert p["complexity"] == "medium"

    def test_custom_complexity(self):
        p = create_proposal("new_tool", "test", "~/repo", "self", "why", "obs-1", complexity="low")
        assert p["complexity"] == "low"

class TestSaveLoadRoundTrip:
    def test_save_creates_file(self, tmp_path):
        p = create_proposal("new_tool", "test", "~/r", "self", "why", "obs-1")
        path = save_proposal(p, tmp_path)
        assert path.exists()

    def test_round_trip(self, tmp_path):
        p = create_proposal("new_tool", "test action", "~/r", "self", "why", "obs-1")
        path = save_proposal(p, tmp_path)
        loaded = load_proposal(path)
        assert loaded["action"] == "test action"
        assert loaded["type"] == "new_tool"

class TestListProposals:
    def test_empty_dir(self, tmp_path):
        assert list_proposals(tmp_path) == []

    def test_finds_proposals(self, tmp_path):
        save_proposal(create_proposal("new_tool", "t1", "~/r", "self", "w", "o1"), tmp_path)
        save_proposal(create_proposal("improvement", "t2", "~/r", "self", "w", "o2"), tmp_path)
        assert len(list_proposals(tmp_path)) == 2

    def test_filter_by_status(self, tmp_path):
        save_proposal(create_proposal("new_tool", "t1", "~/r", "self", "w", "o1"), tmp_path)
        assert len(list_proposals(tmp_path, status="pending")) == 1
        assert len(list_proposals(tmp_path, status="implemented")) == 0

class TestUpdateStatus:
    def test_updates_status(self, tmp_path):
        p = create_proposal("new_tool", "t1", "~/r", "self", "w", "o1")
        path = save_proposal(p, tmp_path)
        update_proposal_status(path, "implemented")
        loaded = load_proposal(path)
        assert loaded["status"] == "implemented"

    def test_updates_status_to_failed(self, tmp_path):
        p = create_proposal("new_tool", "t1", "~/r", "self", "w", "o1")
        path = save_proposal(p, tmp_path)
        update_proposal_status(path, "failed", reason="Tests did not pass")
        loaded = load_proposal(path)
        assert loaded["status"] == "failed"
        assert loaded["failure_reason"] == "Tests did not pass"
