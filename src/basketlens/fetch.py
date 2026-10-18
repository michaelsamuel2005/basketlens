"""Download the Complete Journey files (CC0, 84.51 degrees, via the `completejourney` R package v1.1.1).

Files come from raw.githubusercontent.com/bradleyboehmke/completejourney. Nothing here is Nectar or Sainsbury's data.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/bradleyboehmke/completejourney/master/data/"
FILES = ["transactions.rds", "promotions.rds", "products.rda", "demographics.rda", "campaigns.rda",
         "campaign_descriptions.rda", "coupons.rda", "coupon_redemptions.rda"]


def fetch(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for f in FILES:
        p = dest / f
        if not p.exists():
            print(f"downloading {f} ...", file=sys.stderr)
            urllib.request.urlretrieve(BASE + f, p)
        out.append(p)
    return out


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


if __name__ == "__main__":
    for p in fetch(Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")):
        print(p.name, p.stat().st_size, sha256(p)[:16])
