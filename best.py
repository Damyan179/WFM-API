
import requests

#API 
URL = "https://api.warframe.market/v2"
URL2 = "https://api.warframe.market/v1/tools/ducats"


def fetch_data():
    v1 = requests.get(f"{URL}/items")
    v2 = requests.get(f"{URL2}")

    v1 = v1.json()
    v2 = v2.json()


    name_id = {item['id']: item['i18n']['en']['name'] for item in v1['data']}

    result_day = [
        {
            'name': name_id[item['item']],
            'wa_price': item['wa_price']
        }
        for item in v2['payload']['previous_day']
        if item['item'] in name_id
    ]

    result_hour = [
        {
            'name': name_id[item['item']],
            'wa_price': item['wa_price']
        }
        for item in v2['payload']['previous_hour']
        if item['item'] in name_id
    ]

    result_hour.sort(key=lambda x: x['wa_price'], reverse=True)
    result_day.sort(key=lambda x: x['wa_price'], reverse=True)
    return result_hour, result_day

def best_sets(price):
    result_hour, result_day = fetch_data()
    result_set_day = [item for item in result_day if 'Set' in item['name']]
    result_set_hour = [item for item in result_hour if 'Set' in item['name']]

    print("Warframe sets by Warframe.market average price (last 24 hours):")
    for item in result_set_day[:10]:
        print(f"{item['name']}: {item['wa_price']} platinum")
    print("\nWarframe sets by Warframe.market average price (last hour):")
    for item in result_set_hour[:10]:
        print(f"{item['name']}: {item['wa_price']} platinum")

def best_components(price):
    result_hour, result_day = fetch_data()
    result_component_day = [item for item in result_day if not 'Set' in item['name']]
    result_component_hour = [item for item in result_hour if not 'Set' in item['name']]
    print("\nWarframe components by Warframe.market average price (last 24 hours):")
    for item in result_component_day:
        if item['wa_price'] >= price:
            print(f"{item['name']}: {item['wa_price']} platinum")
    print("\nWarframe components by Warframe.market average price (last hour):")
    for item in result_component_hour:
        if item['wa_price'] >= price:
            print(f"{item['name']}: {item['wa_price']} platinum")

def aver_item(item_name):
    result_hour, result_day = fetch_data()
    for item in result_day:
        if item['name'] == item_name:
            print(f"\nAverage price of {item_name} last 24 hours: {item['wa_price']} platinum")
    for item in result_hour:
        if item['name'] == item_name:
            print(f"Average price of {item_name} last hour: {item['wa_price']} platinum")

best_components(40)