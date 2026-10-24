/**
 * The docs site: one page in the design of www.linuxserver.io ("Raft"). Everything shown is read from
 * the spec and the data; nothing is invented.
 */
import { apiRoot, siteRoot, type SiteConfig } from '../config.ts';
import type { Model } from '../api/responses.ts';
import type { Stats } from '../api/types.ts';
import type { OpenApiDoc } from '../openapi.ts';
import wordmark from './brand/wordmark.json' with { type: 'json' };
import { external, html, markdown, raw, toString, type Raw } from './html.ts';
import { reference, referenceNav } from './reference.ts';

const LINKS = {
  site: 'https://www.linuxserver.io',
  images: 'https://www.linuxserver.io/images/',
  docs: 'https://docs.linuxserver.io/',
  github: 'https://github.com/linuxserver',
  support: 'https://www.linuxserver.io/support/',
  discord: 'https://discord.gg/YWrKVTn',
};

interface PageContext {
  model: Model;
  stats: Stats;
  spec: OpenApiDoc;
  config: SiteConfig;
  /** Image used in the examples. */
  example: { name: string; version: string };
}

/** The LinuxServer.io logo, from the site. `id` prefixes its gradient ids, so it must be unique on the page. */
function logo(className: string, id: string): Raw {
  return raw(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${wordmark.viewBox}" class="${className}" aria-hidden="true" focusable="false">${wordmark.body.replaceAll('__ID__', id)}</svg>`,
  );
}

const compact = (n: number) =>
  new Intl.NumberFormat('en-GB', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
const grouped = (n: number) => new Intl.NumberFormat('en-GB').format(n);

/** "2026-10-24T13:11:46.000Z" -> "24 Oct 2026, 13:11 UTC" */
export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'never';
  const date = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' });
  return `${date.format(d)}, ${time.format(d)} UTC`;
}

/** Raft is dark unless the visitor chose light; applied before first paint so the page never flashes. */
const THEME_SCRIPT = `(function(){var t=null;try{t=localStorage.getItem('theme')}catch(e){}if(t==='light')document.documentElement.classList.remove('dark')})()`;

