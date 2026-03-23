from pathlib import Path
import yaml
from orchestrator.registry_sync import scan_mcp_tools, sync_registry


FIXTURE_REGISTRY = Path(__file__).parent / "fixtures" / "sample_registry.yaml"


class TestScanMcpTools:
    def test_finds_decorated_functions(self, tmp_path):
        mcp_dir = tmp_path / "mcp"
        mcp_dir.mkdir()
        (mcp_dir / "server.py").write_text('''
from mcp import Server
mcp = Server("test")

@mcp.tool()
async def search_docs(query: str):
    pass

@mcp.tool()
async def create_folder(name: str):
    pass

def helper_not_a_tool():
    pass
''')
        tools = scan_mcp_tools(tmp_path, "mcp")
        names = [t["name"] for t in tools]
        assert "search_docs" in names
        assert "create_folder" in names
        assert "helper_not_a_tool" not in names

    def test_handles_server_dot_tool(self, tmp_path):
        mcp_dir = tmp_path / "mcp"
        mcp_dir.mkdir()
        (mcp_dir / "server.py").write_text('''
@server.tool()
def my_tool():
    pass
''')
        tools = scan_mcp_tools(tmp_path, "mcp")
        assert len(tools) == 1
        assert tools[0]["name"] == "my_tool"

    def test_returns_empty_for_missing_dir(self, tmp_path):
        assert scan_mcp_tools(tmp_path, "nonexistent") == []

    def test_skips_venv(self, tmp_path):
        venv_dir = tmp_path / "mcp" / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "something.py").write_text('@mcp.tool()\nasync def hidden(): pass')
        assert scan_mcp_tools(tmp_path, "mcp") == []


class TestSyncRegistry:
    def test_detects_new_tools(self, tmp_path):
        # Create a mini registry
        reg = {
            "version": 1,
            "updated": "2026-01-01",
            "domains": {
                "test": {
                    "servers": {
                        "test-server": {
                            "repo": str(tmp_path / "repo"),
                            "mcp_path": "mcp/",
                            "tools": [
                                {"name": "existing_tool", "description": "exists"},
                            ],
                        }
                    }
                }
            }
        }
        reg_path = tmp_path / "registry.yaml"
        with open(reg_path, "w") as f:
            yaml.dump(reg, f)

        # Create repo with existing + new tool
        mcp_dir = tmp_path / "repo" / "mcp"
        mcp_dir.mkdir(parents=True)
        (mcp_dir / "server.py").write_text('''
@mcp.tool()
async def existing_tool(): pass

@mcp.tool()
async def new_tool(): pass
''')

        summary = sync_registry(reg_path)
        assert "new_tool" in summary["test-server"]["added"]
        assert summary["test-server"]["unchanged"] == 1

        # Verify registry was updated
        with open(reg_path) as f:
            updated = yaml.safe_load(f)
        tool_names = [t["name"] for t in updated["domains"]["test"]["servers"]["test-server"]["tools"]]
        assert "new_tool" in tool_names
        assert "existing_tool" in tool_names

    def test_detects_removed_tools(self, tmp_path):
        reg = {
            "version": 1,
            "updated": "2026-01-01",
            "domains": {
                "test": {
                    "servers": {
                        "test-server": {
                            "repo": str(tmp_path / "repo"),
                            "mcp_path": "mcp/",
                            "tools": [
                                {"name": "old_tool", "description": "gone"},
                                {"name": "still_here", "description": "stays"},
                            ],
                        }
                    }
                }
            }
        }
        reg_path = tmp_path / "registry.yaml"
        with open(reg_path, "w") as f:
            yaml.dump(reg, f)

        mcp_dir = tmp_path / "repo" / "mcp"
        mcp_dir.mkdir(parents=True)
        (mcp_dir / "server.py").write_text('@mcp.tool()\nasync def still_here(): pass')

        summary = sync_registry(reg_path)
        assert "old_tool" in summary["test-server"]["removed"]
        assert summary["test-server"]["unchanged"] == 1
