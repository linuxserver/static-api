/**
 * Refreshes data/ from GitHub, Scarf and Docker Hub. Like the Python updater, a source that fails keeps
 * its previous data and the failure is recorded, so the API keeps serving and /health reports it.
 *
 * Usage: GITHUB_TOKEN=… [SCARF_TOKEN=…] node src/refresh.ts [--skip-dockerhub]
 */
import { PATHS } from './config.ts';
import { loadSnapshot, saveSnapshot, type Snapshot, type SourceName } from './snapshot.ts';
import { fetchRepos } from './sources/github.ts';
import type { Fetch } from './sources/http.ts';
import { fetchDockerHubPulls, fetchScarfPulls } from './sources/pulls.ts';
import { listedImageNames } from './transform.ts';
import { errorMessage } from './util.ts';

export interface RefreshOptions {
  githubToken?: string;
  scarfToken?: string;
  skipDockerHub?: boolean;
  fetch?: Fetch;
  now?: () => Date;
  log?: (message: string) => void;
}

export async function refresh(previous: Snapshot, options: RefreshOptions = {}): Promise<Snapshot> {
  const { fetch, now = () => new Date(), log = console.log } = options;
  const next: Snapshot = structuredClone(previous);

  /** Runs one source; on failure the previous data stays and the error is recorded. */
  async function attempt(source: SourceName, run: () => Promise<string | void>) {
    const checked_at = now().toISOString();
    const fetched_at = () => next[source].fetched_at || undefined;
    try {
      const warning = await run();
      next.status[source] = { ok: true, checked_at, fetched_at: fetched_at(), ...(warning ? { error: warning } : {}) };
      log(`  ✓ ${source}${warning ? ` (${warning})` : ''}`);
    } catch (e) {
      next.status[source] = { ok: false, checked_at, fetched_at: fetched_at(), error: errorMessage(e) };
      log(`  ✗ ${source}: ${errorMessage(e)} (keeping data from ${fetched_at() ?? 'never'})`);
    }
  }

  // Docker Hub needs the image names from GitHub; Scarf needs nothing, so it runs alongside.
  const githubThenDockerHub = async () => {
    await attempt('github', async () => {
      if (!options.githubToken) throw new Error('GITHUB_TOKEN is not set');
      const repos = await fetchRepos({ token: options.githubToken, fetch });
      if (!repos.length) throw new Error('no image repositories returned');
      next.github = { fetched_at: now().toISOString(), repos };
    });
    if (options.skipDockerHub) return;
    await attempt('dockerhub', async () => {
      const names = listedImageNames(next.github.repos);
      const { pulls, failed } = await fetchDockerHubPulls({ names, previous: next.dockerhub.pulls, fetch });
      if (names.length && failed.length === names.length) throw new Error('every request failed');
      next.dockerhub = { fetched_at: now().toISOString(), pulls };
      // Sorted: requests finish in any order, and status.json shouldn't change when the same images fail.
      if (failed.length) return `${failed.length} kept previous counts: ${failed.toSorted().join(', ')}`;
    });
  };

  const scarf = () =>
    attempt('scarf', async () => {
      if (!options.scarfToken) throw new Error('SCARF_TOKEN is not set');
      const pulls = await fetchScarfPulls({ token: options.scarfToken, fetch });
      if (!Object.keys(pulls).length) throw new Error('no pull counts returned');
      next.scarf = { fetched_at: now().toISOString(), pulls };
    });

  await Promise.all([githubThenDockerHub(), scarf()]);
  return next;
}

if (import.meta.main) {
  const previous = await loadSnapshot(PATHS.data);
  const next = await refresh(previous, {
    githubToken: process.env.GITHUB_TOKEN,
    scarfToken: process.env.SCARF_TOKEN,
    skipDockerHub: process.argv.includes('--skip-dockerhub'),
  });
  await saveSnapshot(PATHS.data, next);
  if (process.env.GITHUB_ACTIONS) {
    // Workflow command data must have %, CR and LF escaped, or the message is cut at the first newline.
    const escapeData = (s: string) => s.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
    for (const [source, s] of Object.entries(next.status)) {
      if (!s.ok) console.log(`::warning title=${source} refresh failed::${escapeData(s.error ?? '')}`);
    }
  }
  // Only fail when there is nothing to build from at all; otherwise the stale data is still worth serving.
  if (!next.github.repos.length) {
    console.error('No GitHub data, so there is nothing to build.');
    process.exitCode = 1;
  }
}
