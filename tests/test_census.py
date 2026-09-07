"""Self-check: synthetic stores with known defects, plus the parsers.

Run with `python3 -m tests.test_census` (no pytest required).
Every check has at least one KNOWN-BAD case that it must catch and one clean
case it must not flag.
"""
import collections
import hashlib
import sys

sys.path.insert(0, ".")

from fill_census import checks, inventory
from fill_census.inventory import (Entry, _IDX_HREF, _S3_ENTRY, _parse_size,
                                   _index_page, _s3_dir)
from fill_census.zarr2 import Level, root_to_base


def L(path="0", shape=(256, 256, 256), chunks=(128, 128, 128), dtype="|u1",
      fill=0, comp=None, filt=None, sep="/"):
    return Level(path, tuple(shape), tuple(chunks), dtype, fill, comp, filt,
                 "C", sep, None)


# ---------------------------------------------------------------- parsers

def test_root_resolution():
    """Every origin resolves against the root declared beside it, not the bucket."""
    assert root_to_base("s3://vesuvius-challenge-open-data") == \
        "https://vesuvius-challenge-open-data.s3.amazonaws.com"
    assert root_to_base("https://data.aws.ash2txt.org/") == \
        "https://data.aws.ash2txt.org"
    print("  access-root resolution ok")


def test_s3_entry_regex_survives_checksum_elements():
    """S3 interleaves ChecksumAlgorithm/ChecksumType between ETag and Size."""
    xml = ('<Contents><Key>a/0/1/2</Key><LastModified>x</LastModified>'
           '<ETag>&quot;abc&quot;</ETag><ChecksumAlgorithm>CRC64NVME'
           '</ChecksumAlgorithm><ChecksumType>FULL_OBJECT</ChecksumType>'
           '<Size>2097152</Size><StorageClass>STANDARD</StorageClass></Contents>')
    got = _S3_ENTRY.findall(xml)
    assert got == [("a/0/1/2", "abc", "2097152")], got
    plain = ('<Contents><Key>b</Key><LastModified>x</LastModified>'
             '<ETag>&quot;d&quot;</ETag><Size>7</Size></Contents>')
    assert _S3_ENTRY.findall(plain) == [("b", "d", "7")]
    print("  s3 listing parse ok")


def test_autoindex_size_precision():
    """A rounded display size must never be reported as exact."""
    assert _parse_size("235 B") == (235, True)
    assert _parse_size("2.0 MiB") == (2097152, False)
    assert _parse_size("-") == (None, False)
    # KNOWN-BAD: a chunk truncated by 52 bytes still displays as '2.0 MiB'.
    n, exact = _parse_size("2.0 MiB")
    assert n == 2097152 and not exact, "rounded size must be flagged inexact"
    print("  autoindex size precision ok")


def test_autoindex_row_regex():
    row = ('<tr><td class="link"><a href="0/" title="0">0/</a></td>'
           '<td class="size">-</td><td class="date">x</td></tr>'
           '<tr><td class="link"><a href=".zarray" title=".zarray">.zarray</a>'
           '</td><td class="size">235 B</td><td class="date">x</td></tr>')
    assert _IDX_HREF.findall(row) == [("0/", "-"), (".zarray", "235 B")]
    print("  autoindex row parse ok")


# ---------------------------------------------------------------- keys

def test_chunk_key_parsing():
    lv = L(sep="/")
    assert checks.parse_chunk_key("1/2/3", lv, 3) == (1, 2, 3)
    assert checks.parse_chunk_key("1/2", lv, 3) is None        # wrong arity
    assert checks.parse_chunk_key(".zarray", lv, 3) is None
    assert checks.parse_chunk_key("1/2/x", lv, 3) is None      # not an index
    dot = L(sep=".")
    assert checks.parse_chunk_key("1.2.3", dot, 3) == (1, 2, 3)
    print("  chunk key parsing ok")


def test_index_bounds_known_bad():
    """KNOWN-BAD: a key one past the declared grid must be a contract finding."""
    lv = L(shape=(256, 256, 256), chunks=(128, 128, 128))   # grid 2x2x2
    assert lv.n_chunks() == (2, 2, 2)
    assert checks.check_index_bounds(lv, []) == []
    f = checks.check_index_bounds(lv, [(2, 0, 0), (0, 5, 0)])
    assert len(f) == 1 and f[0].severity == "contract", f
    assert f[0].data["n_out_of_range"] == 2 and f[0].data["grid"] == [2, 2, 2]
    print("  index bounds ok")


