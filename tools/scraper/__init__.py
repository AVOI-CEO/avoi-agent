# Migo Scraper Module
# Extracted and adapted from Scrapling (D4Vinci) - MIT License
# 
# Replaces: patchright -> official Playwright
#           browserforge -> hardcoded fingerprints
#           orjson -> stdlib json
#           msgspec -> plain dataclasses
#           tld -> removed (optional)
#
# Core dependencies: lxml, cssselect, curl_cffi, playwright, sqlite3 (stdlib)

from tools.scraper.parser import Selector, from_html, fetch_and_parse, playwright_fetch_and_parse
from tools.scraper.storage import SQLiteStorageSystem, _StorageTools

__all__ = [
    "Selector",
    "from_html",
    "fetch_and_parse",
    "playwright_fetch_and_parse",
    "SQLiteStorageSystem",
    "_StorageTools",
]
