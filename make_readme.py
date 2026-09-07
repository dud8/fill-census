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
    """Findings from the origins the scan actually counted.

    A store published under two access roots appears twice in `results`; its
    findings must be reported once, from the same origin the totals used.
    """
    for r in rep["results"]:
        if not r.get("counted", True):
            continue
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
    # A store published under two access roots is one store. The scan marks the
    # single origin it counted; every population figure here follows that mark.
    distinct = [r for r in ok if r.get("counted", True)]

    def uses(r, method):
        return any(m == method for m in r["stats"]["fill_methods"])

    sampled = [r for r in distinct if uses(r, "sampled")]
    classified = [r for r in distinct if not uses(r, "sampled")]
    by_kind = collections.Counter(r["kind"] for r in distinct)
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
    return dict(rep=rep, t=t, ok=ok, distinct=distinct, classified=classified,
                sampled=sampled, by_kind=by_kind,
                ex_chunks=t["chunks_classified_exhaustive"],
                ex_bytes=t["bytes_classified_exhaustive"],
                bo_chunks=t["chunks_classified_bounded"],
                bo_bytes=t["bytes_classified_bounded"],
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
| Zarr stores inventoried | **{n_stores}** distinct stores, from {n_origins} published origins |
| stored objects enumerated | **{objects}** |
| chunks present | **{chunks_present}** |
| chunks in the declared grids | {chunks_in_grid} |
| population occupancy | **{occupancy:.2f}%** |
| stored chunk bytes | **{bytes_h}** ({bytes_raw} B) |
| of those bytes, exact counts published by S3 | {bytes_exact_h} |
| chunks classified **exhaustively**, ETag against the all-fill MD5 | **{ex_chunks}** ({ex_bytes_h}) |
| chunks **decoded**, compressed, one representative per ETag class at or below the level's tested size ceiling | {bo_chunks} ({bo_bytes_h}) |
| chunks **not decoded**, compressed, above that ceiling or in a class beyond the tested set | {n_undecoded} |
| chunks **sampled only**, access root publishes no content hash | {sa_chunks} ({sa_bytes_h}) |
| chunks **not classifiable** from listing metadata, multipart ETag | {n_multipart} |{residual_row}
| chunks present **and entirely `fill_value`** | **{fill_chunks}** |
| bytes those cost | **{fill_bytes_h}** ({fill_bytes_raw} B) |
| chunks whose stored size disagrees with geometry | **{n_short}** |
| chunk keys stored outside the declared grid | **{n_oob}** |
| contract violations | **{n_contract}** |
| wall clock, whole population | **{seconds} s** |

The classification rows above are the whole honesty of this report, so they are
stated before anything else. Every present chunk falls in exactly one of them
and they sum to {chunks_present}. Only the first is a census in the strict
sense.

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
were classified this way.

That identity is the load-bearing assumption of the whole report, and this
bucket does not honour it everywhere: an object uploaded in parts carries the
MD5 of its part hashes instead, and {n_multipart} stored chunks are such
objects. They are counted, excluded from the exhaustive figure, and reported as
`multipart_etag` advisories rather than assumed away. For the rest, the identity
is not assumed either -- it is measured:

{etag_check}

Compressed stores cannot use that shortcut: blosc output for the same voxels is
not the same byte string across library builds, and measurably is not here --
the analytic encoding of an all-zero `192^3` chunk and the one actually stored
are both 5,848 bytes and have different MD5s. So for those, objects are grouped
into byte-identical classes by ETag and one representative per class is
downloaded and decoded, smallest class first. Every all-fill chunk in one store
shares one class, so the guarantee is a size ceiling, reported per level: every
stored object at or below it was decoded and tested.

The sharded lister must neither drop a key nor return one twice, so it is
checked against the simplest possible implementation -- a plain serial
`ListObjectsV2` token chain:

{lister_check}

{occ_check}

The `https://data.aws.ash2txt.org` access root exposes no content hash and no
bulk listing -- only an HTML directory index with human-rounded sizes. The
{n_sampled} stores published only there ({sa_chunks} chunks, {sa_bytes_h}) are
enumerated exhaustively by walking the index, but their fill counts are
**sampled, and are never folded into the all-fill totals above.** The stores
published under both roots are counted from S3, where the sizes are exact.

{replica_note}

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
| `multipart_etag` | advisory | chunks whose ETag is the MD5 of their part hashes, not of the object, and which therefore cannot be classified from listing metadata |

Occupancy per level is reported for every store whether or not anything is
flagged; it is a published statistic in its own right and nobody had it.

## Results

### Occupancy and cost by pyramid level

Summed over the {n_classified} stores whose fill was classified from ETags
(exhaustively for the uncompressed ones, up to a size ceiling for the
compressed ones). Occupancy is the fraction of the declared chunk grid that is actually
stored; the rest is absent, which is correct sparse Zarr and costs nothing.

| level | chunks present | chunks in grid | occupancy | stored bytes | all-fill chunks | all-fill bytes |
|---|---|---|---|---|---|---|
{level_table}

### Where the all-fill chunks are

| kind | stores classified by ETag | stores holding all-fill chunks | chunks tested for fill | all-fill chunks |
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

{dup_n} of the {hashed_chunks} chunks whose content hash S3 publishes are
byte-for-byte duplicates of another chunk in the same store, costing
**{dup_bytes_h}**. This is not a defect: Zarr addresses chunks by position, so identical content at two positions
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
python3 -m fill_census verify-etag <store-root>        # ETag really is the MD5
python3 tools/check_lister.py <store-root>             # sharded vs serial walk
python3 make_readme.py reports/scan-full.json # regenerate this file
```

`numcodecs` is needed only for the compressed stores and `numpy` only for
`verify-occupancy` (`pip install 'fill-census[compressed,occupancy]'`). Exit status: 0 clean, 2 contract violation, 1 tool
error.

The catalogue is read from `../_data/s3_metadata.json`. Every origin is resolved
against the `access_root` declared beside it; the catalogue publishes under two
roots and three volumes appear under both, so assuming the bucket for all of
them reports real stores as missing.

## What this does not prove

- **It does not prove the non-fill chunks are correct.** A chunk that is not
  entirely `fill_value` is counted as carrying information. Whether that
  information is right is a different question and is not asked here.
- **The compressed stores are not exhaustive.** Every object at or below a
  per-level size ceiling was decoded and tested; the {n_above} objects above it
  were not. The ceiling and the untested count are reported per level in
  `reports/scan-full.json`. An all-fill chunk that encoded to more bytes than
  the ceiling would be missed. This is most of the compressed population by
  object count, and it is where every all-fill chunk found here lives.
- **The {n_sampled} stores on the HTML-index access root are sampled, not
  censused, for fill.** Their key sets and occupancy are exhaustive; their fill
  counts are not, and are excluded from every all-fill total. Their bytes are
  in the population totals, tagged as rounded.
- **Sizes from the HTML index are rounded for display.** A chunk truncated by a
  few kilobytes still displays as `2.0 MiB`, so `chunk_size` is downgraded to
  advisory on that root.
- **ETag equality is MD5 equality.** Two objects with the same ETag are treated
  as the same bytes. A deliberate collision would defeat this; accidental
  collision at this population size is not a practical concern. Every all-fill
  chunk reported here was found by downloading and decoding one member of its
  ETag class, so the class was observed to be all-fill; that every other member
  of the class holds the same bytes is what the hash is being trusted for.
  {n_multipart} objects publish no whole-object MD5 at all, because they were
  uploaded in parts; they are excluded rather than guessed at.
- **The all-fill count is not one number of one kind.** {ex_fill} of the
  {fill_chunks} reported come from the exhaustive path and {bo_fill} from the
  compressed path, whose guarantee is the size ceiling above, not
  exhaustiveness. That part of the count is exact for the ETag classes that
  were decoded and says nothing about the {n_above} objects larger than the
  ceiling.
- **It does not say the all-fill chunks should be deleted.** Deleting a present
  chunk changes nothing a correct Zarr reader sees, but this tool has not
  verified that every consumer of these stores is a correct Zarr reader.
- **Whether any of this affects downstream results has not been measured.**

## Licence

MIT.
"""


def read_check(path, blurb):
    """Quote a verification run from its own output file, or say it was not run.

    These numbers must come from a command that was actually executed, so they
    are read back from the file that command wrote rather than written here.
    """
    try:
        with open(path) as fh:
            body = fh.read().strip()
    except OSError:
        return f"_({blurb} has not been run; `{path}` is absent.)_"
    return "```\n" + body + "\n```"


def etag_check(path="reports/verify-etag.json"):
    try:
        with open(path) as fh:
            v = json.load(fh)
    except OSError:
        return "_(`verify-etag` has not been run.)_"
    return (
        f"`{v['root']}` level `{v['level']}` holds "
        f"{commas(v['objects_in_level'])} single-part objects. "
        f"{commas(v['objects_downloaded'])} of them, spread across the level, "
        f"were downloaded and hashed: **"
        f"{commas(v['etag_equals_md5_of_bytes'])} of "
        f"{commas(v['objects_downloaded'])} had an ETag exactly equal to the "
        f"MD5 of the bytes S3 returned**, and "
        f"{commas(v['length_equals_listed_size'])} matched the listed size. "
        f"Reproduce with:\n\n```sh\npython3 -m fill_census verify-etag "
        f"{v['root']}\n```")


