"""Reprice the user's sell orders so they sit among the cheapest in-game offers.

Two steps, so nothing changes on warframe.market without a look first:
    plan  = build_plan(token, settings)     # read-only: current vs proposed price per order
    apply_plan(token, [p for p in plan if ...])   # sends the updates
"""
import re
import statistics
from dataclasses import dataclass

from . import auth, catalog, client, market


_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _order_url(order_id):
    """URL for one order. The id comes from the server, so check it before it becomes part of a path."""
    if not isinstance(order_id, str) or not _ID_RE.fullmatch(order_id):
        raise ValueError("Unexpected order id from warframe.market.")
    return f"{client.API_V2}/order/{order_id}"


@dataclass
class Settings:
    top_n: int = 4               # be among the N cheapest offers
    troll_floor: float = 0.6     # offers below this fraction of the market median are ignored as lowballs
    band_low: float = 0.7        # final price stays within this band of the daily average (when known)
    band_high: float = 1.3
    min_price: int = 1           # never propose less than this
    max_change: float = 0.4      # proposals moving the price by more than this fraction are flagged for review
    use_online_fallback: bool = True   # too few in-game sellers -> also count sellers online on the site


@dataclass
class Proposal:
    order_id: str
    item_name: str
    slug: str
    rank: object
    subtype: object
    quantity: int
    current: int
    proposed: object = None      # None = no change proposed
    note: str = ""
    result: str = ""             # filled in by apply_plan
    flagged: bool = False        # the proposed change is large: needs a deliberate tick before applying
    visible: bool = True         # False = hidden from other players on warframe.market

    @property
    def changed(self):
        return self.proposed is not None and self.proposed != self.current

    @property
    def variant(self):
        parts = []
        if self.rank is not None:
            parts.append(f"rank {self.rank}")
        if self.subtype:
            parts.append(str(self.subtype).replace("_", " "))
        return ", ".join(parts)


def pick_price(sorted_prices, wa_price=None, settings=None):
    """Highest price that still leaves at most top_n - 1 clean offers strictly cheaper.

    sorted_prices: ascending prices of competing sell orders (same item, rank and subtype).
    Returns None when there is too little reliable data.
    """
    s = settings or Settings()
    n = max(1, s.top_n)
    sample = sorted_prices[:10]
    if len(sample) < n:
        return None

    # Reference = median of the cheapest 10; lowballers would need to be the majority to move it.
    ref = statistics.median(sample)
    clean = [p for p in sorted_prices if p >= ref * s.troll_floor]
    if wa_price:
        clean = [p for p in clean if p >= wa_price * s.band_low]
    if len(clean) < n:
        return None

    if n == 1:
        price = clean[0] - 1                         # undercut the cheapest clean offer
    else:
        price = max(clean[n - 2], clean[n - 1] - 1)  # match the (n-1)th or sit just under the nth

    if wa_price:
        price = min(max(price, wa_price * s.band_low), wa_price * s.band_high)
    return max(1, s.min_price, int(price))


def _competitors(book, order, statuses):
    return sorted(
        o["platinum"] for o in book
        if o.get("type") == "sell"
        and o.get("visible", True)
        and (o.get("user") or {}).get("status") in statuses
        and o.get("id") != order["id"]
        and o.get("rank") == order.get("rank")
        and o.get("subtype") == order.get("subtype")
    )


def _proposal(order, item):
    return Proposal(
        order_id=order["id"],
        item_name=catalog.item_name(item),
        slug=item["slug"],
        rank=order.get("rank"),
        subtype=order.get("subtype"),
        quantity=order.get("quantity", 1),
        current=order.get("platinum", 0),
        visible=order.get("visible", True),
    )


def list_orders(token):
    """Read-only and cheap (one request): the user's sell orders, with no price proposals yet."""
    by_id = catalog.items_by_id()
    return [_proposal(o, by_id[o["itemId"]]) for o in auth.my_orders(token)
            if o.get("type") == "sell" and o.get("itemId") in by_id]


def set_quantity(token, order_id, quantity):
    """Change the quantity of one of the user's orders."""
    if quantity < 1:
        raise ValueError("Quantity must be at least 1.")
    client.patch(_order_url(order_id), token, {"quantity": int(quantity)})


def set_visible(token, order_id, visible):
    """Show or hide one of the user's orders on warframe.market (hidden orders stay in the account)."""
    client.patch(_order_url(order_id), token, {"visible": bool(visible)})


