import list_components
import prices
import best
import re
import os
import auth


def main():
    while True:
        print('\n')
        print("Enter '1' to get sell orders for an item")
        print("Enter '2' to list all Prime items")
        print("Enter '3' to get average price of sell orders for an item")
        print("Enter '4' to get the best components/sets by Warframe.market average price")
        print("Enter '5' to authenticate with Warframe.market")
        print("Enter 'exit' or press Enter to quit")
        item = input()
        if item == 'exit' or item == '':
            print("Exiting the program.")
            break
        if item not in {'1', '2', '3', '4','5'}:
            print("Invalid input. Please enter '1', '2', or 'exit'.")
            continue
        if item == '1':
           item = input("Enter the item component or set name to get sell orders created/updated 30 days ago (e.g., 'Akstiletto Prime Barrel'): ")
           item = re.sub(r'\s+', '_', item.strip().lower())
           prices.list_orders(item)
        if item == '2':
            results = list_components.list_items()
            for item in results: 
                 if 'set' not in item["slug"]:
                     print(item['i18n']['en']['name'])
            continue
        if item == '3':
            avg_item = input("Enter the item component or set name to get average price of sell orders created/updated 30 days ago (e.g., 'Akstiletto Prime Barrel'): ")
            avg_item = re.sub(r'\s+',' ', avg_item.strip().title())
            best.aver_item(avg_item)
            continue
        if item == '4':
            price = input("Enter the minimum warframe.market average price to filter components (e.g., '100'): ")
            type = input("Enter '1' to see best sets, '2' to see best components: ")
            try:
                price = int(price)
                if type == '1':
                    best.best_sets(price)
                elif type == '2':
                    best.best_components(price)
                else:
                    print("Invalid input. Please enter '1', '2', or 'both'.")
            except ValueError:
                print("Invalid input. Please enter a valid number for the price.")
                continue
        if item == '5':
            try:
                email = input("Enter your Warframe.market email: ")
                password = input("Enter your Warframe.market password: ")
                device_id = os.urandom(16).hex()
                token = auth.authentificate(email, password, device_id)
                print("Authentication successful.")
                print("device_id:", device_id)
                print("Select option 1 to check profile details or option 2 to update user orders: ")
                option = input()
                if option == '1':
                    auth.user_data(token)
                elif option == '2':
                    auth.update_orders2(token)
                else:
                    print("Invalid option selected.")
            except Exception as e:
                print(f"Authentication failed: {e}")
            continue
if __name__ == "__main__":
    main()



