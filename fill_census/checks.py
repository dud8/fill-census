"""The checks. Each returns a list of Finding.

Two result classes, kept strictly apart:

  contract  - a machine-checkable condition that the store either meets or does
              not. Safe to gate automation on.
  advisory  - an observation that is unusual, or costly, but not a violation of
              any stated contract. Never fails a run.

Storing an all-fill chunk is *legal* Zarr, so it is advisory, not a contract
violation. A chunk whose stored size disagrees with the geometry, or whose key
indexes past the declared array, is not legal, and is a contract violation.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, asdict


@dataclass
class Finding:
    check: str
    severity: str  # "contract" | "advisory"
    level: str | None
    detail: str
    data: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


def fill_bytes(level):
    """The byte string of a chunk that is entirely fill_value, or None when the
    stored metadata does not determine one.

    Zarr v2 encodes a non-finite float fill as the JSON string "NaN"/"Infinity"
    and a null fill means no fill value was declared at all. Neither fixes a
    single byte pattern, so both are reported as a gap in coverage rather than
    guessed at. Multi-byte dtypes are laid out through numpy so the declared
    byte order is honoured instead of assumed.
    """
    fv = level.fill_value
    if fv is None or isinstance(fv, str):
        return None
    n = level.chunk_nbytes
    if level.itemsize == 1:
        return bytes([int(fv) & 0xFF]) * n
    import numpy as np
    one = np.full(1, fv, dtype=np.dtype(level.dtype)).tobytes()
    return one * (n // level.itemsize)


def fill_md5(level) -> str | None:
    """MD5 of an uncompressed chunk that is entirely fill_value.

    S3 publishes the MD5 of every single-part object as its ETag, so for an
    uncompressed store this hash identifies every all-fill chunk in the whole
    population from listing metadata alone -- no chunk bytes move at all. That
    is what makes an exhaustive census affordable rather than a sample.

    Only valid when no codec is declared: blosc output for the same voxels is
    not the same byte string across library builds, so a compressed store's
    all-fill chunks must be found by decoding representatives instead. None when
    the metadata declares no usable fill value.
    """
    body = fill_bytes(level)
    return hashlib.md5(body).hexdigest() if body is not None else None


def is_multipart_etag(etag) -> bool:
    """True for an ETag that is not a whole-object MD5.

    S3 gives a multipart upload an ETag of the form <hash>-<partcount>, which is
    the MD5 of the concatenated part MD5s, not of the object. Such an object
    cannot be classified from its ETag, and this bucket does contain them, so
    they are counted and excluded rather than assumed away.
    """
    return bool(etag) and "-" in etag


# ---------------------------------------------------------------- keys


def parse_chunk_key(rel: str, level, ndim: int):
    """Split a store-relative key into chunk indices, or None if it is not a
    chunk key. `rel` excludes the level path."""
    sep = level.dimension_separator or "."
    parts = rel.split("/") if sep == "/" else rel.split(".")
    if len(parts) != ndim:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def check_index_bounds(level, out_of_range) -> list[Finding]:
    """No stored chunk key may index past the declared chunk grid.

    An index beyond ceil(shape/chunks) means the array and its own .zarray
    disagree about how big the array is. A reader trusting the metadata never
    sees those bytes; a reader trusting the keys reads past the declared extent.
    Either way one of the two is wrong, and the hosting bill pays for data that
    the published shape says does not exist.
    """
    if not out_of_range:
        return []
    grid = level.n_chunks()
    sample = sorted(out_of_range)[:8]
    return [Finding(
        "index_bounds", "contract", level.path,
        f"{len(out_of_range)} stored chunk keys index outside the declared "
        f"chunk grid {list(grid)} implied by shape {list(level.shape)} / chunks "
        f"{list(level.chunks)}; first: "
        + ", ".join("/".join(map(str, i)) for i in sample),
        {"n_out_of_range": len(out_of_range), "grid": list(grid),
         "examples": [list(i) for i in sample]},
    )]


def check_chunk_size(level, sizes_seen, inexact) -> list[Finding]:
    """In an uncompressed store every present chunk is exactly chunk_nbytes.

    Zarr v2 pads edge chunks: a chunk at the boundary of the array still stores
    the full chunk shape. With no codec the object is therefore a fixed size for
    the whole level, and any other size is a truncated or overrun write. Skipped
    for compressed stores, where the size is whatever the codec produced, and
    reported as advisory where the listing size was rounded for display.
    """
    if level.compressor is not None or level.filters:
        return []
    want = level.chunk_nbytes
    # A size of None means the listing gave no parseable size at all; that is a
    # gap in coverage, not evidence of a wrong size, so it is left out.
    bad = {s: n for s, n in sizes_seen.items() if s is not None and s != want}
    if not bad:
        return []
    sev = "advisory" if inexact else "contract"
    note = (" (sizes for this access root come from a rounded HTML index, so "
            "this is reported as advisory)" if inexact else "")
    return [Finding(
        "chunk_size", sev, level.path,
        f"{sum(bad.values())} present chunks are not the {want}-byte size that "
        f"chunks {list(level.chunks)} of dtype {level.dtype!r} with no codec "
        f"requires; observed sizes: "
        + ", ".join(f"{s}x{n}" for s, n in sorted(bad.items())) + note,
        {"expected_bytes": want, "observed": {str(s): n for s, n in bad.items()}},
    )]


def check_foreign_keys(root, keys) -> list[Finding]:
    """Objects under the store prefix that are neither Zarr metadata nor a chunk
    key for a declared level. They are paid for and no reader will open them."""
    if not keys:
        return []
    sample = sorted(keys)[:8]
    return [Finding(
        "foreign_key", "advisory", None,
        f"{len(keys)} objects under the store prefix are neither Zarr metadata "
        f"nor a chunk of any declared level; first: " + ", ".join(sample),
        {"n": len(keys), "examples": sample},
    )]


# ---------------------------------------------------------------- fill


def check_all_fill(level, n_fill, bytes_fill, n_present, bytes_present,
                   method) -> list[Finding]:
    """Present chunks that are entirely fill_value.

    Zarr omits a chunk that is entirely fill_value, and an omitted chunk costs
    nothing -- that is correct and expected. A chunk that is *present* and
    entirely fill_value is stored bytes carrying no information: a hosting cost,
    and a signal that whatever wrote it emitted a block it did not intend to.
    Legal, so advisory, but exactly measurable.
    """
    if not n_fill:
        return []
    share = 100.0 * bytes_fill / bytes_present if bytes_present else 0.0
    return [Finding(
        "all_fill", "advisory", level.path,
        f"{n_fill} of {n_present} present chunks are entirely fill_value "
        f"({level.fill_value}), costing {bytes_fill} stored bytes "
        f"({share:.3f}% of this level). Zarr omits all-fill chunks, so these "
        f"carry no information a reader could not derive from their absence "
        f"[{method}]",
        {"n_fill": n_fill, "bytes_fill": bytes_fill, "n_present": n_present,
         "bytes_present": bytes_present, "share_pct": round(share, 6),
         "method": method},
    )]


def check_multipart_etags(level, n_multipart, n_present) -> list[Finding]:
    """Objects whose ETag is not a whole-object MD5.

    The census classifies an uncompressed level from its ETags. An object
    uploaded in parts carries the MD5 of its part hashes instead, so it cannot
    be classified that way and is excluded from the exhaustive count. Reported
    so the gap is a number rather than an assumption.
    """
    if not n_multipart:
        return []
    return [Finding(
        "multipart_etag", "advisory", level.path,
        f"{n_multipart} of {n_present} present chunks were uploaded in parts, "
        f"so their ETag is the MD5 of the part hashes rather than of the object "
        f"and they cannot be classified from listing metadata alone",
        {"n_multipart": n_multipart, "n_present": n_present},
    )]


def check_pyramid_cost(levels, per_level) -> list[Finding]:
    """The stored size of each reduced level against what its geometry implies.

    A level reduced by 2 on every axis holds 1/8 of the voxels, so an equally
    occupied level costs about 1/8 as many bytes. A level that costs far more
    than that is storing chunks its parent does not justify; far less means the
    reduction is more sparsely materialised than the level below it. Neither is
    a violation -- occupancy legitimately differs across levels -- so this is
    reported as a measured ratio, not a rule.
    """
    out = []
    for i in range(len(levels) - 1):
        a, b = levels[i], levels[i + 1]
        ba = per_level.get(a.path, {}).get("bytes_present", 0)
        bb = per_level.get(b.path, {}).get("bytes_present", 0)
        if not ba:
            continue
        implied = 1.0
        for sa, sb in zip(a.shape, b.shape):
            implied *= (sb / sa) if sa else 1.0
        actual = bb / ba
        if implied and (actual > implied * 3 or actual < implied / 3):
            out.append(Finding(
                "pyramid_cost", "advisory", b.path,
                f"level {b.path} stores {bb} bytes against level {a.path}'s "
                f"{ba} (ratio {actual:.4f}); the shape reduction implies "
                f"{implied:.4f}. Occupancy differs between levels, so this is "
                f"an observation, not a defect",
                {"parent": a.path, "child": b.path, "bytes_parent": ba,
                 "bytes_child": bb, "ratio": round(actual, 6),
                 "geometric_ratio": round(implied, 6)},
            ))
    return out


def check_replica_agreement(name, a_root, a_keys, b_root, b_keys) -> list[Finding]:
    """A volume published under two access roots must present the same chunks.

    The catalogue lists both origins as equivalent. If they are not, which bytes
    a consumer gets depends on which origin it happened to pick, and nothing in
    the catalogue says they differ.
    """
    only_a, only_b = a_keys - b_keys, b_keys - a_keys
    if not only_a and not only_b:
        return []
    def ex(s):
        return ", ".join(sorted(s)[:5])
    return [Finding(
        "replica_agreement", "contract", None,
        f"{name} is published under two access roots whose chunk key sets "
        f"differ: {len(only_a)} keys only under {a_root} ({ex(only_a)}), "
        f"{len(only_b)} keys only under {b_root} ({ex(only_b)})",
        {"root_a": a_root, "root_b": b_root, "only_a": len(only_a),
         "only_b": len(only_b), "examples_only_a": sorted(only_a)[:20],
         "examples_only_b": sorted(only_b)[:20]},
    )]


def check_duplicate_content(store_root, n_objects, n_distinct, bytes_total,
                            bytes_distinct) -> list[Finding]:
    """Byte-identical chunks stored more than once, counted from ETags.

    Not a defect -- Zarr addresses chunks by position, so identical content at
    two positions must be stored twice. It is reported because it is the second
    half of the same hosting-cost question the all-fill count opens, and it is
    free to compute once every object's MD5 is in hand.
    """
    if n_objects == n_distinct:
        return []
    return [Finding(
        "duplicate_content", "advisory", None,
        f"{n_objects - n_distinct} of {n_objects} stored chunks are byte-for-byte "
        f"duplicates of another chunk in the same store ({n_distinct} distinct "
        f"contents); {bytes_total - bytes_distinct} of {bytes_total} stored bytes "
        f"are repeated content. Zarr addresses chunks positionally so this is "
        f"not a defect, only a cost",
        {"n_objects": n_objects, "n_distinct": n_distinct,
         "bytes_total": bytes_total, "bytes_distinct": bytes_distinct},
    )]
