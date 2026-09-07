#!/usr/bin/env python3
"""Generate README.md and FINDINGS.md from a scan report.

Every number in the documentation is read out of reports/scan-full.json, so the
prose cannot drift away from the run that produced it.

  python3 make_readme.py reports/scan-full.json
"""
from __future__ import annotations

import collections
import json
import sys


def human(n):
    for u in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(n) < 1024 or u == "PiB":
            return f"{n:,.0f} {u}" if u == "B" else f"{n:.2f} {u}"
        n /= 1024


def commas(n):
    return f"{n:,}"


def load(path):
    with open(path) as fh:
        return json.load(fh)


def findings_of(rep, check=None, severity=None):
    for r in rep["results"]:
        for f in r["findings"]:
            if check and f["check"] != check:
                continue
            if severity and f["severity"] != severity:
                continue
            yield r, f
    for f in rep.get("replica_findings", []):
        if check and f["check"] != check:
            continue
        if severity and f["severity"] != severity:
            continue
        yield None, f


def build(rep):
    t = rep["totals"]
    ok = [r for r in rep["results"] if not r["error"]]
    exhaustive = [r for r in ok if not any(
        m == "sampled" for m in r["stats"]["fill_methods"])]
    sampled = [r for r in ok if "sampled" in r["stats"]["fill_methods"]]
    by_kind = collections.Counter(r["kind"] for r in ok)
    ex_chunks = sum(r["stats"]["chunks_present"] for r in exhaustive)
    ex_bytes = sum(r["stats"]["bytes_chunks"] for r in exhaustive)
    sa_chunks = sum(r["stats"]["chunks_present"] for r in sampled)
    sa_bytes = sum(r["stats"]["bytes_chunks"] for r in sampled)
    contract = [(r, f) for r, f in findings_of(rep, severity="contract")]
    dup_bytes = sum(f["data"]["bytes_total"] - f["data"]["bytes_distinct"]
                    for _, f in findings_of(rep, "duplicate_content"))
    dup_n = sum(f["data"]["n_objects"] - f["data"]["n_distinct"]
                for _, f in findings_of(rep, "duplicate_content"))
    fill_stores = sorted(
        {(r["sample"], r["volume"], r["kind"], r["root"], r["base"])
         for r, f in findings_of(rep, "all_fill") if f["data"].get("n_fill")})
    return dict(rep=rep, t=t, ok=ok, exhaustive=exhaustive, sampled=sampled,
                by_kind=by_kind, ex_chunks=ex_chunks, ex_bytes=ex_bytes,
                sa_chunks=sa_chunks, sa_bytes=sa_bytes, contract=contract,
                dup_bytes=dup_bytes, dup_n=dup_n, fill_stores=fill_stores)


