/**
 * Turns one repository's snapshot into an API image. A port of updater.py (get_image and its get_*
 * helpers) in linuxserver/docker-lsio-api, kept deliberately close so the output matches; the
 * differences are that bad data skips the one field or image instead of failing the whole update, and
 * that this also produces the extra fields ImageDetail adds.
 */
import type {
  Architecture,
  Cap,
  Changelog,
  Config,
  Custom,
  Device,
  EnvVar,
  Hostname,
  ImageDetail,
  MacAddress,
  Port,
  SecurityOpt,
  Tag,
  Volume,
} from './api/types.ts';
import { apiSubstitutions, parseReadmeVars, readmeSubstitutions, type ReadmeVars } from './readme-vars.ts';
import { isImageRepo, type RepoSnapshot } from './snapshot.ts';
import { REGISTRY, dockerCompose, dockerRun } from './snippets.ts';
import { dropUndefined, errorMessage } from './util.ts';

interface PullCounts {
  /** Monthly pulls from Scarf. */
  monthly: Record<string, number>;
  /** Lifetime pulls from Docker Hub. */
  lifetime: Record<string, number>;
}

// ---------------------------------------------------------------------------------------------------
// Reading loosely typed YAML values the way the Python version (and Pydantic's coercion) does.

/** Python truthiness: empty strings, lists and mappings are false. */
function truthy(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === 'object') return Object.keys(value).length > 0;
  return Boolean(value);
}

const str = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

const optionalStr = (value: unknown): string | undefined =>
  value === null || value === undefined ? undefined : String(value);

/** Pydantic's lax bool parsing, for the handful of flags that are sometimes quoted. */
function optionalBool(value: unknown): boolean | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value === 'string') return ['true', 'yes', 'on', '1', 'y', 't'].includes(value.toLowerCase());
  return Boolean(value);
}

/** The list under `key`, keeping only mapping entries. */
function items(vars: ReadmeVars, key: string): Record<string, unknown>[] {
  const list = vars[key];
  if (!Array.isArray(list)) return [];
  return list.filter((x): x is Record<string, unknown> => Boolean(x) && typeof x === 'object' && !Array.isArray(x));
}

/** Required entries from `key`, then optional ones from `opt_key`, mapped with `make`. */
function paired<T>(
  vars: ReadmeVars,
  key: string,
  optKey: string,
  make: (item: Record<string, unknown>, optional: boolean) => T,
): T[] | undefined {
  const list = [...items(vars, key).map((x) => make(x, false)), ...items(vars, optKey).map((x) => make(x, true))];
  return list.length ? list : undefined;
}

// ---------------------------------------------------------------------------------------------------
// Dates

/**
 * "2026-10-24T11:25:58.123Z" -> "2026-10-24 11:25:58+00:00": str() of a whole-second Python datetime,
 * which is what the current API's timestamps look like (GitHub's never have fractions anyway).
 */
export function pythonTimestamp(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d
    .toISOString()
    .replace('T', ' ')
    .replace(/(\.\d+)?Z$/, '+00:00');
}

/** The inverse of pythonTimestamp, as epoch milliseconds. */
export const parsePythonTimestamp = (ts: string) => Date.parse(ts.replace(' ', 'T'));

/** "24.10.26:" -> "2026-10-24", following strptime's %y rule (69-99 are 1900s). Null if it isn't a real date. */
export function changelogDate(raw: unknown): string | null {
  const m = /^(\d{1,2})\.(\d{1,2})\.(\d{2}):?$/.exec(str(raw).trim());
  if (!m) return null;
  const [day, month, yy] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const year = yy < 69 ? 2000 + yy : 1900 + yy;
  const d = new Date(Date.UTC(year, month - 1, day));
  if (d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) return null;
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------------------------------
// The get_* helpers from updater.py

export function getTags(vars: ReadmeVars): { tags: Tag[]; stable: boolean } {
  if (!('development_versions_items' in vars))
    return { tags: [{ tag: 'latest', desc: 'Stable releases' }], stable: true };
  const tags = items(vars, 'development_versions_items').map((x) => ({ tag: str(x.tag), desc: str(x.desc) }));
  return { tags, stable: tags.some((t) => t.tag === 'latest') };
}

export function getArchitectures(vars: ReadmeVars): Architecture[] {
  if (!('available_architectures' in vars)) return [{ arch: 'x86_64', tag: 'amd64-latest' }];
  return items(vars, 'available_architectures').map((x) => ({ arch: str(x.arch), tag: str(x.tag) }));
}

/** Every changelog entry with a valid date (newest first), and the date of the oldest one. */
export function getChangelog(vars: ReadmeVars): { changelog?: Changelog[]; initialDate?: string } {
  if (!('changelogs' in vars)) return {};
  const changelog = items(vars, 'changelogs').flatMap((x) => {
    const date = changelogDate(x.date);
    return date ? [{ date, desc: str(x.desc) }] : [];
  });
  return { changelog, initialDate: changelog.at(-1)?.date };
}

export function getDescription(vars: ReadmeVars): string {
  return str(vars.project_blurb ?? 'No description')
    .replaceAll('\n', ' ')
    .replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, '');
}

