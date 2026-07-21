/** Shared staleness checks between the manifest's three freshness tiers:
 * running process (backend_commit) -> local checkout (repo_head_commit) ->
 * upstream remote (origin_main_commit). Used by both the Chrome header
 * build-stamp banner and the About dialog so the two stay consistent. */

/** Strip the "-dirty" suffix so a commit compares equal regardless of
 * working-tree state at the moment each side was read. */
export function baseCommit(commit: string): string {
  return commit.replace(/-dirty$/, '');
}

/** True when the running backend process was started before the latest
 * commit on disk -- i.e. a restart would pick up newer code (user
 * request, 2026-07-18: surface this instead of requiring a manual
 * git log vs. manifest cross-check). */
export function isBackendStale(
  backendCommit: string | null | undefined,
  repoHeadCommit: string | null | undefined,
): boolean {
  if (!backendCommit || !repoHeadCommit) return false;
  return baseCommit(backendCommit) !== baseCommit(repoHeadCommit);
}

/** True when the local checkout's HEAD is behind origin/main -- distinct
 * from isBackendStale (pulled but not restarted): this is "haven't even
 * pulled yet." origin_main_commit/originAheadOfHead are cached server-side
 * and may be null (offline, no network) -- treated as "unknown," not stale.
 *
 * A plain SHA inequality is NOT enough here: repoHeadCommit and
 * originMainCommit also differ when HEAD has unpushed local commits ahead
 * of origin (nothing to pull), so this only fires when the server has
 * confirmed origin is actually ahead via `git merge-base --is-ancestor`
 * (originAheadOfHead === true), not merely "different". */
export function isUpdateAvailable(
  repoHeadCommit: string | null | undefined,
  originMainCommit: string | null | undefined,
  originAheadOfHead: boolean | null | undefined,
): boolean {
  if (!repoHeadCommit || !originMainCommit) return false;
  if (baseCommit(repoHeadCommit) === baseCommit(originMainCommit)) return false;
  return originAheadOfHead === true;
}