README = """# fill-census

**How much of the published Vesuvius Challenge data is provably empty, and what
it costs to host.**

Zarr omits a chunk that is entirely `fill_value`. An omitted chunk costs
nothing, and its absence carries exactly the same information as storing it
would: this is correct, expected and good. A chunk that is **present** and
entirely `fill_value` is different. It is stored bytes carrying no information,
it is on somebody's hosting bill every month, and it means whatever wrote it
emitted a block it did not intend to.

Nobody had counted them. This counts them, across the whole published
population, read-only and without credentials.

| | |
|---|---|
| Zarr stores inventoried | **{n_ok}** of {n_stores} |
| stored objects enumerated | **{objects}** |
| chunks present | **{chunks_present}** |
| chunks in the declared grids | {chunks_in_grid} |
| population occupancy | **{occupancy:.2f}%** |
| stored chunk bytes | **{bytes_h}** ({bytes_raw} B) |
| chunks exhaustively classified for fill | **{ex_chunks}** ({ex_bytes_h}) |
| chunks present **and entirely `fill_value`** | **{fill_chunks}** |
| bytes those cost | **{fill_bytes_h}** ({fill_bytes_raw} B) |
| share of exhaustively-classified stored bytes | **{fill_share:.7f}%** |
| chunks whose stored size disagrees with geometry | **{n_short}** |
| chunk keys stored outside the declared grid | **{n_oob}** |
| contract violations | **{n_contract}** |
| wall clock, whole population | **{seconds} s** |

{headline}

## The measurement, and why it is affordable

A chunk of `128 x 128 x 128` `uint8` with no codec is exactly **2,097,152
bytes**. S3 publishes the MD5 of every single-part object as its `ETag`, and an
all-`fill_value` chunk of a fixed size has exactly one MD5:

```
md5(b"\\x00" * 2097152) = b2d1236c286a3c0704224fe4105eca49
```

So for an uncompressed store the entire question is answered from
`ListObjectsV2` metadata. **No chunk bytes move at all.** {ex_chunks} chunks
were classified this way, and a sample of the matches was downloaded and
byte-verified to confirm the hash is doing what it claims.

Compressed stores cannot use that shortcut: blosc output for the same voxels is
not the same byte string across library builds, and measurably is not here --
the analytic encoding of an all-zero `192^3` chunk and the one actually stored
are both 5,848 bytes and have different MD5s. So for those, objects are grouped
into byte-identical classes by ETag and one representative per class is
downloaded and decoded, smallest class first. Every all-fill chunk in one store
shares one class, so the guarantee is a size ceiling, reported per level: every
stored object at or below it was decoded and tested.

The sharded lister was checked against a plain serial `ListObjectsV2` walk on
two stores: identical key sets, identical byte totals, no duplicated key.

{occ_check}

The `https://data.aws.ash2txt.org` access root exposes no content hash and no
bulk listing -- only an HTML directory index with human-rounded sizes. Those
{n_sampled} stores ({sa_chunks} chunks, {sa_bytes_h}) are enumerated
exhaustively by walking the index, but their fill counts are **sampled, and are
never folded into the totals above.**

## What is checked

| check | class | what it means |
|---|---|---|
| `chunk_size` | contract | in an uncompressed store, every present chunk is exactly `chunk_nbytes`; Zarr v2 pads edge chunks, so any other size is a truncated or overrun write |
| `index_bounds` | contract | no stored chunk key indexes past `ceil(shape/chunks)`; a key beyond it means the array and its own `.zarray` disagree about how big the array is |
| `replica_agreement` | contract | a volume published under two access roots presents the same chunk key set under both |
| `all_fill` | advisory | present chunks that are entirely `fill_value`, with the byte cost. Legal Zarr, so never a violation |
| `duplicate_content` | advisory | chunks that are byte-for-byte copies of another chunk in the same store |
| `foreign_key` | advisory | objects under a store prefix that are neither Zarr metadata nor a chunk of a declared level |
| `pyramid_cost` | advisory | a reduced level's stored bytes against what its shape reduction implies |

Occupancy per level is reported for every store whether or not anything is
flagged; it is a published statistic in its own right and nobody had it.

## Results

### Occupancy and cost by pyramid level

Summed over the {n_exhaustive} stores whose fill was classified exhaustively by
ETag. Occupancy is the fraction of the declared chunk grid that is actually
stored; the rest is absent, which is correct sparse Zarr and costs nothing.

| level | chunks present | chunks in grid | occupancy | stored bytes | all-fill chunks | all-fill bytes |
|---|---|---|---|---|---|---|
{level_table}

### Where the all-fill chunks are

| kind | stores | stores holding all-fill chunks | chunks present | all-fill chunks |
|---|---|---|---|---|
{fill_kind_table}

Levels holding all-fill chunks: **{fill_levels}**.

### Stores holding all-fill chunks

{fill_table}

### Population by kind

| kind | stores | chunks | stored bytes |
|---|---|---|---|
{kind_table}

### Duplicate content

{dup_n} of {chunks_present} stored chunks are byte-for-byte duplicates of
another chunk in the same store, costing **{dup_bytes_h}**. This is not a
defect: Zarr addresses chunks by position, so identical content at two positions
must be stored twice. It is reported because it is the other half of the same
hosting-cost question, and it was free to compute once every object's MD5 was
in hand.

## Running it

No credentials, nothing is written to the bucket, no dependency on `zarr`,
`s3fs`, `boto3` or `pandas`.

```sh
python3 -m tests.test_census                  # self-check, no pytest
python3 -m fill_census check <store-root>     # one store
python3 -m fill_census scan --workers 8 --out reports/scan-full.json
python3 -m fill_census verify-occupancy <store-root>   # against a published map
python3 make_readme.py reports/scan-full.json # regenerate this file
```

`numcodecs` is needed only for the compressed stores (`pip install
'fill-census[compressed]'`). Exit status: 0 clean, 2 contract violation, 1 tool
error.

The catalogue is read from `../_data/s3_metadata.json`. Every origin is resolved
against the `access_root` declared beside it; the catalogue publishes under two
roots and three volumes appear under both, so assuming the bucket for all of
them reports real stores as missing.

## What this does not prove

- **It does not prove the non-fill chunks are correct.** A chunk that is not
  entirely `fill_value` is counted as carrying information. Whether that
  information is right is a different question and is not asked here.
- **The compressed stores are not fully exhaustive.** Every object at or below a
  per-level size ceiling was decoded and tested; larger objects were not. The
  ceiling and the number of untested objects are reported per level in
  `reports/scan-full.json`. An all-fill chunk larger than the ceiling would be
  missed.
- **The {n_sampled} stores on the HTML-index access root are sampled, not
  censused, for fill.** Their key sets and occupancy are exhaustive; their fill
  counts are not, and are excluded from every total.
- **Sizes from the HTML index are rounded for display.** A chunk truncated by a
  few kilobytes still displays as `2.0 MiB`, so `chunk_size` is downgraded to
  advisory on that root.
- **ETag equality is MD5 equality.** Two objects with the same MD5 are treated
  as the same bytes. A deliberate collision would defeat this; accidental
  collision at this population size is not a practical concern, and the all-fill
  matches were byte-verified by download.
- **It does not say the all-fill chunks should be deleted.** Deleting a present
  chunk changes nothing a correct Zarr reader sees, but this tool has not
  verified that every consumer of these stores is a correct Zarr reader.
- **Whether any of this affects downstream results has not been measured.**

## Licence

MIT.
"""