export function getEnvVars(vars: ReadmeVars): EnvVar[] | undefined {
  const common: EnvVar[] = truthy(vars.common_param_env_vars_enabled)
    ? [
        { name: 'PUID', value: '1000', desc: 'User ID', optional: false },
        { name: 'PGID', value: '1000', desc: 'Group ID', optional: false },
        { name: 'TZ', value: 'Etc/UTC', desc: 'Timezone', optional: false },
      ]
    : [];
  const own = paired(vars, 'param_env_vars', 'opt_param_env_vars', (x, optional) => ({
    name: str(x.env_var),
    value: str(x.env_value),
    desc: str(x.desc),
    optional,
  }));
  const all = [...common, ...(own ?? [])];
  return all.length ? all : undefined;
}

export const getVolumes = (vars: ReadmeVars): Volume[] | undefined =>
  paired(vars, 'param_volumes', 'opt_param_volumes', (x, optional) => ({
    path: str(x.vol_path),
    host_path: str(x.vol_host_path),
    desc: str(x.desc),
    optional,
  }));

export const getPorts = (vars: ReadmeVars): Port[] | undefined =>
  paired(vars, 'param_ports', 'opt_param_ports', (x, optional) => ({
    external: str(x.external_port),
    internal: str(x.internal_port),
    desc: str(x.port_desc),
    optional,
  }));

export const getCustom = (vars: ReadmeVars): Custom[] | undefined =>
  paired(vars, 'custom_params', 'opt_custom_params', (x, optional) => ({
    name: str(x.name),
    name_compose: str(x.name_compose),
    value: Array.isArray(x.value) ? x.value.map(str) : str(x.value),
    desc: str(x.desc),
    optional,
  }));

export const getSecurityOpt = (vars: ReadmeVars): SecurityOpt[] | undefined =>
  paired(vars, 'security_opt_param_vars', 'opt_security_opt_param_vars', (x, optional) => ({
    run_var: str(x.run_var),
    compose_var: str(x.compose_var),
    desc: str(x.desc),
    optional,
  }));

export const getDevices = (vars: ReadmeVars): Device[] | undefined =>
  paired(vars, 'param_devices', 'opt_param_devices', (x, optional) => ({
    path: str(x.device_path),
    host_path: str(x.device_host_path),
    desc: str(x.desc),
    optional,
  }));

export const getCaps = (vars: ReadmeVars): Cap[] | undefined =>
  paired(vars, 'cap_add_param_vars', 'opt_cap_add_param_vars', (x, optional) => ({
    cap_add: str(x.cap_add_var),
    desc: str(x.desc),
    optional,
  }));

/** A single parameter whose `flag` is true (required) or "optional"; absent when the flag is falsy. */
function flagged<T extends object>(
  vars: ReadmeVars,
  flag: string,
  make: () => T,
): (T & { optional: boolean }) | undefined {
  const include = vars[flag];
  return truthy(include) ? { ...make(), optional: include === 'optional' } : undefined;
}

export const getHostname = (vars: ReadmeVars): Hostname | undefined =>
  flagged(vars, 'param_usage_include_hostname', () => ({
    hostname: str(vars.param_hostname),
    desc: str(vars.param_hostname_desc),
  }));

export const getMacAddress = (vars: ReadmeVars): MacAddress | undefined =>
  flagged(vars, 'param_usage_include_mac_address', () => ({
    mac_address: str(vars.param_mac_address),
    desc: str(vars.param_mac_address_desc),
  }));

/**
 * The Application Setup section as Markdown, rendered the way the README renders it (with links to the
 * project) rather than with the v1 substitutions, which drop them.
 */
export function getSetupInstructions(text: string, name: string, vars: ReadmeVars): string | undefined {
  if (!truthy(vars.app_setup_block_enabled)) return undefined;
  // Keeping the links can make a value invalid YAML (an unquoted "[Name](url) is …" is a flow sequence),
  // which must cost only this field, not the whole image.
  try {
    const readme = parseReadmeVars(text, readmeSubstitutions(name, str(vars.project_url)));
    return str(readme?.app_setup_block).trim() || undefined;
  } catch (e) {
    console.warn(`  ! no setup instructions for ${name}: ${errorMessage(e)}`);
    return undefined;
  }
}

