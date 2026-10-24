import { readFileSync } from 'node:fs';
import type { Image } from '../src/api/types.ts';
import type { Model } from '../src/api/responses.ts';
import type { RepoSnapshot, Snapshot } from '../src/snapshot.ts';
import type { RepoNode } from '../src/sources/github.ts';
import { toModel } from '../src/build.ts';

const fixture = <T>(name: string): T => JSON.parse(readFileSync(new URL(`fixtures/${name}`, import.meta.url), 'utf8'));

export const fixtureRepos = fixture<{ repos: RepoSnapshot[]; scarf: Record<string, number> }>('repos.json');
export const liveV1 = fixture<Image[]>('live-v1.json');

export const FETCHED_AT = '2026-10-24T13:11:46.000Z';

/** A repository with a minimal valid readme-vars.yml; override anything. */
export function repo(overrides: Partial<RepoSnapshot> = {}): RepoSnapshot {
  return {
    name: 'docker-example',
    url: 'https://github.com/linuxserver/docker-example',
    stars: 5,
    pushed_at: '2026-10-01T10:00:00Z',
    archived: false,
    latest_release: {
      tag: '1.0.0-ls1',
      published_at: '2026-10-20T08:30:00Z',
      url: 'https://github.com/linuxserver/docker-example/releases/tag/1.0.0-ls1',
    },
    readme_vars: 'project_name: example\nproject_blurb: An example.\nproject_categories: "Tools"\n',
    ...overrides,
  };
}

export function fixtureSnapshot(): Snapshot {
  const ok = { ok: true, checked_at: FETCHED_AT, fetched_at: FETCHED_AT };
  return {
    github: { fetched_at: FETCHED_AT, repos: fixtureRepos.repos },
    scarf: { fetched_at: FETCHED_AT, pulls: fixtureRepos.scarf },
    dockerhub: { fetched_at: FETCHED_AT, pulls: { sonarr: 1_000_000, wireguard: 500_000 } },
    status: { github: ok, scarf: ok, dockerhub: ok },
  };
}

/** The model the build makes from the fixtures. */
export const fixtureModel = (): Model => toModel(fixtureSnapshot());

/** A JSON response, as fetch returns it. */
export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

/** A repository as the GitHub GraphQL query returns it. */
export const repoNode = (overrides: Partial<RepoNode> = {}): RepoNode => ({
  name: 'docker-example',
  url: 'https://github.com/linuxserver/docker-example',
  stargazerCount: 3,
  pushedAt: '2026-10-01T00:00:00Z',
  isArchived: false,
  latestRelease: { tagName: 'v1', publishedAt: '2026-10-02T00:00:00Z', url: 'https://example/v1' },
  ...overrides,
});

/** One page of the GitHub GraphQL repository listing. */
export const graphqlPage = (nodes: RepoNode[], nextCursor: string | null = null) =>
  jsonResponse({
    data: {
      organization: { repositories: { pageInfo: { hasNextPage: !!nextCursor, endCursor: nextCursor }, nodes } },
    },
  });