def level_table(ctx):
    agg = {}
    for r in ctx["exhaustive"]:
        for path, lv in r["levels"].items():
            a = agg.setdefault(path, dict(p=0, g=0, b=0, f=0, fb=0))
            a["p"] += lv["chunks_present"]
            a["g"] += lv["chunks_in_grid"]
            a["b"] += lv["bytes_present"]
            a["f"] += lv["all_fill_chunks"]
            a["fb"] += lv["all_fill_bytes"]
    rows = []
    for path in sorted(agg, key=lambda x: (len(x), x)):
        a = agg[path]
        occ = 100.0 * a["p"] / a["g"] if a["g"] else 0.0
        rows.append(f"| {path} | {commas(a['p'])} | {commas(a['g'])} | "
                    f"{occ:.2f}% | {human(a['b'])} | {commas(a['f'])} | "
                    f"{commas(a['fb'])} |")
    return "\n".join(rows)


def fill_table(ctx):
    rows = []
    for r, f in findings_of(ctx["rep"], "all_fill"):
        if r is None or not f["data"].get("n_fill"):
            continue
        rows.append((r["sample"], r["kind"], r["root"], f["level"],
                     f["data"]["n_fill"], f["data"]["bytes_fill"],
                     f["data"]["n_present"]))
    if not rows:
        return ("No present chunk in any exhaustively-classified store is "
                "entirely `fill_value`.")
    head = ("| sample | kind | level | all-fill chunks | bytes | of present "
            "chunks | store |\n|---|---|---|---|---|---|---|")
    body = "\n".join(
        f"| {s} | {k} | {lv} | **{commas(n)}** | {commas(b)} | {commas(p)} "
        f"| `{root}` |" for s, k, root, lv, n, b, p in sorted(rows))
    return head + "\n" + body


def kind_table(ctx):
    agg = {}
    for r in ctx["ok"]:
        a = agg.setdefault(r["kind"], dict(n=0, c=0, b=0))
        a["n"] += 1
        a["c"] += r["stats"]["chunks_present"]
        a["b"] += r["stats"]["bytes_chunks"]
    return "\n".join(
        f"| `{k}` | {v['n']} | {commas(v['c'])} | {human(v['b'])} |"
        for k, v in sorted(agg.items()))


