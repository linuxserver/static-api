/**
 * The raw source data the build reads, committed to data/ by CI. Keeping raw data (rather than finished
 * responses) means a change to how images are built from readme-vars.yml needs no refetch, and the
 * build is deterministic and works offline.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { SourceStatus } from './api/types.ts';

/** Image repositories are docker-<name>, except the base images. */
export const isImageRepo = (repoName: string) =>
  repoName.startsWith('docker-') && !repoName.startsWith('docker-baseimage-');

export interface Release {
  tag: string;
  published_at: string;
  url: string;
}

export interface RepoSnapshot {
  name: string;
  url: string;
  stars: number;
  pushed_at: string | null;
  archived: boolean;
  /** The latest non-prerelease release, as GitHub reports it. */
  latest_release: Release | null;
  /** readme-vars.yml from the first of master, main, develop, nightly that has one. */
  readme_vars: string | null;
}

interface GithubSnapshot {
  fetched_at: string;
  repos: RepoSnapshot[];
}

/** Monthly (Scarf) or lifetime (Docker Hub) pull counts keyed by image name. */
interface PullsSnapshot {
  fetched_at: string;
  pulls: Record<string, number>;
}

export type SourceName = 'github' | 'scarf' | 'dockerhub';

export interface Snapshot {
  github: GithubSnapshot;
  scarf: PullsSnapshot;
  dockerhub: PullsSnapshot;
  /** Outcome of the most recent refresh of each source. */
  status: Record<SourceName, SourceStatus>;
}

const KEYS = ['github', 'scarf', 'dockerhub', 'status'] as const;
const file = (dir: string, key: keyof Snapshot) => join(dir, `${key}.json`);

const emptyPulls = (): PullsSnapshot => ({ fetched_at: '', pulls: {} });

async function readJSON<T>(path: string, fallback: () => T): Promise<T> {
  try {
    return JSON.parse(await readFile(path, 'utf8')) as T;
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === 'ENOENT') return fallback();
    throw e;
  }
}

/** Reads data/. Missing files are treated as empty so a fresh checkout can run `refresh` straight away. */
export async function loadSnapshot(dir: string): Promise<Snapshot> {
  /** A source that has never been tried; `checked_at` stays empty until a refresh tries it. */
  const never = (): SourceStatus => ({ ok: false, checked_at: '' });
  const [github, scarf, dockerhub, status] = await Promise.all([
    readJSON<GithubSnapshot>(file(dir, 'github'), () => ({ fetched_at: '', repos: [] })),
    readJSON(file(dir, 'scarf'), emptyPulls),
    readJSON(file(dir, 'dockerhub'), emptyPulls),
    readJSON<Partial<Snapshot['status']>>(file(dir, 'status'), () => ({})),
  ]);
  return { github, scarf, dockerhub, status: { github: never(), scarf: never(), dockerhub: never(), ...status } };
}

/** One JSON file per source, indented, so the daily data commit is a readable diff. */
export async function saveSnapshot(dir: string, snapshot: Snapshot): Promise<void> {
  await Promise.all(KEYS.map((key) => writeFile(file(dir, key), JSON.stringify(snapshot[key], null, 1) + '\n')));
}
