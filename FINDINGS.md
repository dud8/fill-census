# Findings

Generated from `reports/scan-full.json` by `make_readme.py`. Every figure comes from that run.

Run: `python3 -m fill_census scan --workers 8 --out reports/scan-full.json`
(2026-09-07T08:37:38Z, 2,976 s wall clock, 117 of 117 published origins,
114 distinct stores).

## Contract violations

### `chunk_size` -- level `0`

Location: `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0343P/volumes/20250521134555-8.640um-1.2m-116keV-masked.zarr/`

555 present chunks are not the 2097152-byte size that chunks [128, 128, 128] of dtype '|u1' with no codec requires; observed sizes: 16777216x499, 134217728x56

| stored size (B) | objects | multiple of the declared chunk | cube edge for uint8 |
|---|---|---|---|
| 16,777,216 | 499 | 8x | 256^3 |
| 134,217,728 | 56 | 64x | 512^3 |

The declared chunk is 2,097,152 B. An object of 16,777,216 B cannot be read as the declared chunk shape at all: `numpy.frombuffer(raw, '|u1').reshape(chunks)` raises `cannot reshape array of size ... into shape (...)`.

```json
{
 "expected_bytes": 2097152,
 "observed": {
  "134217728": 56,
  "16777216": 499
 }
}
```

## All-fill chunks (advisory)

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHercMANB/representations/predictions/surfaces/20260323091048-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

779 of 71729 present chunks are entirely fill_value (0), costing 4555592 stored bytes (0.059% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 5924 B decoded; 512/64361 classes, 5733/71729 objects; 65988 larger objects untested)]

```json
{
 "n_fill": 779,
 "bytes_fill": 4555592,
 "n_present": 71729,
 "bytes_present": 7779788607,
 "share_pct": 0.058557,
 "method": "etag-class (every object <= 5924 B decoded; 512/64361 classes, 5733/71729 objects; 65988 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1218/representations/predictions/surfaces/20250521120456-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

424 of 56201 present chunks are entirely fill_value (0), costing 2479552 stored bytes (0.016% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6591 B decoded; 512/52085 classes, 2305/56201 objects; 53892 larger objects untested)]

```json
{
 "n_fill": 424,
 "bytes_fill": 2479552,
 "n_present": 56201,
 "bytes_present": 15097023563,
 "share_pct": 0.016424,
 "method": "etag-class (every object <= 6591 B decoded; 512/52085 classes, 2305/56201 objects; 53892 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0175A/representations/predictions/surfaces/20250521115057-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

338 of 58470 present chunks are entirely fill_value (0), costing 1976624 stored bytes (0.012% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6322 B decoded; 512/55278 classes, 2186/58470 objects; 56283 larger objects untested)]

```json
{
 "n_fill": 338,
 "bytes_fill": 1976624,
 "n_present": 58470,
 "bytes_present": 16014952557,
 "share_pct": 0.012342,
 "method": "etag-class (every object <= 6322 B decoded; 512/55278 classes, 2186/58470 objects; 56283 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0826/representations/predictions/surfaces/20250821151701-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

298 of 46715 present chunks are entirely fill_value (0), costing 1742704 stored bytes (0.018% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6410 B decoded; 512/42881 classes, 2514/46715 objects; 44200 larger objects untested)]

```json
{
 "n_fill": 298,
 "bytes_fill": 1742704,
 "n_present": 46715,
 "bytes_present": 9620029695,
 "share_pct": 0.018115,
 "method": "etag-class (every object <= 6410 B decoded; 512/42881 classes, 2514/46715 objects; 44200 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0175B/representations/predictions/surfaces/20250521125822-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

168 of 93280 present chunks are entirely fill_value (0), costing 982464 stored bytes (0.003% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6331 B decoded; 512/88695 classes, 2712/93280 objects; 90568 larger objects untested)]