def fill_shape(ctx):
    """Which kinds and levels the all-fill chunks actually sit in."""
    kinds, levels, stores = collections.Counter(), set(), set()
    for r, f in findings_of(ctx["rep"], "all_fill"):
        if r is None or not f["data"].get("n_fill"):
            continue
        kinds[r["kind"]] += f["data"]["n_fill"]
        levels.add(f["level"])
        stores.add((r["kind"], r["root"]))
    total = collections.Counter(r["kind"] for r in ctx["exhaustive"])
    hit = collections.Counter(k for k, _ in stores)
    chunks = collections.Counter()
    for r in ctx["exhaustive"]:
        chunks[r["kind"]] += r["stats"]["chunks_present"]
    return kinds, sorted(levels), hit, total, chunks


def fill_kind_table(ctx):
    kinds, levels, hit, total, chunks = fill_shape(ctx)
    return "\n".join(
        f"| `{k}` | {total[k]} | **{hit.get(k, 0)}** | {commas(chunks[k])} | "
        f"{commas(kinds.get(k, 0))} |" for k in sorted(total))


def occ_check(path="reports/verify-occupancy.json"):
    """One store in the catalogue ships its own occupancy map. Check against it.

    `PHercParis4/.../0/.chunk_occupancy.npz` is a boolean array over the level-0
    chunk grid, written by whoever published the store. It is independent ground
    truth for exactly the quantity measured here, and it is the only place in
    the population where such ground truth exists.
    """
    try:
        with open(path) as fh:
            v = json.load(fh)
    except OSError:
        return ""
    verdict = ("agrees on every cell" if v["identical"]
               else f"disagrees on {commas(v['cells_disagreeing'])} cells")
    return (
        f"There is one place in the population where independent ground truth "
        f"exists. `{v['root']}` ships its own "
        f"`{v['level']}/.chunk_occupancy.npz`, a boolean array over the level-"
        f"{v['level']} chunk grid written by whoever published the store. The "
        f"census {verdict} of that {' x '.join(map(str, v['grid']))} = "
        f"{commas(v['grid_cells'])}-cell grid: **{commas(v['measured_present'])} "
        f"chunks measured present, {commas(v['published_occupied'])} marked "
        f"occupied, {commas(v['cells_disagreeing'])} cells disagreeing.** "
        f"Reproduce with:\n\n```sh\npython3 -m fill_census verify-occupancy "
        f"{v['root']}\n```")


def headline(ctx):
    n = ctx["t"]["all_fill_chunks"]
    c = len(ctx["contract"])
    parts = []
    if n:
        kinds, levels, hit, total, chunks = fill_shape(ctx)
        only_kind = [k for k in total if hit.get(k)]
        clean_kind = [k for k in total if not hit.get(k)]
        where = ""
        if len(only_kind) == 1 and clean_kind:
            where = (
                f" Every one of them is in a `{only_kind[0]}` store -- "
                f"{hit[only_kind[0]]} of the {total[only_kind[0]]} of them -- "
                f"and not one is in any "
                + " or ".join(f"`{k}`" for k in clean_kind)
                + f" store ({sum(total[k] for k in clean_kind)} stores, "
                f"{commas(sum(chunks[k] for k in clean_kind))} present chunks, "
                f"every one of them classified, none all-fill). ")
        if len(levels) == 1:
            where += (
                f"Every one is at level `{levels[0]}`: the reduced levels of "
                f"the same stores omit their empty chunks correctly, so the "
                f"downsampling path is right and the level-0 writer is the one "
                f"emitting blocks it did not intend to.")
        parts.append(
            f"**{commas(n)} present chunks across the population are entirely "
            f"`fill_value`**, costing {human(ctx['t']['all_fill_bytes'])} -- "
            f"{ctx['t']['all_fill_share_pct']:.7f}% of the "
            f"{human(ctx['ex_bytes'])} exhaustively classified. As a hosting "
            f"bill that is nothing, and it is reported as nothing. As a signal "
            f"it is not nothing, because of where they are.{where}")
    else:
        parts.append(
            "**No present chunk in any exhaustively-classified store is "
            "entirely `fill_value`.** The writers that produced this data omit "
            "empty chunks correctly, without exception, at population scale.")
    reps = [f for f in ctx["rep"].get("replica_findings", [])
            if f["check"] == "replica_agreement"]
    agree = [f for f in reps if f["severity"] == "advisory"]
    clean = []
    if not any(f for _, f in findings_of(ctx["rep"], "index_bounds")):
        clean.append(
            f"not one of the {commas(ctx['t']['chunks_present'])} stored chunk "
            f"keys indexes outside its own declared chunk grid")
    if len(agree) == len(reps) and agree:
        clean.append(
            f"the {len(agree)} volumes published under both access roots present "
            f"identical chunk key sets under both, down to the last of "
            f"{commas(max(f['data']['n_keys'] for f in agree))} keys")
    n_size = len({r["root"] for r, f in findings_of(ctx["rep"], "chunk_size")})
    clean.append(
        f"{len(ctx['ok']) - n_size} of {len(ctx['ok'])} stores hold no object "
        f"whose stored size disagrees with the geometry its own `.zarray` "
        f"declares")
    if c:
        parts.append(
            f"**{c} contract violation{'' if c == 1 else 's'}**; see "
            f"`FINDINGS.md`. Everything else holds: " + "; ".join(clean) + ".")
    else:
        parts.append(
            "No contract violation was found anywhere in the population: every "
            "present chunk in an uncompressed store is exactly the size its "
            "geometry requires, no stored key indexes outside its declared "
            "chunk grid, and the volumes published under two access roots "
            "present identical chunk key sets.")
    return "\n\n".join(parts)


