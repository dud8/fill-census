#!/usr/bin/env python3
"""Reproduce the chunk_size finding with a real Zarr reader.

Downloads one anomalous level-0 chunk from the affected volume, places it in a
minimal local store carrying the published .zarray, and reads it with zarr.
The finding is that the read raises; this script demonstrates it rather than
asserting it. Read-only against the bucket. Requires: numpy, zarr.

    python3 tools/reader_test.py            # default: the first 16 MB chunk found
    python3 tools/reader_test.py --sample 10  # also download N random anomalous chunks and count all-zero
"""
import argparse, json, pathlib, random, tempfile, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
import numpy as np

B = "https://vesuvius-challenge-open-data.s3.amazonaws.com"
P = "PHerc0343P/volumes/20250521134555-8.640um-1.2m-116keV-masked.zarr"
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
EXPECT = 2097152


def list_level0():
    keys, tok = [], None
    while True:
        u = f"{B}/?list-type=2&prefix={urllib.parse.quote(P + '/0/')}&max-keys=1000"
        if tok:
            u += "&continuation-token=" + urllib.parse.quote(tok)
        x = ET.fromstring(urllib.request.urlopen(u, timeout=60).read())
        for c in x.findall("s:Contents", NS):
            keys.append((c.find("s:Key", NS).text, int(c.find("s:Size", NS).text)))
        t = x.find("s:NextContinuationToken", NS)
        if t is None:
            return keys
        tok = t.text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    a = ap.parse_args()
    keys = list_level0()
    anom = [(k, s) for k, s in keys if s in (16777216, 134217728)]
    print(f"level-0 objects: {len(keys)}; anomalous: {len(anom)} "
          f"({sum(1 for _, s in anom if s == 16777216)} x 16 MB, "
          f"{sum(1 for _, s in anom if s == 134217728)} x 128 MB)")

    za = json.load(urllib.request.urlopen(f"{B}/{P}/0/.zarray", timeout=40))
    assert za["chunks"] == [128, 128, 128] and za["dtype"] == "|u1"

    if a.sample:
        random.seed(7)
        allzero = 0
        for k, s in random.sample(anom, min(a.sample, len(anom))):
            raw = urllib.request.urlopen(f"{B}/{k}", timeout=400).read()
            arr = np.frombuffer(raw, dtype=np.uint8)
            nz = int((arr != 0).sum())
            allzero += nz == 0
            print(f"  {k.split('/0/')[1]:12s} {len(raw):>12,} B  nonzero={nz:>11,}  max={int(arr.max())}")
        print(f"all-zero among sampled: {allzero}/{min(a.sample, len(anom))}")

    import zarr
    k, s = anom[0]
    raw = urllib.request.urlopen(f"{B}/{k}", timeout=400).read()
    d = pathlib.Path(tempfile.mkdtemp()) / "s.zarr"
    (d / "0").mkdir(parents=True)
    (d / "0" / ".zarray").write_text(json.dumps(za))
    (d / ".zgroup").write_text('{"zarr_format":2}')
    idx = k.split("/0/")[1]
    tgt = d / "0" / idx
    tgt.parent.mkdir(parents=True, exist_ok=True)
    tgt.write_bytes(raw)
    zi = [int(v) for v in idx.split("/")]
    sl = tuple(slice(i * 128, (i + 1) * 128) for i in zi)
    print(f"\nzarr {zarr.__version__} reading chunk {idx} ({len(raw):,} B, {EXPECT:,} expected):")
    try:
        arr = zarr.open(str(d / "0"), mode="r")[sl]
        print(f"  did NOT raise; returned {arr.shape}")
        return 1
    except Exception as e:
        print(f"  RAISED {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