```json
{
 "n_fill": 168,
 "bytes_fill": 982464,
 "n_present": 93280,
 "bytes_present": 31998293167,
 "share_pct": 0.00307,
 "method": "etag-class (every object <= 6331 B decoded; 512/88695 classes, 2712/93280 objects; 90568 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0846A/representations/predictions/surfaces/20250728152254-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

167 of 40622 present chunks are entirely fill_value (0), costing 976616 stored bytes (0.009% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6581 B decoded; 512/38566 classes, 1011/40622 objects; 39607 larger objects untested)]

```json
{
 "n_fill": 167,
 "bytes_fill": 976616,
 "n_present": 40622,
 "bytes_present": 10831717016,
 "share_pct": 0.009016,
 "method": "etag-class (every object <= 6581 B decoded; 512/38566 classes, 1011/40622 objects; 39607 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0125/representations/predictions/surfaces/20250821151825-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

149 of 62798 present chunks are entirely fill_value (0), costing 871352 stored bytes (0.005% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6603 B decoded; 512/58509 classes, 1535/62798 objects; 61263 larger objects untested)]

```json
{
 "n_fill": 149,
 "bytes_fill": 871352,
 "n_present": 62798,
 "bytes_present": 18276276827,
 "share_pct": 0.004768,
 "method": "etag-class (every object <= 6603 B decoded; 512/58509 classes, 1535/62798 objects; 61263 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0846B/representations/predictions/surfaces/20250804142305-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

117 of 44698 present chunks are entirely fill_value (0), costing 684216 stored bytes (0.005% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6386 B decoded; 512/42217 classes, 1195/44698 objects; 43503 larger objects untested)]

```json
{
 "n_fill": 117,
 "bytes_fill": 684216,
 "n_present": 44698,
 "bytes_present": 12663249955,
 "share_pct": 0.005403,
 "method": "etag-class (every object <= 6386 B decoded; 512/42217 classes, 1195/44698 objects; 43503 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0841/representations/predictions/surfaces/20250821151531-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

95 of 53895 present chunks are entirely fill_value (0), costing 555560 stored bytes (0.003% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6746 B decoded; 512/51324 classes, 1317/53895 objects; 52578 larger objects untested)]

```json
{
 "n_fill": 95,
 "bytes_fill": 555560,
 "n_present": 53895,
 "bytes_present": 16809125318,
 "share_pct": 0.003305,
 "method": "etag-class (every object <= 6746 B decoded; 512/51324 classes, 1317/53895 objects; 52578 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1545/representations/predictions/surfaces/20250821151648-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

79 of 48120 present chunks are entirely fill_value (0), costing 461992 stored bytes (0.003% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6609 B decoded; 512/45115 classes, 1352/48120 objects; 46766 larger objects untested)]

```json
{
 "n_fill": 79,
 "bytes_fill": 461992,
 "n_present": 48120,
 "bytes_present": 14447295303,
 "share_pct": 0.003198,
 "method": "etag-class (every object <= 6609 B decoded; 512/45115 classes, 1352/48120 objects; 46766 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0800/representations/predictions/surfaces/20250521135224-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

75 of 126209 present chunks are entirely fill_value (0), costing 438600 stored bytes (0.001% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6145 B decoded; 512/121337 classes, 2734/126209 objects; 123474 larger objects untested)]

```json
{
 "n_fill": 75,
 "bytes_fill": 438600,
 "n_present": 126209,
 "bytes_present": 42057799240,
 "share_pct": 0.001043,
 "method": "etag-class (every object <= 6145 B decoded; 512/121337 classes, 2734/126209 objects; 123474 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1451/representations/predictions/surfaces/20260319101107-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

72 of 20198 present chunks are entirely fill_value (0), costing 421056 stored bytes (0.008% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 8318 B decoded; 512/18859 classes, 1102/20198 objects; 19096 larger objects untested)]

```json
{
 "n_fill": 72,
 "bytes_fill": 421056,
 "n_present": 20198,
 "bytes_present": 5204848719,
 "share_pct": 0.00809,
 "method": "etag-class (every object <= 8318 B decoded; 512/18859 classes, 1102/20198 objects; 19096 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1203/representations/predictions/surfaces/20250820131727-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

71 of 50299 present chunks are entirely fill_value (0), costing 415208 stored bytes (0.003% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6635 B decoded; 512/47302 classes, 1309/50299 objects; 48989 larger objects untested)]

