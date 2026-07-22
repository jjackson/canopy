from orchestrator.router import classify_proposal, route_proposal


class TestClassifyProposal:
    def test_new_tool_is_single(self):
        assert classify_proposal({"type": "new_tool"}) == "single"

    def test_tool_improvement_is_single(self):
        assert classify_proposal({"type": "tool_improvement"}) == "single"

    def test_new_server_is_team(self):
        assert classify_proposal({"type": "new_server"}) == "team"

    def test_high_complexity_overrides_to_team(self):
        assert classify_proposal({"type": "new_tool", "complexity": "high"}) == "team"

    def test_low_complexity_stays_single(self):
        assert classify_proposal({"type": "new_tool", "complexity": "low"}) == "single"

    def test_unknown_type_defaults_to_single(self):
        assert classify_proposal({"type": "something_new"}) == "single"


class TestRouteProposal:
    def test_returns_tier(self):
        result = route_proposal({"type": "new_tool"})
        assert result["tier"] == "single"

    def test_returns_budget(self):
        result = route_proposal({"type": "new_tool"})
        assert result["budget"] == 2.00

    def test_team_has_higher_budget(self):
        result = route_proposal({"type": "new_server"})
        assert result["budget"] > route_proposal({"type": "new_tool"})["budget"]
