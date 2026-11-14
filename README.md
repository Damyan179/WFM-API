# WFM Tools

A desktop app (and a small terminal menu) for [warframe.market](https://warframe.market): look up prices, browse Prime items, and keep your own sell orders priced competitively without editing them one by one.

> Unofficial project. It is not affiliated with or endorsed by warframe.market or Digital Extremes. Automating an account can be restricted by a site's terms, so check warframe.market's rules before you use the order features, and use them at your own risk.

## Features

**Item orders**
- Search any item with autocomplete; see sell or buy orders grouped by In game / Online / Offline.
- Offline players appear only if their order was created or updated in the last 30 days.
- Shows the 24-hour and 1-hour average price.
- Double-click a row to copy an in-game whisper message.

**Top prices**
- Sets or components ranked by average price, for the last 24 hours or the last hour, with a minimum-price filter.

**Prime items**
- Filterable list of all Prime items; double-click one to open its orders.

**My orders** (needs a warframe.market account)
- Your sell orders are listed as soon as you sign in; filter them with the search box.
- **Calculate prices** reads the market and proposes a new price for each order, without changing anything.
- Review the table (current price, proposed price, change, reason), tick the rows you want, and press **Apply selected**.
- Large changes are flagged and start unticked, so you have to approve them on purpose.
- **Add order**: type a Prime component into the dropdown, pick a quantity, and the price is set by the same rules. A confirmation dialog shows the price before anything is created.
- Double-click a quantity to change it. Right-click an order to hide it from other players or delete it.
- Double-click an order's name to open its market orders.

## How prices are chosen

For each of your sell orders, the app looks at other players' sell orders for the same item (same mod rank and subtype) and aims for a place among the cheapest offers.

1. It uses in-game sellers. If there are fewer than the target, it can also count sellers who are online on the site.
2. It takes the median of the 10 cheapest offers as a reference and ignores offers below a set share of it (default 60%) as lowballs or trolling.
3. It prices the order so that at most *target − 1* of the remaining offers are cheaper (default: top 4).
4. When warframe.market publishes a 24-hour average for the item, the result is kept within a band around it (default 0.7× to 1.3×).
5. The price never goes below your minimum, and items with too little reliable data are skipped.

Target position, lowball share, band, minimum price and the "flag changes over" limit (default 40%) can all be changed in the app.

## Requirements

- Windows (credentials are stored in Windows Credential Manager)
- Python 3.13 (other recent versions will probably work)
- Packages in `requirements.txt`: `curl_cffi`, `keyring`, `PySide6`

## Run from source

```
git clone https://github.com/Damyan179/WFM-API.git
cd WFM-API
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Browsing prices works without an account. To use **My orders**, open that tab and press **Sign in**.

### Terminal menu

`python main.py` offers the same lookups in the terminal, plus profile details and repricing with a preview and a confirmation question.

## Your login

- Email, password, device id and session token are stored in Windows Credential Manager, not in the project folder.
- The password is checked against warframe.market before it is saved. **Sign out** removes the stored email, password and token.
- The session token is only sent for requests about your own account, never for public price lookups.
- An older `.wfm_token` file from a previous version is moved into Credential Manager and deleted.

## Download a ready-made app

Pushing a version tag builds a Windows app automatically with GitHub Actions and attaches it to the repository's **Releases** page:

```
git tag v1.0.0
git push origin v1.0.0
```

Download `WFM-Tools-windows.zip`, unzip it, and run `WFM Tools.exe`. The app is not code-signed, so Windows SmartScreen may warn you: choose **More info**, then **Run anyway**.

To build it yourself:

```
python -m pip install pyinstaller
python -m PyInstaller --noconsole --onedir --name "WFM Tools" --collect-all curl_cffi --hidden-import keyring.backends.Windows app.py
```

The result is in `dist\WFM Tools\`. Keep the whole folder together.

## Project layout

```
app.py              desktop UI (PySide6)
main.py             terminal menu
wfm/
  client.py         HTTP client: rate limit, timeouts, retries
  catalog.py        item list and price statistics, cached
  market.py         public order books and rankings
  auth.py           sign-in and Credential Manager storage
  repricer.py       pricing rules, previews, order changes
tests/              offline tests (no network needed)
auth.py, best.py, prices.py, list_components.py, setup_credentials.py
                    thin wrappers kept for the old command-line scripts
legacy/, test.py    old experiments
```

## Notes on how it talks to warframe.market

- Requests are limited to just under 3 per second.
- Failed reads and updates are retried a few times. Creating an order is never retried automatically, to avoid duplicates; if it fails, the app reloads your list so you can see what really exists.
- The item list is cached for 24 hours in `.cache/` (ignored by git).

## Tests

```
python -m unittest discover tests
```

The tests use fake data and do not contact warframe.market.
