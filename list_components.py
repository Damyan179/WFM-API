"""Kept for compatibility: the logic now lives in wfm/catalog.py."""
from wfm import catalog


def list_items():
    """All Prime items (sets included, as before). The item list is cached for 24 hours."""
    return catalog.prime_items(include_sets=True)
