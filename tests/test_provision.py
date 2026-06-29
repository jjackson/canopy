"""Tests for portable secret provisioning (no real `op` — the resolver is injected)."""
import stat

import pytest

from orchestrator.provision import (
    ProvisionError,
    load_manifest,
    provision,
    resolve_target,
)


def _manifest(repo, body):
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "config" / "secrets.yaml").write_text(body)


def test_load_manifest_parses(tmp_path):
    _manifest(tmp_path, """
secrets:
  - name: pat
    op: "op://AI-Agents/Canopy Web PAT/credential"
    target: "~/.canopy/agents/eva/pat"
  - name: sa
    op: "op://AI-Agents/chrome-sales GWS SA/key"
    target: "{repo}/.gws-sa-key.json"
    optional: true
""")
    secs = load_manifest(tmp_path)
    assert [s.name for s in secs] == ["pat", "sa"]
    assert secs[1].optional is True


def test_load_manifest_missing_and_malformed(tmp_path):
    with pytest.raises(ProvisionError):
        load_manifest(tmp_path)                      # no file
    _manifest(tmp_path, "secrets:\n  - name: x\n")   # missing op/target
    with pytest.raises(ProvisionError):
        load_manifest(tmp_path)


def test_resolve_target_repo_placeholder_and_relative(tmp_path):
    assert resolve_target("{repo}/.gws-sa-key.json", tmp_path) == tmp_path / ".gws-sa-key.json"
    assert resolve_target("config/x", tmp_path) == tmp_path / "config" / "x"
    assert resolve_target("~/g", tmp_path) == (tmp_path.home() / "g")


def test_provision_writes_with_0600(tmp_path):
    _manifest(tmp_path, """
secrets:
  - name: sa
    op: "op://vault/item/key"
    target: "{repo}/.gws-sa-key.json"
""")
    fake = {"op://vault/item/key": '{"client_email":"x@y.iam"}'}
    res = provision(tmp_path, op_read=lambda ref: fake[ref])
    assert res["provisioned"] == 1 and not res["errors"]
    dest = tmp_path / ".gws-sa-key.json"
    assert dest.read_text().startswith('{"client_email"')
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600


def test_provision_check_mode_writes_nothing(tmp_path):
    _manifest(tmp_path, """
secrets:
  - name: sa
    op: "op://vault/item/key"
    target: "{repo}/.gws-sa-key.json"
""")
    res = provision(tmp_path, op_read=lambda ref: "value", check=True)
    assert res["provisioned"] == 1
    assert not (tmp_path / ".gws-sa-key.json").exists()


def test_provision_required_missing_is_error_optional_is_skip(tmp_path):
    _manifest(tmp_path, """
secrets:
  - name: required
    op: "op://vault/missing/x"
    target: "{repo}/req"
  - name: opt
    op: "op://vault/missing/y"
    target: "{repo}/opt"
    optional: true
""")
    def fake(ref):
        raise ProvisionError("op read failed: item not found")
    res = provision(tmp_path, op_read=fake)
    assert res["errors"] and "required" in res["errors"][0]
    assert res["skipped"] == 1
    assert not (tmp_path / "req").exists() and not (tmp_path / "opt").exists()


def test_env_block_writes_one_dotenv_to_global_home(tmp_path):
    """The env: block materializes many KEY=value into ONE .env at a global (worktree-clean) home."""
    _manifest(tmp_path, """
env:
  target: "{repo}/home/.env"
  mode: "0600"
  vars:
    - key: AGENT_GMAIL_ACCOUNT
      op: "op://V/Item/username"
    - key: AGENT_GMAIL_PASSWORD
      op: "op://V/Item/password"
    - key: AGENT_CLIENT
      value: "agent"
    - key: AGENT_OPTIONAL
      op: "op://V/Missing/x"
      optional: true
""")
    fake = {"op://V/Item/username": "a@b.com\n", "op://V/Item/password": "p>!ss\n"}

    def op_read(ref):
        if ref not in fake:
            raise ProvisionError("not found")
        return fake[ref]

    res = provision(tmp_path, op_read=op_read)
    assert not res["errors"]
    env_path = tmp_path / "home" / ".env"
    body = env_path.read_text()
    assert "AGENT_GMAIL_ACCOUNT=a@b.com" in body          # op ref resolved, newline stripped
    assert "AGENT_GMAIL_PASSWORD=p>!ss" in body           # special chars verbatim, not interpreted
    assert "AGENT_CLIENT=agent" in body                   # literal value
    assert "AGENT_OPTIONAL" not in body                   # missing optional skipped, not failed
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_env_block_required_failure_does_not_write_partial(tmp_path):
    _manifest(tmp_path, """
env:
  target: "{repo}/home/.env"
  vars:
    - key: A
      value: "ok"
    - key: B
      op: "op://V/Missing/x"
""")
    res = provision(tmp_path, op_read=lambda ref: (_ for _ in ()).throw(ProvisionError("nope")))
    assert res["errors"]                                  # required B failed
    assert not (tmp_path / "home" / ".env").exists()      # .env NOT half-written
