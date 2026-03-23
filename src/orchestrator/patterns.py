"""Cross-session pattern detection across all observations.

Aggregates observations to find:
- Recurring friction (same issue across multiple sessions/projects)
- Project hotspots (which projects have the most friction)
- Trend detection (is friction increasing or decreasing?)
"""
from collections import Counter
from pathlib import Path

from orchestrator.observations import list_observations


def detect_patterns(obs_dir: Path) -> list[dict]:
    """Scan all observations and return detected patterns."""
    all_obs = list_observations(obs_dir)
    if not all_obs:
        return []

    patterns = []
    patterns.extend(find_recurring_issues(all_obs))
    patterns.extend(find_project_hotspots(all_obs))
    return patterns


def find_recurring_issues(observations: list[dict]) -> list[dict]:
    """Group observations by type+servers and rank by frequency."""
    groups: dict[str, list[dict]] = {}
    for obs in observations:
        key = f"{obs.get('type', 'unknown')}|{','.join(sorted(obs.get('related_servers', [])))}"
        groups.setdefault(key, []).append(obs)

    patterns = []
    for key, obs_list in groups.items():
        if len(obs_list) < 2:
            continue
        obs_type, servers = key.split("|", 1)
        total_frequency = sum(o.get("frequency", 1) for o in obs_list)
        all_sessions = []
        for o in obs_list:
            all_sessions.extend(o.get("sessions", []))

        patterns.append({
            "type": "recurring_issue",
            "issue_type": obs_type,
            "related_servers": servers.split(",") if servers else [],
            "observation_count": len(obs_list),
            "total_frequency": total_frequency,
            "unique_sessions": len(set(all_sessions)),
            "descriptions": [o.get("description", "") for o in obs_list[:3]],
            "severity": max((o.get("severity", "low") for o in obs_list),
                          key=lambda s: {"high": 3, "medium": 2, "low": 1}.get(s, 0)),
            "actionable": True,
        })

    patterns.sort(key=lambda p: -p["total_frequency"])
    return patterns


def find_project_hotspots(observations: list[dict]) -> list[dict]:
    """Count issues per related server to find hotspots."""
    server_counts: Counter = Counter()
    server_severity: dict[str, list[str]] = {}

    for obs in observations:
        for server in obs.get("related_servers", []):
            server_counts[server] += 1
            server_severity.setdefault(server, []).append(obs.get("severity", "low"))

    patterns = []
    for server, count in server_counts.most_common():
        if count < 2:
            continue
        severities = server_severity[server]
        high_count = severities.count("high")
        patterns.append({
            "type": "project_hotspot",
            "server": server,
            "issue_count": count,
            "high_severity_count": high_count,
            "actionable": high_count > 0,
        })

    return patterns