```json
{
 "n_fill": 71,
 "bytes_fill": 415208,
 "n_present": 50299,
 "bytes_present": 15177154949,
 "share_pct": 0.002736,
 "method": "etag-class (every object <= 6635 B decoded; 512/47302 classes, 1309/50299 objects; 48989 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1447/representations/predictions/surfaces/20250521151220-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

52 of 74683 present chunks are entirely fill_value (0), costing 304096 stored bytes (0.001% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6263 B decoded; 512/70914 classes, 1746/74683 objects; 72936 larger objects untested)]

```json
{
 "n_fill": 52,
 "bytes_fill": 304096,
 "n_present": 74683,
 "bytes_present": 20999206150,
 "share_pct": 0.001448,
 "method": "etag-class (every object <= 6263 B decoded; 512/70914 classes, 1746/74683 objects; 72936 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0343P/representations/predictions/surfaces/20260304131111-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

48 of 3690 present chunks are entirely fill_value (0), costing 280704 stored bytes (0.072% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 16763 B decoded; 512/3207 classes, 888/3690 objects; 2802 larger objects untested)]

```json
{
 "n_fill": 48,
 "bytes_fill": 280704,
 "n_present": 3690,
 "bytes_present": 387987232,
 "share_pct": 0.072349,
 "method": "etag-class (every object <= 16763 B decoded; 512/3207 classes, 888/3690 objects; 2802 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0813/representations/predictions/surfaces/20250821151723-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

46 of 51125 present chunks are entirely fill_value (0), costing 269008 stored bytes (0.002% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6577 B decoded; 512/49004 classes, 1016/51125 objects; 50109 larger objects untested)]

```json
{
 "n_fill": 46,
 "bytes_fill": 269008,
 "n_present": 51125,
 "bytes_present": 17445393823,
 "share_pct": 0.001542,
 "method": "etag-class (every object <= 6577 B decoded; 512/49004 classes, 1016/51125 objects; 50109 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0814/representations/predictions/surfaces/20260309142202-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

44 of 35260 present chunks are entirely fill_value (0), costing 257312 stored bytes (0.002% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 7116 B decoded; 512/33609 classes, 714/35260 objects; 34546 larger objects untested)]

```json
{
 "n_fill": 44,
 "bytes_fill": 257312,
 "n_present": 35260,
 "bytes_present": 11240024794,
 "share_pct": 0.002289,
 "method": "etag-class (every object <= 7116 B decoded; 512/33609 classes, 714/35260 objects; 34546 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0332/representations/predictions/surfaces/20251211183505-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

41 of 7986 present chunks are entirely fill_value (0), costing 239768 stored bytes (0.013% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 15684 B decoded; 512/7219 classes, 878/7986 objects; 7108 larger objects untested)]

```json
{
 "n_fill": 41,
 "bytes_fill": 239768,
 "n_present": 7986,
 "bytes_present": 1776117808,
 "share_pct": 0.0135,
 "method": "etag-class (every object <= 15684 B decoded; 512/7219 classes, 878/7986 objects; 7108 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1203/representations/predictions/surfaces/20260319130212-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

20 of 7830 present chunks are entirely fill_value (0), costing 116960 stored bytes (0.004% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 15910 B decoded; 512/7465 classes, 711/7830 objects; 7119 larger objects untested)]

