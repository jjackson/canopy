"""Load, save, and query project-directory-to-GitHub-repo mappings."""
import re
from pathlib import Path

import yaml


def load_repo_map(path: Path) -> dict:
    """Load repo mappings from a YAML file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {}


def save_repo_mapping(path: Path, project_key: str, repo: str) -> None:
    """Save a single project-to-repo mapping."""
    repo_map = load_repo_map(path)
    repo_map[project_key] = repo
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(repo_map, f, default_flow_style=False, sort_keys=False)


def get_repo_for_project(repo_map: dict, project_key: str) -> str | None:
    """Look up the GitHub repo for a project directory key."""
    return repo_map.get(project_key)


def extract_repo_from_git_url(url: str) -> str | None:
    """Extract owner/repo from a GitHub git URL."""
    if not url:
        return None
    match = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url)
    return match.group(1) if match else None
