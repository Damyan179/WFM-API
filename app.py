"""Desktop UI for the warframe.market tools.

Run:  python app.py        (needs: pip install PySide6)
"""
import sys

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QStyledItemDelegate, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QMenu, QTabWidget, QVBoxLayout, QWidget,
)

from wfm import auth, catalog, client, market, repricer

ACCENT = "#4fa3d1"
GOOD = QColor("#6fcf97")
WARN = QColor("#e2b866")
BAD = QColor("#eb6f6f")
MUTED = QColor("#8a94a3")
STATUS_LABEL = {"ingame": "In game", "online": "Online", "offline": "Offline"}
STATUS_COLOR = {"ingame": GOOD, "online": QColor("#e2b866"), "offline": MUTED}


# ----------------------------------------------------------------------------- background work

class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)


class Worker(QRunnable):
    """Runs fn(*args) off the UI thread. If want_progress, fn receives a progress=callback keyword."""

    def __init__(self, fn, *args, want_progress=False):
        super().__init__()
        self.fn, self.args, self.want_progress = fn, args, want_progress
        self.signals = _Signals()

    def run(self):
        try:
            kwargs = {"progress": self.signals.progress.emit} if self.want_progress else {}
            self.signals.done.emit(self.fn(*self.args, **kwargs))
        except auth.NotSignedIn as exc:
            self.signals.failed.emit(str(exc))
        except (client.WfmError, ValueError) as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # show unexpected errors instead of dying silently in a thread
            self.signals.failed.emit(f"Unexpected error: {type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------------- small helpers

def cell(value, align_right=False, color=None):
    """Table cell. Numbers are stored as numbers so column sorting is numeric."""
    item = QTableWidgetItem()
    if value is None or value == "":
        item.setText("")
    elif isinstance(value, (int, float)):
        item.setData(Qt.DisplayRole, round(value, 1) if isinstance(value, float) else value)
    else:
        item.setText(str(value))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if align_right or isinstance(value, (int, float)):
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if color:
        item.setForeground(color)
    return item


def make_table(headers, stretch_column=0):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)
    return table


def fmt_time(value):
    return value.astimezone().strftime("%Y-%m-%d %H:%M") if value else ""


# ----------------------------------------------------------------------------- tabs

