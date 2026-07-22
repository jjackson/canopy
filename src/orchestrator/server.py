"""HTTP server with JSON API for the transcript browser."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from orchestrator.labels import load_labels, save_label, get_label
from orchestrator.repo_map import load_repo_map, save_repo_mapping
from orchestrator.scanner import scan_all_transcripts, scan_transcript
from orchestrator.observations import (
    list_observations, create_observation, save_observation,
    find_matching_observation, merge_observation,
)
from orchestrator.proposals import list_proposals, create_proposal, save_proposal
from orchestrator.reviewer import load_review


def get_transcripts(projects_dir: Path, state_dir: Path) -> list[dict]:
    """Get all transcripts with labels and repo mapping."""
    labels = load_labels(state_dir / "labels.yaml")
    repo_map = load_repo_map(state_dir / "repo-map.json")
    return scan_all_transcripts(projects_dir, repo_map=repo_map, labels=labels)


def save_label_data(state_dir: Path, session_id: str, data: dict) -> None:
    """Save label data for a session."""
    save_label(
        state_dir / "labels.yaml",
        session_id,
        quality=data.get("quality"),
        use_case_tags=data.get("use_case_tags"),
        eval_candidate=data.get("eval_candidate"),
        notes=data.get("notes"),
    )


def create_app(
    projects_dir: Path,
    state_dir: Path,
):
    """Create an HTTP request handler class with the given configuration."""

    class AppHandler(BaseHTTPRequestHandler):

        def _get_transcripts(self):
            return get_transcripts(projects_dir, state_dir)

        def _save_label(self, session_id, data):
            save_label_data(state_dir, session_id, data)

        def _send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode())

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length))

        def _parse_path(self):
            return urlparse(self.path).path.rstrip("/")

        def do_GET(self):
            path = self._parse_path()

            if path == "" or path == "/":
                self._serve_static()
            elif path == "/api/transcripts":
                self._send_json(self._get_transcripts())
            elif path.startswith("/api/transcript/"):
                session_id = path.split("/")[-1]
                self._handle_get_transcript(session_id)
            else:
                self.send_error(404)

        def do_POST(self):
            path = self._parse_path()

            if path.startswith("/api/labels/"):
                session_id = path.split("/")[-1]
                data = self._read_body()
                self._save_label(session_id, data)
                self._send_json({"ok": True})
            elif path.startswith("/api/analyze/"):
                session_id = path.split("/")[-1]
                self._handle_analyze(session_id)
            elif path.startswith("/api/propose/"):
                session_id = path.split("/")[-1]
                self._handle_propose(session_id)
            elif path.startswith("/api/review/"):
                session_id = path.split("/")[-1]
                self._handle_review(session_id)
            elif path.startswith("/api/repo-map/"):
                project_key = path.split("/")[-1]
                data = self._read_body()
                save_repo_mapping(
                    state_dir / "repo-map.json",
                    project_key,
                    data.get("repo", ""),
                )
                self._send_json({"ok": True})
            else:
                self.send_error(404)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def _serve_static(self):
            static_path = Path(__file__).parent / "static" / "index.html"
            if not static_path.exists():
                self.send_error(404, "index.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(static_path.read_bytes())

        def _handle_get_transcript(self, session_id):
            from orchestrator.transcripts import read_transcript
            # Find the transcript file
            for project_dir in projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                for jsonl in project_dir.glob("*.jsonl"):
                    if jsonl.stem == session_id:
                        entries = read_transcript(jsonl)
                        self._send_json(entries)
                        return
            self.send_error(404, "Transcript not found")

        def _handle_analyze(self, session_id):
            from orchestrator.analyzer import analyze_transcript

            transcript_path = self._find_transcript(session_id)
            if not transcript_path:
                self._send_json({"error": "Transcript not found"}, 404)
                return

            observations = analyze_transcript(transcript_path)

            # Save observations with deduplication
            obs_dir = state_dir / "observations"
            existing = list_observations(obs_dir, status="pending")
            saved = []
            for obs_data in observations:
                obs = create_observation(
                    obs_type=obs_data.get("type", "gap"),
                    description=obs_data.get("description", ""),
                    severity=obs_data.get("severity", "medium"),
                    session_id=session_id,
                    related_servers=obs_data.get("related_servers", []),
                    lifecycle_stage=obs_data.get("lifecycle_stage"),
                )
                match = find_matching_observation(obs, existing)
                if match:
                    merged = merge_observation(match, session_id)
                    save_observation(merged, obs_dir)
                    saved.append(merged)
                else:
                    save_observation(obs, obs_dir)
                    existing.append(obs)
                    saved.append(obs)

            self._send_json(saved)

        def _handle_propose(self, session_id):
            from orchestrator.proposer import generate_proposals

            # Find observations for this session
            obs_dir = state_dir / "observations"
            all_obs = list_observations(obs_dir, status="pending")
            session_obs = [o for o in all_obs if session_id in o.get("sessions", [])]

            if not session_obs:
                self._send_json({"error": "No observations found. Run Analyze first."}, 400)
                return

            proposals_raw = generate_proposals(session_obs)

            proposals_dir = state_dir / "proposals"
            saved = []
            for p_data in proposals_raw:
                proposal = create_proposal(
                    proposal_type=p_data.get("type", "new_tool"),
                    action=p_data.get("action", ""),
                    target_repo=p_data.get("target_repo", ""),
                    ownership=p_data.get("ownership", "self"),
                    motivation=p_data.get("motivation", ""),
                    observation_id=p_data.get("observation_id", ""),
                    complexity=p_data.get("complexity", "medium"),
                    verification=p_data.get("verification"),
                )
                save_proposal(proposal, proposals_dir)
                saved.append(proposal)

            self._send_json(saved)

        def _handle_review(self, session_id):
            from orchestrator.reviewer import run_review, save_review

            transcript_path = self._find_transcript(session_id)
            if not transcript_path:
                self._send_json({"error": "Transcript not found"}, 404)
                return

            content = run_review(transcript_path)

            if content is None:
                self._send_json({"error": "Review failed"}, 500)
                return

            reviews_dir = state_dir / "ai-reviews"
            save_review(reviews_dir, session_id, content)
            self._send_json({"content": content})

        def _find_transcript(self, session_id):
            for project_dir in projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                for jsonl in project_dir.glob("*.jsonl"):
                    if jsonl.stem == session_id:
                        return jsonl
            return None

        def log_message(self, format, *args):
            print(f"[server] {args[0] if args else ''}")

    return AppHandler


def run_server(
    projects_dir: Path,
    state_dir: Path,
    port: int = 8484,
):
    """Start the transcript browser server."""
    handler = create_app(projects_dir, state_dir)
    server = HTTPServer(("127.0.0.1", port), handler)
    print(f"Transcript browser running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()
