"""Load, save, and query project-directory-to-GitHub-repo mappings.

Supports both JSON (new, used by hook) and YAML (legacy) formats.
Reads from JSON first, falls back to YAML for migration.
"""
import json
import re
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_repo_map(path: Path) -> dict:
    """Load repo mappings. Tries JSON first, falls back to YAML."""
    # Try JSON version first
    json_path = path.with_suffix(".json") if path.suffix != ".json" else path
    if json_path.exists():
        try:
            with open(json_path) as f:
                return json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to YAML
    yaml_path = path.with_suffix(".yaml") if path.suffix != ".yaml" else path
    if yaml_path.exists() and HAS_YAML:
        try:
            with open(yaml_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass

    # Try the exact path as-is
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f) or {}
        except Exception:
            if HAS_YAML:
                try:
                    with open(path) as f:
                        return yaml.safe_load(f) or {}
                except Exception:
                    pass

    return {}


def save_repo_mapping(path: Path, project_key: str, repo: str) -> None:
    """Save a single project-to-repo mapping (as JSON)."""
    repo_map = load_repo_map(path)
    repo_map[project_key] = repo
    json_path = path.with_suffix(".json") if path.suffix != ".json" else path
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(repo_map, f, indent=2)


def get_repo_for_project(repo_map: dict, project_key: str) -> str | None:
    """Look up the GitHub repo for a project directory key."""
    return repo_map.get(project_key)


def extract_repo_from_git_url(url: str) -> str | None:
    """Extract owner/repo from a GitHub git URL."""
    if not url:
        return None
    match = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url)
    return match.group(1) if match else None
