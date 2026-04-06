import requests
from datetime import datetime as dt, timezone, timedelta

#API 
URL = "https://api.warframe.market/v2"
URL = "https://api.warframe.market/v1/tools/ducats"

now = dt.now(timezone.utc)

def list_orders_avg_alltime(item):
    url_orders = f"{URL}/orders/item/{item}"
    response = requests.get(url_orders)
    payload = response.json()
    results = []
    for order in payload["data"]:
        if order['type'] == "sell":
            results.append(order)

    sort = sorted(results, key=lambda x: x['platinum'])
    avg = 0
    count = 0

    for user in sort:
        avg += user['platinum']*user['quantity']
        count += user['quantity']

    if count > 0:
        average_price = avg / count
        return average_price
        print(f"Average price of all sell orders: {average_price:.2f} platinum")


def list_orders_avg_30days(item):
    url_orders = f"{URL}/orders/item/{item}"
    response = requests.get(url_orders)
    payload = response.json()
    results = []
    one_month_ago = now - timedelta(days=30)
    for order in payload["data"]:
        if order['type'] == "sell" and (order['createdAt'] > str(one_month_ago) or order['updatedAt'] > str(one_month_ago)):
            results.append(order)

    sort = sorted(results, key=lambda x: x['platinum'])

    avg = 0
    count = 0

    for user in sort:
            avg += user['platinum']*user['quantity']
            count += user['quantity']

    if count > 0:
        average_price = avg / count
        print(item)
        print(f"Average price of {item} sell orders created/updated in the last 30 days: {average_price:.2f} platinum")
        return average_price
        print(f"Average price of sell orders created/updated in the last 30 days: {average_price:.2f} platinum")


def list_orders_avg_7days(item):
    url_orders = f"{URL}/orders/item/{item}"
    response = requests.get(url_orders)
    payload = response.json()
    results = []
    one_week_ago = now - timedelta(days=7)  
    for order in payload["data"]:
        if order['type'] == "sell" and (order['createdAt'] > str(one_week_ago) or order['updatedAt'] > str(one_week_ago)):
            results.append(order)

    sort = sorted(results, key=lambda x: x['platinum'])

    avg = 0
    count = 0 

    for user in sort:
            avg += user['platinum']*user['quantity']
            count += user['quantity']
        
    if count > 0:
        average_price = avg / count
        return average_price
        print(f"Average price of sell orders created/updated in the last 7 days: {average_price:.2f} platinum")