function getConfig(vars: ReadmeVars, githubUrl: string): Config {
  const config: Config = {
    application_setup: truthy(vars.app_setup_block_enabled)
      ? `${githubUrl}?tab=readme-ov-file#application-setup`
      : undefined,
    readonly_supported: optionalBool(vars.readonly_supported),
    nonroot_supported: optionalBool(vars.nonroot_supported),
    privileged: optionalBool(vars.privileged),
    networking: optionalStr(vars.param_net),
    hostname: getHostname(vars),
    mac_address: getMacAddress(vars),
    env_vars: getEnvVars(vars),
    volumes: getVolumes(vars),
    ports: getPorts(vars),
    custom: getCustom(vars),
    security_opt: getSecurityOpt(vars),
    devices: getDevices(vars),
    caps: getCaps(vars),
  };
  return dropUndefined(config);
}

/** "Network,DNS" -> ["Network", "DNS"] */
export const splitCategories = (category: string) =>
  category
    .split(',')
    .map((c) => c.trim())
    .filter(Boolean);

/**
 * The image name and readme-vars for a repository, or null when it isn't one we list: not an image
 * repo, no readme-vars.yml, or categorised Internal. Throws when readme-vars.yml is not valid YAML.
 */
export function listedImage(repo: RepoSnapshot): { name: string; text: string; vars: ReadmeVars } | null {
  if (!isImageRepo(repo.name) || !repo.readme_vars) return null;
  const name = repo.name.replace('docker-', '');
  const vars = parseReadmeVars(repo.readme_vars, apiSubstitutions(name));
  if (!vars || str(vars.project_categories).includes('Internal')) return null;
  return { name, text: repo.readme_vars, vars };
}

export function buildImage(repo: RepoSnapshot, pulls: PullCounts): ImageDetail | null {
  const listed = listedImage(repo);
  if (!listed) return null;
  const { name, text, vars } = listed;
  const category = str(vars.project_categories);
  const { tags, stable } = getTags(vars);
  const { changelog, initialDate } = getChangelog(vars);
  const release = repo.latest_release;
  const config = getConfig(vars, repo.url);
  const deprecated = optionalBool(vars.project_deprecation_status) ?? false;
  const snippets = { docker_compose: dockerCompose(name, config), docker_run: dockerRun(name, config) };

  return dropUndefined({
    name,
    initial_date: initialDate,
    github_url: repo.url,
    project_url: optionalStr(vars.project_url),
    project_logo: optionalStr(vars.project_logo),
    description: getDescription(vars),
    version: release ? release.tag : 'latest',
    version_timestamp: pythonTimestamp(release ? release.published_at : repo.pushed_at),
    category,
    stable,
    deprecated,
    stars: repo.stars,
    monthly_pulls: pulls.monthly[name],
    tags,
    architectures: getArchitectures(vars),
    changelog,
    config,
    categories: splitCategories(category),
    deprecation_message: deprecated ? optionalStr(vars.project_deprecation_message) : undefined,
    setup_instructions: getSetupInstructions(text, name, vars),
    archived: repo.archived,
    release_url: release?.url,
    docker_hub_pulls: pulls.lifetime[name],
    docs_url: `https://docs.linuxserver.io/images/${repo.name}/`,
    registries: {
      lscr: `${REGISTRY}/${name}`,
      ghcr: `ghcr.io/linuxserver/${name}`,
      docker_hub: `docker.io/linuxserver/${name}`,
    },
    snippets,
  });
}

/** Runs `fn` for one repository. A broken readme-vars.yml skips that image rather than failing them all. */
function skippingBroken<T>(repo: RepoSnapshot, fn: () => T | null | undefined): T[] {
  try {
    const result = fn();
    return result === null || result === undefined ? [] : [result];
  } catch (e) {
    console.warn(`  ! skipped ${repo.name}: ${errorMessage(e)}`);
    return [];
  }
}

/** Every listed image, sorted by name like the Python version (which sorts by repository name). */
export function buildImages(repos: RepoSnapshot[], pulls: PullCounts): ImageDetail[] {
  return [...repos]
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .flatMap((repo) => skippingBroken(repo, () => buildImage(repo, pulls)));
}

/** The names buildImages would list, without building the images. */
export const listedImageNames = (repos: RepoSnapshot[]) =>
  repos.flatMap((repo) => skippingBroken(repo, () => listedImage(repo)?.name));
