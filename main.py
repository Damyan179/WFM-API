"""Terminal menu for the warframe.market tools. For the desktop UI run:  python app.py"""
import getpass

from wfm import auth, catalog, client, market, repricer


def show_orders():
    item = catalog.find_item(input("Item name (e.g. Akstiletto Prime Barrel): "))
    groups = market.list_orders(item["slug"])
    titles = {"ingame": "In game", "online": "Online", "offline": "Offline (active in the last 30 days)"}
    print(f"\nSell orders for {catalog.item_name(item)}")
    for status, title in titles.items():
        print(f"\n--- {title} ---")
        for row in groups[status]:
            print(f"{row['user']:<28}{row['platinum']:>6} platinum   updated {row['updated']:%Y-%m-%d}" if row['updated']
                  else f"{row['user']:<28}{row['platinum']:>6} platinum")
        if not groups[status]:
            print("(none)")


def show_prime_items():
    for item in catalog.prime_items():
        print(catalog.item_name(item))


def show_average():
    item = catalog.find_item(input("Item name: "))
    averages = market.average_price(item)
    for label, key in (("last 24 hours", "day"), ("last hour", "hour")):
        value = averages[key]
        print(f"Average price of {catalog.item_name(item)}, {label}: "
              + (f"{value:g} platinum" if value is not None else "not published"))


def show_top():
    min_price = int(input("Minimum average price (e.g. 100): "))
    kind = {"1": "sets", "2": "components"}.get(input("'1' for sets, '2' for components: ").strip())
    if kind is None:
        print("Enter 1 or 2.")
        return
    for period, title in (("day", "last 24 hours"), ("hour", "last hour")):
        print(f"\nBest {kind} by average price ({title}):")
        for row in market.top_prices(period, kind, min_price):
            print(f"{row['name']}: {row['wa_price']:g} platinum")


def account():
    if not auth.has_credentials():
        email = input("warframe.market email: ").strip()
        password = getpass.getpass("Password (not shown): ")
        auth.sign_in(email, password)
        print("Signed in. Credentials saved to Windows Credential Manager.")
    token = auth.get_token()
    choice = input("'1' profile details, '2' reprice my sell orders: ").strip()
    if choice == "1":
        print(auth.profile(token))
    elif choice == "2":
        reprice(token)
    else:
        print("Enter 1 or 2.")


def reprice(token):
    print("Reading the market...")
    plan = repricer.build_plan(token, progress=lambda i, n, name: print(f"  {i}/{n} {name}"))
    changes = [p for p in plan if p.changed]
    print()
    for p in plan:
        target = f"{p.current} -> {p.proposed}" if p.changed else f"{p.current} (no change)"
        print(f"{p.item_name:<40}{target:<20}{p.note}")
    if not changes:
        print("\nNothing to update.")
        return
    if input(f"\nApply {len(changes)} price change(s)? [y/N] ").strip().lower() != "y":
        print("Nothing was changed.")
        return
    done = repricer.apply_plan(token, changes)
    for p in changes:
        print(f"{p.item_name}: {p.result}")
    print(f"{done} of {len(changes)} orders updated.")


ACTIONS = {"1": show_orders, "2": show_prime_items, "3": show_average, "4": show_top, "5": account}


def main():
    while True:
        print("\n1  Sell orders for an item")
        print("2  List all Prime items")
        print("3  Average price of an item")
        print("4  Best sets/components by average price")
        print("5  My account: profile or reprice my orders")
        print("Enter to quit")
        choice = input("> ").strip()
        if choice in ("", "exit"):
            break
        action = ACTIONS.get(choice)
        if action is None:
            print("Enter a number from 1 to 5.")
            continue
        try:
            action()
        except (client.WfmError, auth.NotSignedIn, ValueError) as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
