import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { writeTokenFile } from '../canopy-web-pat-mint.js';

// Ported from ace's test/scripts/ace-web-pat-mint.test.ts and adapted to
// canopy's token sink: canopy writes the RAW token (+ trailing newline) to a
// standalone file at ~/.claude/canopy/workbench-token with mode 600, rather
// than ace's `.env` marker-block. The tests therefore cover the file-write
// contract (parent-dir creation, full overwrite/rotate, trailing newline,
// mode 600) instead of ace's marker-block surgery.

let dir: string;
let tokenPath: string;

beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), 'canopy-web-pat-mint-test-'));
  tokenPath = join(dir, 'workbench-token');
});

afterEach(async () => {
  await rm(dir, { recursive: true, force: true });
});

describe('writeTokenFile', () => {
  it('creates the token file when it does not exist', async () => {
    await writeTokenFile(tokenPath, 'token-1');
    const content = await readFile(tokenPath, 'utf8');
    expect(content).toBe('token-1\n');
  });

  it('creates missing parent directories', async () => {
    const nested = join(dir, 'a', 'b', 'c', 'workbench-token');
    await writeTokenFile(nested, 'token-nested');
    const content = await readFile(nested, 'utf8');
    expect(content).toBe('token-nested\n');
  });

  it('overwrites a prior token on rotation (no append, no stale value)', async () => {
    await writeFile(tokenPath, 'old-token\n');
    await writeTokenFile(tokenPath, 'new-token');
    const content = await readFile(tokenPath, 'utf8');

    expect(content).toBe('new-token\n');
    expect(content).not.toContain('old-token');
  });

  it('writes exactly one trailing newline', async () => {
    await writeTokenFile(tokenPath, 'token-nl');
    const content = await readFile(tokenPath, 'utf8');
    expect(content.endsWith('\n')).toBe(true);
    expect(content.match(/\n/g)?.length).toBe(1);
  });

  it('writes file with mode 600', async () => {
    await writeTokenFile(tokenPath, 'token-mode');
    const s = await stat(tokenPath);
    // Mask off file-type bits, just check the permission bits.
    const mode = s.mode & 0o777;
    expect(mode).toBe(0o600);
  });

  it('preserves the raw token verbatim (no trimming or transformation)', async () => {
    const raw = 'AbC123._-base64url~token';
    await writeTokenFile(tokenPath, raw);
    const content = await readFile(tokenPath, 'utf8');
    expect(content).toBe(`${raw}\n`);
  });
});
