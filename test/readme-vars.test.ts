import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { apiSubstitutions, parseReadmeVars, readmeSubstitutions } from '../src/readme-vars.ts';

describe('parseReadmeVars', () => {
  it('substitutes the template expressions lsio_github.py does', () => {
    const yaml = [
      'project_blurb: "[{{ project_name|capitalize }}]({{ project_url }}) is {{ project_name }}."',
      'available_architectures:',
      '  - {arch: "{{ arch_x86_64 }}", tag: "amd64-latest"}',
      '  - {arch: "{{ arch_arm64 }}", tag: "arm64v8-latest"}',
    ].join('\n');
    assert.deepEqual(parseReadmeVars(yaml, apiSubstitutions('sonarr')), {
      project_blurb: 'sonarr is sonarr.',
      available_architectures: [
        { arch: 'x86_64', tag: 'amd64-latest' },
        { arch: 'arm64', tag: 'arm64v8-latest' },
      ],
    });
  });

  it('renders like the README for the fields this API adds', () => {
    const yaml = [
      'block: |',
      '  {% raw -%}',
      '  [{{ project_name|capitalize }}]({{ project_url }}) and [{{project_name}}]({{project_url}}) on {{ arch_arm64 }}',
      '  {%- endraw %}',
    ].join('\n');
    assert.deepEqual(parseReadmeVars(yaml, readmeSubstitutions('sonarr', 'https://sonarr.tv/')), {
      block: '\n[Sonarr](https://sonarr.tv/) and [sonarr](https://sonarr.tv/) on arm64\n',
    });
  });

  it('parses YAML 1.1 booleans like PyYAML', () => {
    assert.deepEqual(parseReadmeVars('a: yes\nb: off\n', apiSubstitutions('x')), { a: true, b: false });
  });

  it('accepts duplicate keys like PyYAML, the last one winning', () => {
    assert.deepEqual(parseReadmeVars('a: 1\nb: 2\na: 3\n', apiSubstitutions('x')), { a: 3, b: 2 });
  });

  it('inserts substituted values literally', () => {
    assert.deepEqual(parseReadmeVars('u: "{{ project_url }}"\n', readmeSubstitutions('x', "https://e.org/$&$'")), {
      u: "https://e.org/$&$'",
    });
  });

  it('returns null for missing, empty or non-mapping files', () => {
    assert.equal(parseReadmeVars(null, apiSubstitutions('x')), null);
    assert.equal(parseReadmeVars('', apiSubstitutions('x')), null);
    assert.equal(parseReadmeVars('- a\n- b\n', apiSubstitutions('x')), null);
  });

  it('throws on invalid YAML so the caller can skip the image', () => {
    assert.throws(() => parseReadmeVars('a: [unclosed', apiSubstitutions('x')));
  });
});
