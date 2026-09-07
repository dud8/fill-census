"""Census driver: inventory one store, classify every object, run the checks.

The measurement question is "how much of the published data is provably empty,
and what does it cost to host". Everything here is read-only and anonymous.

Three ways of establishing that a present chunk is entirely fill_value, in
descending order of strength. Every reported count says which one produced it,
because the difference between an exhaustive census and a sample is the whole
credibility of the number.

  etag-md5     Uncompressed store on S3. The ETag of a single-part object is the
               MD5 of its bytes, and an all-fill chunk of a fixed size has one
               fixed MD5. Every present chunk in the store is classified from
               listing metadata alone. Exhaustive; no chunk bytes are moved.
  etag-class   Compressed store on S3. Objects are grouped into byte-identical
               classes by ETag; one representative per class is downloaded and
               decoded. Exhaustive over the classes actually decoded, and the
               object coverage of those classes is reported.
  sampled      No ETag available (HTML autoindex root). A bounded sample of
               chunks is range-read. NOT a census, and never reported as one.
"""
from __future__ import annotations

import collections
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import checks
from .checks import Finding
from .zarr2 import (BUCKET, Missing, Unreachable, Unsupported, decode_chunk,
                    fetch, read_multiscale)

META_NAMES = {".zarray", ".zattrs", ".zgroup", ".zmetadata"}
# Catalogue sidecars that legitimately sit beside a store and are not Zarr keys.
SIDECARS = {"metadata.json", "LICENSE.txt", "README.md"}


@dataclass
class StoreReport:
    root: str
    base: str
    ok: bool = True
    error: str | None = None
    levels: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    chunk_keys: dict = field(default_factory=dict)  # level path -> set of rel keys

    def add(self, fs):
        for f in fs:
            self.findings.append(f.as_dict())
            if f.severity == "contract":
                self.ok = False


def _is_all_fill(raw, level):
    """True if a chunk object's decoded bytes are entirely fill_value."""
    want = checks.fill_bytes(level)
    if want is None:
        return False
    body = decode_chunk(raw, level) if level.compressor is not None else raw
    return len(body) == level.chunk_nbytes and body == want


def _resolve_compressed(base, root, level, entries, max_classes=512):
    """Decide which ETag classes of a compressed level are all-fill.

    Every all-fill chunk in one store encodes to the same byte string, so they
    all share one ETag class. Classes are tested smallest-first: an all-fill
    chunk cannot compress to more than a chunk of real data of the same shape,
    and in practice sits at the very bottom of the size distribution.
    """
    by_etag = {}
    for e in entries:
        by_etag.setdefault(e.etag, []).append(e)
    order = sorted(by_etag, key=lambda t: (by_etag[t][0].size, -len(by_etag[t])))
    tested = order[:max_classes]
    ceiling = by_etag[tested[-1]][0].size if tested else 0
    fill_etags, covered = set(), 0

    def probe(et):
        rep = by_etag[et][0]
        try:
            return et, _is_all_fill(fetch(f"{base}/{rep.key}"), level)
        except (Missing, Unreachable, Unsupported):
            return et, None

    with ThreadPoolExecutor(max_workers=min(32, max(1, len(tested)))) as ex:
        for et, verdict in ex.map(probe, tested):
            if verdict is None:
                continue
            covered += len(by_etag[et])
            if verdict:
                fill_etags.add(et)
    return fill_etags, covered, len(tested), len(by_etag), ceiling


