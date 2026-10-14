"""Purge one store's products from the DB without removing it from config.

The dashboard's Remove Store refuses configured stores (they would be re-added
on the next scrape), which is right for deleting a store but not for clearing
stale rows left over from before an ``exclude_terms`` filter existed. This
deletes the store's seen_deals, weekly snapshots, summaries, logo and
known_stores entry; the store stays in config.yaml and is re-scraped clean on
the next run, so a filter added since then finally takes effect.

Usage (inside the app container, from the project root)::

    python maintenance/clear_store.py zumiez-420 [more-store-ids ...]
"""

import os
import sys

# Allow running as a plain script (python maintenance/clear_store.py) from any
# working directory by putting the project root on the import path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.sqlite import SQLiteStorage


def clear_store(storage, store_ids):
    """Delete each store's data; return {store_id: (products_removed, ok)}.

    A failure on one store is reported (ok=False) rather than raised, so a
    single bad id does not abort the rest of the batch.
    """
    results = {}
    for store_id in store_ids:
        try:
            count = storage.count_store_products(store_id)
            ok = storage.delete_store_data(store_id)
        except Exception:
            results[store_id] = (0, False)
            continue
        results[store_id] = (count, ok)
    return results


def main(argv):
    store_ids = argv[1:]
    if not store_ids:
        print(__doc__)
        return 2
    storage = SQLiteStorage()
    results = clear_store(storage, store_ids)
    ok = True
    for store_id, (count, success) in results.items():
        ok = ok and success
        print(f"{store_id}: removed {count} products -> {'ok' if success else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
