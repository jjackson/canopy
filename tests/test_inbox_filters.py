"""Fleet inbox filters — idempotent apply via gog (framework single-source-of-truth)."""
import json
from types import SimpleNamespace
from orchestrator import inbox_filters


def test_filters_conservative_and_complete():
    for f in inbox_filters.FILTERS:
        assert f["query"] and f["archive"] and f["mark_read"] and f["name"]


def _runner(list_json, create_rc=0):
    def run(cmd, capture_output, text, timeout):
        if "list" in cmd:
            return SimpleNamespace(returncode=0, stdout=list_json, stderr="")
        return SimpleNamespace(returncode=create_rc, stdout='{"threads": []}', stderr="boom" if create_rc else "")
    return run


def test_apply_creates_when_none_and_is_idempotent():
    r = _runner('{"filters": null}')
    res = inbox_filters.apply_filters("hal@x", "canopy", runner=r)
    assert res["applied"] == [f["name"] for f in inbox_filters.FILTERS]
    existing = json.dumps({"filters": [{"criteria": {"query": f["query"]}} for f in inbox_filters.FILTERS]})
    res2 = inbox_filters.apply_filters("hal@x", "canopy", runner=_runner(existing))
    assert res2["applied"] == []


def test_apply_raises_on_error():
    import pytest
    with pytest.raises(inbox_filters.FilterError):
        inbox_filters.apply_filters("hal@x", "canopy", runner=_runner('{"filters": null}', create_rc=1))