def _resolve_sampled(base, root, level, entries, n=256):
    """Range-read a bounded sample of chunks and count the all-fill ones.

    Used only where the access root exposes no content hash. The first plane is
    read first; a chunk is only pulled in full when that plane is all-fill, so
    the common case moves 1/128th of the chunk.
    """
    if not entries:
        return 0, 0, 0
    want = checks.fill_bytes(level)
    if want is None:
        return 0, 0, 0
    step = max(1, len(entries) // n)
    picks = entries[::step][:n]
    plane = level.chunk_nbytes // level.chunks[0]

    def probe(e):
        try:
            head = fetch(f"{base}/{e.key}", byte_range=(0, plane))
            if head != want[:len(head)]:
                return 0, 0
            return (1, e.size) if _is_all_fill(fetch(f"{base}/{e.key}"), level) else (0, 0)
        except (Missing, Unreachable, Unsupported):
            return None
    n_fill = b_fill = tested = 0
    with ThreadPoolExecutor(max_workers=24) as ex:
        for r in ex.map(probe, picks):
            if r is None:
                continue
            tested += 1
            n_fill += r[0]
            b_fill += r[1]
    return n_fill, b_fill, tested


def verify_occupancy(root, base=BUCKET, level="0"):
    """Compare the measured chunk key set against a publisher-written occupancy
    map, where one exists.

    One store in the catalogue ships `<level>/.chunk_occupancy.npz`, a boolean
    array over the level's chunk grid written by whoever published it. It is
    independent ground truth for exactly the quantity this tool measures, so it
    is worth checking against rather than only asserting the method is sound.
    """
    import io
    import numpy as np

    from .inventory import list_store

    levels = read_multiscale(root, base=base)
    lv = next(l for l in levels if l.path == level)
    occ = np.load(io.BytesIO(fetch(
        f"{base.rstrip('/')}/{root}{level}/.chunk_occupancy.npz")))["occupancy"]
    entries, _ = list_store(base, f"{root}{level}/")
    from . import checks
    keys = set()
    for e in entries:
        idx = checks.parse_chunk_key(e.key[len(root) + len(level) + 1:], lv,
                                     len(lv.shape))
        if idx is not None:
            keys.add(idx)
    mine = np.zeros(occ.shape, dtype=bool)
    for i in keys:
        if all(a < b for a, b in zip(i, occ.shape)):
            mine[i] = True
    return {
        "root": root, "level": level, "grid": list(occ.shape),
        "published_occupied": int(occ.sum()),
        "measured_present": len(keys),
        "cells_disagreeing": int((mine != occ).sum()),
        "grid_cells": int(occ.size),
        "identical": bool((mine == occ).all()),
    }


def verify_etag(root, base=BUCKET, level="0", n=64):
    """Positive control for the assumption the whole census rests on.

    The census reads an uncompressed store's ETags as whole-object MD5s. That is
    what S3 documents for a single-part upload, but the bucket also holds
    multipart objects, whose ETag is something else entirely. So rather than
    assume the identity holds here, download a spread of ordinary chunks and
    check that md5(bytes) really is the ETag S3 published for them.
    """
    import hashlib

    from .inventory import list_store

    levels = read_multiscale(root, base=base)
    lv = next(l for l in levels if l.path == level)
    entries = [e for e in list_store(base, f"{root}{level}/")[0]
               if e.etag and not checks.is_multipart_etag(e.etag)
               and not e.key.endswith(tuple(META_NAMES))]
    step = max(1, len(entries) // n)
    picks = entries[::step][:n]

    def probe(e):
        try:
            raw = fetch(f"{base}/{e.key}")
        except (Missing, Unreachable):
            return None
        return (hashlib.md5(raw).hexdigest() == e.etag, len(raw) == e.size)

    with ThreadPoolExecutor(max_workers=16) as ex:
        got = [r for r in ex.map(probe, picks) if r is not None]
    return {
        "root": root, "level": level,
        "objects_in_level": len(entries),
        "objects_downloaded": len(got),
        "etag_equals_md5_of_bytes": sum(1 for a, _ in got if a),
        "length_equals_listed_size": sum(1 for _, b in got if b),
        "identical": bool(got) and all(a and b for a, b in got),
    }


def census_store(root, base=BUCKET, verify_samples=4, verbose=False,
                 keep_chunk_keys=False):
    """Inventory and classify one Zarr store. Returns a StoreReport."""
    from .inventory import list_store

    rep = StoreReport(root=root, base=base)
    t0 = time.time()
    try:
        levels = read_multiscale(root, base=base)
    except Missing as e:
        rep.error, rep.ok = f"store metadata absent: {e}", False
        return rep
    except Exception as e:
        rep.error, rep.ok = f"{type(e).__name__}: {e}", False
        return rep

    try:
        entries, how = list_store(base, root)
    except (Unreachable, Unsupported) as e:
        rep.error, rep.ok = f"inventory unavailable: {e}", False
        return rep

    by_path = {lv.path: lv for lv in levels}
    per_level, foreign = {}, []
    buckets = collections.defaultdict(list)
    n_meta = bytes_meta = 0
    for e in entries:
        rel = e.key[len(root):] if e.key.startswith(root) else e.key
        head, _, tail = rel.partition("/")
        name = rel.rsplit("/", 1)[-1]
        if name in META_NAMES or "/" not in rel:
            n_meta += 1
            bytes_meta += e.size or 0
            if name not in META_NAMES and name not in SIDECARS:
                foreign.append(rel)
            continue
        lv = by_path.get(head)
        if lv is None:
            foreign.append(rel)
            continue
        idx = checks.parse_chunk_key(tail, lv, len(lv.shape))
        if idx is None:
            foreign.append(rel)
            continue
        buckets[head].append((idx, e))

    inexact = any(not e.exact for e in entries if e.size)
    n_fill_total = b_fill_total = 0
    n_exh = b_exh = n_bounded = b_bounded = 0
    methods = set()
    all_etags = collections.Counter()
    etag_size = {}

    for lv in levels:
        items = buckets.get(lv.path, [])
        grid = lv.n_chunks()
        n_grid = math.prod(grid)
        oor = [i for i, _ in items if any(a >= b for a, b in zip(i, grid))]
        sizes = collections.Counter(e.size for _, e in items)
        present = len(items)
        b_present = sum(e.size or 0 for _, e in items)
        rep.add(checks.check_index_bounds(lv, oor))
        rep.add(checks.check_chunk_size(lv, sizes, inexact))
        if keep_chunk_keys:
            # Only materialised for volumes published under more than one access
            # root; a level-0 key set runs to hundreds of thousands of strings.
            rep.chunk_keys[lv.path] = {"/".join(map(str, i)) for i, _ in items}

        ents = [e for _, e in items]
        for e in ents:
            if e.etag:
                all_etags[e.etag] += 1
                etag_size.setdefault(e.etag, e.size)

        n_fill = b_fill = 0
        method = "none"
        detail = {}
        n_mp = sum(1 for e in ents if checks.is_multipart_etag(e.etag))
        classified = 0
        if not ents:
            method = "no-chunks"
        elif checks.fill_bytes(lv) is None:
            # No usable fill value declared: there is no byte pattern to look
            # for, so nothing is claimed about this level either way.
            method = "fill-value-undeclared (not classified)"
        elif ents[0].etag and lv.compressor is None and not lv.filters:
            target = checks.fill_md5(lv)
            hits = [e for e in ents if e.etag == target]
            n_fill, b_fill = len(hits), sum(e.size for e in hits)
            classified = present - n_mp
            method = ("etag-md5 (exhaustive)" if not n_mp else
                      f"etag-md5 ({classified}/{present} objects; {n_mp} "
                      f"multipart ETags carry no whole-object MD5 and were "
                      f"not classified)")
            detail = {"fill_md5": target, "verified_by_download": 0,
                      "multipart_etags": n_mp, "objects_classified": classified}
            for e in hits[:verify_samples]:
                try:
                    if _is_all_fill(fetch(f"{base}/{e.key}"), lv):
                        detail["verified_by_download"] += 1
                except (Missing, Unreachable, Unsupported):
                    pass
        elif ents[0].etag:
            fe, covered, tested, total, ceil_b = _resolve_compressed(
                base, root, lv, ents)
            hits = [e for e in ents if e.etag in fe]
            n_fill, b_fill = len(hits), sum(e.size for e in hits)
            above = sum(1 for e in ents if e.size > ceil_b)
            classified = covered
            # Classes are decoded smallest-first, so the guarantee this method
            # gives is a size ceiling: every stored object at or below it was
            # decoded and tested. Say so rather than quoting a bare percentage.
            method = (f"etag-class (every object <= {ceil_b} B decoded; "
                      f"{tested}/{total} classes, {covered}/{len(ents)} objects; "
                      f"{above} larger objects untested)")
            detail = {"classes_tested": tested, "classes_total": total,
                      "objects_covered": covered, "size_ceiling_tested": ceil_b,
                      "objects_above_ceiling": above, "multipart_etags": n_mp}
        else:
            sf, sb, tested = _resolve_sampled(base, root, lv, ents)
            method = f"sampled ({tested}/{len(ents)} chunks read)"
            detail = {"sampled": tested, "sampled_fill": sf,
                      "sampled_fill_bytes": sb}
            if sf:
                rep.findings.append(Finding(
                    "all_fill", "advisory", lv.path,
                    f"{sf} of {tested} sampled present chunks are entirely "
                    f"fill_value. This access root exposes no content hash, so "
                    f"this is a SAMPLE, not a census; the level's total all-fill "
                    f"count is not established",
                    {"sampled": tested, "sampled_fill": sf, "n_present": present},
                ).as_dict())

        if method.startswith(("etag-md5", "etag-class")):
            rep.add(checks.check_all_fill(lv, n_fill, b_fill, present, b_present,
                                          method))
            n_fill_total += n_fill
            b_fill_total += b_fill
            if method.startswith("etag-md5"):
                n_exh += classified
                b_exh += b_present - sum(
                    e.size for e in ents if checks.is_multipart_etag(e.etag))
            else:
                n_bounded += classified
                b_bounded += sum(e.size for e in ents
                                 if e.size <= detail["size_ceiling_tested"])
        if n_mp:
            rep.add(checks.check_multipart_etags(lv, n_mp, present))
        methods.add(method.split(" ")[0])

        per_level[lv.path] = {
            "shape": list(lv.shape), "chunks": list(lv.chunks),
            "grid": list(grid), "chunks_in_grid": n_grid,
            "chunks_present": present,
            "occupancy": round(present / n_grid, 8) if n_grid else None,
            "bytes_present": b_present,
            "chunk_nbytes": lv.chunk_nbytes,
            "compressor": (lv.compressor or {}).get("id") if lv.compressor else None,
            "sizes_exact": not inexact,
            "chunks_out_of_grid": len(oor),
            "all_fill_chunks": n_fill, "all_fill_bytes": b_fill,
            "all_fill_method": method, "all_fill_detail": detail,
            "objects_classified": classified,
            "multipart_etags": n_mp,
        }
        if verbose:
            print(f"    {lv.path}: {present}/{n_grid} chunks "
                  f"({100.0*present/n_grid if n_grid else 0:.2f}%) "
                  f"{b_present} B, all-fill {n_fill} [{method}]", flush=True)

    rep.add(checks.check_foreign_keys(root, foreign))
    rep.add(checks.check_pyramid_cost(levels, per_level))

    n_obj = sum(all_etags.values())
    if n_obj:
        b_tot = sum(etag_size[e] * c for e, c in all_etags.items())
        b_dist = sum(etag_size.values())
        rep.add(checks.check_duplicate_content(root, n_obj, len(all_etags),
                                               b_tot, b_dist))

    rep.levels = per_level
    b_chunks = sum(v["bytes_present"] for v in per_level.values())
    rep.stats = {
        "inventory": how,
        "n_levels": len(levels),
        "n_objects": len(entries),
        "n_metadata_objects": n_meta,
        "chunks_present": sum(v["chunks_present"] for v in per_level.values()),
        "chunks_in_grid": sum(v["chunks_in_grid"] for v in per_level.values()),
        "bytes_chunks": b_chunks,
        "bytes_metadata": bytes_meta,
        "all_fill_chunks": n_fill_total,
        "all_fill_bytes": b_fill_total,
        "chunks_classified_exhaustive": n_exh,
        "bytes_classified_exhaustive": b_exh,
        "chunks_classified_bounded": n_bounded,
        "bytes_classified_bounded": b_bounded,
        "multipart_etags": sum(v["multipart_etags"] for v in per_level.values()),
        "all_fill_share_pct": round(100.0 * b_fill_total / b_chunks, 6) if b_chunks else 0.0,
        "sizes_exact": not inexact,
        "fill_methods": sorted(methods),
        "n_foreign_objects": len(foreign),
        "seconds": round(time.time() - t0, 1),
    }
    return rep