def test_chunk_size_known_bad():
    """KNOWN-BAD: a short object in an uncompressed store is a truncated write."""
    lv = L()
    assert lv.chunk_nbytes == 2097152
    assert checks.check_chunk_size(lv, {2097152: 40}, False) == []
    f = checks.check_chunk_size(lv, {2097152: 39, 1048576: 1}, False)
    assert len(f) == 1 and f[0].severity == "contract", f
    assert f[0].data["expected_bytes"] == 2097152
    # Same defect seen through a rounded index cannot be asserted: advisory.
    f2 = checks.check_chunk_size(lv, {2097152: 39, 1048576: 1}, True)
    assert f2[0].severity == "advisory", f2
    # An unparseable listing size is a coverage gap, not a wrong size.
    assert checks.check_chunk_size(lv, {2097152: 39, None: 1}, False) == []
    # A compressed level has no fixed size, so nothing is claimed.
    cz = L(comp={"id": "blosc"})
    assert checks.check_chunk_size(cz, {5848: 2, 7360: 9}, False) == []
    print("  chunk size ok")


def test_foreign_keys():
    assert checks.check_foreign_keys("r/", []) == []
    f = checks.check_foreign_keys("r/", ["0/junk.txt"])
    assert f[0].severity == "advisory" and f[0].data["n"] == 1
    print("  foreign keys ok")


# ---------------------------------------------------------------- fill

def test_fill_md5_matches_real_zero_bytes():
    """The analytic all-fill hash must equal the MD5 of the actual bytes."""
    lv = L(chunks=(4, 4, 4))                       # 64 bytes
    assert lv.chunk_nbytes == 64
    assert checks.fill_md5(lv) == hashlib.md5(b"\x00" * 64).hexdigest()
    nz = L(chunks=(4, 4, 4), fill=7)
    assert checks.fill_md5(nz) == hashlib.md5(bytes([7]) * 64).hexdigest()
    # KNOWN-BAD: a chunk of a different constant must not match.
    assert checks.fill_md5(lv) != hashlib.md5(bytes([1]) * 64).hexdigest()
    # Real 128^3 uint8 all-zero chunk, the value the census keys off.
    big = L()
    assert checks.fill_md5(big) == "b2d1236c286a3c0704224fe4105eca49"
    print("  fill md5 ok")


def test_fill_bytes_honours_dtype_and_undeclared_fills():
    """The fill pattern comes from the dtype, and is refused when undeclared."""
    assert checks.fill_bytes(L(chunks=(2, 2, 2))) == b"\x00" * 8
    assert checks.fill_bytes(L(chunks=(2, 2, 2), fill=7)) == bytes([7]) * 8
    # KNOWN-BAD: a 2-byte dtype must not be filled a byte at a time. 258 is
    # 0x0102, so the pattern differs between big and little endian and a
    # bytes([fill]) shortcut would be silently wrong for both.
    be = L(chunks=(2, 2, 2), dtype=">u2", fill=258)
    le = L(chunks=(2, 2, 2), dtype="<u2", fill=258)
    assert checks.fill_bytes(be) == b"\x01\x02" * 8
    assert checks.fill_bytes(le) == b"\x02\x01" * 8
    assert checks.fill_bytes(be) != bytes([258 & 0xFF]) * 16
    # A signed fill wraps to its stored byte rather than raising.
    assert checks.fill_bytes(L(chunks=(2, 2, 2), dtype="|i1", fill=-1)) == b"\xff" * 8
    # No usable pattern: null fill, and the JSON spellings of non-finite floats.
    for bad in (None, "NaN", "Infinity", "-Infinity"):
        lv = L(chunks=(2, 2, 2), dtype="<f4", fill=bad)
        assert checks.fill_bytes(lv) is None, bad
        assert checks.fill_md5(lv) is None, bad
    print("  fill bytes ok")


def test_multipart_etag_is_not_an_md5():
    """KNOWN-BAD: a multipart ETag is the MD5 of the part hashes, not the object."""
    assert not checks.is_multipart_etag("b2d1236c286a3c0704224fe4105eca49")
    assert not checks.is_multipart_etag(None)
    assert checks.is_multipart_etag("9e3ab5ec5a16c61cc90bef1c8d009d70-16")
    lv = L()
    assert checks.check_multipart_etags(lv, 0, 100) == []
    f = checks.check_multipart_etags(lv, 555, 8543)
    assert len(f) == 1 and f[0].severity == "advisory", f
    assert f[0].data["n_multipart"] == 555
    print("  multipart etag ok")


def test_delimiter_listing_follows_its_own_pagination():
    """KNOWN-BAD: a delimiter listing is a token chain like any other.

    Stopping at its first page drops every object that sits beside a
    sub-prefix on page two, and the census would under-count them silently.
    """
    pages = [
        ('<Contents><Key>r/a</Key><ETag>&quot;e1&quot;</ETag><Size>1</Size>'
         '</Contents><CommonPrefixes><Prefix>r/0/</Prefix></CommonPrefixes>'
         '<NextContinuationToken>t1</NextContinuationToken>'),
        ('<Contents><Key>r/b</Key><ETag>&quot;e2&quot;</ETag><Size>2</Size>'
         '</Contents><CommonPrefixes><Prefix>r/1/</Prefix></CommonPrefixes>'),
    ]
    calls = []
    real = inventory.fetch
    inventory.fetch = lambda url, **kw: (calls.append(url),
                                         pages[len(calls) - 1].encode())[1]
    try:
        files, dirs = _s3_dir("https://host", "r/")
    finally:
        inventory.fetch = real
    assert [e.key for e in files] == ["r/a", "r/b"], files
    assert dirs == ["r/0/", "r/1/"], dirs
    assert len(calls) == 2 and "continuation-token=t1" in calls[1], calls
    print("  delimiter pagination ok")


