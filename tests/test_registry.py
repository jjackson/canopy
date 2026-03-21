"""Tests for orchestrator.registry module."""

import textwrap
from pathlib import Path

import pytest
import yaml

from orchestrator.registry import (
    RegistryError,
    format_for_skill,
    get_all_servers,
    get_all_tools,
    get_server,
    get_workflows,
    load_registry,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_REGISTRY = FIXTURES_DIR / "sample_registry.yaml"


# ---------------------------------------------------------------------------
# load_registry
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_loads_sample_registry(self):
        registry = load_registry(SAMPLE_REGISTRY)
        assert isinstance(registry, dict)

    def test_version_present(self):
        registry = load_registry(SAMPLE_REGISTRY)
        assert registry["version"] == 1

    def test_domains_present(self):
        registry = load_registry(SAMPLE_REGISTRY)
        assert "domains" in registry
        assert "connect" in registry["domains"]

    def test_missing_file_raises_registry_error(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(RegistryError, match="not found"):
            load_registry(missing)

    def test_invalid_yaml_raises_registry_error(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("key: [unclosed bracket\n")
        with pytest.raises(RegistryError, match="parse"):
            load_registry(bad_yaml)

    def test_missing_version_raises_registry_error(self, tmp_path):
        no_version = tmp_path / "no_version.yaml"
        no_version.write_text("domains: {}\n")
        with pytest.raises(RegistryError, match="version"):
            load_registry(no_version)

    def test_non_dict_yaml_raises_registry_error(self, tmp_path):
        list_yaml = tmp_path / "list.yaml"
        list_yaml.write_text("- item1\n- item2\n")
        with pytest.raises(RegistryError, match="version"):
            load_registry(list_yaml)


# ---------------------------------------------------------------------------
# get_all_servers
# ---------------------------------------------------------------------------


class TestGetAllServers:
    @pytest.fixture(autouse=True)
    def registry(self):
        self.registry = load_registry(SAMPLE_REGISTRY)

    def test_returns_two_servers(self):
        servers = get_all_servers(self.registry)
        assert len(servers) == 2

    def test_server_names(self):
        servers = get_all_servers(self.registry)
        names = {s["name"] for s in servers}
        assert names == {"commcare-hq", "solicitations"}

    def test_servers_annotated_with_name(self):
        servers = get_all_servers(self.registry)
        for server in servers:
            assert "name" in server

    def test_servers_annotated_with_domain(self):
        servers = get_all_servers(self.registry)
        for server in servers:
            assert server["domain"] == "connect"

    def test_server_preserves_original_fields(self):
        servers = get_all_servers(self.registry)
        commcare = next(s for s in servers if s["name"] == "commcare-hq")
        assert commcare["description"] == "CommCare app structure"
        assert commcare["data_access"] == "read-only"

    def test_empty_registry_returns_empty_list(self):
        result = get_all_servers({"version": 1})
        assert result == []

    def test_domain_with_no_servers_returns_empty_list(self):
        registry = {"version": 1, "domains": {"empty": {"description": "no servers"}}}
        result = get_all_servers(registry)
        assert result == []


# ---------------------------------------------------------------------------
# get_server
# ---------------------------------------------------------------------------


class TestGetServer:
    @pytest.fixture(autouse=True)
    def registry(self):
        self.registry = load_registry(SAMPLE_REGISTRY)

    def test_finds_known_server(self):
        server = get_server(self.registry, "commcare-hq")
        assert server is not None
        assert server["name"] == "commcare-hq"

    def test_finds_second_server(self):
        server = get_server(self.registry, "solicitations")
        assert server is not None
        assert server["name"] == "solicitations"

    def test_returns_none_for_unknown_server(self):
        result = get_server(self.registry, "does-not-exist")
        assert result is None

    def test_returned_server_has_domain(self):
        server = get_server(self.registry, "commcare-hq")
        assert server["domain"] == "connect"

    def test_returned_server_has_tools(self):
        server = get_server(self.registry, "commcare-hq")
        assert isinstance(server["tools"], list)
        assert len(server["tools"]) == 2


# ---------------------------------------------------------------------------
# get_all_tools
# ---------------------------------------------------------------------------


class TestGetAllTools:
    @pytest.fixture(autouse=True)
    def registry(self):
        self.registry = load_registry(SAMPLE_REGISTRY)

    def test_returns_four_tools(self):
        tools = get_all_tools(self.registry)
        assert len(tools) == 4

    def test_tool_names(self):
        tools = get_all_tools(self.registry)
        names = {t["name"] for t in tools}
        assert names == {
            "get_app_structure",
            "get_form_questions",
            "create_solicitation",
            "list_solicitations",
        }

    def test_tools_annotated_with_server(self):
        tools = get_all_tools(self.registry)
        for tool in tools:
            assert "server" in tool

    def test_tools_annotated_with_domain(self):
        tools = get_all_tools(self.registry)
        for tool in tools:
            assert tool["domain"] == "connect"

    def test_tool_server_annotation_is_correct(self):
        tools = get_all_tools(self.registry)
        app_tool = next(t for t in tools if t["name"] == "get_app_structure")
        assert app_tool["server"] == "commcare-hq"

    def test_tool_preserves_description(self):
        tools = get_all_tools(self.registry)
        app_tool = next(t for t in tools if t["name"] == "get_app_structure")
        assert app_tool["description"] == "Full tree of modules and forms"

    def test_empty_registry_returns_empty_list(self):
        result = get_all_tools({"version": 1})
        assert result == []


# ---------------------------------------------------------------------------
# get_workflows
# ---------------------------------------------------------------------------


class TestGetWorkflows:
    @pytest.fixture(autouse=True)
    def registry(self):
        self.registry = load_registry(SAMPLE_REGISTRY)

    def test_returns_dict(self):
        workflows = get_workflows(self.registry)
        assert isinstance(workflows, dict)

    def test_contains_create_solicitation(self):
        workflows = get_workflows(self.registry)
        assert "create-solicitation" in workflows

    def test_workflow_has_description(self):
        workflows = get_workflows(self.registry)
        wf = workflows["create-solicitation"]
        assert wf["description"] == "Create a solicitation for a Connect program"

    def test_workflow_has_steps(self):
        workflows = get_workflows(self.registry)
        steps = workflows["create-solicitation"]["steps"]
        assert len(steps) == 2
        assert steps[0]["server"] == "commcare-hq"
        assert steps[1]["server"] == "solicitations"

    def test_workflow_has_trigger_phrases(self):
        workflows = get_workflows(self.registry)
        triggers = workflows["create-solicitation"]["trigger_phrases"]
        assert "create a solicitation for {program}" in triggers

    def test_empty_registry_returns_empty_dict(self):
        result = get_workflows({"version": 1})
        assert result == {}


# ---------------------------------------------------------------------------
# format_for_skill
# ---------------------------------------------------------------------------


class TestFormatForSkill:
    @pytest.fixture(autouse=True)
    def registry(self):
        self.registry = load_registry(SAMPLE_REGISTRY)
        self.output = format_for_skill(self.registry)

    def test_returns_string(self):
        assert isinstance(self.output, str)

    def test_contains_main_heading(self):
        assert "# Capability Registry" in self.output

    def test_contains_domain_heading(self):
        assert "## Domain: connect" in self.output

    def test_contains_server_headings(self):
        assert "### Server: commcare-hq" in self.output
        assert "### Server: solicitations" in self.output

    def test_contains_server_descriptions(self):
        assert "CommCare app structure" in self.output
        assert "Manage solicitations" in self.output

    def test_contains_answers(self):
        assert "What forms does {app} have?" in self.output
        assert "Create a solicitation for {program}" in self.output

    def test_contains_tool_names(self):
        assert "get_app_structure" in self.output
        assert "create_solicitation" in self.output

    def test_contains_workflow_section(self):
        assert "## Workflows" in self.output

    def test_contains_workflow_name(self):
        assert "### Workflow: create-solicitation" in self.output

    def test_contains_workflow_description(self):
        assert "Create a solicitation for a Connect program" in self.output

    def test_contains_workflow_steps(self):
        assert "commcare-hq" in self.output
        assert "Explore app structure" in self.output

    def test_contains_trigger_phrases(self):
        assert "create a solicitation for {program}" in self.output

    def test_contains_data_access(self):
        assert "read-only" in self.output
        assert "read-write" in self.output

    def test_empty_registry_returns_minimal_output(self):
        minimal = format_for_skill({"version": 1})
        assert "# Capability Registry" in minimal

    def test_no_workflows_section_when_none(self):
        registry_no_wf = {"version": 1, "domains": {}}
        output = format_for_skill(registry_no_wf)
        assert "## Workflows" not in output
