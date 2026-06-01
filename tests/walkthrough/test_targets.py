"""Unit tests for target parsing + heuristic (no Playwright required).

Each test pins one behavioural rule from ``_lib/targets.py``. Together they
guarantee that:

  - Explicit prefixes (``css:``, ``testid:``, ``aria:``, ``role:``, ``text:``)
    are parsed and routed correctly.
  - The selector-vs-text heuristic doesn't misclassify the common cases the
    microplans-10-wards spec actually uses.
  - ``to_css_selector`` materialises the shorthand prefixes into real CSS.
"""

from __future__ import annotations

import sys
from pathlib import Path

# tests/ → repo-root/scripts importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.targets import (  # noqa: E402
    looks_like_selector,
    parse_target,
    to_css_selector,
)


# ---- parse_target ---------------------------------------------------------


def test_parse_target_empty():
    assert parse_target("") == ("auto", "")


def test_parse_target_no_prefix_is_auto():
    assert parse_target("Resolved wards") == ("auto", "Resolved wards")
    assert parse_target("#cfg-strategy") == ("auto", "#cfg-strategy")


def test_parse_target_css_prefix():
    assert parse_target("css:#cfg-strategy") == ("css", "#cfg-strategy")


def test_parse_target_testid_prefix():
    assert parse_target("testid:plan-picker") == ("testid", "plan-picker")


def test_parse_target_aria_prefix():
    assert parse_target("aria:Resolved wards") == ("aria", "Resolved wards")


def test_parse_target_role_prefix():
    assert parse_target("role:option") == ("role", "option")


def test_parse_target_text_prefix_forces_text_path():
    # Note: the value RETAINS its content unchanged — the prefix is consumed,
    # the rest is the target. So `text:#hashtag` is "look for the literal
    # text '#hashtag'", which is exactly what an author wants when a label
    # contains a # but the heuristic would treat it as a CSS id.
    assert parse_target("text:#hashtag") == ("text", "#hashtag")


def test_parse_target_unknown_prefix_is_left_alone():
    # "blah:foo" is NOT a recognised prefix, so the whole thing stays in
    # value with kind=auto. Authors who typo a prefix get a heuristic match
    # against the literal "blah:foo" string, not a silent change of meaning.
    assert parse_target("blah:foo") == ("auto", "blah:foo")


# ---- looks_like_selector --------------------------------------------------


def test_looks_like_selector_empty_is_false():
    assert looks_like_selector("") is False
    assert looks_like_selector("   ") is False


def test_looks_like_selector_leading_punct_is_true():
    assert looks_like_selector("#cfg-strategy") is True
    assert looks_like_selector(".btn-primary") is True
    assert looks_like_selector("[data-testid=foo]") is True
    assert looks_like_selector(":focus") is True
    assert looks_like_selector("> li.active") is True


def test_looks_like_selector_plain_text_is_false():
    # The cases that the old `wait_for` stacked 12s of hang on, one each.
    assert looks_like_selector("Resolved wards") is False
    assert looks_like_selector("Creating 10 plans") is False
    assert looks_like_selector("Plan metric definitions") is False


def test_looks_like_selector_compound_selector_is_true():
    # The microplans-10-wards spec uses these — they must be recognised.
    assert looks_like_selector("tr.is-unresolved select") is True
    assert looks_like_selector("#resolved-tbody tr.is-unresolved select") is True
    assert looks_like_selector("#plan-picker > label:nth-of-type(1) input.psel") is True


def test_looks_like_selector_word_with_dot_is_true():
    # "input.psel" is an unprefixed tag.class — should resolve as a selector.
    assert looks_like_selector("input.psel") is True


# ---- to_css_selector ------------------------------------------------------


def test_to_css_selector_explicit_css():
    assert to_css_selector("css", "#x") == "#x"


def test_to_css_selector_testid_shorthand():
    assert to_css_selector("testid", "plan-picker") == '[data-testid="plan-picker"]'


def test_to_css_selector_aria_shorthand():
    assert to_css_selector("aria", "Resolved wards") == '[aria-label*="Resolved wards"]'


def test_to_css_selector_role_shorthand():
    assert to_css_selector("role", "option") == '[role="option"]'


def test_to_css_selector_auto_routes_via_heuristic():
    # Bare text → no CSS.
    assert to_css_selector("auto", "Resolved wards") is None
    # Bare selector → CSS.
    assert to_css_selector("auto", "#cfg-strategy") == "#cfg-strategy"


def test_to_css_selector_text_kind_returns_none():
    # Explicit text: stays text, even when content looks like CSS.
    assert to_css_selector("text", "#hashtag") is None
