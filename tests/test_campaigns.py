from pathlib import Path
from orchestrator.campaigns import (
    create_campaign, save_campaign, load_campaign,
    list_campaigns, advance_campaign,
)


class TestCreateCampaign:
    def test_returns_dict(self):
        c = create_campaign("Fix auth", ["o1"], ["p1"])
        assert isinstance(c, dict)

    def test_has_id(self):
        c = create_campaign("Fix auth", ["o1"], ["p1"])
        assert "id" in c

    def test_starts_active(self):
        c = create_campaign("Fix auth", ["o1"], ["p1"])
        assert c["status"] == "active"

    def test_has_observed_phase(self):
        c = create_campaign("Fix auth", ["o1"], ["p1"])
        assert c["phases"][0]["name"] == "observed"


class TestSaveLoadRoundTrip:
    def test_round_trip(self, tmp_path):
        c = create_campaign("Test campaign", ["o1"], ["p1"], description="Test desc")
        path = save_campaign(c, tmp_path)
        loaded = load_campaign(path)
        assert loaded["title"] == "Test campaign"
        assert loaded["description"] == "Test desc"

    def test_list_campaigns(self, tmp_path):
        save_campaign(create_campaign("A", ["o1"], ["p1"]), tmp_path)
        save_campaign(create_campaign("B", ["o2"], ["p2"]), tmp_path)
        assert len(list_campaigns(tmp_path)) == 2

    def test_filter_by_status(self, tmp_path):
        c1 = create_campaign("A", ["o1"], ["p1"])
        c2 = advance_campaign(create_campaign("B", ["o2"], ["p2"]), "completed")
        save_campaign(c1, tmp_path)
        save_campaign(c2, tmp_path)
        assert len(list_campaigns(tmp_path, status="active")) == 1
        assert len(list_campaigns(tmp_path, status="completed")) == 1


class TestAdvanceCampaign:
    def test_adds_phase(self):
        c = create_campaign("Test", ["o1"], ["p1"])
        c = advance_campaign(c, "implementing")
        assert len(c["phases"]) == 2
        assert c["phases"][-1]["name"] == "implementing"

    def test_sets_status(self):
        c = create_campaign("Test", ["o1"], ["p1"])
        c = advance_campaign(c, "implementing")
        assert c["status"] == "implementing"

    def test_completed_sets_status(self):
        c = create_campaign("Test", ["o1"], ["p1"])
        c = advance_campaign(c, "completed")
        assert c["status"] == "completed"

    def test_adds_note(self):
        c = create_campaign("Test", ["o1"], ["p1"])
        c = advance_campaign(c, "implementing", note="Started implementation")
        assert "Started implementation" in c["notes"]
