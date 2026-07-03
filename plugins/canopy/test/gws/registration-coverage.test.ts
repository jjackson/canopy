/**
 * Registration-coverage drift gate for the canopy-gws MCP server.
 *
 * Catches the "tool added to a handler module but not registered on the
 * MCP server" class of bug — and its inverse. `mcp/gws-server.ts` calls
 * `server.tool('name', ...)` for every atom it exposes; this test parses
 * those calls statically and asserts:
 *
 *   1. Snapshot count: the number of `server.tool(...)` calls matches an
 *      explicit expected count. Update intentionally when shipping atoms.
 *   2. Prefix allowlist: every tool name starts with one of the prefixes
 *      the server is allowed to register.
 *   3. No duplicate tool registrations.
 *   4. The server file is actually wired into the canopy plugin's
 *      plugin.json `mcpServers` map (a server file that exists on disk but
 *      is not registered is silently unreachable by agents).
 *   5. Fail-loud identity: the startup path must call
 *      `resolveIdentityFromEnv()` so a missing GWS_* identity env is a
 *      fatal, named error — never a silent fallback to a default identity.
 *
 * Parses statically (never imports the server module) so no MCP transport
 * or Google auth is touched. Ported from ACE's registration-coverage gate.
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

// plugins/canopy/ — the plugin root this test suite lives under.
const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function extractToolRegistrations(relpath: string): string[] {
  const src = fs.readFileSync(path.join(PLUGIN_ROOT, relpath), 'utf-8');
  // Multiline-tolerant: matches `server.tool(\n  'name',` and `server.tool('name',`.
  const re = /\bserver\.tool\s*\(\s*['"]([a-z][a-z0-9_]*)['"]/g;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) out.push(m[1]);
  return out;
}

// Snapshot of registered atoms (32 as of the initial port from ACE —
// all drive_*/docs_*/sheets_*/slides_* atoms plus the forms reader and the
// gog-CLI personal-Drive fallback; the ACE-aware atoms stayed in ACE).
// Update intentionally when shipping a new atom.
const SERVER_FILE = 'mcp/gws-server.ts';
const EXPECTED_COUNT = 32;
const ALLOWED_PREFIXES = [
  'drive_',
  'sheets_',
  'docs_',
  'slides_',
  'read_personal_drive_doc',
  'get_google_form_definition',
];

describe('canopy-gws tool registration', () => {
  const tools = extractToolRegistrations(SERVER_FILE);

  it('registers the expected number of tools (update snapshot when shipping atoms)', () => {
    expect(tools, `${SERVER_FILE} actual tools: ${JSON.stringify(tools)}`)
      .toHaveLength(EXPECTED_COUNT);
  });

  it('uses only the allowed prefixes for this server', () => {
    const offenders = tools.filter(
      (t) => !ALLOWED_PREFIXES.some((p) => t === p || t.startsWith(p)),
    );
    expect(offenders, `tools in ${SERVER_FILE} with unrecognized prefix`).toEqual([]);
  });

  it('has no duplicate tool names', () => {
    const seen = new Set<string>();
    const dupes: string[] = [];
    for (const t of tools) {
      if (seen.has(t)) dupes.push(t);
      seen.add(t);
    }
    expect(dupes, `${SERVER_FILE}: duplicate tool registrations`).toEqual([]);
  });

  it('does not register any ACE-aware atom (those live in the ACE plugin)', () => {
    const aceOnly = [
      'resolve_opp_path',
      'resolve_current_run_id',
      'validate_run_state',
      'classify_phase_writeback',
      'verify_phase_products',
      'verify_phase_artifacts',
      'render_run_readme',
      'render_decisions_log',
      'generate_inputs_manifest',
      'update_yaml_file',
    ];
    const leaked = tools.filter((t) => aceOnly.includes(t) || t.startsWith('decisions_'));
    expect(leaked, 'ACE-aware atoms must not be registered on canopy-gws').toEqual([]);
  });
});

describe('canopy-gws plugin.json wiring', () => {
  it('mcp/gws-server.ts is registered in .claude-plugin/plugin.json mcpServers', () => {
    const pluginJson = JSON.parse(
      fs.readFileSync(path.join(PLUGIN_ROOT, '.claude-plugin/plugin.json'), 'utf-8'),
    );
    const registered = new Set<string>();
    for (const entry of Object.values(pluginJson.mcpServers ?? {}) as Array<{
      args?: string[];
    }>) {
      for (const arg of entry.args ?? []) {
        const m = arg.match(/mcp\/[A-Za-z0-9_-]+-server\.ts$/);
        if (m) registered.add(m[0]);
      }
    }
    expect(
      registered.has('mcp/gws-server.ts'),
      'mcp/gws-server.ts exists on disk but is not wired into plugin.json ' +
        'mcpServers — agents would silently lack every gws atom.',
    ).toBe(true);
  });
});

describe('canopy-gws fail-loud identity startup', () => {
  it('main() runs the identity check (resolveIdentityFromEnv) before connecting', () => {
    const src = fs.readFileSync(path.join(PLUGIN_ROOT, SERVER_FILE), 'utf-8');
    // The startup path must resolve identity and exit non-zero on failure.
    expect(src).toMatch(/async function main\(\)[\s\S]*?resolveIdentityFromEnv\(\)/);
    expect(src).toMatch(/GwsIdentityError/);
    expect(src).toMatch(/process\.exit\(1\)/);
  });

  it('never reads a non-GWS credential env var (no ACE_/GOOGLE_APPLICATION_CREDENTIALS fallback)', () => {
    const serverSrc = fs.readFileSync(path.join(PLUGIN_ROOT, SERVER_FILE), 'utf-8');
    const identitySrc = fs.readFileSync(
      path.join(PLUGIN_ROOT, 'mcp/gws/lib/identity.ts'),
      'utf-8',
    );
    for (const src of [serverSrc, identitySrc]) {
      expect(src).not.toMatch(/GOOGLE_APPLICATION_CREDENTIALS/);
      expect(src).not.toMatch(/\bACE_[A-Z_]+/);
    }
  });
});
