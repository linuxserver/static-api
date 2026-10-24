/**
 * Shapes of everything the API serves. The v1 types mirror the Pydantic models in
 * linuxserver/docker-lsio-api (root/app/models.py) field for field and in the same order, because
 * key order is part of what clients see. openapi/openapi.yaml describes the same shapes; the
 * contract tests fail if the two drift apart.
 */

export interface Tag {
  tag: string;
  desc: string;
}

export interface Architecture {
  arch: string;
  tag: string;
}

export interface Changelog {
  date: string;
  desc: string;
}

export interface Volume {
  path: string;
  host_path: string;
  desc: string;
  optional: boolean;
}

export interface Port {
  external: string;
  internal: string;
  desc: string;
  optional: boolean;
}

export interface EnvVar {
  name: string;
  value: string;
  desc: string;
  optional: boolean;
}

export interface Custom {
  name: string;
  name_compose: string;
  value: string | string[];
  desc: string;
  optional: boolean;
}

export interface SecurityOpt {
  run_var: string;
  compose_var: string;
  desc: string;
  optional: boolean;
}

export interface Device {
  path: string;
  host_path: string;
  desc: string;
  optional: boolean;
}

export interface Cap {
  cap_add: string;
  desc: string;
  optional: boolean;
}

export interface Hostname {
  hostname: string;
  desc: string;
  optional: boolean;
}

export interface MacAddress {
  mac_address: string;
  desc: string;
  optional: boolean;
}

export interface Config {
  application_setup?: string;
  readonly_supported?: boolean;
  nonroot_supported?: boolean;
  privileged?: boolean;
  networking?: string;
  hostname?: Hostname;
  mac_address?: MacAddress;
  env_vars?: EnvVar[];
  volumes?: Volume[];
  ports?: Port[];
  custom?: Custom[];
  security_opt?: SecurityOpt[];
  devices?: Device[];
  caps?: Cap[];
}

/** An image as /api/v1/images lists it. */
export interface Image {
  name: string;
  initial_date?: string;
  github_url: string;
  project_url?: string;
  project_logo?: string;
  description: string;
  version: string;
  version_timestamp: string;
  category: string;
  stable: boolean;
  deprecated: boolean;
  stars: number;
  monthly_pulls?: number;
  tags: Tag[];
  architectures: Architecture[];
  /** The three most recent entries. */
  changelog?: Changelog[];
  config?: Config;
}

export interface Registries {
  lscr: string;
  ghcr: string;
  docker_hub: string;
}

export interface Snippets {
  docker_compose: string;
  docker_run: string;
}

/** Everything known about one image: the v1 fields plus the additions this API makes. */
export interface ImageDetail extends Omit<Image, 'changelog' | 'config'> {
  /** Every entry, newest first. */
  changelog?: Changelog[];
  config: Config;
  categories: string[];
  deprecation_message?: string;
  /** The image's "Application Setup" section, as Markdown. */
  setup_instructions?: string;
  archived: boolean;
  release_url?: string;
  docker_hub_pulls?: number;
  docs_url: string;
  registries: Registries;
  snippets: Snippets;
}

export type Health = 'Success' | 'Failed';

export interface Envelope<T> {
  status: 'OK';
  last_updated: string;
  data: T;
}

export interface ImagesResponse extends Envelope<{ repositories: { linuxserver: Image[] } }> {}

export interface Category {
  name: string;
  slug: string;
  count: number;
  images: string[];
}

export interface Stats {
  images: number;
  deprecated: number;
  monthly_pulls: number;
  docker_hub_pulls: number;
  stars: number;
  architectures: Record<string, number>;
  readonly_supported: number;
  nonroot_supported: number;
  updated_last_7_days: number;
  categories: number;
  first_release?: string;
}

export interface ChangelogEntry extends Changelog {
  image: string;
}

export interface SourceStatus {
  ok: boolean;
  checked_at: string;
  /** When this source last returned data; older data is kept when a refresh fails. */
  fetched_at?: string;
  error?: string;
}

export interface Status {
  health: Health;
  images: number;
  deprecated: number;
  sources: Record<string, SourceStatus>;
}
