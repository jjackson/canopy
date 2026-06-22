#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block local-patching of Claude plugin cache.

Canopy's CLAUDE.md explicitly forbids "local patching" — copying, rsyncing,
writing, or otherwise mutating files under ``~/.claude/plugins/cache/`` or
``~/.claude/plugins/installed_plugins.json``. The proper update path is
``/canopy:update`` after bumping VERSION + ``plugin.json`` together.

This hook intercepts mutating ``Bash`` / ``Edit`` / ``Write`` / ``MultiEdit``
calls touching those paths and blocks them with a clear remediation message.
Set ``CANOPY_ALLOW_CACHE_PATCH=1`` in the environment to override (the hook
will then allow the call but emit a warning to stderr).

Stdlib-only — runs under system python3 which may not have third-party deps.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

# Tools we care about. Anything else is silently allowed.
_GUARDED_TOOLS = {"Bash", "Edit", "Write", "MultiEdit"}

# Mutating Bash command tokens. Match conservatively — false negatives are
# fine, false positives are the real cost. We look for these as the first
# token of a (possibly piped/&&-joined) statement, OR for shell redirects
# in the raw command string.
_MUTATING_COMMANDS = {
    "rsync",
    "cp",
    "mv",
    "tee",
    "rm",
    "ln",
    "sed",
    "install",
    "touch",
    "chmod",
    "chown",
}

# CLAUDE.md sentence we surface verbatim when blocking.
_CLAUDE_MD_QUOTE = (
    "Never directly copy, rsync, or write files into "
    "`~/.claude/plugins/cache/` or edit `~/.claude/plugins/installed_plugins.json` "
    "by hand. This is \"local patching\" and it bypasses the plugin system, "
    "creates version mismatches, and makes bugs hard to diagnose."
)

_REMEDIATION = (
    "Use `/canopy:update` instead: bump VERSION + plugins/canopy/.claude-plugin/"
    "plugin.json (matching), commit, push to main, then run /canopy:update "
    "and /reload-plugins. Override this guard with CANOPY_ALLOW_CACHE_PATCH=1 "
    "only when you have a deliberate reason."
)

# Hint shown when a blocked command LOOKS like a hand-rolled update (it writes into
# plugins/cache/). The sanctioned marketplace→cache copy IS auto-exempted, so if you hit
# this you deviated from the canonical form — almost always: a relative rsync source after
# `cd` (so `plugins/marketplaces/` isn't in the command string), or an `rm` bundled in the
# same statement (deletions are never exempted). This points you back at the canonical form.
_SANCTIONED_HINT = (
    "If this IS the sanctioned plugin update, it's auto-allowed only in the canonical form: "
    "`rsync -a ~/.claude/plugins/marketplaces/canopy/plugins/canopy/ "
    "~/.claude/plugins/cache/canopy/canopy/<version>/` — use the FULL marketplaces source "
    "path (a relative path after `cd` is not recognized), and do NOT bundle `rm`/deletions "
    "in the same statement (run cleanup separately)."
)


def _expand(path: str) -> str:
    """Tilde- and env-expand a path-ish string."""
    return os.path.expanduser(os.path.expandvars(path))


def _guarded_paths() -> list[str]:
    """Return the absolute path prefixes we guard."""
    home = os.path.expanduser("~")
    return [
        os.path.join(home, ".claude", "plugins", "cache"),
        os.path.join(home, ".claude", "plugins", "installed_plugins.json"),
    ]


def _path_is_guarded(candidate: str) -> bool:
    """True if ``candidate`` resolves under a guarded prefix.

    We match on string prefix after expansion — no filesystem access required,
    so this works even when the target doesn't exist yet (e.g. ``Write`` of
    a new file inside the cache).
    """
    if not candidate:
        return False
    expanded = _expand(candidate)
    # Normalise but don't resolve symlinks — Path.resolve() would touch the FS
    # and we want this to be cheap and side-effect-free.
    norm = os.path.normpath(expanded)
    for guarded in _guarded_paths():
        if norm == guarded or norm.startswith(guarded + os.sep):
            return True
    return False


