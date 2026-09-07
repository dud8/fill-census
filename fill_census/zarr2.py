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

    def chunk_key(self, idx) -> str:
        sep = self.dimension_separator or "."
        return sep.join(str(i) for i in idx)


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


def read_chunk(root: str, level: Level, idx, z_slab: tuple[int, int] | None = None,
               base: str = BUCKET):
    """Return a numpy array for one chunk, or None if the chunk is absent.

    Absence is not an error: Zarr omits chunks that are entirely fill_value.

    z_slab=(z0, z1) reads only that half-open range of leading-axis planes.
    These stores are uncompressed and C-ordered, so a plane range is exactly one
    contiguous byte range and can be served by an HTTP Range request. This is
    what makes a whole-catalogue census affordable: verifying a 16-plane slab
    moves 1/8th of the bytes of a full 128^3 chunk and is equally exact over the
    planes it covers.
    """
    import numpy as np

    url = f"{base.rstrip('/')}/{root.rstrip('/')}/{level.path}/{level.chunk_key(idx)}"
    if level.filters:
        raise Unsupported(f"{url}: filters are not supported")
    if level.compressor is not None:
        z_slab = None  # compressed chunks cannot be byte-ranged
    if level.order != "C":
        z_slab = None  # plane ranges are only contiguous in C order

    plane = level.itemsize
    for c in level.chunks[1:]:
        plane *= c
    br = None
    if z_slab is not None:
        z0, z1 = z_slab
        z0 = max(0, z0)
        z1 = min(level.chunks[0], z1)
        if z1 <= z0:
            return None
        br = (z0 * plane, z1 * plane)
        want = (z1 - z0) * plane
    else:
        want = level.chunk_nbytes

    try:
        raw = fetch(url, byte_range=br)
    except Missing:
        return None
    if level.compressor is not None:
        raw = decode_chunk(raw, level)
        want = level.chunk_nbytes
        br = None
    if len(raw) != want:
        raise ValueError(
            f"{url}: got {len(raw)} bytes, declared shape/dtype/range require {want}"
        )
    a = np.frombuffer(raw, dtype=np.dtype(level.dtype))
    nz = (z_slab[1] - z_slab[0]) if br else level.chunks[0]
    return a.reshape((nz,) + tuple(level.chunks[1:]), order="C")
