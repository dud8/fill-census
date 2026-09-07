# fill-census

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
| Zarr stores inventoried | **114** distinct stores, from 117 published origins |
| stored objects enumerated | **135,910,932** |
| chunks present | **135,909,633** |
| chunks in the declared grids | 433,367,457 |
| population occupancy | **31.36%** |
| stored chunk bytes | **252.92 TiB** (278,087,441,113,724 B) |
| of those bytes, exact counts published by S3 | 249.40 TiB |
| chunks classified **exhaustively**, ETag against the all-fill MD5 | **129,776,533** (247.53 TiB) |
| chunks **decoded**, compressed, one representative per ETag class at or below the level's tested size ceiling | 122,340 (7.52 GiB) |
| chunks **not decoded**, compressed, above that ceiling or in a class beyond the tested set | 4,166,872 |
| chunks **sampled only**, access root publishes no content hash | 1,843,333 (3.52 TiB) |
| chunks **not classifiable** from listing metadata, multipart ETag | 555 |
| chunks present **and entirely `fill_value`** | **3,144** |
| bytes those cost | **17.53 MiB** (18,386,112 B) |
| chunks whose stored size disagrees with geometry | **555** |
| chunk keys stored outside the declared grid | **0** |
| contract violations | **1** |
| wall clock, whole population | **2,976 s** |

The classification rows above are the whole honesty of this report, so they are
stated before anything else. Every present chunk falls in exactly one of them
and they sum to 135,909,633. Only the first is a census in the strict
sense.

**3,144 present chunks are entirely `fill_value`**, costing 17.53 MiB against the 252.92 TiB published. As a hosting bill that is nothing, and it is reported as nothing. As a signal it is not nothing, because of where they are. Every one of them is in a `surface-prediction-zarr` store -- 28 of the 43 of them -- and not one is in any of the 64 `ome-zarr` stores classified by ETag (129,778,779 chunks tested against the all-fill pattern, none matching). Every one is at level `0`. An all-fill chunk in these stores encodes to exactly 5,848 bytes. 1 reduced level was tested only below that size (PHerc0139 level 1), so it cannot be called clean; every other reduced level of every classified store was tested at or above it, so a reduced level holding an all-fill chunk would have been caught. At level `0` itself, 1 store was tested only below that size (PHerc0139), so the count above is a floor there too.

**1 contract violation**; see `FINDINGS.md`. Everything else holds: not one of the 135,909,633 stored chunk keys indexes outside its own declared chunk grid; the 3 volumes published under both access roots present identical chunk key sets under both, down to the last of 210,858 keys; 113 of 114 stores hold no object whose stored size disagrees with the geometry its own `.zarray` declares.

## The measurement, and why it is affordable

A chunk of `128 x 128 x 128` `uint8` with no codec is exactly **2,097,152
bytes**. S3 publishes the MD5 of every single-part object as its `ETag`, and an
all-`fill_value` chunk of a fixed size has exactly one MD5:

```
md5(b"\x00" * 2097152) = b2d1236c286a3c0704224fe4105eca49
```

So for an uncompressed store the entire question is answered from
`ListObjectsV2` metadata. **No chunk bytes move at all.** 129,776,533 chunks
were classified this way.

That identity is the load-bearing assumption of the whole report, and this
bucket does not honour it everywhere: an object uploaded in parts carries the
MD5 of its part hashes instead, and 555 stored chunks are such
objects. They are counted, excluded from the exhaustive figure, and reported as
`multipart_etag` advisories rather than assumed away. For the rest, the identity
is not assumed either -- it is measured:

`PHerc0343P/volumes/20250521134555-8.640um-1.2m-116keV-masked.zarr/` level `0` holds 7,988 single-part objects. 64 of them, spread across the level, were downloaded and hashed: **64 of 64 had an ETag exactly equal to the MD5 of the bytes S3 returned**, and 64 matched the listed size. Reproduce with:

```sh
python3 -m fill_census verify-etag PHerc0343P/volumes/20250521134555-8.640um-1.2m-116keV-masked.zarr/
```

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

```
ok   PHerc0343P/volumes/20250521134555-8.640um-1.2m-116keV-masked.zarr/: sharded 10549 objects 36815516839 B / serial 10549 objects 36815516839 B; missing 0, extra 0, duplicated 0
ok   PHercMANB/representations/predictions/surfaces/20260323091048-surface-20260413222639-surface-m7-L2-th0.2.zarr/: sharded 83842 objects 9740677468 B / serial 83842 objects 9740677468 B; missing 0, extra 0, duplicated 0
```

