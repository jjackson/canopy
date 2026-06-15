"""external-systems links come from the render manifest (resolved URLs).

Reading links from the manifest (not the spec) means every URL is fully
resolved — no unsubstituted ${...} placeholders — and includes the pages the
run actually navigated to mid-scene (urls_visited), e.g. a freshly-created
audit page.
"""
from scripts.ddd.upload import _external_links_from_manifest


def test_links_from_manifest_resolved_and_include_visited():
    manifest = {
        "base_url": "https://labs",
        "slides": [
            {
                "type": "scene",
                "title": "Amani opens",
                "url": "https://labs/labs/workflow/3149/run/?run_id=4318",
                "urls_visited": [
                    "https://labs/labs/workflow/3149/run/?run_id=4318",
                    "https://labs/audit/4317/bulk/?opportunity_id=10000",
                ],
            }
        ],
    }
    urls = [l["url"] for l in _external_links_from_manifest(manifest)]
    assert all("${" not in u for u in urls)
    assert "https://labs/audit/4317/bulk/?opportunity_id=10000" in urls


def test_links_base_first_and_deduped():
    manifest = {
        "base_url": "https://labs/",
        "slides": [
            {"type": "scene", "title": "A", "url": "https://labs/a", "urls_visited": ["https://labs/a"]},
            {"type": "scene", "title": "B", "url": "https://labs/b", "urls_visited": []},
            # a non-scene slide is ignored
            {"type": "summary"},
        ],
    }
    links = _external_links_from_manifest(manifest)
    assert links[0] == {"label": "App", "url": "https://labs", "kind": "reference"}
    assert [l["url"] for l in links] == ["https://labs", "https://labs/a", "https://labs/b"]
    assert all(l["kind"] == "reference" for l in links)


def test_links_drop_unsubstituted_placeholder_urls():
    manifest = {
        "base_url": "https://labs",
        "slides": [
            {"type": "scene", "title": "Tmpl", "url": "https://labs/${wk4_url}", "urls_visited": []},
        ],
    }
    urls = [l["url"] for l in _external_links_from_manifest(manifest)]
    assert urls == ["https://labs"]  # only the base; the ${...} url is dropped
