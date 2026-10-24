import { setTimeout as sleep } from 'node:timers/promises';

export type Fetch = typeof fetch;

const USER_AGENT = 'linuxserver-static-api (+https://github.com/linuxserver)';

interface RequestOptions {
  fetch?: Fetch;
  headers?: Record<string, string>;
  method?: string;
  body?: string;
  retries?: number;
  /** Base delay between retries; doubled each attempt unless the server sends Retry-After. */
  backoffMs?: number;
}

/** GET (or POST) JSON, retrying on network errors, 429 and 5xx. Throws on any other non-2xx response. */
export async function requestJSON<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { fetch: doFetch = fetch, headers = {}, method = 'GET', body, retries = 3, backoffMs = 1500 } = options;
  for (let attempt = 0; ; attempt++) {
    let res: Response;
    try {
      res = await doFetch(url, {
        method,
        body,
        headers: { 'User-Agent': USER_AGENT, Accept: 'application/json', ...headers },
      });
    } catch (e) {
      // A reset connection or DNS hiccup is as transient as a 503.
      if (attempt >= retries) throw e;
      await sleep(backoffMs * 2 ** attempt);
      continue;
    }
    if (res.ok) return (await res.json()) as T;
    // Release the connection; an unread body holds it until garbage collection.
    await res.body?.cancel();
    if (attempt >= retries || (res.status !== 429 && res.status < 500)) {
      throw new Error(`${res.status} ${res.statusText} for ${url}`);
    }
    const retryAfter = Number(res.headers.get('retry-after')) * 1000;
    await sleep(retryAfter || backoffMs * 2 ** attempt);
  }
}

/** Map over items with at most `size` calls in flight, preserving order. */
export async function pool<T, R>(items: readonly T[], size: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await fn(items[index]!);
    }
  };
  await Promise.all(Array.from({ length: Math.min(size, items.length) }, worker));
  return results;
}
