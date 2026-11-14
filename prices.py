"""Kept for compatibility: the logic now lives in wfm/market.py. Importing this file no longer runs anything."""
from wfm import catalog, market


def list_orders(item):
    """Print the cheapest sell orders for an item name or slug."""
    found = catalog.find_item(item.replace("_", " "))
    groups = market.list_orders(found["slug"])
    for status, title in (("ingame", "Ingame"), ("online", "Online"),
                          ("offline", "Offline (created/updated in last 30 days)")):
        print(f"\n---------{title}---------")
        for row in groups[status]:
            print(row["user"], row["platinum"], row["created"], row["updated"])


if __name__ == "__main__":
    list_orders("akstiletto_prime_barrel")
