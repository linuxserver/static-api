import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { toV1Image } from '../src/api/responses.ts';
import { apiSubstitutions, parseReadmeVars } from '../src/readme-vars.ts';
import { isImageRepo } from '../src/snapshot.ts';
import {
  buildImage,
  buildImages,
  changelogDate,
  getArchitectures,
  getChangelog,
  getCustom,
  getDescription,
  getEnvVars,
  getHostname,
  getPorts,
  getSetupInstructions,
  getTags,
  pythonTimestamp,
  splitCategories,
} from '../src/transform.ts';
import { fixtureRepos, liveV1, repo } from './helpers.ts';

const noPulls = { monthly: {}, lifetime: {} };
const vars = (yaml: string) => parseReadmeVars(yaml, apiSubstitutions('example'))!;

describe('parity with api.linuxserver.io', () => {
  const images = buildImages(fixtureRepos.repos, { monthly: fixtureRepos.scarf, lifetime: {} });

  it('lists the same images', () => {
    assert.deepEqual(
      images.map((i) => i.name),
      liveV1.map((i) => i.name).sort(),
    );
  });

  for (const expected of liveV1) {
    it(`produces ${expected.name} exactly, key order included`, () => {
      const image = images.find((i) => i.name === expected.name)!;
      assert.equal(JSON.stringify(toV1Image(image, true)), JSON.stringify(expected));
    });
  }
});

describe('isImageRepo', () => {
  it('accepts docker-* repositories except base images', () => {
    assert.equal(isImageRepo('docker-sonarr'), true);
    assert.equal(isImageRepo('docker-baseimage-alpine'), false);
    assert.equal(isImageRepo('docker-mods'), true);
    assert.equal(isImageRepo('site'), false);
  });
});

describe('buildImage', () => {
  it('skips repositories that are not listed', () => {
    assert.equal(buildImage(repo({ name: 'docs' }), noPulls), null);
    assert.equal(buildImage(repo({ name: 'docker-baseimage-ubuntu' }), noPulls), null);
    assert.equal(buildImage(repo({ readme_vars: null }), noPulls), null);
    assert.equal(buildImage(repo({ readme_vars: 'project_categories: "Internal,Tools"\n' }), noPulls), null);
  });

  it('uses the latest release for the version', () => {
    const image = buildImage(repo(), noPulls)!;
    assert.equal(image.version, '1.0.0-ls1');
    assert.equal(image.version_timestamp, '2026-10-20 08:30:00+00:00');
    assert.equal(image.release_url, 'https://github.com/linuxserver/docker-example/releases/tag/1.0.0-ls1');
  });

  it('falls back to "latest" and the last push when there is no stable release', () => {
    const image = buildImage(repo({ latest_release: null }), noPulls)!;
    assert.equal(image.version, 'latest');
    assert.equal(image.version_timestamp, '2026-10-01 10:00:00+00:00');
    assert.equal(image.release_url, undefined);
  });

  it('adds pull counts when the sources have them', () => {
    const image = buildImage(repo(), { monthly: { example: 12 }, lifetime: { example: 3400 } })!;
    assert.equal(image.monthly_pulls, 12);
    assert.equal(image.docker_hub_pulls, 3400);
    assert.equal('monthly_pulls' in buildImage(repo(), noPulls)!, false);
  });

  it('adds the detail fields', () => {
    const image = buildImage(repo({ archived: true }), noPulls)!;
    assert.equal(image.archived, true);
    assert.equal(image.docs_url, 'https://docs.linuxserver.io/images/docker-example/');
    assert.deepEqual(image.registries, {
      lscr: 'lscr.io/linuxserver/example',
      ghcr: 'ghcr.io/linuxserver/example',
      docker_hub: 'docker.io/linuxserver/example',
    });
    assert.deepEqual(image.categories, ['Tools']);
    assert.match(image.snippets.docker_compose, /image: lscr\.io\/linuxserver\/example:latest/);
  });

  it('includes the deprecation message only for deprecated images', () => {
    const yaml = 'project_deprecation_status: true\nproject_deprecation_message: "Upstream is gone."\n';
    assert.equal(buildImage(repo({ readme_vars: yaml }), noPulls)!.deprecation_message, 'Upstream is gone.');
    const notDeprecated = 'project_deprecation_message: "Left over."\n';
    assert.equal(buildImage(repo({ readme_vars: notDeprecated }), noPulls)!.deprecation_message, undefined);
  });

  it('keeps going when one readme-vars.yml is broken', () => {
    const images = buildImages([repo({ name: 'docker-broken', readme_vars: 'a: [unclosed' }), repo()], noPulls);
    assert.deepEqual(
      images.map((i) => i.name),
      ['example'],
    );
  });

  it('sorts by repository name', () => {
    const images = buildImages([repo({ name: 'docker-zeta' }), repo({ name: 'docker-alpha' })], noPulls);
    assert.deepEqual(
      images.map((i) => i.name),
      ['alpha', 'zeta'],
    );
  });
});

