/** The hand-written spec in openapi/openapi.yaml, and the small subset of OpenAPI the build reads. */
import { readFile } from 'node:fs/promises';
import { parse } from 'yaml';

export interface Schema {
  $ref?: string;
  type?: string;
  format?: string;
  description?: string;
  enum?: unknown[];
  const?: unknown;
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
  additionalProperties?: Schema | boolean;
  allOf?: Schema[];
  oneOf?: Schema[];
}

export interface Parameter {
  $ref?: string;
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema?: Schema;
  example?: unknown;
}

export interface Response {
  $ref?: string;
  description: string;
  content?: Record<string, { schema?: Schema }>;
}

export interface Operation {
  operationId: string;
  summary: string;
  description?: string;
  tags?: string[];
  parameters?: Parameter[];
  responses: Record<string, Response>;
}

export interface OpenApiDoc {
  openapi: string;
  info: { title: string; version: string; summary?: string; description?: string };
  servers: { url: string }[];
  tags?: { name: string; description?: string }[];
  paths: Record<string, { get?: Operation }>;
  components: {
    schemas: Record<string, Schema>;
    parameters?: Record<string, Parameter>;
    responses?: Record<string, Response>;
  };
}

export async function loadSpec(path: string): Promise<OpenApiDoc> {
  return parse(await readFile(path, 'utf8')) as OpenApiDoc;
}

/** Follows a local "#/components/…" reference. */
export function resolve<T extends { $ref?: string }>(spec: OpenApiDoc, node: T): T {
  if (!node.$ref) return node;
  const target = node.$ref
    .replace(/^#\//, '')
    .split('/')
    .reduce<unknown>((obj, key) => (obj as Record<string, unknown> | undefined)?.[key], spec);
  if (!target) throw new Error(`Unresolvable $ref ${node.$ref}`);
  return resolve(spec, target as T);
}

/** Resolves a schema and merges its allOf parts, so an object's properties are all in one place. */
export function flatten(spec: OpenApiDoc, schema: Schema): Schema {
  const s = resolve(spec, schema);
  if (!s.allOf) return s;
  const parts = s.allOf.map((p) => flatten(spec, p));
  return {
    type: 'object',
    description: s.description ?? parts.find((p) => p.description)?.description,
    properties: Object.assign({}, ...parts.map((p) => p.properties ?? {})),
    required: parts.flatMap((p) => p.required ?? []),
  };
}

/** "#/components/schemas/Image" -> "Image" */
export const refName = (ref: string) => ref.slice(ref.lastIndexOf('/') + 1);

/** Every GET operation with its path, in spec order. */
export const operations = (spec: OpenApiDoc) =>
  Object.entries(spec.paths).flatMap(([path, item]) => (item.get ? [{ path, operation: item.get }] : []));

/** The schema of an operation's 200 response, and its media type. */
export function successContent(spec: OpenApiDoc, operation: Operation): { mediaType: string; schema?: Schema } {
  const response = resolve(spec, operation.responses['200'] ?? { description: '' });
  const [mediaType = 'application/json', content] = Object.entries(response.content ?? {})[0] ?? [];
  return { mediaType, schema: content?.schema };
}
