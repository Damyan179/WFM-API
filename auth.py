"""Kept for compatibility: the logic now lives in the wfm package (wfm/auth.py, wfm/repricer.py).

Running this file previews new prices for your sell orders and asks before applying them.
"""
import getpass

from wfm.auth import get_credentials, get_token, login, save_credentials, sign_in  # noqa: F401
from wfm.repricer import pick_price  # noqa: F401


def setup_credentials():
    """One-time prompt; the password is not echoed and is verified before it is stored."""
    email = input("warframe.market email: ").strip()
    password = getpass.getpass("Password: ")
    if not email or not password:
        raise SystemExit("Email and password are required.")
    sign_in(email, password)
    print("Credentials saved to Windows Credential Manager.")


if __name__ == "__main__":
    from main import reprice
    reprice(get_token())
