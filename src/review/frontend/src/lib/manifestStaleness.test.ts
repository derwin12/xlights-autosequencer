import { describe, it, expect } from 'vitest';
import { baseCommit, isBackendStale, isUpdateAvailable } from './manifestStaleness';

describe('baseCommit', () => {
  it('strips a trailing -dirty suffix', () => {
    expect(baseCommit('abc1234-dirty')).toBe('abc1234');
  });

  it('leaves a clean commit unchanged', () => {
    expect(baseCommit('abc1234')).toBe('abc1234');
  });
});

describe('isBackendStale', () => {
  it('is true when the backend commit differs from repo HEAD', () => {
    expect(isBackendStale('aaa1111', 'bbb2222')).toBe(true);
  });

  it('is false when they match, ignoring -dirty', () => {
    expect(isBackendStale('aaa1111-dirty', 'aaa1111')).toBe(false);
  });

  it('is false when either value is missing (unknown, not stale)', () => {
    expect(isBackendStale(null, 'bbb2222')).toBe(false);
    expect(isBackendStale('aaa1111', undefined)).toBe(false);
  });
});

describe('isUpdateAvailable', () => {
  it('is false when repo HEAD already matches origin/main', () => {
    expect(isUpdateAvailable('aaa1111', 'aaa1111', true)).toBe(false);
  });

  it('is true when origin is confirmed ahead of HEAD', () => {
    expect(isUpdateAvailable('aaa1111', 'bbb2222', true)).toBe(true);
  });

  it('is false when HEAD has unpushed local commits ahead of origin — the bug this guards against', () => {
    // Same shape as: committed locally but never pushed, so repo_head_commit
    // and origin_main_commit differ even though origin has nothing new.
    expect(isUpdateAvailable('bbb2222', 'aaa1111', false)).toBe(false);
  });

  it('is false when origin_ahead_of_head is unknown (offline/no network)', () => {
    expect(isUpdateAvailable('aaa1111', 'bbb2222', null)).toBe(false);
    expect(isUpdateAvailable('aaa1111', 'bbb2222', undefined)).toBe(false);
  });

  it('is false when either commit is missing', () => {
    expect(isUpdateAvailable(null, 'bbb2222', true)).toBe(false);
    expect(isUpdateAvailable('aaa1111', undefined, true)).toBe(false);
  });
});
