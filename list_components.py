import requests

#API 
URL = "https://api.warframe.market/v2"

# Prime list
url_prime_items = f"{URL}/items"
def list_items():
    results = []
    def find_item(tags):
        response = requests.get(url_prime_items)
        payload = response.json()

        for item in payload["data"]:
            if tags in item.get('tags', []):
                results.append(item)

        return results

    item = find_item('prime')
    return results