class MarketTab(QWidget):
    """Order book for one item, plus its average prices."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.current_item = None
        self.forced = None          # (typed text, slug) set when another tab opens an exact item

        self.search = QLineEdit()
        self.search.setPlaceholderText("Item name, e.g. Akstiletto Prime Barrel")
        self.search.returnPressed.connect(self.load)
        self.kind = QComboBox()
        self.kind.addItem("Sell orders", "sell")
        self.kind.addItem("Buy orders", "buy")
        self.kind.currentIndexChanged.connect(lambda _: self.current_item and self.load())
        self.button = QPushButton("Search")
        self.button.setDefault(True)
        self.button.clicked.connect(self.load)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.kind)
        top.addWidget(self.button)

        self.summary = QLabel("Search for an item to see who is trading it.")
        self.summary.setObjectName("summary")
        self.table = make_table(["Player", "Status", "Platinum", "Qty", "Rank", "Subtype", "Updated"])
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(self.copy_whisper)
        hint = QLabel("Double-click a row to copy an in-game whisper message. "
                      "Offline players are listed only if their order changed in the last 30 days.")
        hint.setObjectName("hint")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        layout.addWidget(hint)

    def set_item_names(self, names):
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.search.setCompleter(completer)

    def show_item(self, name, slug=None):
        """Switch to this tab and load an item. `slug` (when known) avoids any name ambiguity."""
        self.search.setText(name)
        self.forced = (name, slug) if slug else None
        self.window.tabs.setCurrentWidget(self)
        self.load()

    def load(self):
        text = self.search.text().strip()
        if not text:
            return
        order_type = self.kind.currentData()

        forced = self.forced
        self.forced = None

        def job():
            # use the exact slug only if the search box still holds the text it was opened with
            item = catalog.find_item(forced[1] if forced and forced[0] == text else text)
            return item, market.list_orders(item["slug"], order_type), market.average_price(item)

        self.button.setEnabled(False)
        self.window.run(job, self.show_result, busy=f"Loading orders for {text}...",
                        always=lambda: self.button.setEnabled(True))

    def show_result(self, result):
        item, groups, averages = result
        self.current_item = item
        name = catalog.item_name(item)
        self.search.setText(name)

        parts = [f"<b>{name}</b>"]
        for label, key in (("24h average", "day"), ("1h average", "hour")):
            if averages[key] is not None:
                parts.append(f"{label}: <b>{averages[key]:g}</b> platinum")
        if len(parts) == 1:
            parts.append("no average price published for this item")
        self.summary.setText("  ·  ".join(parts))

        rows = [(status, row) for status in ("ingame", "online", "offline") for row in groups[status]]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, (status, row) in enumerate(rows):
            self.table.setItem(r, 0, cell(row["user"]))
            self.table.setItem(r, 1, cell(STATUS_LABEL[status], color=STATUS_COLOR[status]))
            self.table.setItem(r, 2, cell(row["platinum"]))
            self.table.setItem(r, 3, cell(row["quantity"]))
            self.table.setItem(r, 4, cell(row["rank"]))
            self.table.setItem(r, 5, cell((row["subtype"] or "").replace("_", " ")))
            self.table.setItem(r, 6, cell(fmt_time(row["updated"])))
        self.table.setColumnHidden(4, all(row["rank"] is None for _, row in rows))
        self.table.setColumnHidden(5, all(not row["subtype"] for _, row in rows))
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)   # keep best-price order
        self.table.setSortingEnabled(True)
        self.window.status(f"{len(rows)} orders shown for {name}.")

    def copy_whisper(self, clicked):
        row = clicked.row()
        if not self.current_item or self.table.item(row, 0) is None:
            return
        player = self.table.item(row, 0).text()
        price = self.table.item(row, 2).text()
        verb = "buy" if self.kind.currentData() == "sell" else "sell"
        message = (f"/w {player} Hi! I want to {verb}: \"{catalog.item_name(self.current_item)}\" "
                   f"for {price} platinum. (warframe.market)")
        QGuiApplication.clipboard().setText(message)
        self.window.status(f"Whisper for {player} copied to the clipboard.")


class TopTab(QWidget):
    """Items ranked by warframe.market average price."""

    def __init__(self, window):
        super().__init__()
        self.window = window

        self.period = QComboBox()
        self.period.addItem("Last 24 hours", "day")
        self.period.addItem("Last hour", "hour")
        self.kind = QComboBox()
        self.kind.addItem("Components", "components")
        self.kind.addItem("Sets", "sets")
        self.kind.addItem("Everything", "all")
        self.min_price = QSpinBox()
        self.min_price.setRange(0, 100000)
        self.min_price.setValue(40)
        self.min_price.setSuffix(" platinum")
        self.button = QPushButton("Refresh")
        self.button.clicked.connect(self.load)

        top = QHBoxLayout()
        top.addWidget(QLabel("Period"))
        top.addWidget(self.period)
        top.addWidget(QLabel("Show"))
        top.addWidget(self.kind)
        top.addWidget(QLabel("Minimum average"))
        top.addWidget(self.min_price)
        top.addStretch(1)
        top.addWidget(self.button)

        self.table = make_table(["Item", "Average price", "Ducats", "Volume"])
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(
            lambda clicked: self.window.market_tab.show_item(self.table.item(clicked.row(), 0).text()))
        hint = QLabel("Double-click an item to open its orders.")
        hint.setObjectName("hint")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(hint)

    def load(self):
        args = (self.period.currentData(), self.kind.currentData(), self.min_price.value())
        self.button.setEnabled(False)
        self.window.run(lambda: market.top_prices(*args), self.show_result, busy="Loading average prices...",
                        always=lambda: self.button.setEnabled(True))

    def show_result(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, cell(row["name"]))
            self.table.setItem(r, 1, cell(float(row["wa_price"])))
            self.table.setItem(r, 2, cell(row["ducats"]))
            self.table.setItem(r, 3, cell(row["volume"]))
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(1, Qt.DescendingOrder)
        self.window.status(f"{len(rows)} items at or above {self.min_price.value()} platinum.")


class PrimeTab(QWidget):
    """Browsable list of Prime items."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.names = []

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter, e.g. rhino")
        self.filter.textChanged.connect(self.refill)
        self.sets = QCheckBox("Include sets")
        self.sets.toggled.connect(self.load)
        self.count = QLabel("")
        self.count.setObjectName("hint")

        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(self.sets)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.itemDoubleClicked.connect(lambda item: self.window.market_tab.show_item(item.text()))

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.count)

    def load(self):
        include_sets = self.sets.isChecked()
        self.window.run(lambda: [catalog.item_name(i) for i in catalog.prime_items(include_sets)],
                        self.show_result, busy="Loading Prime items...")

    def show_result(self, names):
        self.names = names
        self.refill()

    def refill(self):
        wanted = self.filter.text().strip().lower()
        shown = [n for n in self.names if wanted in n.lower()]
        self.list.clear()
        self.list.addItems(shown)
        self.count.setText(f"{len(shown)} of {len(self.names)} Prime items. Double-click one to open its orders.")