def delete_order(token, order_id):
    """Permanently delete one of the user's orders."""
    client.delete(_order_url(order_id), token)


def build_plan(token, settings=None, progress=None):
    """Read-only. Returns a Proposal for every sell order the user has."""
    s = settings or Settings()
    by_id = catalog.items_by_id()
    try:
        day_stats = catalog.get_stats()["day"]
    except client.WfmError:
        day_stats = {}          # the average is a safety band, not a requirement

    orders = [o for o in auth.my_orders(token) if o.get("type") == "sell"]
    plan = []
    for index, order in enumerate(orders, start=1):
        item = by_id.get(order.get("itemId"))
        if item is None:
            continue
        proposal = _proposal(order, item)
        plan.append(proposal)
        if progress:
            progress(index, len(orders), proposal.item_name)

        try:
            book = market.fetch_orders(item["slug"])
        except (client.WfmError, ValueError) as exc:
            proposal.note = f"Could not read the market: {exc}"   # one bad item must not stop the run
            continue

        wa_price = (day_stats.get(item["id"]) or {}).get("wa_price")
        prices = _competitors(book, order, {"ingame"})
        source = "in-game sellers"
        if len(prices) < s.top_n and s.use_online_fallback:
            prices = _competitors(book, order, {"ingame", "online"})
            source = "in-game + online sellers"

        price = pick_price(prices, wa_price, s)
        if price is None:
            proposal.note = f"Not enough reliable data ({len(prices)} comparable offers)"
        elif price == proposal.current:
            proposal.note = "Already at the target price"
        else:
            proposal.proposed = price
            proposal.note = f"Based on {len(prices)} {source}"
            if proposal.current > 0:
                change = (price - proposal.current) / proposal.current
                if abs(change) > s.max_change:
                    proposal.flagged = True
                    proposal.note = f"Large change ({change:+.0%}): check it before applying. " + proposal.note
    return plan


def apply_plan(token, proposals, progress=None):
    """Send the price updates for the given proposals. Returns the number that succeeded."""
    todo = [p for p in proposals if p.changed]
    done = 0
    for index, proposal in enumerate(todo, start=1):
        if progress:
            progress(index, len(todo), proposal.item_name)
        try:
            client.patch(_order_url(proposal.order_id), token, {"platinum": proposal.proposed})
        except client.WfmError as exc:
            proposal.result = f"Failed: {exc}"
            continue
        proposal.result = f"Updated {proposal.current} -> {proposal.proposed}"
        proposal.current = proposal.proposed
        proposal.proposed = None
        done += 1
    return done


def suggest_price(item, settings=None, rank=None, subtype=None):
    """Price for a new sell order of `item`, using the same rules as repricing.

    Returns (price, note). Falls back to the 24h average when there are too few sellers;
    raises ValueError when there is nothing to base a price on.
    """
    s = settings or Settings()
    book = market.fetch_orders(item["slug"])
    try:
        wa_price = (catalog.get_stats()["day"].get(item["id"]) or {}).get("wa_price")
    except client.WfmError:
        wa_price = None

    new_order = {"id": None, "rank": rank, "subtype": subtype}
    prices = _competitors(book, new_order, {"ingame"})
    source = "in-game sellers"
    if len(prices) < s.top_n and s.use_online_fallback:
        prices = _competitors(book, new_order, {"ingame", "online"})
        source = "in-game + online sellers"

    price = pick_price(prices, wa_price, s)
    if price is not None:
        return price, f"Based on {len(prices)} {source}"
    if wa_price:
        return max(1, s.min_price, int(round(wa_price))), "Too few sellers right now: using the 24h average"
    raise ValueError(f"Not enough market data to price {catalog.item_name(item)} automatically.")


def create_sell_order(token, item, platinum, quantity=1):
    """Create a visible sell order. Returns the order as warframe.market reports it (may be empty)."""
    if platinum < 1 or quantity < 1:
        raise ValueError("Price and quantity must be at least 1.")
    payload = {"itemId": item["id"], "type": "sell", "platinum": int(platinum),
               "quantity": int(quantity), "visible": True}
    response = client.request("POST", f"{client.API_V2}/order", token=token, json=payload)
    data = response.get("data") if isinstance(response, dict) else None
    return data if isinstance(data, dict) else {}
