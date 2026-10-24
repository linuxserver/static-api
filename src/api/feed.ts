/** The recent changelog as an Atom feed, so people can follow notable image changes in a feed reader. */
import { createHash } from 'node:crypto';
import { escapeMarkup as escapeXml } from '../util.ts';
import type { ChangelogEntry, ImageDetail } from './types.ts';

/** Stable across builds, so readers don't show an entry twice. */
const entryId = (e: ChangelogEntry) =>
  `urn:sha1:${createHash('sha1').update(`${e.image}\n${e.date}\n${e.desc}`).digest('hex')}`;

interface FeedOptions {
  /** Absolute URL of the feed itself. */
  selfUrl: string;
  /** Absolute URL of the docs page. */
  siteUrl: string;
  /** ISO 8601. */
  updated: string;
}

export function changelogFeed(entries: ChangelogEntry[], images: ImageDetail[], options: FeedOptions): string {
  const githubUrl = new Map(images.map((i) => [i.name, i.github_url]));
  const items = entries.map((e) => {
    const link = `${githubUrl.get(e.image) ?? 'https://github.com/linuxserver'}#versions`;
    return [
      '  <entry>',
      `    <id>${entryId(e)}</id>`,
      `    <title>${escapeXml(`${e.image}: ${e.desc}`)}</title>`,
      `    <updated>${e.date}T00:00:00Z</updated>`,
      `    <link rel="alternate" href="${escapeXml(link)}"/>`,
      `    <category term="${escapeXml(e.image)}"/>`,
      `    <content type="text">${escapeXml(e.desc)}</content>`,
      '  </entry>',
    ].join('\n');
  });
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom">',
    '  <title>LinuxServer.io image changelog</title>',
    '  <subtitle>Notable changes to LinuxServer.io container images.</subtitle>',
    `  <id>${escapeXml(options.selfUrl)}</id>`,
    `  <link rel="self" href="${escapeXml(options.selfUrl)}"/>`,
    `  <link rel="alternate" href="${escapeXml(options.siteUrl)}"/>`,
    `  <updated>${options.updated}</updated>`,
    '  <author><name>LinuxServer.io</name></author>',
    ...items,
    '</feed>',
    '',
  ].join('\n');
}
