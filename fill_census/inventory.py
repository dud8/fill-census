"""Bulk object inventory for the two access roots the catalogue publishes under.

The census question -- how many stored chunks exist, how large are they, and
which of them carry no information -- is answered from object *metadata* wherever
possible. Probing keys one at a time would cost one request per chunk; a
population with millions of chunks makes that a non-starter. Both roots expose a
bulk listing instead:

  s3   ListObjectsV2 returns key, size and ETag, 1000 at a time.
  http an nginx-style autoindex returns one directory of names and sizes.

The two differ in what they can support, and the difference is load-bearing:
S3 gives an exact byte count and a content hash for every object, the autoindex
gives an exact key set but only a human-rounded size and no hash. Every figure
this tool reports is tagged with which of the two produced it.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .zarr2 import fetch, Unreachable

# S3 interleaves optional <ChecksumAlgorithm>/<ChecksumType> elements between
# ETag and Size, so match non-greedily across whatever sits in between rather
# than pinning the exact element order.
_S3_ENTRY = re.compile(
    r"<Key>(.*?)</Key>.*?<ETag>(?:&quot;|\")(.*?)(?:&quot;|\").*?<Size>(\d+)</Size>",
    re.S,
)
_S3_PREFIX = re.compile(r"<CommonPrefixes>\s*<Prefix>(.*?)</Prefix>\s*</CommonPrefixes>")
_S3_TOKEN = re.compile(r"<NextContinuationToken>(.*?)</NextContinuationToken>")

_IDX_HREF = re.compile(r'<a href="([^"]+)"[^>]*>.*?</a></td><td class="size">([^<]*)</td>')

_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4}


class Entry:
    """One stored object. `exact` is False when the size is a rounded display
    value from an HTML index rather than a byte count from S3."""

    __slots__ = ("key", "etag", "size", "exact")

    def __init__(self, key, etag, size, exact=True):
        self.key, self.etag, self.size, self.exact = key, etag, size, exact

    def __repr__(self):
        return f"Entry({self.key!r}, {self.etag!r}, {self.size}, exact={self.exact})"


# ------------------------------------------------------------------ S3


def _s3_page(base, prefix, token=None, delimiter=None):
    q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
    if token:
        q["continuation-token"] = token
    if delimiter:
        q["delimiter"] = delimiter
    body = fetch(f"{base}/?{urllib.parse.urlencode(q)}").decode()
    # CommonPrefixes carry no Key/ETag/Size, but splitting keeps the entry regex
    # from ever straddling the boundary between the two sections.
    contents = body.split("<CommonPrefixes>")[0]
    entries = [
        Entry(html.unescape(k), e, int(s)) for k, e, s in _S3_ENTRY.findall(contents)
    ]
    prefixes = [html.unescape(p) for p in _S3_PREFIX.findall(body)]
    m = _S3_TOKEN.search(body)
    return entries, prefixes, (m.group(1) if m else None)


def _s3_walk(base, prefix):
    out, token = [], None
    while True:
        e, _, token = _s3_page(base, prefix, token)
        out += e
        if not token:
            return out


def _s3_dir(base, prefix):
    """Every object and sub-prefix directly under `prefix`.

    A delimiter listing is still a token chain: a directory with more than 1000
    immediate children needs more than one page. Following it to the end here is
    what keeps the sharded walk below from silently dropping the objects that
    sit beside sub-prefixes on the second and later pages.
    """
    files, dirs, token = [], [], None
    while True:
        f, d, token = _s3_page(base, prefix, token, delimiter="/")
        files += f
        dirs += d
        if not token:
            return files, dirs


def list_s3(base, prefix, workers=64, min_shards=128):
    """Every object under `prefix`, with exact sizes and MD5 ETags.

    A single listing is a serial token chain -- one request per 1000 keys -- so a
    level-0 directory holding 700,000 chunks would take 700 round trips in
    sequence. The prefix tree is expanded with `delimiter=/` until there are
    enough independent sub-prefixes to shard across, and those are then walked in
    parallel. Expansion stops as soon as the shard count is reached, so a small
    store still costs one request.

    Every object is reached through exactly one shard or listed once during the
    expansion, so the result holds no duplicate and drops nothing. Checked
    against a plain serial walk by `tools/check_lister.py`.
    """
    top, dirs = _s3_dir(base, prefix)
    if not dirs:
        return top
    out, leaves = list(top), []
    while dirs and len(dirs) + len(leaves) < min_shards:
        with ThreadPoolExecutor(max_workers=min(workers, len(dirs))) as ex:
            expanded = list(ex.map(lambda d: _s3_dir(base, d), dirs))
        nxt = []
        for (files, subs), d in zip(expanded, dirs):
            if subs:
                out += files       # objects sitting beside the sub-prefixes
                nxt += subs
            else:
                leaves.append(d)
        dirs = nxt
    dirs += leaves
    with ThreadPoolExecutor(max_workers=min(workers, len(dirs))) as ex:
        for part in ex.map(lambda d: _s3_walk(base, d), dirs):
            out += part
    return out


# ------------------------------------------------------------------ autoindex


def _parse_size(text):
    """'2.0 MiB' -> (2097152, exact=False). '235 B' -> (235, exact=True).

    Only a plain byte count is exact. Everything else has been rounded for
    display and is carried through the report tagged as inexact, because a
    truncated 2,097,000-byte chunk also displays as '2.0 MiB'.
    """
    t = text.strip()
    m = re.fullmatch(r"([\d.]+)\s*(B|KiB|MiB|GiB|TiB)", t)
    if not m:
        return None, False
    v, unit = float(m.group(1)), m.group(2)
    return int(round(v * _UNITS[unit])), unit == "B"


def _index_page(base, path):
    body = fetch(f"{base}/{path}").decode(errors="replace")
    files, dirs = [], []
    for href, size in _IDX_HREF.findall(body):
        if href.startswith("../") or href == "../":
            continue
        name = html.unescape(urllib.parse.unquote(href))
        if name.endswith("/"):
            dirs.append(path + name)
        else:
            n, exact = _parse_size(size)
            files.append((path + name, n, exact))
    return files, dirs


def list_autoindex(base, prefix, workers=96, max_requests=200_000):
    """Every object under `prefix` on an HTML-autoindex host.

    Breadth-first: one request per directory. Sizes are whatever the index
    displays, so they are marked inexact unless the index gave plain bytes.
    """
    out, frontier, used = [], [prefix], 1
    files, dirs = _index_page(base, prefix)
    out += [Entry(k, None, n, e) for k, n, e in files]
    frontier = dirs
    while frontier:
        if used + len(frontier) > max_requests:
            raise Unreachable(
                f"{base}/{prefix}: directory walk exceeds {max_requests} requests"
            )
        used += len(frontier)
        nxt = []
        with ThreadPoolExecutor(max_workers=min(workers, len(frontier))) as ex:
            for files, dirs in ex.map(lambda d: _index_page(base, d), frontier):
                out += [Entry(k, None, n, e) for k, n, e in files]
                nxt += dirs
        frontier = nxt
    return out


def list_store(base, prefix):
    """Inventory one store, choosing the backend its access root supports."""
    if base.endswith(".s3.amazonaws.com"):
        return list_s3(base, prefix), "s3-list"
    return list_autoindex(base, prefix), "html-autoindex"
