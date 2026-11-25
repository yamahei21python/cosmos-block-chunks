#!/usr/bin/env python3
"""Fetch raw block data and emit gz + manifest."""
import argparse
import base64
import gzip
import hashlib
import json
import os
import urllib.request

CHAIN = "cosmos"


def get_json(url, timeout=45):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def post_json(url, payload, timeout=45):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.load(r)
    if isinstance(obj, dict) and "error" in obj:
        raise RuntimeError(str(obj["error"]))
    return obj["result"]


def canon(value):
    """Make msgpack-decoded values JSON-safe (bytes -> str/base64)."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return {"__base64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {canon(k) if not isinstance(k, str) else k: canon(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canon(v) for v in value]
    if isinstance(value, tuple):
        return [canon(v) for v in value]
    return value



BASE = "https://cosmos-rest.publicnode.com/cosmos/base/tendermint/v1beta1/blocks/"


def fetch(height):
    doc = get_json(BASE + str(height))
    raw_txs = (doc.get("block", {}).get("data", {}).get("txs") or [])
    txs = []
    for i, b64 in enumerate(raw_txs):
        try:
            decoded = json.loads(base64.b64decode(b64).decode("utf-8"))
        except Exception:
            decoded = None
        txs.append({"index": i, "tx_bytes_b64": b64, "decoded": decoded})
    block = dict(doc.get("block", {}))
    block["data"] = {"tx_count": len(raw_txs)}
    return {"height": height, "block_id": doc.get("block_id"), "block": block, "txs": txs, "_tx_count": len(txs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.first < 0 or args.count < 1 or args.count > 100:
        raise SystemExit("invalid first/count")
    first, last = args.first, args.first + args.count - 1
    blocks = []
    tx_count = 0
    for h in range(first, last + 1):
        rec = fetch(h)
        tx_count += rec.pop("_tx_count", 0)
        blocks.append(rec)
    payload = {
        "chain": CHAIN,
        "first": first,
        "last": last,
        "block_count": len(blocks),
        "tx_count": tx_count,
        "blocks": blocks,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    gz_path = args.out + ".gz"
    with gzip.GzipFile(filename=gz_path, mode="wb", mtime=0) as f:
        f.write(raw)
    with open(gz_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    manifest = {
        "first": first,
        "last": last,
        "block_count": len(blocks),
        "tx_count": tx_count,
        "bytes": os.path.getsize(gz_path),
        "sha256": digest,
    }
    with open(args.out + ".manifest.json", "w") as f:
        json.dump(manifest, f, sort_keys=True)
        f.write("\n")
    print("MANIFEST " + json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
