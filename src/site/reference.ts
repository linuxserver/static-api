/** The endpoint reference, rendered from the OpenAPI spec so the docs can never disagree with it. */
import {
  flatten,
  operations,
  refName,
  resolve,
  successContent,
  type OpenApiDoc,
  type Operation,
  type Schema,
} from '../openapi.ts';
import { external, html, markdown, type Raw } from './html.ts';

export const operationAnchor = (operation: Operation) => `op-${operation.operationId}`;

const isObject = (s: Schema) => Boolean(s.properties || s.allOf);

export function typeLabel(spec: OpenApiDoc, schema: Schema): string {
  if (schema.$ref) {
    const target = resolve(spec, schema);
    return isObject(target) ? refName(schema.$ref) : typeLabel(spec, target);
  }
  if (schema.const !== undefined) return JSON.stringify(schema.const);
  if (schema.enum) return schema.enum.map((v) => JSON.stringify(v)).join(' | ');
  if (schema.oneOf) return schema.oneOf.map((s) => typeLabel(spec, s)).join(' | ');
  if (schema.allOf) return 'object';
  if (schema.type === 'array') return `${typeLabel(spec, schema.items ?? {})}[]`;
  if (schema.type === 'object' && typeof schema.additionalProperties === 'object') {
    return `map<string, ${typeLabel(spec, schema.additionalProperties)}>`;
  }
  return schema.format ? `${schema.type} (${schema.format})` : (schema.type ?? 'any');
}

/** The object a field expands into, if any: its own properties, or those of its array items or map values. */
function expandable(spec: OpenApiDoc, schema: Schema): Schema | null {
  const s = resolve(spec, schema);
  if (isObject(s)) return flatten(spec, s);
  const inner =
    s.type === 'array' ? s.items : typeof s.additionalProperties === 'object' ? s.additionalProperties : null;
  return inner && isObject(resolve(spec, inner)) ? flatten(spec, inner) : null;
}

/** Deep enough for every schema in the spec; stops a recursive schema from recursing forever. */
const MAX_DEPTH = 6;

function fields(spec: OpenApiDoc, schema: Schema, depth = 0): Raw {
  const s = flatten(spec, schema);
  const required = new Set(s.required ?? []);
  return html`<ul class="fields">
    ${Object.entries(s.properties ?? {}).map(([name, prop]) => {
      const child = expandable(spec, prop);
      const description = prop.description ?? resolve(spec, prop).description;
      const head = html`<span class="field-name">${name}</span>
        <span class="field-type">${typeLabel(spec, prop)}</span>
        ${required.has(name) ? html`<span class="field-req">required</span>` : ''}`;
      const desc = description ? html`<div class="field-desc">${markdown(description)}</div>` : '';
      const body = child && depth < MAX_DEPTH ? fields(spec, child, depth + 1) : '';
      return html`<li>
        ${
          body
            ? html`<details>
                <summary>${head}</summary>
                ${desc} ${body}
              </details>`
            : html`<div class="field-head">${head}</div>
                ${desc}`
        }
      </li>`;
    })}
  </ul>`;
}

/** "/api/v1/catalog/{name}.json" with the parameter highlighted. */
const pathMarkup = (path: string) =>
  path
    .split(/(\{[^}]+\})/)
    .map((part) => (part.startsWith('{') ? html`<span class="path-param">${part}</span>` : part));

function operationSection(
  spec: OpenApiDoc,
  path: string,
  operation: Operation,
  imageNames: string[],
  base: string,
): Raw {
  const { mediaType, schema } = successContent(spec, operation);
  const params = (operation.parameters ?? []).map((p) => resolve(spec, p));
  const nameParam = params.find((p) => p.in === 'path');
  const anchor = operationAnchor(operation);
  const defaultName = String(nameParam?.example ?? imageNames[0] ?? '');
  // The real URL, so Open works before (or without) the script, which keeps it in sync with the input.
  const openHref = `${base}${path.slice(1).replace(/\{[^}]+\}/, encodeURIComponent(defaultName))}`;
  return html`<article class="op raft-panel" id="${anchor}" aria-labelledby="${anchor}-title">
    <header class="op-head">
      <span class="method">GET</span>
      <code class="op-path">${pathMarkup(path)}</code>
    </header>
    <div class="op-body">
      <h3 id="${anchor}-title">${operation.summary}</h3>
      <div class="prose">${markdown(operation.description)}</div>
      ${
        params.length
          ? html`<h4>Parameters</h4>
              <ul class="fields">
                ${params.map(
                  (p) =>
                    html`<li>
                      <div class="field-head">
                        <span class="field-name">${p.name}</span>
                        <span class="field-type">${p.in} · ${typeLabel(spec, p.schema ?? {})}</span>
                        ${p.required ? html`<span class="field-req">required</span>` : ''}
                      </div>
                      <div class="field-desc">${markdown(p.description)}</div>
                    </li>`,
                )}
              </ul>`
          : ''
      }
      <h4>Response <span class="media">${mediaType}</span></h4>
      ${
        schema && expandable(spec, schema)
          ? html`<details class="schema">
              <summary>${schema.$ref ? refName(schema.$ref) : 'Schema'}</summary>
              ${fields(spec, schema)}
            </details>`
          : html`<p class="muted">
              ${schema ? typeLabel(spec, schema) : 'Text'}${mediaType === 'application/json' ? '' : ' document'}.
            </p>`
      }
      <div class="try" data-path="${path}">
        ${
          nameParam
            ? html`<label class="try-label"
                >${nameParam.name}
                <input
                  class="try-input"
                  name="${nameParam.name}"
                  list="image-names"
                  value="${defaultName}"
                  autocomplete="off"
                  spellcheck="false"
              /></label>`
            : ''
        }
        <button type="button" class="btn btn-primary try-send">Try it</button>
        ${external(openHref, 'Open', 'btn try-open')}
        <div class="try-result" hidden>
          <p class="try-meta" aria-live="polite"></p>
          <pre class="code"><code></code></pre>
        </div>
      </div>
    </div>
  </article>`;
}

/** Operations grouped by tag, in the order the spec lists its tags. */
function groupedOperations(spec: OpenApiDoc) {
  const all = operations(spec);
  return (spec.tags ?? []).map((tag) => ({
    tag,
    items: all.filter(({ operation }) => operation.tags?.includes(tag.name)),
  }));
}

export function referenceNav(spec: OpenApiDoc): Raw {
  return html`<nav class="ref-nav" aria-label="Endpoints">
    ${groupedOperations(spec).map(
      ({ tag, items }) =>
        html`<p class="raft-eyebrow">${tag.name}</p>
          <ul>
            ${items.map(
              ({ path, operation }) =>
                html`<li>
                  <a href="#${operationAnchor(operation)}"><code>${path}</code></a>
                </li>`,
            )}
          </ul>`,
    )}
  </nav>`;
}

/** `base` is the site's base path, for the Open links. */
export function reference(spec: OpenApiDoc, imageNames: string[], base: string): Raw {
  return html`${groupedOperations(spec).map(
      ({ tag, items }) =>
        html`<section class="ref-group" aria-labelledby="tag-${tag.name}">
          <h2 id="tag-${tag.name}" class="ref-tag"><span class="accent" aria-hidden="true">//</span> ${tag.name}</h2>
          <div class="prose muted">${markdown(tag.description)}</div>
          ${items.map(({ path, operation }) => operationSection(spec, path, operation, imageNames, base))}
        </section>`,
    )} <datalist id="image-names">${imageNames.map((name) => html`<option value="${name}"></option>`)}</datalist>`;
}
