from email import header
import httpx
import os 
import asyncio
import requests
import time

APIv1 = "https://api.warframe.market/v1"
APIv2 = "https://api.warframe.market/v2"

async def login(email,password, device_id):
    payload = {
        "auth_type": "header",
        "email": email,
        "password": password,
        "device_id": device_id
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{APIv1}/auth/signin", headers={"Authorization": "JWT"}, json=payload)

    if response.status_code != 200:
        raise RuntimeError(response.text)
    
    auth = response.headers.get("Authorization")
    if not auth or not auth.startswith("JWT "):
        raise RuntimeError("Invalid authorization header")
    
    return auth[4:]  # Remove "JWT " prefix

def authentificate(email, password, device_id):
    if not email or not password or not device_id:
        raise ValueError("Missing environment variables")

    return asyncio.run(login(email, password, device_id))

def user_data(auth_token):
   header = {
       "Authorization": f"Bearer {auth_token}",
       "Content-Type": "application/json"
   }
   req = requests.get(f"{APIv2}/me", headers=header)
   print(req.json())

def update_user_orders(auth_token):
   header = {
       "Authorization": f"Bearer {auth_token}",
       "Content-Type": "application/json"
    }
   payload = {
       "visible": True,
       "type": "sell"
   }
   req = requests.patch(f"{APIv2}/orders/group/all", headers=header, json=payload)
   if req.status_code != 200:
       raise RuntimeError(req.text)
   else:
       print("User orders updated successfully")
   
def item_info(auth_token):
    header = {
         "Authorization": f"Bearer {auth_token}",
         "Content-Type": "application/json"
    }
    req = requests.get(f"{APIv2}/orders/my", headers=header)
    if req.status_code != 200:
         raise RuntimeError(req.text)
    else:
         return req.json()

#Iteme prime utilizand ducanator 
def update_orders(auth_token):
    header = {
         "Authorization": f"Bearer {auth_token}",
         "Content-Type": "application/json"
    }
    # Orders detine id-ul comenzii si id-ul itemului de actualizat
    # Prices id-ul itemului, numele si comenzile online pentru acel item
    # Vreau sa obtin id-ul comenzii si pretul itemului pentru a face update la comanda respectiva
    orders = item_info(auth_token)
    prices = requests.get(f"{APIv1}/tools/ducats").json()
    price_id = {order['itemId']: order['id'] for order in orders['data']}

    result = [
        {
            'order_id': price_id[price['item']],
            'wa_price': price['wa_price']
        }
        for price in prices['payload']['previous_day']
        if price['item'] in price_id
    ]

    for item in result:
        payload = {
            'platinum': int(item['wa_price'])
        }
        req = requests.patch(f"{APIv2}/order/{item['order_id']}", headers=header, json=payload)
        time.sleep(0.33)
        if req.status_code != 200:
            print(f"Failed to update order {item['order_id']}: {req.text}")
        else:
            print(f"Order {item['order_id']} updated successfully")    

# Actualizeaza comenzile utilizand pretul mediu al primelor 4 comenzi online
def update_orders2(auth_token):
    header = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
    }
    # Get user's orders id, item id
    # Get order item id, parse it through /items to get slug from item id
    # get slug, add it to /order/item/{slug} to get currents orders
    # Get 1st 6 online orders average price from warframe.market average price
    orders = item_info(auth_token)
    items = requests.get(f"{APIv2}/items").json()
    item_id_to_slug = {item['id']: item['slug'] for item in items['data']}
    for order in (o for o in orders['data'] if o['type'] == 'sell'):
        order_id = order['id']
        item_id = order['itemId']
        if item_id not in item_id_to_slug:
            continue

        slug = item_id_to_slug[item_id]
        prices = requests.get(f"{APIv2}/orders/item/{slug}").json()

        sell_orders = [
            o for o in prices['data']
            if o['type'] == 'sell'
            and o['visible']
            and o['user']['status'] == 'ingame'
            and o['id'] != order_id
        ]

        if not sell_orders:
            continue

        sell_orders.sort(key=lambda x: x['platinum'])

        top_prices = [o['platinum'] for o in sell_orders[:4]]

        if not top_prices:
            continue

        if len(top_prices) > 1:
            average_price = sum(top_prices[1:]) / (len(top_prices) - 1)
        else:
            average_price = top_prices[0]

        new_price = max(1, int(average_price))

        payload = {
            'platinum': new_price
        }

        req = requests.patch(
            f"{APIv2}/order/{order_id}",
            headers=header,
            json=payload
        )

        time.sleep(0.33)

        if not req.ok:
            print(f"Failed to update order {order_id}: {req.text}")
        else:
            print(f"Order {order_id} updated to {new_price} platinum")

token = None
if (token is None):
    token = authentificate("damyan17904@gmail.com","e4F#cJHo8P","test453253535")

update_orders2(token)