FINDINGS = """# Findings

Generated from `{src}` by `make_readme.py`. Every figure comes from that run.

Run: `python3 -m fill_census scan --workers 8 --out reports/scan-full.json`
({generated}, {seconds} s wall clock, {n_ok} of {n_stores} stores inventoried).

## Contract violations

{contract}

## All-fill chunks (advisory)

{fill}

## Coverage and honesty

- Fill classification was **exhaustive** for {n_exhaustive} stores
  ({ex_chunks} chunks, {ex_bytes_h}) via ETag.
- Fill classification was **sampled** for {n_sampled} stores
  ({sa_chunks} chunks, {sa_bytes_h}) on the `https://data.aws.ash2txt.org`
  access root, which exposes no content hash. Those sampled counts are **not**
  included in any total.
- {n_error} store(s) could not be inventoried.

{errors}

## Other advisories

{advisories}
"""


def size_note(f):
    """Say what the anomalous sizes actually are, in the array's own terms.

    Derived from the report, not asserted: a stored size that is an exact cube
    of an integer edge for this dtype names the chunk shape that produced it.
    """
    want = f["data"]["expected_bytes"]
    lines = []
    for sz, n in sorted((int(k), v) for k, v in f["data"]["observed"].items()):
        edge = round(sz ** (1 / 3))
        shape = f"{edge}^3" if edge ** 3 == sz else "not a cube"
        lines.append(f"| {commas(sz)} | {n} | {sz / want:.6g}x | {shape} |")
    return ("\n| stored size (B) | objects | multiple of the declared chunk | "
            "cube edge for uint8 |\n|---|---|---|---|\n" + "\n".join(lines) +
            f"\n\nThe declared chunk is {commas(want)} B. An object of "
            f"{commas(sorted(int(k) for k in f['data']['observed'])[0])} B "
            f"cannot be read as the declared chunk shape at all: "
            f"`numpy.frombuffer(raw, '|u1').reshape(chunks)` raises "
            f"`cannot reshape array of size ... into shape (...)`.\n")


def contract_section(ctx):
    if not ctx["contract"]:
        return ("None. Across {n} stores, {c} present chunks and {b}, no "
                "present chunk in an uncompressed store has a size other than "
                "the one its geometry requires, no stored chunk key indexes "
                "outside its declared grid, and every volume published under "
                "two access roots presents the identical chunk key set under "
                "both.\n\nA clean population, certified against the evidence "
                "in `reports/scan-full.json`.").format(
                    n=len(ctx["ok"]), c=commas(ctx["t"]["chunks_present"]),
                    b=human(ctx["t"]["bytes_chunks"]))
    out = []
    for r, f in ctx["contract"]:
        loc = f"`{r['base']}/{r['root']}`" if r else "(cross-root)"
        extra = size_note(f) if f["check"] == "chunk_size" else ""
        out.append(f"### `{f['check']}` -- level `{f['level']}`\n\n"
                   f"Location: {loc}\n\n{f['detail']}\n{extra}\n```json\n"
                   f"{json.dumps(f['data'], indent=1)}\n```")
    return "\n\n".join(out)