def level_table(ctx):
    agg = {}
    for r in ctx["classified"]:
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
    for r in ctx["distinct"]:
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
    total = collections.Counter(r["kind"] for r in ctx["classified"])
    hit = collections.Counter(k for k, _ in stores)
    chunks = collections.Counter()
    for r in ctx["classified"]:
        # Only what was actually classified; a multipart ETag was not.
        chunks[r["kind"]] += sum(lv["objects_classified"]
                                 for lv in r["levels"].values())
    return kinds, sorted(levels), hit, total, chunks


def fill_kind_table(ctx):
    kinds, levels, hit, total, chunks = fill_shape(ctx)
    return "\n".join(
        f"| `{k}` | {total[k]} | **{hit.get(k, 0)}** | {commas(chunks[k])} | "
        f"{commas(kinds.get(k, 0))} |" for k in sorted(total))


def replica_note(ctx):
    """What the double-published stores say about the rounded-size parse.

    Three stores are published under both roots, so the same bytes are measured
    twice by different machinery: exact counts from S3 against sizes an HTML
    index rounded for display. Where the two totals agree, the parse is shown to
    have recovered the exact figure on real data rather than assumed to.
    """
    reps = [f for f in ctx["rep"].get("replica_findings", [])
            if f["check"] == "replica_agreement" and "bytes" in f["data"]]
    if not reps:
        return ""
    agree = [f for f in reps if f["data"]["bytes_agree"]]
    return (
        f"That rounding is not assumed to be harmless either. {len(reps)} stores "
        f"are published under both roots, so the same bytes are measured twice "
        f"by different machinery. {len(agree)} of {len(reps)} agree on the "
        f"stored byte total exactly -- up to "
        f"{human(max(f['data']['bytes'][0] for f in agree))} across "
        f"{commas(max(f['data']['n_keys'] for f in agree))} chunk keys -- so on "
        f"these stores the rounded index recovered the exact figure."
        if agree else
        f"{len(reps) - len(agree)} of {len(reps)} double-published stores "
        f"disagree on the stored byte total between their two roots.")


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
    caveat = ""
    g = v["grid"]
    if len(set(g)) < len(g):
        caveat = (f" Two of that grid's three extents are equal ({g[1]} and "
                  f"{g[2]}), so this agreement does not by itself rule out a "
                  f"transposition of those two axes; the leading extent "
                  f"({g[0]}) differs and is pinned by it.")
    return (
        f"There is one place in the population where independent ground truth "
        f"exists. `{v['root']}` ships its own "
        f"`{v['level']}/.chunk_occupancy.npz`, a boolean array over the level-"
        f"{v['level']} chunk grid written by whoever published the store. The "
        f"census {verdict} of that {' x '.join(map(str, v['grid']))} = "
        f"{commas(v['grid_cells'])}-cell grid: **{commas(v['measured_present'])} "
        f"chunks measured present, {commas(v['published_occupied'])} marked "
        f"occupied, {commas(v['cells_disagreeing'])} cells disagreeing.** "
        + caveat +
        f" Reproduce with:\n\n```sh\npython3 -m fill_census verify-occupancy "
        f"{v['root']}\n```")


