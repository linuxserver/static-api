/**
 * Builds dist/ from data/ and the OpenAPI spec: every endpoint as a static file, the spec, and the docs
 * page. Rendering is pure (snapshot in, map of path -> contents out) and validates the API's files against
 * the spec; only main() touches the disk.
 *
 * Usage: [SITE_URL=https://api.linuxserver.io] [BASE_PATH=/] node src/build.ts
 */
import { cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { stringify } from 'yaml';
import { changelogFeed } from './api/feed.ts';
import {
  catalogResponse,
  categoriesResponse,
  changelogResponse,
  imageResponse,
  imagesResponse,
  recentChangelog,
  statsResponse,
  statusResponse,
  type Model,
} from './api/responses.ts';
import { apiRoot, PATHS, siteConfig, siteRoot, type SiteConfig } from './config.ts';
import { loadSpec, type OpenApiDoc } from './openapi.ts';
import { indexPage, notFoundPage } from './site/page.ts';
import { loadSnapshot, type Snapshot } from './snapshot.ts';
import { buildImages } from './transform.ts';
import { createValidator } from './validate.ts';

export type Files = Map<string, string>;

/** Image used in the docs examples when it exists. */
const EXAMPLE_IMAGE = 'sonarr';

export function toModel(snapshot: Snapshot): Model {
  return {
    images: buildImages(snapshot.github.repos, { monthly: snapshot.scarf.pulls, lifetime: snapshot.dockerhub.pulls }),
    updatedAt: snapshot.github.fetched_at,
    health: snapshot.status.github.ok ? 'Success' : 'Failed',
    // A source no refresh has tried yet (say, after --skip-dockerhub on an empty data/) has nothing to report.
    sources: Object.fromEntries(Object.entries(snapshot.status).filter(([, s]) => s.checked_at)),
  };
}

const json = (value: unknown) => JSON.stringify(value);

/** The original API's query switches, as files. */
const IMAGE_LIST_VARIANTS = [
  { file: 'api/v1/images.json', includeConfig: false, includeDeprecated: false },
  { file: 'api/v1/images.config.json', includeConfig: true, includeDeprecated: false },
  { file: 'api/v1/images.deprecated.json', includeConfig: false, includeDeprecated: true },
  { file: 'api/v1/images.config.deprecated.json', includeConfig: true, includeDeprecated: true },
] as const;

/** Every endpoint of the API, as the files the spec describes. */
export function renderApi(model: Model, config: SiteConfig): Files {
  const files: Files = new Map();

  files.set('health', json(model.health));
  files.set('health.json', json(model.health));
  for (const variant of IMAGE_LIST_VARIANTS) files.set(variant.file, json(imagesResponse(model, variant)));
  files.set('api/v1/images', files.get('api/v1/images.json')!);

  for (const image of model.images) {
    files.set(`api/v1/catalog/${image.name}.json`, json(imageResponse(model, image)));
    files.set(`api/v1/catalog/${image.name}/docker-compose.yml`, image.snippets.docker_compose);
  }
  files.set('api/v1/catalog.json', json(catalogResponse(model)));
  files.set('api/v1/categories.json', json(categoriesResponse(model)));
  files.set('api/v1/stats.json', json(statsResponse(model)));
  files.set('api/v1/changelog.json', json(changelogResponse(model)));
  files.set('api/v1/status.json', json(statusResponse(model)));
  files.set(
    'api/v1/changelog.xml',
    changelogFeed(recentChangelog(model), model.images, {
      selfUrl: `${apiRoot(config)}/api/v1/changelog.xml`,
      siteUrl: siteRoot(config),
      updated: model.updatedAt,
    }),
  );
  return files;
}

/** The spec as published: pointing at wherever this copy of the site is served. */
export function renderSpec(spec: OpenApiDoc, config: SiteConfig): Files {
  const published = { ...spec, servers: [{ url: apiRoot(config) }] };
  return new Map([
    ['openapi.json', JSON.stringify(published, null, 2) + '\n'],
    ['openapi.yaml', stringify(published, { lineWidth: 0 })],
  ]);
}

export function renderSite(model: Model, spec: OpenApiDoc, config: SiteConfig): Files {
  const example = model.images.find((i) => i.name === EXAMPLE_IMAGE) ?? model.images[0];
  const ctx = {
    model,
    spec,
    config,
    stats: statsResponse(model).data.stats,
    example: { name: example?.name ?? EXAMPLE_IMAGE, version: example?.version ?? 'latest' },
  };
  return new Map([
    ['index.html', indexPage(ctx)],
    ['404.html', notFoundPage(ctx)],
  ]);
}

/** Every file of the site. Throws if the API's files don't match the spec. */
export function render(model: Model, spec: OpenApiDoc, config: SiteConfig): Files {
  const api = renderApi(model, config);
  const problems = createValidator(spec).validateAll(api);
  if (problems.length) throw new Error(`The output does not match openapi/openapi.yaml:\n  ${problems.join('\n  ')}`);
  return new Map([...api, ...renderSpec(spec, config), ...renderSite(model, spec, config)]);
}

/** Static assets copied as they are: our CSS/JS/icons, and the Geist fonts from npm. */
const FONTS = [
  ['@fontsource-variable/geist/files/geist-latin-wght-normal.woff2', 'assets/fonts/geist.woff2'],
  ['@fontsource-variable/geist-mono/files/geist-mono-latin-wght-normal.woff2', 'assets/fonts/geist-mono.woff2'],
] as const;

export async function writeSite(outDir: string, files: Files): Promise<void> {
  await rm(outDir, { recursive: true, force: true });
  await cp(PATHS.public, outDir, { recursive: true });
  for (const [from, to] of FONTS) {
    await mkdir(dirname(join(outDir, to)), { recursive: true });
    await cp(join(PATHS.modules, from), join(outDir, to));
  }
  for (const [path, contents] of files) {
    await mkdir(dirname(join(outDir, path)), { recursive: true });
    await writeFile(join(outDir, path), contents);
  }
}

if (import.meta.main) {
  const config = siteConfig();
  const [snapshot, spec] = await Promise.all([loadSnapshot(PATHS.data), loadSpec(PATHS.openapi)]);
  const model = toModel(snapshot);
  if (!model.images.length) throw new Error('No images in data/. Run `npm run refresh` first.');
  const files = render(model, spec, config);
  await writeSite(PATHS.dist, files);
  console.log(`Built ${files.size} files for ${model.images.length} images into dist/ (${siteRoot(config)})`);
}
