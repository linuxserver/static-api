/**
 * Serves dist/ the way GitHub Pages does: under BASE_PATH, index.html for directories, 404.html for
 * anything missing, and content types by extension. Build with the same SITE_URL/BASE_PATH first.
 *
 * Usage: npm run build && npm run preview
 */
import { readFile, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { extname, join, normalize } from 'node:path';
import { PATHS, siteConfig } from '../src/config.ts';

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.json': 'application/json',
  '.yaml': 'application/yaml',
  '.yml': 'application/yaml',
  '.xml': 'application/atom+xml',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

const { basePath } = siteConfig();
const port = Number(process.env.PORT ?? 4322);

async function resolveFile(urlPath: string): Promise<string | null> {
  if (!urlPath.startsWith(basePath)) return null;
  let decoded: string;
  try {
    decoded = decodeURIComponent(urlPath.slice(basePath.length));
  } catch {
    return null; // A malformed escape such as "%E0%A4%A" is a 404, not a crash.
  }
  const relative = normalize(decoded).replace(/^(\.\.[/\\])+/, '');
  const file = join(PATHS.dist, relative);
  const info = await stat(file).catch(() => null);
  if (info?.isFile()) return file;
  if (info?.isDirectory())
    return (await stat(join(file, 'index.html')).catch(() => null)) ? join(file, 'index.html') : null;
  return null;
}

createServer(async (req, res) => {
  const path = new URL(req.url ?? '/', 'http://localhost').pathname;
  const file = await resolveFile(path);
  res.setHeader('Access-Control-Allow-Origin', '*');
  if (!file) {
    res.writeHead(404, { 'Content-Type': TYPES['.html'] });
    res.end(await readFile(join(PATHS.dist, '404.html')).catch(() => 'Not found'));
    return;
  }
  res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream' });
  res.end(await readFile(file));
}).listen(port, () => console.log(`http://localhost:${port}${basePath}`));