```json
{
 "n_fill": 20,
 "bytes_fill": 116960,
 "n_present": 7830,
 "bytes_present": 2671588338,
 "share_pct": 0.004378,
 "method": "etag-class (every object <= 15910 B decoded; 512/7465 classes, 711/7830 objects; 7119 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc1299/representations/predictions/surfaces/20260309130042-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

14 of 11607 present chunks are entirely fill_value (0), costing 81872 stored bytes (0.003% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 14456 B decoded; 512/10623 classes, 697/11607 objects; 10910 larger objects untested)]

```json
{
 "n_fill": 14,
 "bytes_fill": 81872,
 "n_present": 11607,
 "bytes_present": 3272808766,
 "share_pct": 0.002502,
 "method": "etag-class (every object <= 14456 B decoded; 512/10623 classes, 697/11607 objects; 10910 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHercMAN5/representations/predictions/surfaces/20260311104824-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

14 of 6540 present chunks are entirely fill_value (0), costing 81872 stored bytes (0.006% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 16536 B decoded; 512/5942 classes, 867/6540 objects; 5673 larger objects untested)]

```json
{
 "n_fill": 14,
 "bytes_fill": 81872,
 "n_present": 6540,
 "bytes_present": 1289791699,
 "share_pct": 0.006348,
 "method": "etag-class (every object <= 16536 B decoded; 512/5942 classes, 867/6540 objects; 5673 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0814/representations/predictions/surfaces/20250804134230-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

12 of 37245 present chunks are entirely fill_value (0), costing 70176 stored bytes (0.001% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 6897 B decoded; 512/35841 classes, 678/37245 objects; 36567 larger objects untested)]

```json
{
 "n_fill": 12,
 "bytes_fill": 70176,
 "n_present": 37245,
 "bytes_present": 11707361280,
 "share_pct": 0.000599,
 "method": "etag-class (every object <= 6897 B decoded; 512/35841 classes, 678/37245 objects; 36567 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0846A/representations/predictions/surfaces/20260319102732-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

9 of 12416 present chunks are entirely fill_value (0), costing 52632 stored bytes (0.001% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 11567 B decoded; 512/11716 classes, 983/12416 objects; 11433 larger objects untested)]

```json
{
 "n_fill": 9,
 "bytes_fill": 52632,
 "n_present": 12416,
 "bytes_present": 3691363286,
 "share_pct": 0.001426,
 "method": "etag-class (every object <= 11567 B decoded; 512/11716 classes, 983/12416 objects; 11433 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0500P2/representations/predictions/surfaces/20250526151718-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

6 of 3770 present chunks are entirely fill_value (0), costing 35088 stored bytes (0.010% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 13841 B decoded; 512/3362 classes, 830/3770 objects; 2940 larger objects untested)]

```json
{
 "n_fill": 6,
 "bytes_fill": 35088,
 "n_present": 3770,
 "bytes_present": 345771500,
 "share_pct": 0.010148,
 "method": "etag-class (every object <= 13841 B decoded; 512/3362 classes, 830/3770 objects; 2940 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0841/representations/predictions/surfaces/20260319124803-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

2 of 9356 present chunks are entirely fill_value (0), costing 11696 stored bytes (0.000% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 21453 B decoded; 512/9104 classes, 592/9356 objects; 8764 larger objects untested)]

```json
{
 "n_fill": 2,
 "bytes_fill": 11696,
 "n_present": 9356,
 "bytes_present": 3176651462,
 "share_pct": 0.000368,
 "method": "etag-class (every object <= 21453 B decoded; 512/9104 classes, 592/9356 objects; 8764 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0009B/representations/predictions/surfaces/20260319104112-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

2 of 6736 present chunks are entirely fill_value (0), costing 11696 stored bytes (0.001% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 9154 B decoded; 512/6047 classes, 1066/6736 objects; 5670 larger objects untested)]

```json
{
 "n_fill": 2,
 "bytes_fill": 11696,
 "n_present": 6736,
 "bytes_present": 1047330181,
 "share_pct": 0.001117,
 "method": "etag-class (every object <= 9154 B decoded; 512/6047 classes, 1066/6736 objects; 5670 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHerc0500P2/representations/predictions/surfaces/20250820143440-surface-20260413222639-surface-m7-L0-th0.2.zarr/` level `0`

1 of 3439 present chunks are entirely fill_value (0), costing 5848 stored bytes (0.001% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 13648 B decoded; 512/3138 classes, 751/3439 objects; 2688 larger objects untested)]