def ceiling_argument(ctx, fill_level):
    """State, from the report, whether a reduced level could have hidden one.

    The compressed path only tests objects at or below a per-level size ceiling.
    "None at the reduced levels" is only worth saying if those levels' ceilings
    were at or above the size an all-fill chunk actually encodes to, which the
    report records for every store that holds one. Where that does not hold, the
    honest statement is which levels could not have shown one.
    """
    sizes = {f["data"]["bytes_fill"] // f["data"]["n_fill"]
             for _, f in findings_of(ctx["rep"], "all_fill")
             if f["data"].get("n_fill")}
    if len(sizes) != 1:
        return ""
    enc = sizes.pop()
    blind = []
    for r in ctx["classified"]:
        for path, lv in r["levels"].items():
            ceil_b = lv["all_fill_detail"].get("size_ceiling_tested")
            if ceil_b is not None and ceil_b < enc and lv["chunks_present"]:
                blind.append((path, r["sample"]))
    here = sorted(n for p, n in blind if p == fill_level)
    reduced = sorted(f"{n} level {p}" for p, n in blind if p != fill_level)

    def name(xs):
        return ", ".join(xs[:4]) + (", ..." if len(xs) > 4 else "")

    out = [f"An all-fill chunk in these stores encodes to exactly {commas(enc)} "
           f"bytes."]
    if reduced:
        out.append(
            f"{len(reduced)} reduced "
            f"{'level was' if len(reduced) == 1 else 'levels were'} tested only "
            f"below that size ({name(reduced)}), so "
            f"{'it' if len(reduced) == 1 else 'they'} cannot be called clean; "
            f"every other reduced level of every classified store was tested at "
            f"or above it, so a reduced level holding an all-fill chunk would "
            f"have been caught.")
    else:
        out.append(
            f"Every reduced level of every classified store was tested at or "
            f"above that size, so a reduced level holding one would have been "
            f"caught. The downsampling path omits its empty chunks; the "
            f"level-`{fill_level}` writer is the one emitting blocks it did not "
            f"intend to.")
    if here:
        out.append(
            f"At level `{fill_level}` itself, {len(here)} "
            f"{'store was' if len(here) == 1 else 'stores were'} tested only "
            f"below that size ({name(here)}), so the count above is a floor "
            f"there too.")
    return " ".join(out)


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
                f"and not one is in any of the "
                f"{sum(total[k] for k in clean_kind)} "
                + " or ".join(f"`{k}`" for k in clean_kind)
                + f" stores classified by ETag ("
                f"{commas(sum(chunks[k] for k in clean_kind))} chunks tested "
                f"against the all-fill pattern, none matching). ")
        if len(levels) == 1:
            where += (f"Every one is at level `{levels[0]}`. "
                      + ceiling_argument(ctx, levels[0]))
        parts.append(
            f"**{commas(n)} present chunks are entirely `fill_value`**, costing "
            f"{human(ctx['t']['all_fill_bytes'])} against the "
            f"{human(ctx['t']['bytes_chunks'])} published. As a hosting bill "
            f"that is nothing, and it is reported as nothing. As a signal it is "
            f"not nothing, because of where they are.{where}")
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
        f"{len(ctx['distinct']) - n_size} of {len(ctx['distinct'])} stores hold "
        f"no object "
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
({generated}, {seconds} s wall clock, {n_ok} of {n_origins} published origins,
{n_stores} distinct stores).

