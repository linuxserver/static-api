"""The recent changelog as an Atom feed, so people can follow notable image changes in a feed reader."""

import hashlib
from xml.sax.saxutils import escape, quoteattr

from .models import ChangelogEntry, ImageDetail


def _entry_id(e: ChangelogEntry) -> str:
    """Stable across builds, so readers don't show an entry twice."""
    return "urn:sha1:" + hashlib.sha1(f"{e.image}\n{e.date}\n{e.desc}".encode()).hexdigest()


def changelog_feed(
    entries: list[ChangelogEntry], images: list[ImageDetail], *, self_url: str, site_url: str, updated: str
) -> str:
    github_urls = {i.name: i.github_url for i in images}
    items = [
        f"""  <entry>
    <id>{_entry_id(e)}</id>
    <title>{escape(f"{e.image}: {e.desc}")}</title>
    <updated>{e.date}T00:00:00Z</updated>
    <link rel="alternate" href={quoteattr(github_urls.get(e.image, "https://github.com/linuxserver") + "#versions")}/>
    <category term={quoteattr(e.image)}/>
    <content type="text">{escape(e.desc)}</content>
  </entry>"""
        for e in entries
    ]
    return "\n".join(
        [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            "  <title>LinuxServer.io image changelog</title>",
            "  <subtitle>Notable changes to LinuxServer.io container images.</subtitle>",
            f"  <id>{escape(self_url)}</id>",
            f'  <link rel="self" href={quoteattr(self_url)}/>',
            f'  <link rel="alternate" href={quoteattr(site_url)}/>',
            f"  <updated>{updated}</updated>",
            "  <author><name>LinuxServer.io</name></author>",
            *items,
            "</feed>",
            "",
        ]
    )
