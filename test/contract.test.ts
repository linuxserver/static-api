/**
 * The built files and openapi/openapi.yaml must agree: every file is described by a path in the spec,
 * every path in the spec is built, and every JSON body validates against its response schema with no
 * fields the spec doesn't declare.
 */
import assert from 'node:assert/strict';
import { before, describe, it } from 'node:test';
import { parse } from 'yaml';
import { renderApi, renderSpec, toModel, type Files } from '../src/build.ts';
import { PATHS, type SiteConfig } from '../src/config.ts';
import { loadSpec, operations, resolve, type OpenApiDoc } from '../src/openapi.ts';
import { createValidator } from '../src/validate.ts';
import { fixtureModel, fixtureSnapshot } from './helpers.ts';

const config: SiteConfig = { siteUrl: 'https://api.example.org', basePath: '/' };

let spec: OpenApiDoc;
let files: Files;
let published: Files;
let validator: ReturnType<typeof createValidator>;

before(async () => {
  spec = await loadSpec(PATHS.openapi);
  files = renderApi(fixtureModel(), config);
  published = renderSpec(spec, config);
  validator = createValidator(spec);
});

describe('OpenAPI contract', () => {
  it('describes every built file with exactly one path, and builds every path', () => {
    assert.deepEqual(validator.validateAll(files), []);
  });

  it('rejects files no path describes', () => {
    assert.deepEqual(validator.validate('api/v1/catalog/a/b.json', '{}'), [
      'api/v1/catalog/a/b.json matches 0 paths in the spec',
    ]);
    assert.deepEqual(validator.validate('api/v1/catalog/sonarr/docker-compose.yml', 'not checked'), []);
    assert.deepEqual(validator.validate('api/v1/catalog/changedetection.io.json', 'nope'), [
      'api/v1/catalog/changedetection.io.json: Unexpected token \'o\', "nope" is not valid JSON',
    ]);
  });

  it('catches bodies that drift from the spec', () => {
    const image = JSON.parse(files.get('api/v1/catalog/sonarr.json')!);
    image.data.image.config.new_field = true;
    assert.deepEqual(validator.validate('api/v1/catalog/sonarr.json', JSON.stringify(image)), [
      'api/v1/catalog/sonarr.json.data.image.config.new_field is not in the spec',
    ]);
    const stats = JSON.parse(files.get('api/v1/stats.json')!);
    stats.data.stats.images = 'many';
    assert.match(validator.validate('api/v1/stats.json', JSON.stringify(stats)).join(), /must be integer/);
    assert.match(
      validator.validateAll(new Map([['api/v1/stats.json', '{}']])).join('\n'),
      /nothing built for \/health/,
    );
  });

  it('builds valid files when a source has never been tried', () => {
    const snapshot = fixtureSnapshot();
    snapshot.status.dockerhub = { ok: false, checked_at: '' };
    const model = toModel(snapshot);
    assert.deepEqual(Object.keys(model.sources), ['github', 'scarf']);
    assert.deepEqual(validator.validateAll(renderApi(model, config)), []);
  });

  it('gives every operation a unique id and a tag the spec defines', () => {
    const ids = operations(spec).map(({ operation }) => operation.operationId);
    assert.equal(new Set(ids).size, ids.length);
    const tags = new Set(spec.tags?.map((t) => t.name));
    for (const { path, operation } of operations(spec)) {
      assert.ok(
        operation.tags?.every((t) => tags.has(t)),
        path,
      );
    }
  });

  it('serves compose files that are valid YAML and an Atom feed', () => {
    assert.equal(
      parse(files.get('api/v1/catalog/sonarr/docker-compose.yml')!).services.sonarr.restart,
      'unless-stopped',
    );
    assert.match(
      files.get('api/v1/changelog.xml')!,
      /^<\?xml[\s\S]*<feed xmlns="http:\/\/www.w3.org\/2005\/Atom">[\s\S]*<\/feed>\n$/,
    );
  });

  it('publishes the spec pointing at the configured server', () => {
    const json = JSON.parse(published.get('openapi.json')!) as OpenApiDoc;
    assert.deepEqual(json.servers, [{ url: 'https://api.example.org' }]);
    assert.deepEqual(parse(published.get('openapi.yaml')!), json);
    assert.deepEqual({ ...json, servers: spec.servers }, spec);
  });

  it('resolves every $ref in the spec', () => {
    const visit = (node: unknown): void => {
      if (Array.isArray(node)) return node.forEach(visit);
      if (!node || typeof node !== 'object') return;
      if ('$ref' in node) resolve(spec, node as { $ref: string });
      Object.values(node).forEach(visit);
    };
    visit(spec);
  });
});