describe('dates', () => {
  it('formats timestamps like str(datetime)', () => {
    assert.equal(pythonTimestamp('2026-10-24T11:25:58Z'), '2026-10-24 11:25:58+00:00');
    assert.equal(pythonTimestamp('2026-10-24T11:25:58.123Z'), '2026-10-24 11:25:58+00:00');
    assert.equal(pythonTimestamp(null), '');
    assert.equal(pythonTimestamp('nonsense'), '');
  });

  it('parses changelog dates with strptime %y rules', () => {
    assert.equal(changelogDate('24.10.26:'), '2026-10-24');
    assert.equal(changelogDate('01.01.50:'), '2050-01-01');
    assert.equal(changelogDate('29.06.15:'), '2015-06-29');
    assert.equal(changelogDate('01.01.69:'), '1969-01-01');
    assert.equal(changelogDate('1.2.24'), '2024-02-01');
  });

  it('rejects dates that do not exist or do not parse', () => {
    assert.equal(changelogDate('31.02.24:'), null);
    assert.equal(changelogDate('2024-01-01'), null);
    assert.equal(changelogDate(undefined), null);
  });
});

describe('readme-vars fields', () => {
  it('defaults tags and architectures', () => {
    assert.deepEqual(getTags(vars('a: 1')), { tags: [{ tag: 'latest', desc: 'Stable releases' }], stable: true });
    assert.deepEqual(getArchitectures(vars('a: 1')), [{ arch: 'x86_64', tag: 'amd64-latest' }]);
  });

  it('is stable only when a latest tag is published', () => {
    const yaml = 'development_versions_items:\n  - {tag: "develop", desc: "Dev"}\n';
    assert.deepEqual(getTags(vars(yaml)), { tags: [{ tag: 'develop', desc: 'Dev' }], stable: false });
  });

  it('keeps every valid changelog entry and dates the image from the oldest', () => {
    const yaml = [
      'changelogs:',
      '  - {date: "03.01.25:", desc: "Third"}',
      '  - {date: "99.99.99:", desc: "Broken"}',
      '  - {date: "02.01.25:", desc: "Second"}',
      '  - {date: "01.01.25:", desc: "First"}',
    ].join('\n');
    const { changelog, initialDate } = getChangelog(vars(yaml));
    assert.deepEqual(
      changelog?.map((c) => c.desc),
      ['Third', 'Second', 'First'],
    );
    assert.equal(initialDate, '2025-01-01');
    assert.deepEqual(getChangelog(vars('a: 1')), {});
  });

  it('flattens the description', () => {
    assert.equal(getDescription(vars('project_blurb: |\n  Line one\n  line two\n')), 'Line one line two');
    assert.equal(getDescription(vars('a: 1')), 'No description');
  });

  it('puts the common env vars first, then required, then optional', () => {
    const yaml = [
      'common_param_env_vars_enabled: true',
      'param_env_vars:',
      '  - {env_var: "A", env_value: "1", desc: "a"}',
      'opt_param_env_vars:',
      '  - {env_var: "B", env_value: 2, desc: "b"}',
    ].join('\n');
    const env = getEnvVars(vars(yaml))!;
    assert.deepEqual(
      env.map((e) => [e.name, e.value, e.optional]),
      [
        ['PUID', '1000', false],
        ['PGID', '1000', false],
        ['TZ', 'Etc/UTC', false],
        ['A', '1', false],
        ['B', '2', true],
      ],
    );
    assert.equal(getEnvVars(vars('a: 1')), undefined);
  });

  it('maps ports and custom params, keeping list values', () => {
    const yaml = [
      'param_ports:',
      '  - {external_port: "51820", internal_port: "51820/udp", port_desc: "wg"}',
      'custom_params:',
      '  - {name: "sysctl", name_compose: "sysctls", value: ["a=1", "b=2"], desc: "d"}',
    ].join('\n');
    assert.deepEqual(getPorts(vars(yaml)), [{ external: '51820', internal: '51820/udp', desc: 'wg', optional: false }]);
    assert.deepEqual(getCustom(vars(yaml))?.[0]?.value, ['a=1', 'b=2']);
  });

  it('marks the hostname optional only when asked to', () => {
    const required = 'param_usage_include_hostname: true\nparam_hostname: "h"\nparam_hostname_desc: "d"\n';
    assert.deepEqual(getHostname(vars(required)), { hostname: 'h', desc: 'd', optional: false });
    const optional = required.replace('true', '"optional"');
    assert.equal(getHostname(vars(optional))?.optional, true);
    assert.equal(getHostname(vars('param_hostname: "h"')), undefined);
  });

  it('returns setup instructions as the README renders them, links included', () => {
    const yaml = [
      'project_url: "https://example.org"',
      'app_setup_block_enabled: true',
      'app_setup_block: |',
      '  {% raw -%}',
      '  See [{{ project_name|capitalize }}]({{ project_url }}) or [docs]({{project_url}}).',
      '  {%- endraw %}',
    ].join('\n');
    assert.equal(
      getSetupInstructions(yaml, 'example', vars(yaml)),
      'See [Example](https://example.org) or [docs](https://example.org).',
    );
    const disabled = 'app_setup_block: "x"';
    assert.equal(getSetupInstructions(disabled, 'example', vars(disabled)), undefined);
  });

  it('drops only the setup instructions when keeping the links breaks the YAML', () => {
    // Fine with the v1 substitutions ("example is great"), a flow sequence followed by text with the README ones.
    const yaml = [
      'project_url: "https://example.org"',
      'project_blurb: [{{ project_name|capitalize }}]({{ project_url }}) is great',
      'app_setup_block_enabled: true',
      'app_setup_block: "x"',
    ].join('\n');
    const image = buildImage(repo({ readme_vars: yaml }), noPulls)!;
    assert.equal(image.description, 'example is great');
    assert.equal(image.setup_instructions, undefined);
  });

  it('splits categories', () => {
    assert.deepEqual(splitCategories('Network, DNS,, '), ['Network', 'DNS']);
    assert.deepEqual(splitCategories(''), []);
  });
});
