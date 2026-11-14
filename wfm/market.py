"""Public market data: order books, top prices, per-item averages. Returns data; never prints."""
from datetime import datetime, timedelta, timezone

from . import catalog, client

RECENT_DAYS = 30


def parse_time(value):
    """'2026-01-10T14:04:39Z' -> aware datetime (None when missing or malformed)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def fetch_orders(slug):
    """Raw order list for one item. The slug is validated because it becomes part of the URL."""
    if not catalog.SLUG_RE.fullmatch(slug):
        raise ValueError(f"'{slug}' is not a valid item slug.")
    try:
        return client.get(f"{client.API_V2}/orders/item/{slug}")["data"]
    except (KeyError, TypeError) as exc:
        raise client.WfmError("Unexpected order format from warframe.market.") from exc


def _row(order):
    user = order.get("user") or {}
    return {
        "user": user.get("ingameName", "?"),
        "status": user.get("status", "offline"),
        "platinum": order.get("platinum", 0),
        "quantity": order.get("quantity", 1),
        "rank": order.get("rank"),
        "subtype": order.get("subtype"),
        "created": parse_time(order.get("createdAt")),
        "updated": parse_time(order.get("updatedAt")),
    }


def list_orders(slug, order_type="sell", limit=10):
    """Order book for one item, grouped by seller status and sorted by best price first.

    Offline orders are kept only if created or updated in the last RECENT_DAYS days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    rows = [
        _row(o) for o in fetch_orders(slug)
        if o.get("type") == order_type and o.get("visible", True)
    ]
    rows.sort(key=lambda r: r["platinum"], reverse=(order_type == "buy"))

    groups = {"ingame": [], "online": [], "offline": []}
    for row in rows:
        status = row["status"] if row["status"] in groups else "offline"
        if status == "offline":
            latest = max((t for t in (row["created"], row["updated"]) if t), default=None)
            if latest is None or latest < cutoff:
                continue
        if len(groups[status]) < limit:
            groups[status].append(row)
    return groups


def top_prices(period="day", kind="components", min_price=0, limit=None):
    """Items ranked by warframe.market average price.

    period: 'day' or 'hour'.  kind: 'sets', 'components' or 'all'.
    """
    by_id = catalog.items_by_id()
    rows = []
    for item_id, stat in catalog.get_stats()[period].items():
        item = by_id.get(item_id)
        if item is None:
            continue
        item_is_set = catalog.is_set(item)
        if (kind == "sets" and not item_is_set) or (kind == "components" and item_is_set):
            continue
        price = stat.get("wa_price") or 0
        if price < min_price:
            continue
        rows.append({
            "name": catalog.item_name(item),
            "slug": item["slug"],
            "wa_price": price,
            "ducats": stat.get("ducats"),
            "volume": stat.get("volume"),
        })
    rows.sort(key=lambda r: r["wa_price"], reverse=True)
    return rows[:limit] if limit else rows


def average_price(item):
    """Daily and hourly average for one catalogue item: {'day': price|None, 'hour': price|None}."""
    stats = catalog.get_stats()
    return {
        period: (stats[period].get(item["id"]) or {}).get("wa_price")
        for period in ("day", "hour")
    }
