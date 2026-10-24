/** Pydantic's exclude_none: fields without a value are absent rather than null. */
export function dropUndefined<T extends object>(obj: T): T {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined)) as T;
}

export const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Escapes text for HTML and XML, in content and in quoted attributes. */
export const escapeMarkup = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