def test_all_fill_reporting():
    lv = L()
    assert checks.check_all_fill(lv, 0, 0, 100, 209715200, "etag-md5") == []
    f = checks.check_all_fill(lv, 3, 6291456, 100, 209715200, "etag-md5")
    assert len(f) == 1 and f[0].severity == "advisory", f   # legal Zarr, not a violation
    assert f[0].data["bytes_fill"] == 6291456
    assert abs(f[0].data["share_pct"] - 3.0) < 1e-6, f[0].data
    print("  all-fill reporting ok")


def test_pyramid_cost():
    a, b = L("0", (256, 256, 256)), L("1", (128, 128, 128))
    per = {"0": {"bytes_present": 8_000_000}, "1": {"bytes_present": 1_000_000}}
    assert checks.check_pyramid_cost([a, b], per) == []      # exactly 1/8
    # KNOWN-BAD: child costs as much as its parent despite 8x fewer voxels.
    per["1"]["bytes_present"] = 8_000_000
    f = checks.check_pyramid_cost([a, b], per)
    assert len(f) == 1 and f[0].severity == "advisory", f
    assert abs(f[0].data["geometric_ratio"] - 0.125) < 1e-9
    print("  pyramid cost ok")


def test_replica_agreement_known_bad():
    """KNOWN-BAD: two access roots for one volume presenting different keys."""
    a = {"0/1/2/3", "0/1/2/4"}
    assert checks.check_replica_agreement("v", "s3://x", a, "https://y", set(a)) == []
    f = checks.check_replica_agreement("v", "s3://x", a, "https://y", {"0/1/2/3"})
    assert len(f) == 1 and f[0].severity == "contract", f
    assert f[0].data["only_a"] == 1 and f[0].data["only_b"] == 0
    print("  replica agreement ok")


def test_duplicate_content():
    assert checks.check_duplicate_content("r/", 10, 10, 100, 100) == []
    f = checks.check_duplicate_content("r/", 10, 7, 100, 70)
    assert f[0].severity == "advisory" and f[0].data["n_distinct"] == 7
    print("  duplicate content ok")


def test_occupancy_arithmetic():
    """A level's grid is ceil(shape/chunks) on every axis, including odd extents."""
    lv = L(shape=(11173, 3340, 3440), chunks=(128, 128, 128))
    assert lv.n_chunks() == (88, 27, 27), lv.n_chunks()
    assert lv.chunk_nbytes == 2097152
    print("  occupancy arithmetic ok")


def test_catalog_blocks_are_stores_not_volumes():
    """KNOWN-BAD: two surface-prediction stores on one volume are different
    stores, and must not be compared against each other as replicas.

    Origins WITHIN one `data` block are alternate locations of one store; two
    `data` blocks of the same type on one volume are two different stores.
    Grouping by (sample, volume, kind) merges them and invents a replica
    disagreement out of two unrelated models.
    """
    import json, os, tempfile
    from fill_census.__main__ import load_catalog
    cat = {"samples": {"S": {"volumes": {"V": {"long_id": "V.zarr", "data": [
        {"type": "surface-prediction-zarr", "origins": [
            {"path": "a/", "access_roots": [{"url": "s3://b"}]}]},
        {"type": "surface-prediction-zarr", "origins": [
            {"path": "c/", "access_roots": [{"url": "s3://b"}]}]},
        {"type": "ome-zarr", "origins": [
            {"path": "d/", "access_roots": [{"url": "s3://b"}]},
            {"path": "e/", "access_roots": [{"url": "https://h"}]}]},
    ]}}}}, "models": {}}
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(cat, fh)
    try:
        got = load_catalog(path, ("surface-prediction-zarr", "ome-zarr"))
    finally:
        os.unlink(path)
    blocks = collections.Counter(x["block"] for x in got)
    assert len(got) == 4, got
    assert len(blocks) == 3, blocks                  # 3 stores, not 2
    rep = [b for b, n in blocks.items() if n > 1]
    assert len(rep) == 1, rep                        # only the two-origin block
    pair = [x for x in got if x["block"] == rep[0]]
    assert {x["root"] for x in pair} == {"d/", "e/"}, pair
    assert {x["base"] for x in pair} == {"https://b.s3.amazonaws.com",
                                         "https://h"}, pair
    print("  catalogue block grouping ok")


def run():
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
        except AssertionError as e:
            fails += 1
            print(f"  FAIL {name}: {e}")
    print("FAILURES" if fails else "all self-checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
