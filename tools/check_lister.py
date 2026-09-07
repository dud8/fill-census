#!/usr/bin/env python3
"""Cross-check the sharded lister against a plain serial ListObjectsV2 walk.

The census counts every object exactly once, so the parallel prefix expansion
must neither drop a key nor return one twice. This compares it against the
simplest possible implementation on whatever prefixes are given.

  python3 tools/check_lister.py <prefix> [<prefix> ...]
"""
import collections
import sys

sys.path.insert(0, ".")

from fill_census.inventory import _s3_walk, list_s3
from fill_census.zarr2 import BUCKET


def main(prefixes):
    bad = 0
    for p in prefixes:
        fast = list_s3(BUCKET, p)
        slow = _s3_walk(BUCKET, p)
        kf = collections.Counter(e.key for e in fast)
        ks = collections.Counter(e.key for e in slow)
        dup = [k for k, n in kf.items() if n > 1]
        bf = sum(e.size for e in fast)
        bs = sum(e.size for e in slow)
        same = kf == ks and bf == bs and not dup
        bad += not same
        print(f"{'ok  ' if same else 'FAIL'} {p}: sharded {len(fast)} objects "
              f"{bf} B / serial {len(slow)} objects {bs} B; "
              f"missing {len(set(ks) - set(kf))}, extra {len(set(kf) - set(ks))}, "
              f"duplicated {len(dup)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
