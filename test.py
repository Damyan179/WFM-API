import requests

url = "https://api.warframe.market/v2"

request = requests.get(f"{url}/user/hyper-4964")
print(request.json())