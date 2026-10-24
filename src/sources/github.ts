/**
 * Every image repository in the linuxserver org, with its stars, latest release and readme-vars.yml.
 *
 * The Python version makes one REST call per repository for releases and up to four for readme-vars;
 * GraphQL gets the same data for the whole org in a handful of requests. `latestRelease` is GitHub's
 * "most recent non-prerelease, non-draft release", which is what iterating the release list and
 * skipping prereleases finds.
 */
import { isImageRepo, type RepoSnapshot } from '../snapshot.ts';
import { requestJSON, type Fetch } from './http.ts';

/** Where readme-vars.yml is looked for, in order. */
const README_VARS_BRANCHES = ['master', 'main', 'develop', 'nightly'] as const;

const blob = (branch: string) => `${branch}: object(expression: "${branch}:readme-vars.yml") { ... on Blob { text } }`;

const QUERY = `
query ($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 50, after: $cursor, orderBy: { field: NAME, direction: ASC }) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        url
        stargazerCount
        pushedAt
        isArchived
        latestRelease { tagName publishedAt url }
        ${README_VARS_BRANCHES.map(blob).join('\n        ')}
      }
    }
  }
}`;

type Blob = { text: string | null } | null;

export interface RepoNode extends Partial<Record<(typeof README_VARS_BRANCHES)[number], Blob>> {
  name: string;
  url: string;
  stargazerCount: number;
  pushedAt: string | null;
  isArchived: boolean;
  latestRelease: { tagName: string; publishedAt: string | null; url: string } | null;
}

interface QueryResponse {
  data?: {
    organization: {
      repositories: { pageInfo: { hasNextPage: boolean; endCursor: string | null }; nodes: RepoNode[] };
    } | null;
  };
  errors?: { message: string }[];
}

export function toRepoSnapshot(node: RepoNode): RepoSnapshot {
  const release = node.latestRelease;
  return {
    name: node.name,
    url: node.url,
    stars: node.stargazerCount,
    pushed_at: node.pushedAt,
    archived: node.isArchived,
    latest_release:
      release && release.publishedAt
        ? { tag: release.tagName, published_at: release.publishedAt, url: release.url }
        : null,
    readme_vars: README_VARS_BRANCHES.map((b) => node[b]?.text).find((text) => text) ?? null,
  };
}

const ORG = 'linuxserver';

export async function fetchRepos(options: { token: string; fetch?: Fetch }): Promise<RepoSnapshot[]> {
  const { token, fetch } = options;
  const repos: RepoSnapshot[] = [];
  let cursor: string | null = null;
  do {
    const res: QueryResponse = await requestJSON<QueryResponse>('https://api.github.com/graphql', {
      fetch,
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: QUERY, variables: { org: ORG, cursor } }),
    });
    if (res.errors?.length) throw new Error(`GitHub GraphQL: ${res.errors.map((e) => e.message).join('; ')}`);
    const page = res.data?.organization?.repositories;
    if (!page) throw new Error(`GitHub GraphQL: organization ${ORG} not found`);
    repos.push(...page.nodes.filter((n) => isImageRepo(n.name)).map(toRepoSnapshot));
    cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (cursor);
  return repos;
}
