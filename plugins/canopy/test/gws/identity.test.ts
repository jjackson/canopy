/**
 * Unit tests for the per-agent identity + write-scope resolution contract
 * (jjackson/canopy#262): GWS_IDENTITY_MODE / GWS_SA_KEY_PATH /
 * GWS_ALLOWED_DRIVE_IDS. The invariant under test is FAIL LOUD — a missing
 * or invalid identity env must throw a GwsIdentityError that names the
 * exact vars, and must never fall back to any default identity.
 */
import { describe, it, expect } from 'vitest';
import {
  resolveIdentityFromEnv,
  parseAllowedDriveIds,
  GwsIdentityError,
} from '../../mcp/gws/lib/identity.js';

describe('resolveIdentityFromEnv', () => {
  it('throws a named error when GWS_IDENTITY_MODE is unset (no default identity)', () => {
    expect(() => resolveIdentityFromEnv({})).toThrow(GwsIdentityError);
    expect(() => resolveIdentityFromEnv({})).toThrow(/GWS_IDENTITY_MODE/);
  });

  it('sa mode requires GWS_SA_KEY_PATH', () => {
    expect(() => resolveIdentityFromEnv({ GWS_IDENTITY_MODE: 'sa' })).toThrow(
      /GWS_SA_KEY_PATH/,
    );
  });

  it('sa mode requires the key file to exist', () => {
    expect(() =>
      resolveIdentityFromEnv(
        { GWS_IDENTITY_MODE: 'sa', GWS_SA_KEY_PATH: '/nope/key.json' },
        () => false,
      ),
    ).toThrow(/does not exist.*\/nope\/key\.json|\/nope\/key\.json/);
  });

  it('sa mode resolves when the key file exists', () => {
    const id = resolveIdentityFromEnv(
      { GWS_IDENTITY_MODE: 'sa', GWS_SA_KEY_PATH: '/keys/agent.json' },
      () => true,
    );
    expect(id).toEqual({ mode: 'sa', saKeyPath: '/keys/agent.json' });
  });

  it('gog mode fails loud as not-yet-implemented (tracked follow-up)', () => {
    expect(() => resolveIdentityFromEnv({ GWS_IDENTITY_MODE: 'gog' })).toThrow(
      /gog.*not implemented|not implemented.*gog/i,
    );
  });

  it('rejects unrecognized modes by name', () => {
    expect(() => resolveIdentityFromEnv({ GWS_IDENTITY_MODE: 'oauth' })).toThrow(
      /Unrecognized GWS_IDENTITY_MODE "oauth"/,
    );
  });
});

describe('parseAllowedDriveIds', () => {
  it('returns null when unset (no allowlist restriction)', () => {
    expect(parseAllowedDriveIds({})).toBeNull();
  });

  it('returns null for a blank value', () => {
    expect(parseAllowedDriveIds({ GWS_ALLOWED_DRIVE_IDS: '  ' })).toBeNull();
  });

  it('parses a comma-separated list, trimming whitespace and dropping empties', () => {
    expect(
      parseAllowedDriveIds({ GWS_ALLOWED_DRIVE_IDS: 'driveA, driveB ,,driveC' }),
    ).toEqual(['driveA', 'driveB', 'driveC']);
  });
});