There is one place in the population where independent ground truth exists. `PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr/` ships its own `0/.chunk_occupancy.npz`, a boolean array over the level-0 chunk grid written by whoever published the store. The census agrees on every cell of that 593 x 256 x 256 = 38,862,848-cell grid: **9,917,101 chunks measured present, 9,917,101 marked occupied, 0 cells disagreeing.**  Two of that grid's three extents are equal (256 and 256), so this agreement does not by itself rule out a transposition of those two axes; the leading extent (593) differs and is pinned by it. Reproduce with:

```sh
python3 -m fill_census verify-occupancy PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr/
```

The `https://data.aws.ash2txt.org` access root exposes no content hash and no
bulk listing -- only an HTML directory index with human-rounded sizes. The
7 stores published only there (1,843,333 chunks, 3.52 TiB) are
enumerated exhaustively by walking the index, but their fill counts are
**sampled, and are never folded into the all-fill totals above.** The stores
published under both roots are counted from S3, where the sizes are exact.

That rounding is not assumed to be harmless either. 3 stores are published under both roots, so the same bytes are measured twice by different machinery. 3 of 3 agree on the stored byte total exactly -- up to 411.83 GiB across 210,858 chunk keys -- so on these stores the rounded index recovered the exact figure.

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

Summed over the 107 stores whose fill was classified from ETags
(exhaustively for the uncompressed ones, up to a size ceiling for the
compressed ones). Occupancy is the fraction of the declared chunk grid that is actually
stored; the rest is absent, which is correct sparse Zarr and costs nothing.

| level | chunks present | chunks in grid | occupancy | stored bytes | all-fill chunks | all-fill bytes |
|---|---|---|---|---|---|---|
| 0 | 116,529,899 | 375,043,379 | 31.07% | 216.76 TiB | 3,144 | 18,386,112 |
| 1 | 15,165,310 | 47,238,491 | 32.10% | 28.23 TiB | 0 | 0 |
| 2 | 2,032,585 | 5,968,699 | 34.05% | 3.78 TiB | 0 | 0 |
| 3 | 286,548 | 766,372 | 37.39% | 544.08 GiB | 0 | 0 |
| 4 | 44,347 | 100,379 | 44.18% | 83.37 GiB | 0 | 0 |
| 5 | 7,611 | 13,981 | 54.44% | 14.03 GiB | 0 | 0 |

### Where the all-fill chunks are

| kind | stores classified by ETag | stores holding all-fill chunks | chunks tested for fill | all-fill chunks |
|---|---|---|---|---|
| `ome-zarr` | 64 | **0** | 129,778,779 | 0 |
| `surface-prediction-zarr` | 43 | **28** | 120,094 | 3,144 |

Levels holding all-fill chunks: **`0`**.

### Stores holding all-fill chunks

