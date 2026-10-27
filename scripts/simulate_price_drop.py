#!/usr/bin/env python3
"""Lower one seed listing's price so the next scan shows a price drop (Person C).

    python scripts/simulate_price_drop.py --list
    python scripts/simulate_price_drop.py --listing-id mu-schwabing-01 --drop 100000
    python scripts/simulate_price_drop.py --restore     # put the original prices back

Only the price number of that listing is rewritten, so the file keeps its format and the git
diff is one line. The original file is saved once to the system temp dir for --restore.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_listings.json"
BACKUP = Path(tempfile.gettempdir()) / "munich_seed_listings.orig.json"


def drop_price(text: str, listing_id: str, drop: float | None, pct: float | None) -> tuple[str, float, float]:
    """Return (new_text, old_price, new_price). Raises KeyError if the listing is unknown."""
    listing = next((x for x in json.loads(text) if x["listing_id"] == listing_id), None)
    if listing is None:
        raise KeyError(listing_id)
    old = float(listing["price"])
    new = round(old - drop) if drop else round(old * (1 - pct / 100))
    if new <= 0 or new >= old:
        raise ValueError(f"new price {new} must be positive and below the current {old:.0f}")

    pattern = re.compile(rf'("listing_id":\s*"{re.escape(listing_id)}"[^\n]*?"price":\s*)\d+(\.\d+)?')
    new_text, n = pattern.subn(lambda m: f"{m.group(1)}{new}", text, count=1)
    if n != 1:  # pretty-printed or reordered file: fall back to a full rewrite
        data = json.loads(text)
        next(x for x in data if x["listing_id"] == listing_id)["price"] = new
        new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return new_text, old, float(new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show listing ids and prices")
    ap.add_argument("--restore", action="store_true", help="restore the original seed file")
    ap.add_argument("--listing-id", default="mu-schwabing-01")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--drop", type=float, help="absolute drop in EUR (default 100000)")
    group.add_argument("--pct", type=float, help="drop in percent")
    args = ap.parse_args()

    if args.restore:
        if not BACKUP.exists():
            print("Nothing to restore (no backup found).")
            return 1
        shutil.copyfile(BACKUP, SEED)
        BACKUP.unlink()
        print("Restored original seed_listings.json")
        return 0

    text = SEED.read_text(encoding="utf-8")
    if args.list:
        for x in json.loads(text):
            print(f"{x['listing_id']:<22} EUR {x['price']:>10,.0f}  {x['title']}")
        return 0

    if not BACKUP.exists():
        BACKUP.write_text(text, encoding="utf-8")
    try:
        drop = args.drop if args.drop or args.pct else 100_000
        new_text, old, new = drop_price(text, args.listing_id, drop, args.pct)
    except KeyError:
        print(f"Unknown listing id {args.listing_id!r}; use --list")
        return 1
    except ValueError as exc:
        print(exc)
        return 1
    SEED.write_text(new_text, encoding="utf-8")
    print(f"{args.listing_id}: EUR {old:,.0f} -> EUR {new:,.0f} (drop EUR {old - new:,.0f})")
    print("Now run the scan again; use --restore afterwards.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
