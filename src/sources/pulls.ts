/** Pull counts: monthly from Scarf (what the current API reports) and lifetime from Docker Hub. */
import { pool, requestJSON, type Fetch } from './http.ts';

interface ScarfOverview {
  results: { package: { name: string }; total_installs?: number }[];
}

/** Monthly installs per image, as updater.py's get_monthly_pulls reads them. */
export async function fetchScarfPulls(options: { token: string; fetch?: Fetch }): Promise<Record<string, number>> {
  const res = await requestJSON<ScarfOverview>(
    'https://api.scarf.sh/v2/packages/linuxserver-ci/overview?per_page=1000',
    {
      fetch: options.fetch,
      headers: { Authorization: `Bearer ${options.token}` },
    },
  );
  const pulls: Record<string, number> = {};
  for (const result of res.results) {
    if (result.total_installs === undefined) continue;
    pulls[result.package.name.replace('linuxserver/', '')] = result.total_installs;
  }
  return pulls;
}

/**
 * Lifetime pull counts from Docker Hub, one request per image (anonymous listing only pages 100 deep).
 * Images that fail keep their previous count; the error lists them.
 */
export async function fetchDockerHubPulls(options: {
  names: string[];
  previous: Record<string, number>;
  fetch?: Fetch;
}): Promise<{ pulls: Record<string, number>; failed: string[] }> {
  const failed: string[] = [];
  const counts = await pool(options.names, 4, async (name) => {
    try {
      const repo = await requestJSON<{ pull_count: number }>(
        `https://hub.docker.com/v2/repositories/linuxserver/${name}/`,
        { fetch: options.fetch },
      );
      return repo.pull_count;
    } catch {
      failed.push(name);
      return options.previous[name];
    }
  });
  const pulls: Record<string, number> = {};
  options.names.forEach((name, i) => {
    const count = counts[i];
    if (count !== undefined) pulls[name] = count;
  });
  return { pulls, failed };
}
