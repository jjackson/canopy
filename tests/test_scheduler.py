from pathlib import Path
from orchestrator.scheduler import generate_plist, PLIST_NAME


class TestGeneratePlist:
    def test_returns_xml(self):
        plist = generate_plist(Path("/tmp/project"))
        assert "<?xml" in plist
        assert "plist" in plist

    def test_includes_project_dir(self):
        plist = generate_plist(Path("/tmp/my-project"))
        assert "/tmp/my-project" in plist

    def test_includes_interval(self):
        plist = generate_plist(Path("/tmp/p"), interval_hours=4)
        assert "14400" in plist  # 4 * 3600

    def test_default_interval_is_8_hours(self):
        plist = generate_plist(Path("/tmp/p"))
        assert "28800" in plist  # 8 * 3600

    def test_includes_python_path(self):
        plist = generate_plist(Path("/tmp/p"), python_path="/usr/bin/python3.11")
        assert "/usr/bin/python3.11" in plist


class TestPlistName:
    def test_has_plist_extension(self):
        assert PLIST_NAME.endswith(".plist")