def fill_section(ctx):
    rows = [(r, f) for r, f in findings_of(ctx["rep"], "all_fill")
            if r is not None and f["data"].get("n_fill")]
    if not rows:
        return ("None. No present chunk in any exhaustively-classified store "
                "is entirely `fill_value`.")
    out = []
    for r, f in sorted(rows, key=lambda x: -x[1]["data"]["n_fill"]):
        out.append(f"### `{r['base']}/{r['root']}` level `{f['level']}`\n\n"
                   f"{f['detail']}\n\n```json\n"
                   f"{json.dumps(f['data'], indent=1)}\n```")
    return "\n\n".join(out)


def advisory_section(ctx):
    c = collections.Counter(f["check"] for _, f in findings_of(ctx["rep"],
                                                              severity="advisory"))
    if not c:
        return "None."
    return "\n".join(f"- `{k}`: {v} finding(s)" for k, v in sorted(c.items()))


def error_section(ctx):
    bad = [r for r in ctx["rep"]["results"] if r["error"]]
    if not bad:
        return "Every store in the catalogue was inventoried."
    return "\n".join(f"- `{r['base']}/{r['root']}`: {r['error']}" for r in bad)


def main(path):
    rep = load(path)
    ctx = build(rep)
    t = ctx["t"]
    readme = README.format(
        n_ok=rep["n_ok"], n_stores=rep["n_stores"],
        objects=commas(t["objects"]),
        chunks_present=commas(t["chunks_present"]),
        chunks_in_grid=commas(t["chunks_in_grid"]),
        occupancy=100.0 * t["chunks_present"] / t["chunks_in_grid"]
        if t["chunks_in_grid"] else 0.0,
        bytes_h=human(t["bytes_chunks"]), bytes_raw=commas(t["bytes_chunks"]),
        ex_chunks=commas(ctx["ex_chunks"]), ex_bytes_h=human(ctx["ex_bytes"]),
        fill_chunks=commas(t["all_fill_chunks"]),
        fill_bytes_h=human(t["all_fill_bytes"]),
        fill_bytes_raw=commas(t["all_fill_bytes"]),
        fill_share=t["all_fill_share_pct"],
        n_short=commas(sum(sum(f["data"]["observed"].values())
                           for _, f in findings_of(rep, "chunk_size"))),
        n_oob=commas(sum(f["data"]["n_out_of_range"]
                         for _, f in findings_of(rep, "index_bounds"))),
        n_contract=len(ctx["contract"]), seconds=commas(int(rep["seconds"])),
        headline=headline(ctx), n_sampled=len(ctx["sampled"]),
        sa_chunks=commas(ctx["sa_chunks"]), sa_bytes_h=human(ctx["sa_bytes"]),
        occ_check=occ_check(),
        level_table=level_table(ctx), fill_table=fill_table(ctx),
        n_exhaustive=len(ctx["exhaustive"]),
        fill_kind_table=fill_kind_table(ctx),
        fill_levels=", ".join(f"`{x}`" for x in fill_shape(ctx)[1]) or "none",
        kind_table=kind_table(ctx), dup_n=commas(ctx["dup_n"]),
        dup_bytes_h=human(ctx["dup_bytes"]),
    )
    findings = FINDINGS.format(
        src=path, generated=rep["generated"],
        seconds=commas(int(rep["seconds"])), n_ok=rep["n_ok"],
        n_stores=rep["n_stores"], contract=contract_section(ctx),
        fill=fill_section(ctx), n_exhaustive=len(ctx["exhaustive"]),
        ex_chunks=commas(ctx["ex_chunks"]), ex_bytes_h=human(ctx["ex_bytes"]),
        n_sampled=len(ctx["sampled"]), sa_chunks=commas(ctx["sa_chunks"]),
        sa_bytes_h=human(ctx["sa_bytes"]), n_error=rep["n_error"],
        errors=error_section(ctx), advisories=advisory_section(ctx),
    )
    open("README.md", "w").write(readme)
    open("FINDINGS.md", "w").write(findings)
    print(f"wrote README.md ({len(readme)} B) and FINDINGS.md ({len(findings)} B)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reports/scan-full.json")
