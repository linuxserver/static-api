import { fileURLToPath } from 'node:url';

const path = (relative: string) => fileURLToPath(new URL(`../${relative}`, import.meta.url));

export const PATHS = {
  data: path('data'),
  dist: path('dist'),
  public: path('public'),
  openapi: path('openapi/openapi.yaml'),
  modules: path('node_modules'),
};

export interface SiteConfig {
  /** Origin the site is served from, e.g. https://api.linuxserver.io */
  siteUrl: string;
  /** Path prefix, with leading and trailing slash: "/" or "/static-api/". */
  basePath: string;
}

/** SITE_URL and BASE_PATH come from actions/configure-pages in CI. */
export function siteConfig(env: NodeJS.ProcessEnv = process.env): SiteConfig {
  const siteUrl = (env.SITE_URL || 'http://localhost:4322').replace(/\/+$/, '');
  const basePath = `/${(env.BASE_PATH ?? '').replace(/^\/+|\/+$/g, '')}/`.replace('//', '/');
  return { siteUrl, basePath };
}

/** The site's public URL, with a trailing slash: "https://api.linuxserver.io/". */
export const siteRoot = (cfg: SiteConfig) => `${cfg.siteUrl}${cfg.basePath}`;

/** The API's base URL for `servers` and examples, without a trailing slash: "https://api.linuxserver.io". */
export const apiRoot = (cfg: SiteConfig) => siteRoot(cfg).replace(/\/$/, '');
