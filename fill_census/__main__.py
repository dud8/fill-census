"""fill-census CLI.

  python -m fill_census check <store-root> [--base URL]
  python -m fill_census scan  [--kinds ome-zarr,surface-prediction-zarr] [--out ...]

Exit status: 0 clean, 2 contract violation found, 1 tool error.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import checks
from .census import census_store, verify_occupancy
from .zarr2 import BUCKET, root_to_base

CATALOG_LOCAL = "../_data/s3_metadata.json"
KINDS = ("ome-zarr", "surface-prediction-zarr")


def load_catalog(path=None, kinds=KINDS):
    """Return every published Zarr store origin, resolved against the access
    root declared beside it.

    A path is only meaningful relative to its own access_root. The catalogue
    publishes under two, and three volumes are published under both; assuming
    the bucket for all of them reports real stores as missing.
    """
    p = path or CATALOG_LOCAL
    try:
        with gzip.open(p) as fh:
            cat = json.load(fh)
    except OSError:
        with open(p) as fh:
            cat = json.load(fh)
    out = []
    for sid, s in cat["samples"].items():
        for vid, vol in (s.get("volumes") or {}).items():
            for n, d in enumerate(vol.get("data") or []):
                if d.get("type") not in kinds:
                    continue
                # One `data` block is one store; its `origins` are alternate
                # locations of that same store. Two blocks of the same type on
                # one volume are two DIFFERENT stores (different model, level or
                # threshold) and must never be compared against each other.
                block = f"{sid}/{vid}#{n}"
                for o in d.get("origins") or []:
                    if not o.get("path"):
                        continue
                    roots = o.get("access_roots") or []
                    base = root_to_base(roots[0]["url"]) if roots else BUCKET
                    out.append({
                        "sample": sid, "volume": vol.get("long_id", vid),
                        "volume_id": vid, "kind": d["type"], "block": block,
                        "root": o["path"], "base": base,
                        "access_root": roots[0]["url"] if roots else "",
                    })
    return out


def _replica_findings(results):
    """Volumes published under more than one access root must agree."""
    groups = {}
    for r in results:
        groups.setdefault(r["block"], []).append(r)
    out = []
    for block, rs in sorted(groups.items()):
        rs = [r for r in rs if not r["error"]]
        if len(rs) < 2:
            continue
        a, b = rs[0], rs[1]
        ka = {f"{lp}/{k}" for lp, ks in a["chunk_keys"].items() for k in ks}
        kb = {f"{lp}/{k}" for lp, ks in b["chunk_keys"].items() for k in ks}
        name = f"{block} ({a['kind']})"
        fs = checks.check_replica_agreement(
            name, a["access_root"], ka, b["access_root"], kb)
        for f in fs:
            out.append(f.as_dict())
        if not fs:
            out.append(checks.Finding(
                "replica_agreement", "advisory", None,
                f"{name} is published under {a['access_root']} and "
                f"{b['access_root']}; both present the identical set of "
                f"{len(ka)} chunk keys",
                {"n_keys": len(ka), "roots": [a["access_root"], b["access_root"]]},
            ).as_dict())
    return out


def _row(rep, item):
    return {
        **item,
        "ok": rep.ok, "error": rep.error, "stats": rep.stats,
        "levels": rep.levels, "findings": rep.findings,
        "chunk_keys": {k: sorted(v) for k, v in rep.chunk_keys.items()},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fill-census")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="census one store")
    c.add_argument("root")
    c.add_argument("--base", default=None)

    v = sub.add_parser("verify-occupancy",
                       help="compare measured occupancy against a store's own "
                            ".chunk_occupancy.npz, where one is published")
    v.add_argument("root")
    v.add_argument("--base", default=None)
    v.add_argument("--level", default="0")

    s = sub.add_parser("scan", help="census every published Zarr store")
    s.add_argument("--catalog", default=None)
    s.add_argument("--kinds", default=",".join(KINDS))
    s.add_argument("--out", default="reports/scan.json")
    s.add_argument("--workers", type=int, default=6)
    s.add_argument("--limit", type=int, default=None)

    a = ap.parse_args(argv)

    if a.cmd == "check":
        rep = census_store(a.root, base=a.base or BUCKET, verbose=True)
        print(json.dumps({"root": rep.root, "ok": rep.ok, "error": rep.error,
                          "stats": rep.stats, "levels": rep.levels,
                          "findings": rep.findings}, indent=2))
        return 0 if rep.ok else 2

    if a.cmd == "verify-occupancy":
        got = verify_occupancy(a.root, base=a.base or BUCKET, level=a.level)
        print(json.dumps(got, indent=2))
        return 0 if got["identical"] else 2

    stores = load_catalog(a.catalog, tuple(a.kinds.split(",")))
    if a.limit:
        stores = stores[: a.limit]
    seen = collections.Counter(x["block"] for x in stores)
    for x in stores:
        x["replicated"] = seen[x["block"]] > 1
    print(f"census over {len(stores)} stores, {a.workers} workers", flush=True)
    t0 = time.time()

    def one(item):
        rep = census_store(item["root"], base=item["base"],
                           keep_chunk_keys=item["replicated"])
        st = rep.stats
        status = "ERROR" if rep.error else ("clean" if rep.ok else "VIOLATION")
        print(f"  [{status:9s}] {item['sample']}/{item['volume']} ({item['kind']}) "
              f"{st.get('chunks_present', 0)} chunks "
              f"{st.get('bytes_chunks', 0)} B "
              f"fill={st.get('all_fill_chunks', 0)} "
              f"{st.get('seconds', 0)}s", flush=True)
        return _row(rep, item)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(one, stores))

    replicas = _replica_findings(results)
    # chunk_keys exist only to compare replicas; they would dominate the report.
    for r in results:
        r.pop("chunk_keys", None)

    ok = [r for r in results if not r["error"]]
    bad = [r for r in results if not r["ok"]]
    tot_bytes = sum(r["stats"].get("bytes_chunks", 0) for r in ok)
    fill_bytes = sum(r["stats"].get("all_fill_bytes", 0) for r in ok)
    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_stores": len(results),
        "n_ok": len(ok),
        "n_error": len(results) - len(ok),
        "n_with_contract_finding": len([r for r in bad if not r["error"]]),
        "totals": {
            "objects": sum(r["stats"].get("n_objects", 0) for r in ok),
            "chunks_present": sum(r["stats"].get("chunks_present", 0) for r in ok),
            "chunks_in_grid": sum(r["stats"].get("chunks_in_grid", 0) for r in ok),
            "bytes_chunks": tot_bytes,
            "bytes_metadata": sum(r["stats"].get("bytes_metadata", 0) for r in ok),
            "all_fill_chunks": sum(r["stats"].get("all_fill_chunks", 0) for r in ok),
            "all_fill_bytes": fill_bytes,
            "all_fill_share_pct": round(100.0 * fill_bytes / tot_bytes, 8)
            if tot_bytes else 0.0,
        },
        "replica_findings": replicas,
        "seconds": round(time.time() - t0, 1),
        "results": results,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(summary, fh, indent=1)
    t = summary["totals"]
    print(f"\n{len(ok)}/{len(results)} stores inventoried; "
          f"{t['chunks_present']} chunks, {t['bytes_chunks']} B, "
          f"{t['all_fill_chunks']} all-fill ({t['all_fill_bytes']} B). "
          f"wrote {a.out} in {summary['seconds']}s")
    viol = [r for r in results if not r["ok"]] + \
           [f for f in replicas if f["severity"] == "contract"]
    for r in bad:
        print(f"  {r['sample']}/{r['volume']}: "
              f"{r['error'] or str(len(r['findings'])) + ' findings'}")
    return 0 if not viol else 2


if __name__ == "__main__":
    sys.exit(main())