| sample | kind | level | all-fill chunks | bytes | of present chunks | store |
|---|---|---|---|---|---|---|
| PHerc0009B | surface-prediction-zarr | 0 | **2** | 11,696 | 6,736 | `PHerc0009B/representations/predictions/surfaces/20260319104112-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0125 | surface-prediction-zarr | 0 | **149** | 871,352 | 62,798 | `PHerc0125/representations/predictions/surfaces/20250821151825-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0175A | surface-prediction-zarr | 0 | **338** | 1,976,624 | 58,470 | `PHerc0175A/representations/predictions/surfaces/20250521115057-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0175B | surface-prediction-zarr | 0 | **168** | 982,464 | 93,280 | `PHerc0175B/representations/predictions/surfaces/20250521125822-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0332 | surface-prediction-zarr | 0 | **41** | 239,768 | 7,986 | `PHerc0332/representations/predictions/surfaces/20251211183505-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0343P | surface-prediction-zarr | 0 | **48** | 280,704 | 3,690 | `PHerc0343P/representations/predictions/surfaces/20260304131111-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0500P2 | surface-prediction-zarr | 0 | **6** | 35,088 | 3,770 | `PHerc0500P2/representations/predictions/surfaces/20250526151718-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0500P2 | surface-prediction-zarr | 0 | **1** | 5,848 | 3,439 | `PHerc0500P2/representations/predictions/surfaces/20250820143440-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0800 | surface-prediction-zarr | 0 | **75** | 438,600 | 126,209 | `PHerc0800/representations/predictions/surfaces/20250521135224-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0813 | surface-prediction-zarr | 0 | **46** | 269,008 | 51,125 | `PHerc0813/representations/predictions/surfaces/20250821151723-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0814 | surface-prediction-zarr | 0 | **12** | 70,176 | 37,245 | `PHerc0814/representations/predictions/surfaces/20250804134230-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0814 | surface-prediction-zarr | 0 | **44** | 257,312 | 35,260 | `PHerc0814/representations/predictions/surfaces/20260309142202-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0826 | surface-prediction-zarr | 0 | **298** | 1,742,704 | 46,715 | `PHerc0826/representations/predictions/surfaces/20250821151701-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0841 | surface-prediction-zarr | 0 | **95** | 555,560 | 53,895 | `PHerc0841/representations/predictions/surfaces/20250821151531-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0841 | surface-prediction-zarr | 0 | **2** | 11,696 | 9,356 | `PHerc0841/representations/predictions/surfaces/20260319124803-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0846A | surface-prediction-zarr | 0 | **167** | 976,616 | 40,622 | `PHerc0846A/representations/predictions/surfaces/20250728152254-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc0846A | surface-prediction-zarr | 0 | **9** | 52,632 | 12,416 | `PHerc0846A/representations/predictions/surfaces/20260319102732-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc0846B | surface-prediction-zarr | 0 | **117** | 684,216 | 44,698 | `PHerc0846B/representations/predictions/surfaces/20250804142305-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc1203 | surface-prediction-zarr | 0 | **71** | 415,208 | 50,299 | `PHerc1203/representations/predictions/surfaces/20250820131727-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc1203 | surface-prediction-zarr | 0 | **20** | 116,960 | 7,830 | `PHerc1203/representations/predictions/surfaces/20260319130212-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc1218 | surface-prediction-zarr | 0 | **424** | 2,479,552 | 56,201 | `PHerc1218/representations/predictions/surfaces/20250521120456-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc1299 | surface-prediction-zarr | 0 | **14** | 81,872 | 11,607 | `PHerc1299/representations/predictions/surfaces/20260309130042-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc1447 | surface-prediction-zarr | 0 | **52** | 304,096 | 74,683 | `PHerc1447/representations/predictions/surfaces/20250521151220-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHerc1451 | surface-prediction-zarr | 0 | **72** | 421,056 | 20,198 | `PHerc1451/representations/predictions/surfaces/20260319101107-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHerc1545 | surface-prediction-zarr | 0 | **79** | 461,992 | 48,120 | `PHerc1545/representations/predictions/surfaces/20250821151648-surface-20260413222639-surface-m7-L0-th0.2.zarr/` |
| PHercMAN5 | surface-prediction-zarr | 0 | **14** | 81,872 | 6,540 | `PHercMAN5/representations/predictions/surfaces/20260311104824-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHercMANB | surface-prediction-zarr | 0 | **779** | 4,555,592 | 71,729 | `PHercMANB/representations/predictions/surfaces/20260323091048-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |
| PHercMANBp | surface-prediction-zarr | 0 | **1** | 5,848 | 1,140 | `PHercMANBp/representations/predictions/surfaces/20251216152116-surface-20260413222639-surface-m7-L2-th0.2.zarr/` |

### Population by kind

| kind | stores | chunks | stored bytes |
|---|---|---|---|
| `ome-zarr` | 71 | 132,026,338 | 251.62 TiB |
| `surface-prediction-zarr` | 43 | 3,883,295 | 1.30 TiB |

### Duplicate content

350,997 of the 134,066,300 chunks whose content hash S3 publishes are
byte-for-byte duplicates of another chunk in the same store, costing
**465.68 GiB**. This is not a defect: Zarr addresses chunks by position, so identical content at two positions
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
  per-level size ceiling was decoded and tested; the 4,166,828 objects above it
  were not. The ceiling and the untested count are reported per level in
  `reports/scan-full.json`. An all-fill chunk that encoded to more bytes than
  the ceiling would be missed. This is most of the compressed population by
  object count, and it is where every all-fill chunk found here lives.
- **The 7 stores on the HTML-index access root are sampled, not
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
  555 objects publish no whole-object MD5 at all, because they were
  uploaded in parts; they are excluded rather than guessed at.
- **The all-fill count is not one number of one kind.** 0 of the
  3,144 reported come from the exhaustive path and 3,144 from the
  compressed path, whose guarantee is the size ceiling above, not
  exhaustiveness. That part of the count is exact for the ETag classes that
  were decoded and says nothing about the 4,166,828 objects larger than the
  ceiling.
- **It does not say the all-fill chunks should be deleted.** Deleting a present
  chunk changes nothing a correct Zarr reader sees, but this tool has not
  verified that every consumer of these stores is a correct Zarr reader.
- **Whether any of this affects downstream results has not been measured.**

## Licence

MIT.