function layout(ctx: PageContext, title: string, description: string, body: Raw): string {
  const { config, model } = ctx;
  const base = config.basePath;
  const healthy = model.health === 'Success';
  return (
    '<!doctype html>\n' +
    toString(
      html`<html lang="en-GB" class="dark">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>${title}</title>
          <meta name="description" content="${description}" />
          <meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />
          <meta name="theme-color" content="#0b0913" media="(prefers-color-scheme: dark)" />
          <link rel="canonical" href="${siteRoot(config)}" />
          <link rel="icon" href="${base}favicon.svg" type="image/svg+xml" />
          <link
            rel="alternate"
            type="application/atom+xml"
            title="Image changelog"
            href="${base}api/v1/changelog.xml"
          />
          <link rel="preload" href="${base}assets/fonts/geist.woff2" as="font" type="font/woff2" crossorigin />
          <link rel="stylesheet" href="${base}assets/site.css" />
          <script>
            ${raw(THEME_SCRIPT)};
          </script>
          <script src="${base}assets/site.js" defer></script>
        </head>
        <body>
          <a href="#main" class="skip-link">Skip to content</a>
          <aside aria-label="Data status" class="strip">
            <div class="container strip-inner">
              <p class="strip-status">
                <span class="${healthy ? 'pulse' : 'pulse pulse-bad'}" aria-hidden="true"></span>
                <span
                  ><a href="${base}api/v1/status.json">${healthy ? 'Data is current' : 'Last refresh failed'}</a> ·
                  <span class="fg">${ctx.stats.images}</span> images</span
                >
              </p>
              <p class="strip-date">
                refreshed
                <time datetime="${model.updatedAt}">${formatTimestamp(model.updatedAt)}</time>
              </p>
            </div>
          </aside>
          <header class="site-header">
            <div class="container header-inner">
              <a href="${base}" class="brand" aria-label="LinuxServer.io API home">
                ${logo('brand-logo', 'logo-header')}<span class="brand-tag">API</span>
              </a>
              <nav aria-label="Main" class="main-nav">
                <ul>
                  <li><a href="${base}#endpoints">Endpoints</a></li>
                  <li><a href="${base}openapi.json">OpenAPI</a></li>
                  <li>${external(LINKS.images, 'Images')}</li>
                  <li>${external(LINKS.docs, 'Docs')}</li>
                </ul>
              </nav>
              <div class="header-actions">
                ${external(
                  LINKS.github,
                  html`<svg viewBox="0 0 24 24" aria-hidden="true" class="icon">
                      <path
                        fill="currentColor"
                        d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 0-.8.4-1.3.7-1.6-2.7-.3-5.5-1.3-5.5-6 0-1.2.5-2.3 1.3-3.1-.2-.4-.6-1.6 0-3.2 0 0 1-.3 3.4 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.6 1.6.2 2.8 0 3.2.9.8 1.3 1.9 1.3 3.2 0 4.6-2.8 5.6-5.5 5.9.5.4.9 1 .9 2.2v3.3c0 .3.1.7.8.6A12 12 0 0 0 12 .3"
                      /></svg
                    ><span class="sr-only">LinuxServer.io on GitHub</span>`,
                  'icon-btn',
                )}
                <button
                  type="button"
                  class="icon-btn theme-toggle"
                  aria-label="Switch to light theme"
                  data-theme-toggle
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" class="icon icon-sun">
                    <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2" />
                    <path
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
                    />
                  </svg>
                  <svg viewBox="0 0 24 24" aria-hidden="true" class="icon icon-moon">
                    <path
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linejoin="round"
                      d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </header>
          <main id="main" tabindex="-1">${body}</main>
          <footer class="site-footer">
            <div class="container footer-inner">
              <div>
                ${logo('footer-logo', 'logo-footer')}
                <p class="muted">
                  Volunteers building and maintaining the largest collection of community Docker images. Free and open
                  source, always.
                </p>
              </div>
              <ul class="footer-links">
                <li>${external(LINKS.site, 'linuxserver.io')}</li>
                <li>${external(LINKS.docs, 'Documentation')}</li>
                <li>${external(LINKS.support, 'Support')}</li>
                <li>${external(LINKS.discord, 'Discord')}</li>
                <li>${external(LINKS.github, 'GitHub')}</li>
              </ul>
            </div>
          </footer>
        </body>
      </html>`,
    ) +
    '\n'
  );
}

/** A headline number; screen readers get it in full with its noun ("1,234 images"). */
function statTile(label: string, n: number, noun: string, short = grouped): Raw {
  return html`<div class="raft-panel stat">
    <p class="raft-eyebrow">${label}</p>
    <p class="stat-value">
      <span aria-hidden="true">${short(n)}</span><span class="sr-only">${grouped(n)} ${noun}</span>
    </p>
  </div>`;
}

/** The data sources behind each field, so nobody has to read the code to find out. */
const SOURCES: [string, string, string][] = [
  [
    'Image list, description, tags, architectures, changelog, config',
    'readme-vars.yml in each docker-* repository',
    'https://github.com/linuxserver',
  ],
  [
    'version, version_timestamp, release_url',
    'Latest stable GitHub release',
    'https://docs.github.com/en/repositories/releasing-projects-on-github',
  ],
  ['stars, archived', 'GitHub repository', 'https://github.com/linuxserver'],
  ['monthly_pulls', 'Scarf, which serves lscr.io', 'https://about.scarf.sh/'],
  ['docker_hub_pulls', 'Docker Hub', 'https://hub.docker.com/u/linuxserver'],
];

