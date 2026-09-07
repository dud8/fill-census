"""Minimal, dependency-light reader for the uncompressed Zarr v2 volumes
published by Vesuvius Challenge. Read-only, anonymous HTTP, no credentials.

Deliberately does not use zarr/s3fs: the audit must be able to observe
malformed stores that a real Zarr reader would reject or silently repair.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

BUCKET = "https://vesuvius-challenge-open-data.s3.amazonaws.com"
UA = "fill-census/1.0 (Vesuvius Challenge open-data storage census)"


class Missing(Exception):
    """Key absent from the store (a legitimate state for sparse Zarr)."""


class Unreachable(Exception):
    """The object could not be retrieved for a transport reason.

    Kept strictly distinct from Missing and from a data defect. A connection
    reset is a statement about the network, not about the data, and must never
    be reported as a contract violation.
    """


def decode_chunk(raw: bytes, level) -> bytes:
    """Return raw bytes for a chunk, decompressing if the store declares a codec."""
    comp = level.compressor
    if not comp:
        return raw
    cid = (comp or {}).get("id")
    if cid == "blosc":
        try:
            import numcodecs
        except ImportError as e:
            raise Unsupported(
                "chunk is blosc-compressed; install numcodecs to verify it"
            ) from e
        return numcodecs.blosc.decompress(raw)
    if cid in ("zlib", "gzip"):
        import zlib
        return zlib.decompress(raw)
    raise Unsupported(f"unsupported compressor {cid!r}")


class Unsupported(Exception):
    """The store uses an encoding this build cannot verify."""


def fetch(url: str, timeout: int = 60, byte_range: tuple[int, int] | None = None,
          attempts: int = 4) -> bytes:
    """GET with bounded retry.

    Transient transport failures are retried with backoff and, if they persist,
    raised as Unreachable rather than propagating as a generic error that a
    caller might mistake for a data defect.
    """
    headers = {"User-Agent": UA}
    if byte_range is not None:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1] - 1}"
    req = urllib.request.Request(url, headers=headers)
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise Missing(url) from e
            if e.code in (429, 500, 502, 503, 504):
                last = e
            else:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
        if i < attempts - 1:
            time.sleep(0.6 * (2 ** i))
    raise Unreachable(f"{url}: {type(last).__name__}: {last}")


def fetch_json(url: str, timeout: int = 60):
    return json.loads(fetch(url, timeout))


@dataclass(frozen=True)
class Level:
    path: str
    shape: tuple[int, ...]
    chunks: tuple[int, ...]
    dtype: str
    fill_value: int
    compressor: object
    filters: object
    order: str
    dimension_separator: str
    scale: tuple[float, ...] | None

    @property
    def itemsize(self) -> int:
        return int(self.dtype[-1])

    @property
    def chunk_nbytes(self) -> int:
        n = self.itemsize
        for c in self.chunks:
            n *= c
        return n

    def n_chunks(self) -> tuple[int, ...]:
        return tuple(math.ceil(s / c) for s, c in zip(self.shape, self.chunks))


def root_to_base(access_root: str) -> str:
    """Map a catalog access_root to an HTTPS origin.

    The catalog publishes under two roots: an S3 bucket and a plain HTTPS host.
    A path is only meaningful relative to the root declared alongside it, so the
    audit must resolve each origin against its own root rather than assuming the
    bucket. Ignoring this produces confident false reports of missing data.
    """
    if access_root.startswith("s3://"):
        return f"https://{access_root[len('s3://'):].rstrip('/')}.s3.amazonaws.com"
    return access_root.rstrip("/")


def read_multiscale(root: str, base: str = BUCKET) -> list[Level]:
    """root is a path under `base`, ending in '/'. Returns levels in order."""
    base = f"{base.rstrip('/')}/{root.rstrip('/')}"
    attrs = fetch_json(f"{base}/.zattrs")
    ms = attrs["multiscales"][0]
    levels = []
    for ds in ms["datasets"]:
        p = ds["path"]
        za = fetch_json(f"{base}/{p}/.zarray")
        scale = None
        for ct in ds.get("coordinateTransformations") or []:
            if ct.get("type") == "scale":
                scale = tuple(float(v) for v in ct["scale"])
        levels.append(
            Level(
                path=p,
                shape=tuple(int(v) for v in za["shape"]),
                chunks=tuple(int(v) for v in za["chunks"]),
                dtype=za["dtype"],
                fill_value=za.get("fill_value"),
                compressor=za.get("compressor"),
                filters=za.get("filters"),
                order=za.get("order", "C"),
                dimension_separator=za.get("dimension_separator", "."),
                scale=scale,
            )
        )
    return levels