```json
{
 "n_fill": 1,
 "bytes_fill": 5848,
 "n_present": 3439,
 "bytes_present": 421120698,
 "share_pct": 0.001389,
 "method": "etag-class (every object <= 13648 B decoded; 512/3138 classes, 751/3439 objects; 2688 larger objects untested)"
}
```

### `https://vesuvius-challenge-open-data.s3.amazonaws.com/PHercMANBp/representations/predictions/surfaces/20251216152116-surface-20260413222639-surface-m7-L2-th0.2.zarr/` level `0`

1 of 1140 present chunks are entirely fill_value (0), costing 5848 stored bytes (0.008% of this level). Zarr omits all-fill chunks, so these carry no information a reader could not derive from their absence [etag-class (every object <= 36436 B decoded; 512/1047 classes, 588/1140 objects; 552 larger objects untested)]

```json
{
 "n_fill": 1,
 "bytes_fill": 5848,
 "n_present": 1140,
 "bytes_present": 72958224,
 "share_pct": 0.008016,
 "method": "etag-class (every object <= 36436 B decoded; 512/1047 classes, 588/1140 objects; 552 larger objects untested)"
}
```

## Coverage and honesty

- **Exhaustive**: 129,776,533 chunks (247.53 TiB). Uncompressed, single-part
  objects on S3, every one classified by comparing its ETag against the MD5 of
  an all-fill chunk. 0 all-fill chunks were found on this path.
- **Bounded by a size ceiling**: 122,340 chunks (7.52 GiB). Compressed
  stores, where one representative of each byte-identical ETag class was
  downloaded and decoded, smallest class first. 4,166,828 objects sit above the
  per-level ceiling and were not decoded. 3,144 of the 3,144
  all-fill chunks reported came from this path, so that part of the count is a
  floor, not a census.
- **Sampled**: 7 stores (1,843,333 chunks, 3.52 TiB) on the
  `https://data.aws.ash2txt.org` access root, which publishes no content hash.
  Their key sets and byte totals are in the population figures; their sampled
  fill counts are **not** included in any all-fill total.
- **Not classifiable**: 555 chunks carry a multipart ETag, which is
  the MD5 of the part hashes rather than of the object.
- 0 store(s) could not be inventoried.

Every store in the catalogue was inventoried.

## Other advisories

- `all_fill`: 28 finding(s)
- `duplicate_content`: 71 finding(s)
- `foreign_key`: 22 finding(s)
- `multipart_etag`: 1 finding(s)
- `pyramid_cost`: 2 finding(s)
- `replica_agreement`: 3 finding(s)

## Reader test (added after review)

The `chunk_size` finding was originally inferred from object sizes. It has now
been demonstrated with a real reader. `tools/reader_test.py` downloads one
anomalous chunk, places it in a minimal local store carrying the published
`.zarray`, and reads it with zarr.

Result, zarr 3.3.0, chunk `14/9/13`, 16,777,216 bytes where 2,097,152 expected:

```
ValueError: cannot reshape array of size 16777216 into shape (128,128,128)
```

With `--sample 10`, ten anomalous objects were downloaded at random (eight
16 MB, two 128 MB). None is all-zero; non-zero byte counts ranged from 16,674 to
14,722,166. That is a sample of ten, not a census of all 555, and the claim is
bounded accordingly. The full level-0 listing confirms exactly 499 objects at
16 MB and 56 at 128 MB.
