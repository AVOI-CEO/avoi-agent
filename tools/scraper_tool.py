#!/usr/bin/env python3
"""
Migo Scraper Tool — stealth web scraping with adaptive element tracking.

Provides two main tools:
1. scraper_fetch — HTTP-level fetch with TLS fingerprint spoofing (fast, no browser)
2. scraper_scrape — Headless browser fetch with stealth, optional Cloudflare bypass,
   adaptive CSS selectors, and structured data extraction

Uses the Migo Scraper module (tools/scraper/) which is extracted and adapted from
Scrapling (D4Vinci, MIT License) with these dependency replacements:
  - patchright → official Playwright + JS injection stealth
  - browserforge → hardcoded browser fingerprints
  - orjson → stdlib json
  - msgspec → plain dicts
  - tld → removed
"""

import logging
import json
import re
from urllib.parse import urlparse

from tools.registry import registry, tool_error
from tools.scraper.parser import (
    Selector,
    from_html,
    fetch_and_parse,
    playwright_fetch_and_parse,
)
from tools.scraper.constants import BROWSER_FINGERPRINTS

logger = logging.getLogger(__name__)

# ============================================================================
# Tool Schemas
# ============================================================================

SCRAPER_TOOL_SCHEMAS = [
    {
        "name": "scraper_fetch",
        "description": "Fast HTTP-level page fetch with TLS fingerprint spoofing (browser fingerprinting). "
                       "No browser overhead — use for static HTML pages, REST APIs returning HTML, or "
                       "sites without heavy JavaScript rendering.  Bypasses basic anti-bot protection. "
                       "For JS-rendered sites, use scraper_scrape instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch (e.g., 'https://old.reddit.com/r/LocalLLaMA/')"
                },
                "extract": {
                    "type": "string",
                    "description": "Optional CSS selector to extract specific content (e.g., '.thing', 'h1'). "
                                   "Returns structured data. Supports ::text and ::attr(href) pseudo-elements.",
                    "default": ""
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items to return when extract is a list selector (default: 10, 0 = all)",
                    "default": 10
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                    "default": 30
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "scraper_scrape",
        "description": "Headless browser page fetch with stealth anti-detection, JavaScript rendering, "
                       "optional Cloudflare Turnstile solving, and adaptive CSS selectors. "
                       "Use for JS-heavy sites, Cloudflare-protected pages, SPAs, or when you need "
                       "to extract content that requires JavaScript execution.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to scrape"
                },
                "extract": {
                    "type": "string",
                    "description": "Optional CSS selector to extract specific content. "
                                   "Supports ::text and ::attr(href) pseudo-elements.",
                    "default": ""
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items to return when extract is a list selector (default: 10, 0 = all)",
                    "default": 10
                },
                "solve_cloudflare": {
                    "type": "boolean",
                    "description": "Attempt to solve Cloudflare Turnstile/interstitial challenges "
                                   "(default: false, set true for Cloudflare-protected sites)",
                    "default": False
                },
                "adaptive": {
                    "type": "boolean",
                    "description": "Enable adaptive element tracking — if the CSS selector fails, "
                                   "attempt to relocate elements by structural similarity "
                                   "(survives website redesigns). Requires prior auto_save=True call.",
                    "default": False
                },
                "auto_save": {
                    "type": "boolean",
                    "description": "Save element fingerprints for future adaptive relocation. "
                                   "Use on first scrape, then subsequent calls can use adaptive=True.",
                    "default": False
                },
                "wait_for": {
                    "type": "string",
                    "description": "Wait for a specific CSS selector to appear before extracting "
                                   "(useful for lazy-loaded content)",
                    "default": ""
                },
                "timeout": {
                    "type": "integer",
                    "description": "Navigation timeout in milliseconds (default: 30000)",
                    "default": 30000
                }
            },
            "required": ["url"]
        }
    },
]


# ============================================================================
# Handler Functions
# ============================================================================

def _check_scraper_requirements():
    """Check that at least curl_cffi is available for scraper_fetch."""
    missing = []
    try:
        import curl_cffi  # noqa
    except ImportError:
        missing.append("curl_cffi (for TLS fingerprint spoofing)")
    
    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}. Install with: pip install curl_cffi"
    return True, None


def _check_browser_requirements():
    """Check that Playwright is available for scraper_scrape."""
    missing = []
    try:
        import playwright  # noqa
    except ImportError:
        missing.append("playwright")
    
    if missing:
        return False, f"Missing dependencies: {', '.join(missing)}. Install with: pip install playwright && python3 -m playwright install chromium"
    return True, None


