#!/usr/bin/env python3
"""Packs out/samples.jsonl into one file to send to Andrew:
    python3 pack.py <your-first-name>   ->  out/opus55-<name>-<date>.jsonl.gz
Checks every line, drops duplicates and prints what is inside."""
import collections
import datetime as dt
import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = HERE / "out" / "samples.jsonl"
if not src.exists():
    sys.exit("No out/samples.jsonl yet: run python3 collect.py first.")
name = re.sub(r"[^a-z0-9]+", "-", (sys.argv[1] if len(sys.argv) > 1 else "friend").lower()).strip("-") or "friend"
rows, seen = [], set()
for line in src.open():
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if r.get("text") and r.get("id") not in seen:
        seen.add(r["id"])
        rows.append({**r, "contributor": name})
dst = HERE / "out" / f"opus55-{name}-{dt.date.today()}.jsonl.gz"
with gzip.open(dst, "wt") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{len(rows)} samples -> {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
print(dict(collections.Counter(r["kind"] for r in rows)))
print("Send this file to Andrew (email, Google Drive, Dropbox, AirDrop...).")
