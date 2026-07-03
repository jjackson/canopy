/**
 * Tests for the GWS_ALLOWED_DRIVE_IDS write-scope enforcement in the shared
 * write probe (`assertParentOnSharedDrive`). Generalizes ACE's
 * Shared-Drive-only probe: when an allowlist is present, a parent that lives
 * on a Shared Drive OUTSIDE the allowlist is rejected with a message naming
 * GWS_ALLOWED_DRIVE_IDS — writes are scoped per agent, not merely
 * per-Shared-Drive.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  assertParentOnSharedDrive,
  __resetSharedDriveProbeCacheForTests,
} from '../../mcp/gws-server.js';

const fakeDrive = (driveId: string | null) => ({
  files: {
    get: vi.fn(async () => ({
      data: {
        id: 'parent-1',
        name: 'parent',
        driveId,
        mimeType: 'application/vnd.google-apps.folder',
      },
    })),
  },
});

describe('assertParentOnSharedDrive with GWS_ALLOWED_DRIVE_IDS', () => {
  beforeEach(() => {
    __resetSharedDriveProbeCacheForTests();
  });

  it('accepts a parent on an allowlisted Shared Drive', async () => {
    const drive = fakeDrive('drive-allowed');
    const r = await assertParentOnSharedDrive('parent-1', drive as any, ['drive-allowed']);
    expect(r).toEqual({ ok: true });
  });

  it('rejects a parent on a Shared Drive outside the allowlist, naming the env var', async () => {
    const drive = fakeDrive('drive-other');
    const r = await assertParentOnSharedDrive('parent-1', drive as any, ['drive-allowed']);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.message).toMatch(/GWS_ALLOWED_DRIVE_IDS/);
      expect(r.message).toMatch(/drive-other/);
    }
  });

  it('still rejects My-Drive parents regardless of allowlist', async () => {
    const drive = fakeDrive(null);
    const r = await assertParentOnSharedDrive('parent-1', drive as any, ['drive-allowed']);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.message).toMatch(/My Drive/);
  });

  it('null allowlist means any Shared Drive is writable', async () => {
    const drive = fakeDrive('any-shared-drive');
    const r = await assertParentOnSharedDrive('parent-1', drive as any, null);
    expect(r).toEqual({ ok: true });
  });

  it('does not share cache entries across different allowlists for the same parent', async () => {
    const drive = fakeDrive('drive-a');
    const ok = await assertParentOnSharedDrive('parent-1', drive as any, ['drive-a']);
    expect(ok).toEqual({ ok: true });
    // Same parent, different scope: must re-probe and reject, not reuse the
    // cached ok from the other allowlist.
    const rejected = await assertParentOnSharedDrive('parent-1', drive as any, ['drive-b']);
    expect(rejected.ok).toBe(false);
  });
});
