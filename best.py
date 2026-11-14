"""Kept for compatibility: the logic now lives in wfm/market.py. Importing this file no longer runs anything."""
from wfm import catalog, market


def best_sets(price=0, limit=10):
    for period, title in (("day", "last 24 hours"), ("hour", "last hour")):
        print(f"\nWarframe sets by warframe.market average price ({title}):")
        for row in market.top_prices(period, "sets", price, limit):
            print(f"{row['name']}: {row['wa_price']} platinum")


def best_components(price=0):
    for period, title in (("day", "last 24 hours"), ("hour", "last hour")):
        print(f"\nWarframe components by warframe.market average price ({title}):")
        for row in market.top_prices(period, "components", price):
            print(f"{row['name']}: {row['wa_price']} platinum")


def aver_item(item_name):
    item = catalog.find_item(item_name)
    averages = market.average_price(item)
    print(f"\nAverage price of {catalog.item_name(item)} last 24 hours: {averages['day']} platinum")
    print(f"Average price of {catalog.item_name(item)} last hour: {averages['hour']} platinum")


if __name__ == "__main__":
    best_components(40)
