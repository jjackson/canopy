import json

import pytest
from click.testing import CliRunner

from orchestrator.cli import main


@pytest.fixture
def fake_http(monkeypatch):
    calls = []

    def transport(method, url, headers, body):
        calls.append((method, url, json.loads(body) if body else None))
        return (200, "{}")

    monkeypatch.setenv("CANOPY_WEB_PAT", "t")
    monkeypatch.setenv("CANOPY_WEB_API_URL", "https://x.test")
    monkeypatch.setattr("orchestrator.canopy_web.urllib_transport", transport)
    return calls


def test_eval_score_weighted(tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps([
        {"name": "design", "score": 90, "weight": 2},
        {"name": "correctness", "score": 60, "weight": 1},
    ]))
    r = CliRunner().invoke(main, ["eval", "score", "--rubric-json", str(f)])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["overall_score"] == 80.0 and out["verdict"] == "pass"


def test_eval_record_judge_from_rubric(fake_http, tmp_path):
    f = tmp_path / "r.json"
    f.write_text(json.dumps([{"name": "design", "score": 90, "weight": 1}]))
    r = CliRunner().invoke(main, [
        "eval", "record", "--slug", "echo", "--run-id", "R1", "--step", "render",
        "--rubric-json", str(f),
    ])
    assert r.exit_code == 0, r.output
    method, url, body = fake_http[0]
    assert method == "POST"
    assert url == "https://x.test/api/agents/echo/runs/R1/steps/render/verdict"
    assert body["kind"] == "judge" and body["score"] == 90.0
    assert body["criteria"]["verdict"] == "pass"


def test_eval_record_qa_passed(fake_http):
    r = CliRunner().invoke(main, [
        "eval", "record", "--slug", "echo", "--run-id", "R1", "--step", "render",
        "--kind", "qa", "--passed",
    ])
    assert r.exit_code == 0, r.output
    method, url, body = fake_http[0]
    assert url.endswith("/runs/R1/steps/render/verdict")
    assert body["kind"] == "qa" and body["passed"] is True
