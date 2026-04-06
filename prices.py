import requests
from datetime import datetime as dt, timezone, timedelta

#API 
URL = "https://api.warframe.market/v2"

def list_orders(item):
    url_orders = f"{URL}/orders/item/{item}"
    response = requests.get(url_orders)
    payload = response.json()
    results = []
    now = dt.now(timezone.utc)
    one_month_ago = now - timedelta(days=30)


    for order in payload["data"]:
        if order['type'] == "sell":
            results.append(order)

    sort = sorted(results, key=lambda x: x['platinum'])

    print('\n')
    print("--------------------------Ingame--------------------------")
    i = 0
    for order in sort:
        if order['createdAt'] and order['user']['status'] == 'ingame':
            print(order['user']['ingameName'], order['platinum'], order['createdAt'], order['updatedAt'])
            i = i + 1
        if i == 10:
            break

    print('\n')
    print("---------Offline (created/updated in last 30 days)---------")
    i = 0
    for order in sort:
        if order['createdAt'] > str(one_month_ago) and order['updatedAt'] > str(one_month_ago) and order['user']['status'] == 'offline':
            print(order['user']['ingameName'], order['platinum'], order['createdAt'], order['updatedAt'])
            i = i + 1
        if i == 10:
            break

req = requests.get(f"{URL}/orders/item/akstiletto_prime_barrel")
print(req.json()['data'][0])   


#/orders/item/akstiletto_prime_barrel
{'id': '5b137a703048b200cc8c2b47', 
 'type': 'sell', 
 'platinum': 20, 
 'quantity': 4, 
 'perTrade': 1, 
 'visible': True, 
 'createdAt': '2018-06-03T05:19:44Z', 
 'updatedAt': '2026-01-10T14:04:39Z', 
 'itemId': '573b804a0ec44a47787a6916', 
}

#/orders/my
{'id': '696be7ee6a51e1b3b0c3575d', 
 'type': 'sell', 
 'platinum': 56, 
 'quantity': 1, 
 'perTrade': 1, 
 'visible': True, 
 'createdAt': '2026-01-17T19:50:06Z', 
 'updatedAt': '2026-01-29T16:33:06Z', 
 'itemId': '58b57068eb26db5c31192113'}

#/items
{'id': '54aae292e7798909064f1575', 
 'slug': 'secura_dual_cestra', 
}