"""Item catalogue and price statistics, cached so each is downloaded once instead of on every call."""
import json
import re
import threading
import time
from pathlib import Path

from . import client

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
ITEMS_CACHE = CACHE_DIR / "items.json"
ITEMS_TTL = 24 * 3600   # the item list changes only when the game adds items
STATS_TTL = 5 * 60      # the hourly/daily averages

SLUG_RE = re.compile(r"[a-z0-9_]+")

_lock = threading.Lock()
_items = None
_items_loaded_at = 0.0
_stats = None
_stats_loaded_at = 0.0


def item_name(item):
    return (item.get("i18n", {}).get("en", {}).get("name")
            or item["slug"].replace("_", " ").title())


def is_set(item):
    return "set" in item.get("tags", []) or item["slug"].endswith("_set")


def _read_disk_cache():
    try:
        cached = json.loads(ITEMS_CACHE.read_text(encoding="utf-8"))
        return cached["saved_at"], cached["items"]
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0, None


def get_items(force=False):
    """All tradable items. Memory cache -> disk cache (24h) -> network. Falls back to a stale cache offline."""
    global _items, _items_loaded_at
    with _lock:
        now = time.time()
        if _items is not None and not force and now - _items_loaded_at < ITEMS_TTL:
            return _items

        saved_at, disk_items = _read_disk_cache()
        if disk_items and not force and now - saved_at < ITEMS_TTL:
            _items, _items_loaded_at = disk_items, saved_at
            return _items

        try:
            items = client.get(f"{client.API_V2}/items")["data"]
        except (client.WfmError, KeyError, TypeError):
            if disk_items:          # offline: an old list is better than none
                _items, _items_loaded_at = disk_items, now
                return _items
            raise
        _items, _items_loaded_at = items, now
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            ITEMS_CACHE.write_text(json.dumps({"saved_at": now, "items": items}), encoding="utf-8")
        except OSError:
            pass                    # the cache is only an optimisation
        return _items


def items_by_id():
    return {item["id"]: item for item in get_items()}


def prime_items(include_sets=False):
    """Prime items, sorted by name."""
    result = [
        item for item in get_items()
        if "prime" in item.get("tags", []) and (include_sets or not is_set(item))
    ]
    return sorted(result, key=item_name)


def to_slug(text):
    """Turn what the user typed ('Akstiletto Prime Barrel') into a validated slug."""
    slug = re.sub(r"[\s\-]+", "_", text.strip().lower())
    slug = slug.replace("&", "and").replace("'", "").replace(".", "")
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"'{text}' is not a valid item name.")
    return slug


def find_item(text):
    """Resolve a typed name or slug to an item: exact name, exact slug, then unique partial match."""
    wanted = " ".join(text.strip().lower().split())
    if not wanted:
        raise ValueError("Enter an item name.")
    items = get_items()
    for item in items:
        if item_name(item).lower() == wanted or item["slug"] == wanted:
            return item
    try:
        slug = to_slug(text)
    except ValueError:
        slug = None
    if slug:
        for item in items:
            if item["slug"] == slug:
                return item
    partial = [item for item in items if wanted in item_name(item).lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        examples = ", ".join(item_name(i) for i in partial[:5])
        raise ValueError(f"'{text}' matches {len(partial)} items (e.g. {examples}). Be more specific.")
    raise ValueError(f"No item named '{text}'.")


def get_stats(force=False):
    """warframe.market weighted-average prices. Returns {'day': {item_id: row}, 'hour': {item_id: row}}."""
    global _stats, _stats_loaded_at
    with _lock:
        now = time.time()
        if _stats is not None and not force and now - _stats_loaded_at < STATS_TTL:
            return _stats
    try:
        payload = client.get(f"{client.API_V1}/tools/ducats")["payload"]
        stats = {
            "day": {row["item"]: row for row in payload.get("previous_day", [])},
            "hour": {row["item"]: row for row in payload.get("previous_hour", [])},
        }
    except (KeyError, TypeError) as exc:
        raise client.WfmError("Unexpected price statistics format from warframe.market.") from exc
    with _lock:
        _stats, _stats_loaded_at = stats, time.time()
    return stats
