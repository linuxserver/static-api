/**
 * readme-vars.yml is the source of truth for every image's README, docs page and API entry. It is a
 * Jinja template in places, so the expressions that appear in values are substituted in the text before
 * parsing (substituting after parsing would not work: an unquoted "[{{ project_name }}]" is a YAML list).
 */
import { parse } from 'yaml';

export type ReadmeVars = Record<string, unknown>;

type Substitution = [string | RegExp, string];

/**
 * Exactly what lsio_github.py substitutes, so the v1 fields match the original API. Applied in order;
 * the bracketed forms must go before the bare ones. Links to the project are dropped.
 */
export const apiSubstitutions = (projectName: string): Substitution[] => [
  ['[{{ project_name|capitalize }}]', projectName],
  ['{{ project_name|capitalize }}', projectName],
  ['[{{ project_name }}]', projectName],
  ['{{ project_name }}', projectName],
  ['({{ project_url }})', ''],
  ['{{ project_url }}', ''],
  ['{{ arch_x86_64 }}', 'x86_64'],
  ['{{ arch_arm64 }}', 'arm64'],
];

/** What Jinja renders for the README, for fields this API adds: links kept, raw markers removed. */
export const readmeSubstitutions = (projectName: string, projectUrl: string): Substitution[] => [
  [/\{\{\s*project_name\s*\|\s*capitalize\s*\}\}/g, projectName.charAt(0).toUpperCase() + projectName.slice(1)],
  [/\{\{\s*project_name\s*\}\}/g, projectName],
  [/\{\{\s*project_url\s*\}\}/g, projectUrl],
  [/\{\{\s*arch_x86_64\s*\}\}/g, 'x86_64'],
  [/\{\{\s*arch_arm64\s*\}\}/g, 'arm64'],
  [/\{%-?\s*(?:end)?raw\s*-?%\}/g, ''],
];

/** Returns null when the file is missing, empty or not a YAML mapping. Throws on invalid YAML. */
export function parseReadmeVars(text: string | null, substitutions: Substitution[]): ReadmeVars | null {
  if (!text) return null;
  // A function replacement, so a "$&" or "$'" in a project URL is inserted literally like Python's replace.
  const rendered = substitutions.reduce((s, [expression, value]) => s.replaceAll(expression, () => value), text);
  // YAML 1.1 to match PyYAML's SafeLoader (yes/no/on/off are booleans there), which also accepts
  // duplicate keys with the last one winning.
  const parsed: unknown = parse(rendered, { version: '1.1', uniqueKeys: false });
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as ReadmeVars) : null;
}