def _bash_mentions_guarded_path(command: str) -> tuple[bool, str | None]:
    """Inspect a Bash command string for guarded-path mutation.

    Returns ``(matched, offending_token)``. ``matched`` is True if any
    mutating command or shell redirect targets a guarded path.
    """
    if not command:
        return False, None

    # Cheap pre-filter: if neither guarded prefix nor "$HOME/.claude/plugins"
    # appears at all, we're done.
    cheap_markers = (
        "~/.claude/plugins",
        "$HOME/.claude/plugins",
        "${HOME}/.claude/plugins",
        ".claude/plugins/cache",
        ".claude/plugins/installed_plugins.json",
    )
    if not any(marker in command for marker in cheap_markers):
        return False, None

    # Tokenise with shlex so we can inspect command names + arguments.
    # Fall back to whitespace split if shlex chokes on weird quoting.
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()

    # Identify guarded tokens (paths that resolve under our prefixes).
    guarded_tokens = [t for t in tokens if _path_is_guarded(t)]

    # Also check for shell redirects targeting guarded paths. shlex strips
    # operators like `>` so we re-scan the raw command for redirect patterns.
    # Catches: > path, >> path, < path is irrelevant (read-only).
    redirect_re = re.compile(r"(?:>>?|\b(?:tee))\s+(\S+)")
    for match in redirect_re.finditer(command):
        target = match.group(1).strip("\"'")
        if _path_is_guarded(target):
            return True, target

    if not guarded_tokens:
        return False, None

    # Are any of the tokens preceded by a mutating command? Walk the token
    # list and track "current command" — the first token after a shell
    # separator (``;``, ``&&``, ``||``, ``|``) is treated as a fresh command.
    separators = {";", "&&", "||", "|"}
    # An env-assignment prefix (`FOO=bar cmd`) or `env`/`export` must not be
    # mistaken for the command itself — otherwise `FOO=1 rsync … cache/` would
    # slip through (the assignment becomes "current_cmd", so the real rsync is
    # never checked). Skip them when resolving the command. shlex may glue a
    # trailing separator onto an assignment token (`FOO=1;`); the regex still
    # matches, and the next real token becomes the command.
    assign_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    current_cmd: str | None = None
    for tok in tokens:
        if tok in separators:
            current_cmd = None
            continue
        if current_cmd is None:
            if assign_re.match(tok) or os.path.basename(tok.rstrip(";")) in ("env", "export"):
                continue  # env-var prefix / env / export — not the command
            current_cmd = os.path.basename(tok)
            continue
        # tok is an argument to current_cmd
        if _path_is_guarded(tok) and current_cmd in _MUTATING_COMMANDS:
            return True, tok

    # Special case: ``sed -i ... <guarded>`` is covered above (sed is in the
    # mutating set). ``rm -rf <guarded>`` likewise.
    return False, None


def _is_sanctioned_update(command: str) -> bool:
    """True for the canonical ``/canopy:update`` install step.

    That step copies the marketplace checkout into the version-keyed plugin
    cache::

        rsync -a ~/.claude/plugins/marketplaces/<p>/plugins/<p>/ \
                 ~/.claude/plugins/cache/<p>/<p>/<version>/

    It is the ONLY sanctioned writer of the cache, so the guard must not block
    it (doing so wedges the very update flow the guard tells you to use). The
    anti-pattern the guard exists to stop — hand-copying a *dev build* into the
    cache, or editing cache files in place — does NOT match this signature: it
    copies from a worktree/build dir (never ``plugins/marketplaces/``), or
    mutates files directly. We require a copy op (rsync/cp/install) reading
    from ``plugins/marketplaces/`` and writing to ``plugins/cache/``, and never
    exempt deletions.
    """
    if "plugins/marketplaces/" not in command or "plugins/cache/" not in command:
        return False
    if re.search(r"\brm\b", command):  # never exempt deletions
        return False
    return bool(re.search(r"\b(?:rsync|cp|install)\b", command))


