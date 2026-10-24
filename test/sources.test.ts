import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { fetchRepos, toRepoSnapshot } from '../src/sources/github.ts';
import { pool, requestJSON, type Fetch } from '../src/sources/http.ts';
import { fetchDockerHubPulls, fetchScarfPulls } from '../src/sources/pulls.ts';
import { graphqlPage, jsonResponse as json, repoNode as node } from './helpers.ts';

/** A fetch that answers from a list of responses and records what was asked. */
function fakeFetch(respond: (url: string, init: RequestInit | undefined, call: number) => Response) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn: Fetch = async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    return respond(url, init, calls.length - 1);
  };
  return { fetch: fn, calls };
}

describe('requestJSON', () => {
  it('retries 429 and 5xx, then succeeds', async () => {
    const { fetch, calls } = fakeFetch((_, __, call) => (call < 2 ? json({}, call ? 503 : 429) : json({ ok: 1 })));
    assert.deepEqual(await requestJSON('https://x', { fetch, backoffMs: 0 }), { ok: 1 });
    assert.equal(calls.length, 3);
  });

  it('retries network errors', async () => {
    let calls = 0;
    const fetch: Fetch = async () => {
      if (calls++ === 0) throw new TypeError('fetch failed');
      return json({ ok: 1 });
    };
    assert.deepEqual(await requestJSON('https://x', { fetch, backoffMs: 0 }), { ok: 1 });
    assert.equal(calls, 2);
    const down: Fetch = async () => {
      throw new TypeError('fetch failed');
    };
    await assert.rejects(requestJSON('https://x', { fetch: down, retries: 1, backoffMs: 0 }), /fetch failed/);
  });

  it('does not retry other errors', async () => {
    const { fetch, calls } = fakeFetch(() => json({}, 404));
    await assert.rejects(requestJSON('https://x', { fetch, backoffMs: 0 }), /404/);
    assert.equal(calls.length, 1);
  });

  it('gives up after the retries', async () => {
    const { fetch, calls } = fakeFetch(() => json({}, 500));
    await assert.rejects(requestJSON('https://x', { fetch, retries: 2, backoffMs: 0 }), /500/);
    assert.equal(calls.length, 3);
  });
});

describe('pool', () => {
  it('keeps order and limits concurrency', async () => {
    let running = 0;
    let peak = 0;
    const out = await pool([1, 2, 3, 4, 5], 2, async (n) => {
      peak = Math.max(peak, ++running);
      await sleep(5 - n);
      running--;
      return n * 10;
    });
    assert.deepEqual(out, [10, 20, 30, 40, 50]);
    assert.equal(peak, 2);
  });
});

describe('github', () => {
  it('takes readme-vars.yml from the first branch that has one', () => {
    const snap = toRepoSnapshot(
      node({ master: null, main: { text: 'from: main' }, develop: { text: 'from: develop' } }),
    );
    assert.equal(snap.readme_vars, 'from: main');
    assert.equal(toRepoSnapshot(node()).readme_vars, null);
  });

  it('maps the latest release', () => {
    assert.deepEqual(toRepoSnapshot(node()).latest_release, {
      tag: 'v1',
      published_at: '2026-10-02T00:00:00Z',
      url: 'https://example/v1',
    });
    assert.equal(toRepoSnapshot(node({ latestRelease: null })).latest_release, null);
  });

  it('pages through the org and keeps only image repositories', async () => {
    const { fetch, calls } = fakeFetch((_, __, call) =>
      call === 0
        ? graphqlPage([node({ name: 'docker-a' }), node({ name: 'site' })], 'c1')
        : graphqlPage([node({ name: 'docker-baseimage-alpine' }), node({ name: 'docker-b' })]),
    );
    const repos = await fetchRepos({ token: 't', fetch });
    assert.deepEqual(
      repos.map((r) => r.name),
      ['docker-a', 'docker-b'],
    );
    assert.equal(calls.length, 2);
    assert.equal(JSON.parse(String(calls[1]!.init!.body)).variables.cursor, 'c1');
    assert.equal((calls[0]!.init!.headers as Record<string, string>).Authorization, 'Bearer t');
  });

  it('surfaces GraphQL errors', async () => {
    const { fetch } = fakeFetch(() => json({ errors: [{ message: 'Bad credentials' }] }));
    await assert.rejects(fetchRepos({ token: 't', fetch }), /Bad credentials/);
  });
});

describe('scarf', () => {
  it('reads monthly installs per image', async () => {
    const { fetch, calls } = fakeFetch(() =>
      json({
        results: [
          { package: { name: 'linuxserver/sonarr' }, total_installs: 100 },
          { package: { name: 'linuxserver/radarr' } },
        ],
      }),
    );
    assert.deepEqual(await fetchScarfPulls({ token: 's', fetch }), { sonarr: 100 });
    assert.equal((calls[0]!.init!.headers as Record<string, string>).Authorization, 'Bearer s');
  });
});

describe('docker hub', () => {
  it('keeps the previous count for images that fail', async () => {
    const { fetch } = fakeFetch((url) => (url.includes('/sonarr/') ? json({ pull_count: 42 }) : json({}, 404)));
    const result = await fetchDockerHubPulls({ names: ['sonarr', 'radarr', 'new'], previous: { radarr: 7 }, fetch });
    assert.deepEqual(result, { pulls: { sonarr: 42, radarr: 7 }, failed: ['radarr', 'new'] });
  });
});