class QuantityDelegate(QStyledItemDelegate):
    """Edits the Qty column with a number box, so only whole numbers of at least 1 can be entered."""

    def createEditor(self, parent, option, index):
        box = QSpinBox(parent)
        box.setRange(1, 999999)
        box.setFrame(False)
        return box

    def updateEditorGeometry(self, editor, option, index):
        # The Qty column is narrow, so let the editor grow leftward (right edge stays aligned).
        rect = option.rect
        width = max(rect.width(), 120)
        rect.setLeft(rect.right() - width + 1)
        editor.setGeometry(rect)

    def setEditorData(self, editor, index):
        editor.setValue(int(index.data(Qt.EditRole) or 1))

    def setModelData(self, editor, model, index):
        editor.interpretText()
        model.setData(index, editor.value(), Qt.EditRole)


class SignInDialog(QDialog):
    def __init__(self, parent, email=""):
        super().__init__(parent)
        self.setWindowTitle("Sign in to warframe.market")
        self.setMinimumWidth(380)
        self.email = QLineEdit(email)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        form = QFormLayout()
        form.addRow("Email", self.email)
        form.addRow("Password", self.password)
        note = QLabel("Your email and password are stored in Windows Credential Manager, "
                      "not in the project folder.")
        note.setWordWrap(True)
        note.setObjectName("hint")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Sign in")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)


