import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { before, describe, it } from 'node:test';
import { render, renderSite, writeSite, type Files } from '../src/build.ts';
import { PATHS, siteConfig, type SiteConfig } from '../src/config.ts';
import { loadSpec, operations, type OpenApiDoc } from '../src/openapi.ts';
import { html, toString } from '../src/site/html.ts';
import { formatTimestamp } from '../src/site/page.ts';
import { operationAnchor, typeLabel } from '../src/site/reference.ts';
import { escapeMarkup } from '../src/util.ts';
import { fixtureModel } from './helpers.ts';

const config: SiteConfig = { siteUrl: 'https://example.github.io', basePath: '/static-api/' };
let spec: OpenApiDoc;
let site: Files;

before(async () => {
  spec = await loadSpec(PATHS.openapi);
  site = renderSite(fixtureModel(), spec, config);
});

describe('html', () => {
  it('escapes interpolated values but not nested templates', () => {
    const name = '<script>"x"</script>';
    assert.equal(
      toString(html`<p title="${name}">${html`<b>${name}</b>`}</p>`),
      `<p title="${escapeMarkup(name)}"><b>${escapeMarkup(name)}</b></p>`,
    );
  });

  it('joins arrays and drops empty values', () => {
    assert.equal(toString(html`${['a', 'b']}${null}${undefined}${false}${0}`), 'ab0');
  });
});

describe('docs page', () => {
  it('documents every operation', () => {
    const page = site.get('index.html')!;
    for (const { path, operation } of operations(spec)) {
      assert.ok(page.includes(`id="${operationAnchor(operation)}"`), path);
      assert.ok(page.includes(`data-path="${path}"`), path);
    }
  });

  it('prefixes every local link with the base path', () => {
    for (const page of site.values()) {
      const local = [...page.matchAll(/(?:href|src)="(\/[^"]*)"/g)].map((m) => m[1]!);
      assert.ok(local.length > 0);
      for (const url of local) assert.ok(url.startsWith('/static-api/'), url);
    }
  });

  it('shows real data in the examples', () => {
    const page = site.get('index.html')!;
    const sonarr = fixtureModel().images.find((i) => i.name === 'sonarr')!;
    assert.ok(page.includes(`https://example.github.io/static-api/api/v1/catalog/sonarr.json`));
    assert.ok(page.includes(`<span class="out">${sonarr.version}</span>`));
    assert.ok(page.includes('<option value="wireguard">'));
  });

  it('says when the last refresh failed', () => {
    const failed = renderSite({ ...fixtureModel(), health: 'Failed' }, spec, config).get('index.html')!;
    assert.match(failed, /Last refresh failed/);
    assert.match(failed, /pulse pulse-bad/);
  });

  it('has one h1 and labelled landmarks', () => {
    for (const page of site.values()) {
      assert.equal(page.match(/<h1[\s>]/g)?.length, 1);
      assert.match(page, /<main id="main"/);
      assert.match(page, /<nav aria-label="Main"/);
      assert.match(page, /<html lang="en-GB"/);
    }
  });

  it('labels types readably', () => {
    assert.equal(typeLabel(spec, { $ref: '#/components/schemas/Config' }), 'Config');
    assert.equal(typeLabel(spec, { $ref: '#/components/schemas/Timestamp' }), 'string');
    assert.equal(typeLabel(spec, { type: 'array', items: { $ref: '#/components/schemas/Tag' } }), 'Tag[]');
    assert.equal(typeLabel(spec, { $ref: '#/components/schemas/Health' }), '"Success" | "Failed"');
    assert.equal(
      typeLabel(spec, { type: 'object', additionalProperties: { type: 'integer' } }),
      'map<string, integer>',
    );
  });

  it('formats timestamps in UTC', () => {
    assert.equal(formatTimestamp('2026-10-24T13:11:46.000Z'), '24 Oct 2026, 13:11 UTC');
    assert.equal(formatTimestamp(''), 'never');
  });
});

describe('siteConfig', () => {
  it('normalises the base path and URL', () => {
    assert.deepEqual(siteConfig({ SITE_URL: 'https://x.io/', BASE_PATH: 'api' }), {
      siteUrl: 'https://x.io',
      basePath: '/api/',
    });
    assert.deepEqual(siteConfig({ SITE_URL: 'https://x.io', BASE_PATH: '/' }), {
      siteUrl: 'https://x.io',
      basePath: '/',
    });
    assert.equal(siteConfig({}).basePath, '/');
  });
});

describe('writeSite', () => {
  it('writes the files, the public assets and the fonts', async () => {
    const out = await mkdtemp(join(tmpdir(), 'static-api-'));
    try {
      const model = fixtureModel();
      await writeSite(out, render(model, spec, config));
      assert.equal(await readFile(join(out, 'health'), 'utf8'), '"Success"');
      assert.equal(
        await readFile(join(out, 'api/v1/images'), 'utf8'),
        await readFile(join(out, 'api/v1/images.json'), 'utf8'),
      );
      assert.deepEqual((await readdir(join(out, 'assets/fonts'))).sort(), ['geist-mono.woff2', 'geist.woff2']);
      for (const asset of ['assets/site.css', 'assets/site.js', 'favicon.svg', 'index.html', '404.html']) {
        assert.ok((await readFile(join(out, asset))).length > 0, asset);
      }
      assert.equal(
        (await readdir(join(out, 'api/v1/catalog'))).filter((f) => f.endsWith('.json')).length,
        model.images.length,
      );
    } finally {
      await rm(out, { recursive: true, force: true });
    }
  });
});