def _has_inline_override(command: str) -> bool:
    """Honour ``CANOPY_ALLOW_CACHE_PATCH=1`` set inline on the command.

    The hook evaluates the command string *before* it runs, in its own process
    — so a var exported in a separate shell (or prefixed on the same command
    line) is invisible to ``os.environ`` here. Without this, the documented
    escape hatch is unusable for the common ``CANOPY_ALLOW_CACHE_PATCH=1 <cmd>``
    / ``export CANOPY_ALLOW_CACHE_PATCH=1; <cmd>`` forms. Accept either.
    """
    return bool(re.search(r"CANOPY_ALLOW_CACHE_PATCH=1\b", command))


def _block(reason: str) -> None:
    """Emit a PreToolUse decision blocking the call and exit cleanly.

    Uses the documented hookSpecificOutput contract so the agent sees the
    permission decision and the rationale.
    """
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    # Exit 0 — the JSON decision drives the block. (Non-zero exit codes are
    # also a valid block signal but we prefer the structured form so the
    # message is shown to the agent verbatim.)
    sys.exit(0)


def _allow_silently() -> None:
    sys.stdout.write(json.dumps({"continue": True}))
    sys.stdout.flush()
    sys.exit(0)


def _allow_with_warning(message: str) -> None:
    sys.stderr.write(f"[canopy plugin-cache guard] WARNING: {message}\n")
    _allow_silently()


def _build_block_message(detail: str) -> str:
    msg = (
        "BLOCKED by canopy plugin-cache guard.\n\n"
        f"Detected: {detail}\n\n"
        f"Why: {_CLAUDE_MD_QUOTE}\n\n"
        f"Fix: {_REMEDIATION}"
    )
    # If the block was a Bash command WRITING into the cache, it may be a hand-rolled
    # update that deviated from the canonical (auto-exempted) form — surface how to fix that.
    if "mutates the plugin cache" in detail:
        msg += f"\n\n{_SANCTIONED_HINT}"
    return msg


def evaluate(hook_data: dict) -> tuple[str, str | None]:
    """Pure logic: decide what to do for a hook payload.

    Returns ``(action, detail)`` where ``action`` is one of:
      - ``"allow"`` — not a guarded scenario
      - ``"block"`` — must block; ``detail`` is a human-readable reason
      - ``"override"`` — guarded scenario but env override is set; ``detail``
        is the warning to surface
    """
    tool_name = hook_data.get("tool_name", "")
    if tool_name not in _GUARDED_TOOLS:
        return "allow", None

    tool_input = hook_data.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        return "allow", None

    detail: str | None = None
    command = ""

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        matched, offending = _bash_mentions_guarded_path(command)
        if matched:
            # The sanctioned /canopy:update install copies marketplaces → cache.
            # That's the prescribed flow, not local patching — never block it.
            if _is_sanctioned_update(command):
                return "allow", None
            detail = (
                f"Bash command mutates the plugin cache — offending path "
                f"`{offending}` in command: {command!r}"
            )
    else:  # Edit / Write / MultiEdit
        file_path = tool_input.get("file_path", "") or ""
        if _path_is_guarded(file_path):
            detail = (
                f"{tool_name} targets the plugin cache directly: "
                f"`{file_path}`"
            )

    if detail is None:
        return "allow", None

    if os.environ.get("CANOPY_ALLOW_CACHE_PATCH") == "1" or _has_inline_override(command):
        return "override", detail
    return "block", detail


def main() -> None:
    try:
        raw = sys.stdin.read()
        hook_data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, EOFError):
        # If we can't parse the payload, don't block — hook failures must
        # never wedge Claude Code.
        _allow_silently()
        return

    action, detail = evaluate(hook_data)

    if action == "allow":
        _allow_silently()
    elif action == "override":
        _allow_with_warning(
            f"CANOPY_ALLOW_CACHE_PATCH=1 — allowing despite guarded match. {detail}"
        )
    else:  # block
        _block(_build_block_message(detail or "guarded path"))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Last-ditch: never wedge Claude Code on hook failure.
        try:
            _allow_silently()
        except Exception:
            pass