export function indexPage(ctx: PageContext): string {
  const { spec, stats, config, example, model } = ctx;
  const api = apiRoot(config);
  const base = config.basePath;
  const names = model.images.map((i) => i.name);

  const body = html`
    <div class="hero">
      <div class="aurora" aria-hidden="true"></div>
      <div class="grid-bg" aria-hidden="true"></div>
      <div class="container hero-inner">
        <div>
          <p class="raft-eyebrow"><span class="accent" aria-hidden="true">//</span> api v${spec.info.version}</p>
          <h1>The <span class="gradient-text">LinuxServer.io</span> API</h1>
          <div class="lede">${markdown(spec.info.summary)}</div>
          <p class="lede-small">
            Static JSON, refreshed daily from the same sources as the images themselves. No keys, nothing to install.
          </p>
          <div class="hero-actions">
            <a href="#endpoints" class="btn btn-solid">Browse endpoints</a>
            <a href="${base}openapi.json" class="btn">openapi.json</a>
            <a href="${base}openapi.yaml" class="btn">openapi.yaml</a>
          </div>
        </div>
        <figure class="raft-panel terminal">
          <div class="panel-bar" aria-hidden="true">
            <span class="dots"><span></span><span></span><span></span></span>
            <span class="panel-title">~ curl</span>
          </div>
          <figcaption class="sr-only">Example requests and their output</figcaption>
          <pre class="code"><code><span class="prompt">$</span> curl -s ${api}/api/v1/catalog/${example.name}.json \\
    | jq -r .data.image.version
<span class="out">${example.version}</span>
<span class="prompt">$</span> curl -s ${api}/api/v1/stats.json | jq .data.stats.images
<span class="out">${stats.images}</span>
<span class="prompt">$</span> curl -sO ${api}/api/v1/catalog/${example.name}/docker-compose.yml</code></pre>
        </figure>
      </div>
    </div>

    <div class="container">
      <section aria-label="At a glance" class="stats">
        ${statTile('Images', stats.images, 'images')}
        ${
          stats.monthly_pulls
            ? statTile('Monthly pulls', stats.monthly_pulls, 'pulls in the last month', compact)
            : statTile('Docker Hub pulls', stats.docker_hub_pulls, 'pulls from Docker Hub', compact)
        }
        ${statTile('Categories', stats.categories, 'categories')}
        ${statTile('On arm64', stats.architectures.arm64 ?? 0, 'images for arm64')}
      </section>

      <div class="ref" id="endpoints">
        <aside class="ref-side">${referenceNav(spec)}</aside>
        <div class="ref-main">
          <div class="section-head">
            <p class="raft-eyebrow"><span class="accent" aria-hidden="true">//</span> reference</p>
            <h2>Endpoints</h2>
            <div class="prose muted">${markdown(spec.info.description)}</div>
          </div>
          ${reference(spec, names, base)}

          <section class="ref-group" aria-labelledby="sources">
            <h2 id="sources" class="ref-tag">
              <span class="accent" aria-hidden="true">//</span> Where the data comes from
            </h2>
            <div class="raft-panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Fields</th>
                    <th scope="col">Source</th>
                  </tr>
                </thead>
                <tbody>
                  ${SOURCES.map(
                    ([fields, source, href]) =>
                      html`<tr>
                        <td><code>${fields}</code></td>
                        <td>${external(href, source)}</td>
                      </tr>`,
                  )}
                </tbody>
              </table>
            </div>
            <p class="muted small">
              When a source can't be reached the previous data keeps being served;
              <a href="${base}api/v1/status.json">status.json</a> shows when each one last succeeded.
            </p>
          </section>
        </div>
      </div>
    </div>
  `;
  return layout(ctx, `${spec.info.title} | LinuxServer.io`, spec.info.summary ?? spec.info.title, body);
}

export function notFoundPage(ctx: PageContext): string {
  const body = html`<div class="hero">
    <div class="grid-bg" aria-hidden="true"></div>
    <div class="container hero-inner hero-narrow">
      <div>
        <p class="raft-eyebrow"><span class="accent" aria-hidden="true">//</span> 404</p>
        <h1>Nothing here</h1>
        <p class="lede">
          There is no endpoint or image at this address. Image names are lowercase, as in
          <code>lscr.io/linuxserver/&lt;name&gt;</code>.
        </p>
        <div class="hero-actions">
          <a href="${ctx.config.basePath}#endpoints" class="btn btn-solid">See all endpoints</a>
        </div>
      </div>
    </div>
  </div>`;
  return layout(ctx, 'Not found | LinuxServer API', 'There is nothing at this address.', body);
}
