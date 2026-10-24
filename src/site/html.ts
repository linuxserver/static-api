/**
 * A minimal HTML template tag: interpolated values are escaped unless wrapped in raw(), and arrays are
 * joined, so pages read like markup without a framework and can't inject unescaped data by accident.
 */
import { marked } from 'marked';
import { escapeMarkup } from '../util.ts';

const RAW = Symbol('raw');

export interface Raw {
  [RAW]: string;
}

type Value = string | number | boolean | null | undefined | Raw | Value[];

export const raw = (s: string): Raw => ({ [RAW]: s });

function render(value: Value): string {
  if (value === null || value === undefined || value === false) return '';
  if (Array.isArray(value)) return value.map(render).join('');
  if (typeof value === 'object') return value[RAW];
  return escapeMarkup(String(value));
}

export function html(strings: TemplateStringsArray, ...values: Value[]): Raw {
  return raw(strings.reduce((out, s, i) => out + s + (i < values.length ? render(values[i]!) : ''), ''));
}

export const toString = (value: Raw) => value[RAW];

/** Markdown from our own OpenAPI descriptions (trusted content). */
export const markdown = (s: string | undefined): Raw => raw(s ? (marked.parse(s, { async: false }) as string) : '');

/** A link that opens in a new tab and says so to screen readers. */
export const external = (href: string, label: string | Raw, className = '') =>
  html`<a href="${href}" class="${className}" target="_blank" rel="noopener"
    >${label}<span class="sr-only"> (opens in a new tab)</span></a
  >`;
