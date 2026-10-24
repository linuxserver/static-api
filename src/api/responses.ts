/** Builds every JSON payload from the image list. Pure, so each endpoint is tested without the filesystem. */
import type {
  Category,
  ChangelogEntry,
  Envelope,
  Health,
  Image,
  ImageDetail,
  ImagesResponse,
  SourceStatus,
  Stats,
  Status,
} from './types.ts';
import { parsePythonTimestamp, pythonTimestamp } from '../transform.ts';
import { dropUndefined } from '../util.ts';

const CHANGELOG_LIMIT = 100;

export interface Model {
  images: ImageDetail[];
  /** ISO 8601 time of the last successful GitHub refresh. */
  updatedAt: string;
  health: Health;
  sources: Record<string, SourceStatus>;
}

/** Every response is wrapped like the original's, with its Python-style last_updated. */
const envelope = <T>(model: Model, data: T): Envelope<T> => ({
  status: 'OK',
  last_updated: pythonTimestamp(model.updatedAt),
  data,
});

const current = (model: Model) => model.images.filter((i) => !i.deprecated);

/** The v1 view of an image: the original fields only, three changelog entries, config on request. */
export function toV1Image(image: ImageDetail, includeConfig: boolean): Image {
  return dropUndefined({
    name: image.name,
    initial_date: image.initial_date,
    github_url: image.github_url,
    project_url: image.project_url,
    project_logo: image.project_logo,
    description: image.description,
    version: image.version,
    version_timestamp: image.version_timestamp,
    category: image.category,
    stable: image.stable,
    deprecated: image.deprecated,
    stars: image.stars,
    monthly_pulls: image.monthly_pulls,
    tags: image.tags,
    architectures: image.architectures,
    changelog: image.changelog?.slice(0, 3),
    config: includeConfig ? image.config : undefined,
  });
}

/** /api/v1/images with its two query switches. */
export function imagesResponse(
  model: Model,
  { includeConfig = false, includeDeprecated = false } = {},
): ImagesResponse {
  const images = includeDeprecated ? model.images : current(model);
  return envelope(model, { repositories: { linuxserver: images.map((i) => toV1Image(i, includeConfig)) } });
}

export const imageResponse = (model: Model, image: ImageDetail) => envelope(model, { image });

export const catalogResponse = (model: Model) => envelope(model, { images: model.images });

export const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');

export function categoriesResponse(model: Model) {
  const byName = new Map<string, string[]>();
  for (const image of current(model)) {
    for (const c of image.categories) {
      if (!byName.has(c)) byName.set(c, []);
      byName.get(c)!.push(image.name);
    }
  }
  const categories: Category[] = [...byName]
    .map(([name, images]) => ({ name, slug: slugify(name), count: images.length, images: images.sort() }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'en'));
  return envelope(model, { categories });
}

const sum = (xs: (number | undefined)[]) => xs.reduce<number>((a, b) => a + (b ?? 0), 0);

export function statsResponse(model: Model) {
  const images = current(model);
  const architectures: Record<string, number> = {};
  for (const image of images) {
    for (const arch of new Set(image.architectures.map((a) => a.arch))) {
      architectures[arch] = (architectures[arch] ?? 0) + 1;
    }
  }
  const weekBefore = Date.parse(model.updatedAt) - 7 * 864e5;
  const firstRelease = images
    .map((i) => i.initial_date)
    .filter((d): d is string => Boolean(d))
    .sort()[0];
  const stats: Stats = {
    images: images.length,
    deprecated: model.images.length - images.length,
    monthly_pulls: sum(images.map((i) => i.monthly_pulls)),
    docker_hub_pulls: sum(images.map((i) => i.docker_hub_pulls)),
    stars: sum(images.map((i) => i.stars)),
    architectures,
    readonly_supported: images.filter((i) => i.config.readonly_supported).length,
    nonroot_supported: images.filter((i) => i.config.nonroot_supported).length,
    updated_last_7_days: images.filter((i) => parsePythonTimestamp(i.version_timestamp) >= weekBefore).length,
    categories: new Set(images.flatMap((i) => i.categories)).size,
    ...(firstRelease ? { first_release: firstRelease } : {}),
  };
  return envelope(model, { stats });
}

/** The most recent changelog entries across current images: newest first, then by image name. */
export function recentChangelog(model: Model): ChangelogEntry[] {
  return current(model)
    .flatMap((image) => (image.changelog ?? []).map((c) => ({ image: image.name, date: c.date, desc: c.desc })))
    .sort((a, b) => b.date.localeCompare(a.date) || a.image.localeCompare(b.image))
    .slice(0, CHANGELOG_LIMIT);
}

export const changelogResponse = (model: Model) => envelope(model, { changelog: recentChangelog(model) });

export function statusResponse(model: Model) {
  const images = current(model).length;
  const status: Status = {
    health: model.health,
    images,
    deprecated: model.images.length - images,
    sources: model.sources,
  };
  return envelope(model, { status });
}