class OrdersTab(QWidget):
    """The user's sell orders: calculate new prices, review them, apply the ticked ones."""

    COLUMNS = ["", "Item", "Variant", "Qty", "Current", "Proposed", "Change", "Note"]

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.plan = []

        # account row
        self.account = QLabel()
        self.sign_in_button = QPushButton("Sign in")
        self.sign_in_button.clicked.connect(self.sign_in)
        self.sign_out_button = QPushButton("Sign out")
        self.sign_out_button.clicked.connect(self.sign_out)
        account_row = QHBoxLayout()
        account_row.addWidget(self.account, 1)
        account_row.addWidget(self.sign_in_button)
        account_row.addWidget(self.sign_out_button)

        # pricing rules
        defaults = repricer.Settings()
        self.top_n = QSpinBox()
        self.top_n.setRange(1, 10)
        self.top_n.setValue(defaults.top_n)
        self.top_n.setToolTip("Price each order so it is among this many cheapest offers.")
        self.troll = QSpinBox()
        self.troll.setRange(0, 100)
        self.troll.setValue(int(defaults.troll_floor * 100))
        self.troll.setSuffix(" %")
        self.troll.setToolTip("Offers below this share of the market median are ignored as lowballs.")
        self.band_low = QDoubleSpinBox()
        self.band_low.setRange(0.1, 1.0)
        self.band_low.setSingleStep(0.05)
        self.band_low.setValue(defaults.band_low)
        self.band_high = QDoubleSpinBox()
        self.band_high.setRange(1.0, 5.0)
        self.band_high.setSingleStep(0.05)
        self.band_high.setValue(defaults.band_high)
        for box in (self.band_low, self.band_high):
            box.setPrefix("x ")
            box.setToolTip("The proposed price stays within this multiple of the 24h average, when one exists.")
        self.min_price = QSpinBox()
        self.min_price.setRange(1, 100000)
        self.min_price.setValue(defaults.min_price)
        self.min_price.setSuffix(" platinum")
        self.min_price.setToolTip("No order is ever priced below this.")
        self.fallback = QCheckBox("Count online sellers when too few are in game")
        self.fallback.setChecked(defaults.use_online_fallback)
        self.max_change = QSpinBox()
        self.max_change.setRange(5, 500)
        self.max_change.setValue(int(defaults.max_change * 100))
        self.max_change.setSuffix(" %")
        self.max_change.setToolTip("A proposed price this far from your current price is left unticked "
                                   "so you have to approve it on purpose.")

        rules = QHBoxLayout()
        for label, widget in (("Target top", self.top_n), ("Ignore offers under", self.troll),
                              ("Average band", self.band_low), ("to", self.band_high),
                              ("Never below", self.min_price)):
            rules.addWidget(QLabel(label))
            rules.addWidget(widget)
        rules.addStretch(1)
        rules2 = QHBoxLayout()
        rules2.addWidget(QLabel("Flag changes over"))
        rules2.addWidget(self.max_change)
        rules2.addWidget(self.fallback)
        rules2.addStretch(1)
        rules_layout = QVBoxLayout()
        rules_layout.addLayout(rules)
        rules_layout.addLayout(rules2)
        rules_box = QGroupBox("Pricing rules")
        rules_box.setLayout(rules_layout)

        # add a new order: type a Prime component, the price comes from the pricing rules
        self.components = {}                       # lower-case name -> catalogue item
        self.new_item = QComboBox()
        self.new_item.setEditable(True)
        self.new_item.setInsertPolicy(QComboBox.NoInsert)
        self.new_item.setMinimumWidth(320)
        self.new_item.lineEdit().setPlaceholderText("Type a Prime component, e.g. rhino prime sys")
        self.new_item.lineEdit().editingFinished.connect(self.autofill_item)
        self.new_qty = QSpinBox()
        self.new_qty.setRange(1, 999)
        self.add_button = QPushButton("Add order")
        self.add_button.clicked.connect(self.add_order)
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Item"))
        add_row.addWidget(self.new_item, 1)
        add_row.addWidget(QLabel("Quantity"))
        add_row.addWidget(self.new_qty)
        add_row.addWidget(self.add_button)
        add_box = QGroupBox("New sell order (price set automatically)")
        add_box.setLayout(add_row)

        # actions
        self.refresh_button = QPushButton("Refresh orders")
        self.refresh_button.clicked.connect(self.refresh_orders)
        self.calc_button = QPushButton("Calculate prices")
        self.calc_button.clicked.connect(self.calculate)
        self.apply_button = QPushButton("Apply selected")
        self.apply_button.setObjectName("primary")
        self.apply_button.setEnabled(False)
        self.apply_button.setMinimumWidth(190)
        self.apply_button.clicked.connect(self.apply)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.calc_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search my listings...")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self.apply_filter)
        actions.addWidget(self.search)
        actions.addWidget(self.progress, 1)
        actions.addStretch(0)
        actions.addWidget(self.apply_button)

        self.table = make_table(self.COLUMNS, stretch_column=7)
        self.table.setItemDelegateForColumn(3, QuantityDelegate(self.table))
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.itemDoubleClicked.connect(self.open_item)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.order_menu)
        hint = QLabel("Right-click an order to hide or delete it. "
                      "Double-click an order's name to see its market orders, or its quantity to change it. "
                      "Calculating only reads the market. Nothing changes on warframe.market until you "
                      "press Apply selected and confirm.")
        hint.setObjectName("hint")

        layout = QVBoxLayout(self)
        layout.addLayout(account_row)
        layout.addWidget(rules_box)
        layout.addWidget(add_box)
        layout.addLayout(actions)
        layout.addWidget(self.table, 1)
        layout.addWidget(hint)
        self.refresh_account()

    # --- account

    def refresh_account(self):
        email = auth.stored_email() if auth.has_credentials() else None
        if email:
            self.account.setText(f"Signed in as <b>{email}</b>")
        else:
            self.account.setText("Not signed in. Sign in to see and reprice your orders.")
        self.sign_in_button.setVisible(not email)
        self.sign_out_button.setVisible(bool(email))
        self.calc_button.setEnabled(bool(email))
        self.add_button.setEnabled(bool(email))
        self.refresh_button.setEnabled(bool(email))

    def sign_in(self):
        dialog = SignInDialog(self, auth.stored_email() or "")
        if dialog.exec() != QDialog.Accepted:
            return
        email, password = dialog.email.text().strip(), dialog.password.text()
        if not email or not password:
            QMessageBox.warning(self, "Sign in", "Email and password are both required.")
            return
        self.window.run(lambda: auth.sign_in(email, password), lambda _: self.signed_in(),
                        busy="Signing in...")

    def signed_in(self):
        self.refresh_account()
        self.window.status("Signed in.")
        self.refresh_orders()

    def sign_out(self):
        auth.sign_out()
        self.plan = []
        self.fill_table()
        self.refresh_account()
        self.window.status("Signed out. Stored credentials removed.")

    # --- listing and quantities

    def refresh_orders(self, quiet=False):
        """Show the user's current sell orders (no market data needed, so it is quick)."""
        if not auth.has_credentials():
            return
        self.refresh_button.setEnabled(False)
        self.window.run(lambda: repricer.list_orders(auth.get_token()), self.show_listing,
                        busy="Loading your orders...",
                        on_error=(lambda message: self.window.status(f"Could not load your orders: {message}"))
                        if quiet else None,
                        always=lambda: self.refresh_button.setEnabled(auth.has_credentials()))

    def show_listing(self, orders):
        self.plan = orders
        self.fill_table()
        self.window.status(f"{len(orders)} sell orders loaded. Press Calculate prices to see new prices.")

    def on_item_changed(self, item):
        if item.column() == 0:
            self.update_apply_button()
        elif item.column() == 3:
            self.quantity_edited(item)

    def quantity_edited(self, item):
        row = item.row()
        if row >= len(self.plan):
            return
        proposal = self.plan[row]
        try:
            new = int(item.data(Qt.DisplayRole))
        except (TypeError, ValueError):
            new = proposal.quantity
        if new == proposal.quantity:
            return
        if not proposal.order_id:
            self.show_quantity(row, proposal.quantity)
            QMessageBox.information(self, "Quantity", "Press Refresh orders first, then change the quantity.")
            return
        order_id = proposal.order_id
        self.window.run(lambda: repricer.set_quantity(auth.get_token(), order_id, new),
                        lambda _: self.quantity_saved(proposal, row, new),
                        busy=f"Updating the quantity of {proposal.item_name}...",
                        always=lambda: self.show_quantity(row, proposal.quantity))   # runs first: reverts, then saved

    def quantity_saved(self, proposal, row, new):
        proposal.quantity = new
        self.show_quantity(row, new)
        self.window.status(f"{proposal.item_name}: quantity set to {new}.")

    def show_quantity(self, row, value):
        self.table.blockSignals(True)
        self.table.setItem(row, 3, self.quantity_cell(value))
        self.table.blockSignals(False)

    @staticmethod
    def quantity_cell(value):
        item = cell(value)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setToolTip("Double-click to change the quantity")
        return item

    # --- adding an order

    def load_components(self):
        """Fill the dropdown with every Prime component (sets excluded)."""
        self.window.run(lambda: catalog.prime_items(include_sets=False), self.components_ready)

    def components_ready(self, items):
        self.components = {catalog.item_name(i).lower(): i for i in items}
        names = [catalog.item_name(i) for i in items]
        self.new_item.clear()
        self.new_item.addItems(names)
        self.new_item.setCurrentIndex(-1)
        completer = QCompleter(names, self.new_item)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)      # match anywhere in the name, not only the start
        self.new_item.setCompleter(completer)

    def resolve_component(self, text):
        """Typed text -> catalogue item: exact name, else the only component containing the text."""
        wanted = " ".join(text.lower().split())
        if not wanted:
            return None
        if wanted in self.components:
            return self.components[wanted]
        matches = [item for name, item in self.components.items() if wanted in name]
        return matches[0] if len(matches) == 1 else None

    def autofill_item(self):
        item = self.resolve_component(self.new_item.currentText())
        if item:
            self.new_item.setEditText(catalog.item_name(item))

    def add_order(self):
        item = self.resolve_component(self.new_item.currentText())
        if item is None:
            QMessageBox.warning(self, "Add order", "Pick a Prime component from the list. "
                                "Keep typing until only one item matches, or choose it from the dropdown.")
            return
        name = catalog.item_name(item)
        self.new_item.setEditText(name)
        if any(p.slug == item["slug"] for p in self.plan):
            QMessageBox.information(self, "Add order", f"You already have a sell order for {name}. "
                                    "Use Calculate prices to reprice it.")
            return
        quantity, settings = self.new_qty.value(), self.settings()
        self.add_button.setEnabled(False)
        self.window.run(lambda: repricer.suggest_price(item, settings),
                        lambda result: self.confirm_order(item, quantity, *result),
                        busy=f"Working out a price for {name}...",
                        always=lambda: self.add_button.setEnabled(auth.has_credentials()))

    def confirm_order(self, item, quantity, price, note):
        name = catalog.item_name(item)
        answer = QMessageBox.question(
            self, "Add order",
            f"List {quantity} x {name} for {price} platinum each on warframe.market?\n\n{note}.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            self.window.status("No order was created.")
            return
        self.add_button.setEnabled(False)
        def failed(message):
            # the request may have reached warframe.market even though it errored: show what is really there
            QMessageBox.warning(self, "Add order", message)
            self.window.status(message)
            self.refresh_orders(quiet=True)

        self.window.run(lambda: repricer.create_sell_order(auth.get_token(), item, price, quantity),
                        lambda order: self.order_created(item, quantity, price, order),
                        busy=f"Creating the order for {name}...", on_error=failed,
                        always=lambda: self.add_button.setEnabled(auth.has_credentials()))

    def order_created(self, item, quantity, price, order):
        name = catalog.item_name(item)
        if order.get("id"):
            self.plan.append(repricer.Proposal(
                order_id=order["id"], item_name=name, slug=item["slug"], rank=None, subtype=None,
                quantity=quantity, current=price, note="Just listed"))
            self.fill_table()
            self.table.scrollToBottom()
        else:
            self.refresh_orders()
        self.new_item.setCurrentIndex(-1)
        self.new_item.clearEditText()
        self.new_qty.setValue(1)
        self.window.status(f"Listed {quantity} x {name} for {price} platinum.")

    # --- repricing

    def settings(self):
        return repricer.Settings(
            top_n=self.top_n.value(),
            troll_floor=self.troll.value() / 100,
            band_low=self.band_low.value(),
            band_high=self.band_high.value(),
            min_price=self.min_price.value(),
            max_change=self.max_change.value() / 100,
            use_online_fallback=self.fallback.isChecked(),
        )

    def set_busy(self, busy):
        self.calc_button.setEnabled(not busy and auth.has_credentials())
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
            self.apply_button.setEnabled(False)
        else:
            self.update_apply_button()

    def on_progress(self, index, total, name):
        self.progress.setRange(0, total)
        self.progress.setValue(index)
        self.progress.setFormat(f"{index}/{total}  {name}")

    def calculate(self):
        settings = self.settings()

        def job(progress):
            return repricer.build_plan(auth.get_token(), settings, progress=progress)

        self.set_busy(True)
        self.window.run(job, self.show_plan, busy="Reading the market for your orders...",
                        progress=self.on_progress, always=lambda: self.set_busy(False))

    def show_plan(self, plan):
        self.plan = plan
        self.fill_table()
        changes = sum(1 for p in plan if p.changed)
        self.window.status(f"{len(plan)} sell orders checked, {changes} price changes proposed.")

    def fill_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.plan))
        for r, p in enumerate(self.plan):
            check = QTableWidgetItem()
            if p.changed:
                check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                check.setCheckState(Qt.Unchecked if p.flagged else Qt.Checked)
            else:
                check.setFlags(Qt.NoItemFlags)
            self.table.setItem(r, 0, check)
            self.table.setItem(r, 1, cell(p.item_name, color=None if p.visible else BAD))
            self.table.setItem(r, 2, cell(p.variant))
            self.table.setItem(r, 3, self.quantity_cell(p.quantity))
            self.table.setItem(r, 4, cell(p.current))
            self.table.setItem(r, 5, cell(p.proposed if p.changed else None))
            if p.changed:
                diff = p.proposed - p.current
                self.table.setItem(r, 6, cell(f"{diff:+d}", align_right=True, color=GOOD if diff > 0 else BAD))
            else:
                self.table.setItem(r, 6, cell(""))
            failed = p.result.startswith("Failed")
            warn = p.flagged and p.changed and not p.result
            self.table.setItem(r, 7, cell(p.result or p.note, color=BAD if failed else (WARN if warn else (None if p.changed else MUTED))))
        self.table.blockSignals(False)
        self.apply_filter()
        self.update_apply_button()

    def apply_filter(self, *_):
        """Hide rows whose item name or variant doesn't contain every word typed in the search box."""
        words = self.search.text().lower().split()
        for r, p in enumerate(self.plan):
            text = f"{p.item_name} {p.variant or ''}".lower()
            self.table.setRowHidden(r, not all(w in text for w in words))

    def order_menu(self, pos):
        """Right-click menu: hide/show an order on warframe.market, or delete it."""
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self.plan):
            return
        proposal = self.plan[row]
        menu = QMenu(self.table)
        toggle = menu.addAction("Show on warframe.market" if not proposal.visible else "Hide from warframe.market")
        delete = menu.addAction("Delete order...")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is toggle:
            self.toggle_visible(proposal)
        elif chosen is delete:
            self.delete_order(proposal)

    def toggle_visible(self, proposal):
        if not proposal.order_id:
            QMessageBox.information(self, "Order", "Press Refresh orders first.")
            return
        show = not proposal.visible
        order_id = proposal.order_id

        def done(_):
            proposal.visible = show
            self.fill_table()
            self.window.status(f"{proposal.item_name}: now {'visible' if show else 'hidden'} on warframe.market.")
        self.window.run(lambda: repricer.set_visible(auth.get_token(), order_id, show), done,
                        busy=f"{'Showing' if show else 'Hiding'} {proposal.item_name}...")

    def delete_order(self, proposal):
        if not proposal.order_id:
            QMessageBox.information(self, "Order", "Press Refresh orders first.")
            return
        answer = QMessageBox.question(
            self, "Delete order",
            f"Permanently delete your sell order for {proposal.item_name} "
            f"({proposal.quantity} x {proposal.current} platinum) from warframe.market?\n\n"
            "This cannot be undone. Use Hide instead to keep it.")
        if answer != QMessageBox.Yes:
            return
        order_id = proposal.order_id

        def done(_):
            if proposal in self.plan:
                self.plan.remove(proposal)
            self.fill_table()
            self.window.status(f"{proposal.item_name}: order deleted.")
        self.window.run(lambda: repricer.delete_order(auth.get_token(), order_id), done,
                        busy=f"Deleting {proposal.item_name}...")

    def open_item(self, clicked):
        """Double-click on one of my orders -> open that item in the Item orders tab."""
        row = clicked.row()
        if clicked.column() in (0, 3) or row >= len(self.plan):   # tick box and quantity have their own meaning
            return
        proposal = self.plan[row]
        self.window.market_tab.show_item(proposal.item_name, proposal.slug)

    def selected(self):
        return [p for r, p in enumerate(self.plan)
                if p.changed and self.table.item(r, 0) is not None
                and self.table.item(r, 0).checkState() == Qt.Checked]

    def update_apply_button(self, *_):
        count = len(self.selected())
        self.apply_button.setEnabled(count > 0 and not self.progress.isVisible())
        self.apply_button.setText(f"Apply selected ({count})" if count else "Apply selected")

    def apply(self):
        chosen = self.selected()
        if not chosen:
            return
        large = sum(1 for p in chosen if p.flagged)
        extra = f"\n\n{large} of them are large changes you ticked yourself." if large else ""
        answer = QMessageBox.question(
            self, "Update orders",
            f"Change the price of {len(chosen)} order(s) on warframe.market?{extra}",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return

        def job(progress):
            return repricer.apply_plan(auth.get_token(), chosen, progress=progress)

        self.set_busy(True)
        self.window.run(job, lambda done: self.applied(done, len(chosen)), busy="Updating orders...",
                        progress=self.on_progress, always=self.after_apply)

    def after_apply(self):
        self.set_busy(False)
        self.fill_table()

    def applied(self, done, total):
        failed = total - done
        self.window.status(f"{done} order(s) updated" + (f", {failed} failed (see Note column)." if failed else "."))


# ----------------------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Warframe Market Tools")
        self.resize(1080, 700)
        self.pool = QThreadPool.globalInstance()
        self.workers = set()
        self.loaded_tabs = set()

        self.tabs = QTabWidget()
        self.market_tab = MarketTab(self)
        self.top_tab = TopTab(self)
        self.prime_tab = PrimeTab(self)
        self.orders_tab = OrdersTab(self)
        self.tabs.addTab(self.market_tab, "Item orders")
        self.tabs.addTab(self.top_tab, "Top prices")
        self.tabs.addTab(self.prime_tab, "Prime items")
        self.tabs.addTab(self.orders_tab, "My orders")
        self.tabs.currentChanged.connect(self.tab_opened)
        self.setCentralWidget(self.tabs)
        self.status("Loading the item list...")

        # item names feed the search box autocomplete
        self.run(lambda: sorted(catalog.item_name(i) for i in catalog.get_items()),
                 self.items_ready, busy="Loading the item list...")

    def items_ready(self, names):
        self.market_tab.set_item_names(names)
        self.orders_tab.load_components()
        self.orders_tab.refresh_orders(quiet=True)
        self.status(f"Ready. {len(names)} tradable items loaded.")

    def tab_opened(self, _index):
        """Top prices and Prime items load themselves the first time they are opened."""
        tab = self.tabs.currentWidget()
        if tab in (self.top_tab, self.prime_tab) and tab not in self.loaded_tabs:
            self.loaded_tabs.add(tab)
            tab.load()

    def status(self, text):
        self.statusBar().showMessage(text)

    def run(self, fn, on_done, busy=None, progress=None, always=None, on_error=None):
        """Run fn in the background; deliver the result (or a readable error) on the UI thread."""
        worker = Worker(fn, want_progress=progress is not None)
        self.workers.add(worker)   # keep a reference until it finishes

        def finish():
            self.workers.discard(worker)
            if always:
                always()

        def done(result):
            finish()
            on_done(result)

        def failed(message):
            finish()
            if on_error:
                on_error(message)
                return
            self.status(message)
            QMessageBox.warning(self, "Warframe Market Tools", message)

        worker.signals.done.connect(done)
        worker.signals.failed.connect(failed)
        if progress:
            worker.signals.progress.connect(progress)
        if busy:
            self.status(busy)
        self.pool.start(worker)


STYLE = f"""
QWidget {{ font-size: 10pt; }}
QTabWidget::pane {{ border: 1px solid #2c3440; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ padding: 8px 18px; margin-right: 2px; border: 1px solid transparent;
               border-top-left-radius: 6px; border-top-right-radius: 6px; color: #9aa5b5; }}
QTabBar::tab:selected {{ color: #e8ecf1; border-color: #2c3440; border-bottom-color: #1b2028;
                        background: #1b2028; }}
QLineEdit, QComboBox {{ padding: 5px 8px; border: 1px solid #353e4c; border-radius: 5px; background: #151a21; }}
QSpinBox, QDoubleSpinBox {{ padding: 4px 2px 4px 6px; min-width: 70px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
QPushButton {{ padding: 6px 16px; border: 1px solid #3a4454; border-radius: 5px; background: #262e3a; }}
QPushButton:hover {{ background: #2f3948; }}
QPushButton:disabled {{ color: #6b7585; background: #20262f; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #0e1318; font-weight: 600; }}
QPushButton#primary:disabled {{ background: #2a3a47; border-color: #2a3a47; color: #6b7585; }}
QTableWidget, QListWidget {{ border: 1px solid #2c3440; border-radius: 6px; background: #151a21;
               alternate-background-color: #1a2029; }}
QTableWidget::item, QListWidget::item {{ padding: 4px 8px; }}
QHeaderView::section {{ background: #1f2630; color: #9aa5b5; padding: 6px 8px; border: none;
               border-bottom: 1px solid #2c3440; }}
QGroupBox {{ border: 1px solid #2c3440; border-radius: 6px; margin-top: 10px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9aa5b5; }}
QLabel#hint {{ color: #8a94a3; }}
QLabel#summary {{ padding: 4px 0; }}
QProgressBar {{ border: 1px solid #2c3440; border-radius: 5px; text-align: center; background: #151a21; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
"""


def dark_palette():
    palette = QPalette()
    colours = {
        QPalette.Window: "#1b2028", QPalette.WindowText: "#e8ecf1", QPalette.Base: "#151a21",
        QPalette.AlternateBase: "#1a2029", QPalette.Text: "#e8ecf1", QPalette.Button: "#262e3a",
        QPalette.ButtonText: "#e8ecf1", QPalette.Highlight: "#2d6a8c", QPalette.HighlightedText: "#ffffff",
        QPalette.ToolTipBase: "#262e3a", QPalette.ToolTipText: "#e8ecf1", QPalette.PlaceholderText: "#6b7585",
    }
    for role, colour in colours.items():
        palette.setColor(role, QColor(colour))
    return palette


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
