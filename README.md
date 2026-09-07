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
| Zarr stores inventoried | **117** of 117 |
| stored objects enumerated | **136,127,008** |
| chunks present | **136,125,677** |
| chunks in the declared grids | 433,650,543 |
| population occupancy | **31.39%** |
| stored chunk bytes | **253.33 TiB** (278,540,518,220,412 B) |
| chunks exhaustively classified for fill | **134,066,300** (249.40 TiB) |
| chunks present **and entirely `fill_value`** | **3,144** |
| bytes those cost | **17.53 MiB** (18,386,112 B) |
| share of exhaustively-classified stored bytes | **0.0000066%** |
| chunks whose stored size disagrees with geometry | **555** |
| chunk keys stored outside the declared grid | **0** |
| contract violations | **1** |
| wall clock, whole population | **5,114 s** |

**3,144 present chunks across the population are entirely `fill_value`**, costing 17.53 MiB -- 0.0000066% of the 249.40 TiB exhaustively classified. As a hosting bill that is nothing, and it is reported as nothing. As a signal it is not nothing, because of where they are. Every one of them is in a `surface-prediction-zarr` store -- 28 of the 43 of them -- and not one is in any `ome-zarr` store (64 stores, 130,183,005 present chunks, every one of them classified, none all-fill). Every one is at level `0`: the reduced levels of the same stores omit their empty chunks correctly, so the downsampling path is right and the level-0 writer is the one emitting blocks it did not intend to.

**1 contract violation**; see `FINDINGS.md`. Everything else holds: not one of the 136,125,677 stored chunk keys indexes outside its own declared chunk grid; the 3 volumes published under both access roots present identical chunk key sets under both, down to the last of 210,858 keys; 116 of 117 stores hold no object whose stored size disagrees with the geometry its own `.zarray` declares.

## The measurement, and why it is affordable

A chunk of `128 x 128 x 128` `uint8` with no codec is exactly **2,097,152
bytes**. S3 publishes the MD5 of every single-part object as its `ETag`, and an
all-`fill_value` chunk of a fixed size has exactly one MD5:

```
md5(b"\x00" * 2097152) = b2d1236c286a3c0704224fe4105eca49
```

So for an uncompressed store the entire question is answered from
`ListObjectsV2` metadata. **No chunk bytes move at all.** 134,066,300 chunks
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

There is one place in the population where independent ground truth exists. `PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr/` ships its own `0/.chunk_occupancy.npz`, a boolean array over the level-0 chunk grid written by whoever published the store. The census agrees on every cell of that 593 x 256 x 256 = 38,862,848-cell grid: **9,917,101 chunks measured present, 9,917,101 marked occupied, 0 cells disagreeing.** Reproduce with:

```sh
python3 -m fill_census verify-occupancy PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr/
```

The `https://data.aws.ash2txt.org` access root exposes no content hash and no
bulk listing -- only an HTML directory index with human-rounded sizes. Those
10 stores (2,059,377 chunks, 3.93 TiB) are enumerated
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

Summed over the 107 stores whose fill was classified exhaustively by
ETag. Occupancy is the fraction of the declared chunk grid that is actually
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

| kind | stores | stores holding all-fill chunks | chunks present | all-fill chunks |
|---|---|---|---|---|
| `ome-zarr` | 64 | **0** | 130,183,005 | 0 |
| `surface-prediction-zarr` | 43 | **28** | 3,883,295 | 3,144 |

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
| `ome-zarr` | 74 | 132,242,382 | 252.03 TiB |
| `surface-prediction-zarr` | 43 | 3,883,295 | 1.30 TiB |

### Duplicate content

350,997 of 136,125,677 stored chunks are byte-for-byte duplicates of
another chunk in the same store, costing **465.68 GiB**. This is not a
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
- **The 10 stores on the HTML-index access root are sampled, not
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
