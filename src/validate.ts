/**
 * Checks the API's files against the OpenAPI spec: each file must be served at exactly one path the spec
 * describes, each JSON body must validate against that path's response schema without undeclared fields,
 * and every path must have been built. The build runs this on its output, so data that doesn't fit the
 * spec is never published.
 */
import { Ajv2020, type ValidateFunction } from 'ajv/dist/2020.js';
import ajvFormats from 'ajv-formats';
import { flatten, operations, successContent, type OpenApiDoc, type Schema } from './openapi.ts';
import { errorMessage } from './util.ts';

// ajv-formats is CommonJS: the plugin is its `default` property.
const addFormats = ajvFormats.default;

/** "/api/v1/catalog/{name}.json" -> a regex matching "api/v1/catalog/sonarr.json". */
function pathPattern(path: string): RegExp {
  const escaped = path
    .slice(1)
    .split(/\{[^}]+\}/)
    .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(`^${escaped.join('[^/]+')}$`);
}

/** Properties in `value` the schema doesn't declare. The published spec stays open to additions. */
function undeclared(spec: OpenApiDoc, schema: Schema, value: unknown, at: string): string[] {
  const s = flatten(spec, schema);
  if (Array.isArray(value)) return s.items ? value.flatMap((v, i) => undeclared(spec, s.items!, v, `${at}[${i}]`)) : [];
  if (!value || typeof value !== 'object' || s.oneOf) return [];
  return Object.entries(value).flatMap(([key, v]) => {
    const declared =
      s.properties?.[key] ?? (typeof s.additionalProperties === 'object' ? s.additionalProperties : null);
    return declared ? undeclared(spec, declared, v, `${at}.${key}`) : [`${at}.${key} is not in the spec`];
  });
}

export function createValidator(spec: OpenApiDoc) {
  const ajv = new Ajv2020({ strict: false, allErrors: true });
  addFormats(ajv);

  const ops = operations(spec).map(({ path, operation }) => {
    const { mediaType, schema } = successContent(spec, operation);
    const json = mediaType === 'application/json' && schema ? schema : undefined;
    // The components travel with each schema so its local "#/components/…" references resolve.
    let compiled: ValidateFunction | undefined;
    const check = () => (compiled ??= ajv.compile({ ...json, components: spec.components }));
    return { path, pattern: pathPattern(path), schema: json, check };
  });

  /** Problems with one file; empty when it is fine. */
  function validate(file: string, body: string): string[] {
    const matches = ops.filter((op) => op.pattern.test(file));
    if (matches.length !== 1) return [`${file} matches ${matches.length} paths in the spec`];
    const op = matches[0]!;
    if (!op.schema) return [];
    let data: unknown;
    try {
      data = JSON.parse(body);
    } catch (e) {
      return [`${file}: ${errorMessage(e)}`];
    }
    const check = op.check();
    const errors = check(data) ? [] : [`${file}: ${ajv.errorsText(check.errors)}`];
    return [...errors, ...undeclared(spec, op.schema, data, file)];
  }

  /** Problems across every file of the API, including spec paths nothing was built for. */
  function validateAll(files: Map<string, string>): string[] {
    const problems = [...files].flatMap(([file, body]) => validate(file, body));
    const unbuilt = ops.filter((op) => ![...files.keys()].some((f) => op.pattern.test(f)));
    return [...problems, ...unbuilt.map((op) => `nothing built for ${op.path}`)];
  }

  return { validate, validateAll };
}