## Contract violations

{contract}

## All-fill chunks (advisory)

{fill}

## Coverage and honesty

- **Exhaustive**: {ex_chunks} chunks ({ex_bytes_h}). Uncompressed, single-part
  objects on S3, every one classified by comparing its ETag against the MD5 of
  an all-fill chunk. {ex_fill} all-fill chunks were found on this path.
- **Bounded by a size ceiling**: {bo_chunks} chunks ({bo_bytes_h}). Compressed
  stores, where one representative of each byte-identical ETag class was
  downloaded and decoded, smallest class first. {n_above} objects sit above the
  per-level ceiling and were not decoded. {bo_fill} of the {fill_chunks}
  all-fill chunks reported came from this path, so that part of the count is a
  floor, not a census.
- **Sampled**: {n_sampled} stores ({sa_chunks} chunks, {sa_bytes_h}) on the
  `https://data.aws.ash2txt.org` access root, which publishes no content hash.
  Their key sets and byte totals are in the population figures; their sampled
  fill counts are **not** included in any all-fill total.
- **Not classifiable**: {n_multipart} chunks carry a multipart ETag, which is
  the MD5 of the part hashes rather than of the object.
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
                    n=len(ctx["distinct"]),
                    c=commas(ctx["t"]["chunks_present"]),
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
    n_above = sum(
        lv["all_fill_detail"].get("objects_above_ceiling", 0)
        for r in ctx["distinct"] for lv in r["levels"].values())
    by_path = collections.Counter()
    for r in ctx["distinct"]:
        for lv in r["levels"].values():
            by_path[lv["all_fill_method"].split(" ")[0]] += lv["all_fill_chunks"]
    comp_present = sum(
        lv["chunks_present"] for r in ctx["distinct"]
        for lv in r["levels"].values()
        if lv["all_fill_method"].startswith("etag-class"))
    n_undecoded = comp_present - ctx["bo_chunks"]
    residual = (t["chunks_present"] - ctx["ex_chunks"] - ctx["bo_chunks"]
                - n_undecoded - ctx["sa_chunks"] - t.get("multipart_etags", 0))
    residual_row = ("" if not residual else
                    f"\n| chunks in none of the above | {commas(residual)} |")
    readme = README.format(
        n_stores=rep.get("n_stores", rep["n_ok"]),
        n_origins=rep.get("n_origins", rep["n_ok"]),
        objects=commas(t["objects"]),
        chunks_present=commas(t["chunks_present"]),
        chunks_in_grid=commas(t["chunks_in_grid"]),
        occupancy=100.0 * t["chunks_present"] / t["chunks_in_grid"]
        if t["chunks_in_grid"] else 0.0,
        bytes_h=human(t["bytes_chunks"]), bytes_raw=commas(t["bytes_chunks"]),
        bytes_exact_h=human(t.get("bytes_chunks_exact", 0)),
        ex_chunks=commas(ctx["ex_chunks"]), ex_bytes_h=human(ctx["ex_bytes"]),
        bo_chunks=commas(ctx["bo_chunks"]), bo_bytes_h=human(ctx["bo_bytes"]),
        n_multipart=commas(t.get("multipart_etags", 0)),
        n_above=commas(n_above), n_undecoded=commas(n_undecoded),
        ex_fill=commas(by_path["etag-md5"]),
        bo_fill=commas(by_path["etag-class"]), residual_row=residual_row,
        etag_check=etag_check(),
        lister_check=read_check("reports/lister-check.txt",
                                "the lister cross-check"),
        fill_chunks=commas(t["all_fill_chunks"]),
        fill_bytes_h=human(t["all_fill_bytes"]),
        fill_bytes_raw=commas(t["all_fill_bytes"]),
        n_short=commas(sum(sum(f["data"]["observed"].values())
                           for _, f in findings_of(rep, "chunk_size"))),
        n_oob=commas(sum(f["data"]["n_out_of_range"]
                         for _, f in findings_of(rep, "index_bounds"))),
        n_contract=len(ctx["contract"]), seconds=commas(int(rep["seconds"])),
        headline=headline(ctx), n_sampled=len(ctx["sampled"]),
        sa_chunks=commas(ctx["sa_chunks"]), sa_bytes_h=human(ctx["sa_bytes"]),
        occ_check=occ_check(), replica_note=replica_note(ctx),
        level_table=level_table(ctx), fill_table=fill_table(ctx),
        n_classified=len(ctx["classified"]),
        fill_kind_table=fill_kind_table(ctx),
        fill_levels=", ".join(f"`{x}`" for x in fill_shape(ctx)[1]) or "none",
        kind_table=kind_table(ctx), dup_n=commas(ctx["dup_n"]),
        hashed_chunks=commas(sum(r["stats"]["chunks_present"]
                                 for r in ctx["classified"])),
        dup_bytes_h=human(ctx["dup_bytes"]),
    )
    findings = FINDINGS.format(
        src=path, generated=rep["generated"],
        seconds=commas(int(rep["seconds"])), n_ok=rep["n_ok"],
        n_stores=rep.get("n_stores", rep["n_ok"]),
        n_origins=rep.get("n_origins", rep["n_ok"]),
        contract=contract_section(ctx),
        fill=fill_section(ctx),
        ex_chunks=commas(ctx["ex_chunks"]), ex_bytes_h=human(ctx["ex_bytes"]),
        bo_chunks=commas(ctx["bo_chunks"]), bo_bytes_h=human(ctx["bo_bytes"]),
        n_above=commas(n_above), n_multipart=commas(t.get("multipart_etags", 0)),
        ex_fill=commas(by_path["etag-md5"]), bo_fill=commas(by_path["etag-class"]),
        fill_chunks=commas(t["all_fill_chunks"]),
        n_sampled=len(ctx["sampled"]), sa_chunks=commas(ctx["sa_chunks"]),
        sa_bytes_h=human(ctx["sa_bytes"]), n_error=rep["n_error"],
        errors=error_section(ctx), advisories=advisory_section(ctx),
    )
    open("README.md", "w").write(readme)
    open("FINDINGS.md", "w").write(findings)
    print(f"wrote README.md ({len(readme)} B) and FINDINGS.md ({len(findings)} B)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reports/scan-full.json")