def _format_result_as_text(title, items, limit=10):
    """Format extracted items as readable text."""
    if not items:
        return f"No results found for '{title}'."
    
    text = ""
    if isinstance(items, list):
        count = len(items)
        text = f"Found {count} items"
        if limit and count > limit:
            items = items[:limit]
            text += f" (showing first {limit})"
        text += ":\n\n"
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                text += f"  {i}. {json.dumps(item, indent=2)}\n\n"
            else:
                text += f"  {i}. {item}\n\n"
    else:
        text = str(items)
    
    return text


def _scraper_fetch_handler(args, **kwargs):
    """
    Fast HTTP-level page fetch with TLS fingerprint spoofing.
    Uses curl_cffi with Chrome 145 impersonation.
    """
    url = args.get("url", "")
    extract = args.get("extract", "")
    limit = args.get("limit", 10)
    timeout = args.get("timeout", 30)
    
    if not url:
        return tool_error("URL is required")
    
    try:
        sel = fetch_and_parse(url, timeout=timeout)
        result = _extract_and_format(sel, extract, limit, url)
        return result
    except Exception as e:
        return tool_error(f"Fetch failed for {url}: {e}")


def _scraper_scrape_handler(args, **kwargs):
    """
    Headless browser fetch with stealth, Cloudflare bypass, adaptive selectors.
    Uses official Playwright (not patchright) with JS injection stealth.
    """
    url = args.get("url", "")
    extract = args.get("extract", "")
    limit = args.get("limit", 10)
    solve_cf = args.get("solve_cloudflare", False)
    adaptive = args.get("adaptive", False)
    auto_save = args.get("auto_save", False)
    wait_for = args.get("wait_for", "")
    timeout = args.get("timeout", 30000)
    
    if not url:
        return tool_error("URL is required")
    
    try:
        sel = playwright_fetch_and_parse(
            url,
            headless=True,
            timeout=timeout,
            solve_cloudflare=solve_cf,
            wait_for_selector=wait_for,
        )
        result = _extract_and_format(sel, extract, limit, url, adaptive=adaptive, auto_save=auto_save)
        return result
    except Exception as e:
        return tool_error(f"Scrape failed for {url}: {e}")


def _extract_and_format(sel: Selector, extract: str, limit: int, url: str,
                        adaptive: bool = False, auto_save: bool = False) -> str:
    """Extract content by CSS selector and format for the agent."""
    parts = [f"📄 Page: {url}"]
    parts.append(f"   Title: {sel.css('title::text').get() or 'N/A'}")
    parts.append(f"   Size: {len(sel.text_content())} chars")
    
    if extract:
        try:
            items = sel.css(extract, adaptive=adaptive, auto_save=auto_save)
            if items:
                count = len(items)
                truncated = limit > 0 and count > limit
                show = items[:limit] if truncated else items
                
                parts.append(f"\n🎯 Extracted {count} items via '{extract}'" + 
                             (f" (showing first {limit})" if truncated else ""))
                
                for i, item in enumerate(show, 1):
                    text = item.text_content().strip()[:200]
                    if text:
                        parts.append(f"  {i}. {text}")
            else:
                parts.append(f"\nNo matches for selector '{extract}'")
        except Exception as e:
            parts.append(f"\n⚠️  Selector error: {e}")
    
    # Also show key links if no specific extract
    if not extract:
        links = sel.css("a[href]")
        if links:
            shown = 0
            parts.append("\n🔗 Key links:")
            for link in links:
                href = link.attrib.get("href", "")
                text = (link.text_content().strip() or href)[:80]
                if href and not href.startswith("#") and not href.startswith("javascript:"):
                    parts.append(f"  • {text} -> {href}")
                    shown += 1
                    if shown >= 15:
                        break
    
    return "\n".join(parts)


# ============================================================================
# Registry
# ============================================================================

registry.register(
    name="scraper_fetch",
    toolset="scraper",
    schema=SCRAPER_TOOL_SCHEMAS[0],
    handler=_scraper_fetch_handler,
    check_fn=_check_scraper_requirements,
    emoji="⚡",
)

registry.register(
    name="scraper_scrape",
    toolset="scraper",
    schema=SCRAPER_TOOL_SCHEMAS[1],
    handler=_scraper_scrape_handler,
    check_fn=_check_browser_requirements,
    emoji="🕵️",
)
