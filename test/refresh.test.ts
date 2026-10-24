import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { refresh } from '../src/refresh.ts';
import type { Fetch } from '../src/sources/http.ts';
import { fixtureSnapshot, graphqlPage, jsonResponse as json, repoNode } from './helpers.ts';

const NOW = new Date('2026-10-25T04:00:00.000Z');
const silent = () => {};

const githubPage = () =>
  graphqlPage([
    repoNode({ name: 'docker-fresh', latestRelease: null, master: { text: 'project_categories: "Tools"\n' } }),
  ]);

/** Answers GitHub, Scarf and Docker Hub, or fails the ones listed. */
const sources =
  (fail: string[] = []): Fetch =>
  async (input) => {
    const url = String(input);
    const host = new URL(url).hostname;
    if (fail.some((f) => host.includes(f))) return json({ message: 'down' }, 404);
    if (host === 'api.github.com') return githubPage();
    if (host === 'api.scarf.sh')
      return json({ results: [{ package: { name: 'linuxserver/fresh' }, total_installs: 9 }] });
    return json({ pull_count: 123 });
  };

describe('refresh', () => {
  it('replaces every source when all succeed', async () => {
    const next = await refresh(fixtureSnapshot(), {
      githubToken: 'g',
      scarfToken: 's',
      fetch: sources(),
      now: () => NOW,
      log: silent,
    });
    assert.deepEqual(
      next.github.repos.map((r) => r.name),
      ['docker-fresh'],
    );
    assert.deepEqual(next.scarf.pulls, { fresh: 9 });
    assert.deepEqual(next.dockerhub.pulls, { fresh: 123 });
    for (const status of Object.values(next.status)) {
      assert.deepEqual(status, { ok: true, checked_at: NOW.toISOString(), fetched_at: NOW.toISOString() });
    }
  });

  it('keeps previous data and records the error when a source fails', async () => {
    const previous = fixtureSnapshot();
    const next = await refresh(previous, {
      githubToken: 'g',
      scarfToken: 's',
      fetch: sources(['github']),
      now: () => NOW,
      log: silent,
    });
    assert.deepEqual(next.github, previous.github);
    assert.equal(next.status.github.ok, false);
    assert.match(next.status.github.error!, /404/);
    assert.equal(next.status.github.fetched_at, previous.github.fetched_at);
    assert.equal(next.status.scarf.ok, true);
  });

  it('fails a source whose token is missing without calling it', async () => {
    const called: string[] = [];
    const fetch: Fetch = async (input, init) => {
      called.push(new URL(String(input)).hostname);
      return sources()(input, init);
    };
    const next = await refresh(fixtureSnapshot(), { githubToken: 'g', fetch, now: () => NOW, log: silent });
    assert.equal(next.status.scarf.ok, false);
    assert.equal(next.status.scarf.error, 'SCARF_TOKEN is not set');
    assert.ok(!called.includes('api.scarf.sh'));
  });

  it('fails Docker Hub when every request fails', async () => {
    const next = await refresh(fixtureSnapshot(), {
      githubToken: 'g',
      scarfToken: 's',
      fetch: sources(['docker']),
      now: () => NOW,
      log: silent,
    });
    assert.equal(next.status.dockerhub.ok, false);
    assert.equal(next.status.dockerhub.error, 'every request failed');
  });

  it('can skip Docker Hub', async () => {
    const previous = fixtureSnapshot();
    const next = await refresh(previous, {
      githubToken: 'g',
      scarfToken: 's',
      skipDockerHub: true,
      fetch: sources(),
      now: () => NOW,
      log: silent,
    });
    assert.deepEqual(next.dockerhub, previous.dockerhub);
    assert.deepEqual(next.status.dockerhub, previous.status.dockerhub);
  });

  it('does not modify the snapshot it was given', async () => {
    const previous = fixtureSnapshot();
    const copy = structuredClone(previous);
    await refresh(previous, { githubToken: 'g', scarfToken: 's', fetch: sources(), now: () => NOW, log: silent });
    assert.deepEqual(previous, copy);
  });
});
