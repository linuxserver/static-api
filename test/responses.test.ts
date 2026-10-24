import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { changelogFeed } from '../src/api/feed.ts';
import {
  categoriesResponse,
  changelogResponse,
  imagesResponse,
  recentChangelog,
  slugify,
  statsResponse,
  statusResponse,
  toV1Image,
  type Model,
} from '../src/api/responses.ts';
import { buildImages } from '../src/transform.ts';
import { fixtureModel, repo } from './helpers.ts';

const model = fixtureModel();
const names = (images: { name: string }[]) => images.map((i) => i.name);

/** A small model with known dates, categories and architectures. */
function smallModel(): Model {
  const yaml = (category: string, changelog: string[], extra = '') =>
    [
      `project_categories: "${category}"`,
      'available_architectures:',
      '  - {arch: "x86_64", tag: "amd64-latest"}',
      '  - {arch: "arm64", tag: "arm64v8-latest"}',
      'changelogs:',
      ...changelog.map((c) => `  - {date: "${c}:", desc: "Change on ${c}"}`),
      extra,
    ].join('\n');
  const repos = [
    repo({ name: 'docker-alpha', readme_vars: yaml('Media,Tools', ['10.10.26', '01.01.20']) }),
    repo({ name: 'docker-beta', readme_vars: yaml('Tools', ['10.10.26', '02.02.21']), latest_release: null }),
    repo({ name: 'docker-gone', readme_vars: yaml('Media', ['20.10.26'], 'project_deprecation_status: true') }),
  ];
  return {
    images: buildImages(repos, { monthly: { alpha: 10, beta: 5, gone: 100 }, lifetime: { alpha: 1000 } }),
    updatedAt: '2026-10-24T12:00:00.000Z',
    health: 'Success',
    sources: {},
  };
}

describe('imagesResponse', () => {
  it('wraps the list like the original API', () => {
    const res = imagesResponse(model);
    assert.equal(res.status, 'OK');
    assert.equal(res.last_updated, '2026-10-24 13:11:46+00:00');
    assert.ok(Array.isArray(res.data.repositories.linuxserver));
  });

  it('leaves out deprecated images and config by default', () => {
    const images = imagesResponse(model).data.repositories.linuxserver;
    assert.ok(images.every((i) => !i.deprecated && !('config' in i)));
    assert.ok(names(images).includes('sonarr'));
    assert.ok(!names(images).includes('readarr'));
  });

  it('honours both switches', () => {
    const all = imagesResponse(model, { includeConfig: true, includeDeprecated: true }).data.repositories.linuxserver;
    assert.equal(all.length, model.images.length);
    assert.ok(all.every((i) => 'config' in i));
  });
});

describe('toV1Image', () => {
  it('keeps only the original fields and three changelog entries', () => {
    const detail = model.images.find((i) => i.name === 'sonarr')!;
    const v1 = toV1Image(detail, false);
    assert.ok(detail.changelog!.length > 3);
    assert.equal(v1.changelog?.length, 3);
    for (const extra of ['categories', 'snippets', 'registries', 'docs_url', 'archived', 'config']) {
      assert.equal(extra in v1, false, extra);
    }
  });
});

describe('categoriesResponse', () => {
  it('counts current images per category, most populated first', () => {
    assert.deepEqual(categoriesResponse(smallModel()).data.categories, [
      { name: 'Tools', slug: 'tools', count: 2, images: ['alpha', 'beta'] },
      { name: 'Media', slug: 'media', count: 1, images: ['alpha'] },
    ]);
  });

  it('slugifies names', () => {
    assert.equal(slugify('3D Printing'), '3d-printing');
    assert.equal(slugify(' Home Automation '), 'home-automation');
  });
});

describe('statsResponse', () => {
  it('sums current images only', () => {
    assert.deepEqual(statsResponse(smallModel()).data.stats, {
      images: 2,
      deprecated: 1,
      monthly_pulls: 15,
      docker_hub_pulls: 1000,
      stars: 10,
      architectures: { x86_64: 2, arm64: 2 },
      readonly_supported: 0,
      nonroot_supported: 0,
      // alpha's release (20 Oct) is within the week before last_updated; beta has none, and pushed 1 Oct.
      updated_last_7_days: 1,
      categories: 2,
      first_release: '2020-01-01',
    });
  });
});

describe('changelog', () => {
  it('lists current images newest first, ties by name', () => {
    assert.deepEqual(recentChangelog(smallModel()), [
      { image: 'alpha', date: '2026-10-10', desc: 'Change on 10.10.26' },
      { image: 'beta', date: '2026-10-10', desc: 'Change on 10.10.26' },
      { image: 'beta', date: '2021-02-02', desc: 'Change on 02.02.21' },
      { image: 'alpha', date: '2020-01-01', desc: 'Change on 01.01.20' },
    ]);
  });

  it('is limited to the 100 most recent', () => {
    assert.ok(changelogResponse(model).data.changelog.length <= 100);
  });

  it('renders an Atom feed with escaped text and stable ids', () => {
    const entries = [{ image: 'a&b', date: '2026-10-10', desc: 'Use <new> "flag"' }];
    const options = { selfUrl: 'https://x/feed.xml', siteUrl: 'https://x/', updated: '2026-10-24T12:00:00.000Z' };
    const feed = changelogFeed(entries, [], options);
    assert.match(feed, /<title>a&amp;b: Use &lt;new&gt; &quot;flag&quot;<\/title>/);
    assert.match(feed, /<updated>2026-10-10T00:00:00Z<\/updated>/);
    const id = /<id>(urn:sha1:[0-9a-f]{40})<\/id>/.exec(feed)?.[1];
    assert.ok(id);
    assert.equal(changelogFeed(entries, [], options).includes(id), true);
  });
});

describe('statusResponse', () => {
  it('reports health and per-source status', () => {
    const status = statusResponse({
      ...smallModel(),
      health: 'Failed',
      sources: { github: { ok: false, checked_at: 'x' } },
    }).data.status;
    assert.deepEqual(status, {
      health: 'Failed',
      images: 2,
      deprecated: 1,
      sources: { github: { ok: false, checked_at: 'x' } },
    });
  });
});
