"""Adaptive HTML selector engine with CSS3, XPath, and ::text/::attr() support.

Extracted from Scrapling (D4Vinci) - MIT License.
Core features:
- CSS3 selectors with ::text and ::attr(NAME) pseudo-elements
- XPath selectors
- ADAPTIVE mode: find elements even after website redesigns
- Element similarity scoring (tag, text, attributes, path, parent, siblings)
- Auto-save/retrieve element fingerprints via SQLite storage
"""

import re
from urllib.parse import urljoin
from difflib import SequenceMatcher
from pathlib import Path

from lxml.html import HtmlElement, HTMLParser
from cssselect import SelectorError, SelectorSyntaxError, parse as split_selectors
from lxml.etree import XPath, tostring, fromstring, XPathError, XPathEvalError

from tools.scraper.translator import css_to_xpath as _css_to_xpath
from tools.scraper.storage import SQLiteStorageSystem, StorageSystemMixin, _StorageTools

_DEFAULT_DB_FILE = str(Path(__file__).parent / "elements_storage.db")

# Pre-compiled XPath selectors for performance
_find_all_elements = XPath(".//*")
_find_all_text_nodes = XPath(".//text()")


def clean_spaces(string: str) -> str:
    """Normalize whitespace: collapse multiple spaces, strip tabs/newlines."""
    _cleaning_table = str.maketrans({"\t": " ", "\n": None, "\r": None})
    _consecutive_spaces = re.compile(r" +")
    s = string.translate(_cleaning_table)
    return _consecutive_spaces.sub(" ", s)


class Selectors(list):
    """A list of Selector objects with convenience methods."""
    
    def get(self, default=None):
        """Return the first element or default."""
        return self[0] if self else default


class Selector:
    """Wraps an lxml HtmlElement node with CSS/XPath selection and adaptive tracking.
    
    Usage:
        sel = Selector("<html>...")  # from HTML string
        sel.css(".product")          # CSS3 selectors
        sel.css(".title::text").get()  # extract text
        sel.xpath("//div[@class='foo']")
        
    Adaptive mode (survives redesigns):
        sel = Selector("<html>...", adaptive=True)
        sel.css(".product", auto_save=True)    # save element fingerprints
        sel.css(".product", adaptive=True)     # find even if CSS changed
    """
    
    def __init__(self, content: str | bytes = None, *, url: str = "",
                 encoding: str = "utf-8", huge_tree: bool = True,
                 root: HtmlElement = None, adaptive: bool = False,
                 storage=SQLiteStorageSystem, storage_args: dict = None):
        self.url = url
        self.encoding = encoding
        self._adaptive_enabled = adaptive
        self._storage = None
        
        if root is not None:
            self._root = root
        elif content is not None:
            parser = HTMLParser(encoding=encoding, huge_tree=huge_tree)
            if isinstance(content, str):
                content = content.encode(encoding)
            self._root = fromstring(content, parser)
        else:
            self._root = fromstring(b"<html><body></body></html>")
        
        if adaptive:
            if storage_args is None:
                storage_args = {}
            storage_file = storage_args.get("storage_file", _DEFAULT_DB_FILE)
            self._storage = storage(storage_file, url=url)
    
    @property
    def text(self) -> str:
        """The text content of this element."""
        if hasattr(self, '_text_value') and self._text_value is not None:
            return str(self._text_value)
        if hasattr(self._root, "text") and self._root.text:
            return self._root.text.strip()
        return tostring(self._root, method="text", encoding=str).strip()
    
    @property
    def attrib(self) -> dict:
        """Element attributes."""
        return dict(self._root.attrib) if hasattr(self._root, "attrib") else {}
    
    @property
    def tag(self) -> str:
        return str(self._root.tag) if hasattr(self._root, "tag") else ""
    
    @property
    def parent(self):
        """Return parent as Selector or None."""
        p = self._root.getparent()
        if p is not None:
            return Selector(root=p, adaptive=self._adaptive_enabled, storage=type(self._storage) if self._storage else None)
        return None
    
    @property
    def children(self):
        """Return child elements as Selectors."""
        return Selectors(
            Selector(root=child, adaptive=self._adaptive_enabled, storage=type(self._storage) if self._storage else None)
            for child in self._root.iterchildren()
            if not isinstance(child, HtmlElement.HtmlComment)
        )
    
    @property
    def html_content(self) -> str:
        """Inner HTML as string."""
        return tostring(self._root, encoding=str)
    
    def text_content(self) -> str:
        """Extract text content from element."""
        if hasattr(self, '_text_value') and self._text_value is not None:
            return str(self._text_value)
        return tostring(self._root, method="text", encoding=str).strip()
    
    def _is_text_node(self, element) -> bool:
        return not isinstance(element, HtmlElement)
    
    def css(self, selector: str, *, identifier: str = "",
            adaptive: bool = False, auto_save: bool = False,
            percentage: int = 0) -> Selectors:
        """Find elements matching a CSS3 selector.
        
        Supports ::text and ::attr(NAME) pseudo-elements.
        When adaptive=True, relocates elements from saved fingerprints.
        When auto_save=True, saves element fingerprints for future adaptive use.
        """
        if self._is_text_node(self._root):
            return Selectors()
        
        try:
            if not self._adaptive_enabled or "," not in selector:
                xpath = _css_to_xpath(selector)
                return self._xpath_query(xpath, identifier or selector, adaptive, auto_save, percentage)
            
            results = Selectors()
            for single_sel in split_selectors(selector):
                xpath = _css_to_xpath(single_sel.canonical())
                results += self._xpath_query(xpath, identifier or single_sel.canonical(), adaptive, auto_save, percentage)
            return Selectors(results)
        except (SelectorError, SelectorSyntaxError) as e:
            raise SelectorSyntaxError(f"Invalid CSS selector '{selector}': {e}") from e
    
    def xpath(self, selector: str, *, identifier: str = "",
              adaptive: bool = False, auto_save: bool = False,
              percentage: int = 0, **kwargs) -> Selectors:
        """Find elements matching an XPath expression."""
        if self._is_text_node(self._root):
            return Selectors()
        return self._xpath_query(selector, identifier or selector, adaptive, auto_save, percentage, **kwargs)
    
    def _xpath_query(self, selector: str, identifier: str,
                     adaptive: bool, auto_save: bool, percentage: int, **kwargs) -> Selectors:
        try:
            elements = self._root.xpath(selector, **kwargs)
            
            if elements:
                if self._adaptive_enabled and auto_save and elements:
                    self.save(elements[0], identifier)
                return self._wrap_elements(elements)
            elif self._adaptive_enabled and adaptive:
                element_data = self.retrieve(identifier)
                if element_data:
                    relocated = self.relocate(element_data, percentage)
                    if relocated and auto_save:
                        self.save(relocated[0], identifier)
                    return self._wrap_elements(relocated or [])
            return Selectors()
        except (SelectorError, SelectorSyntaxError, XPathError, XPathEvalError) as e:
            raise SelectorSyntaxError(f"XPath error: {selector}") from e
    
    def _wrap_elements(self, elements) -> Selectors:
        """Wrap lxml elements into Selectors, handling text nodes."""
        results = []
        for el in elements:
            if isinstance(el, (str, bytes)):
                # Text node or attribute value result from ::text or ::attr()
                text_sel = Selector.__new__(Selector)
                text_sel._root = self._root
                text_sel._adaptive_enabled = self._adaptive_enabled
                text_sel._storage = self._storage
                text_sel._text_value = str(el)
                text_sel.__dict__["_text_value"] = str(el)
                results.append(text_sel)
            elif isinstance(el, HtmlElement):
                el_sel = Selector.__new__(Selector)
                el_sel._root = el
                el_sel._adaptive_enabled = self._adaptive_enabled
                el_sel._storage = type(self._storage)(self._storage.storage_file) if self._storage else None
                if el_sel._storage is not None:
                    el_sel._storage = type(self._storage)(self._storage.storage_file)
                results.append(el_sel)
            else:
                # Fallback: try to treat as element
                try:
                    el_sel = Selector.__new__(Selector)
                    el_sel._root = el
                    el_sel._adaptive_enabled = self._adaptive_enabled
                    el_sel._storage = self._storage
                    results.append(el_sel)
                except:
                    pass
        return Selectors(results)
    
    def find_all(self, *args, **kwargs) -> Selectors:
        """Find elements by filters (tag name, attributes, etc.)
        
        Similar to BeautifulSoup's find_all. Pass tag name(s), dict of attributes,
        or keyword arguments.
        Example: find_all('a', class_='title')
        """
        tag = None
        attrs = {}
        
        for arg in args:
            if isinstance(arg, str):
                tag = arg
        
        # Handle class_ -> class conversion
        for k, v in kwargs.items():
            key = k.rstrip("_") if k.endswith("_") and k.rstrip("_") in ["class", "for"] else k
            attrs[key] = v
        
        if tag:
            selector = tag
            for k, v in attrs.items():
                selector += f"[{k}='{v}']"
            return self.css(selector)
        
        xpath_parts = [".//*"]
        for k, v in attrs.items():
            xpath_parts.append(f"[@{{k}}='{{v}}']")
        return self._xpath_query("".join(xpath_parts), "", False, False, 0)
    
    def find(self, *args, **kwargs) -> "Selector | None":
        """Like find_all but returns first match or None."""
        for el in self.find_all(*args, **kwargs):
            return el
        return None
    
    # === ADAPTIVE ENGINE ===
    
    def relocate(self, element, percentage: int = 0, selector_type: bool = False):
        """Search the entire page tree for elements similar to the given one.
        
        Uses intelligent scoring: tag, text, attributes, path, parent, siblings.
        Returns elements with the highest similarity score.
        """
        score_table = {}
        
        if isinstance(element, Selector):
            element = element._root
        if isinstance(element, HtmlElement):
            element = _StorageTools.element_to_dict(element)
        
        for node in _find_all_elements(self._root):
            score = self._calculate_similarity_score(element, node)
            score_table.setdefault(score, []).append(node)
        
        if score_table:
            highest = max(score_table.keys())
            if highest >= percentage:
                if selector_type:
                    return self._wrap_elements(score_table[highest])
                return score_table[highest]
        return []
    
    def _calculate_similarity_score(self, original: dict, candidate: HtmlElement) -> float:
        """Score how similar a candidate element is to the original.
        
        Factors: tag name, text content, attributes (class/id/href/src),
        DOM path, parent info, sibling context.
        """
        score = 0.0
        checks = 0
        data = _StorageTools.element_to_dict(candidate)
        
        # Tag match
        score += 1 if original["tag"] == data["tag"] else 0
        checks += 1
        
        # Text similarity
        if original["text"]:
            score += SequenceMatcher(None, original["text"], data.get("text") or "").ratio()
            checks += 1
        
        # Attribute similarity
        score += self._dict_diff(original["attributes"], data["attributes"])
        checks += 1
        
        # Key attribute similarity (class, id, href, src)
        for attr in ("class", "id", "href", "src"):
            if original["attributes"].get(attr):
                score += SequenceMatcher(
                    None,
                    original["attributes"][attr],
                    data["attributes"].get(attr) or "",
                ).ratio()
                checks += 1
        
        # DOM path similarity
        score += SequenceMatcher(None, original["path"], data["path"]).ratio()
        checks += 1
        
        # Parent context
        if original.get("parent_name"):
            if data.get("parent_name"):
                score += SequenceMatcher(None, original["parent_name"], data.get("parent_name") or "").ratio()
                checks += 1
                score += self._dict_diff(original["parent_attribs"], data.get("parent_attribs") or {})
                checks += 1
                if original["parent_text"]:
                    score += SequenceMatcher(None, original["parent_text"], data.get("parent_text") or "").ratio()
                    checks += 1
        
        # Sibling context
        if original.get("siblings"):
            score += SequenceMatcher(None, original["siblings"], data.get("siblings") or []).ratio()
            checks += 1
        
        return round((score / checks) * 100, 2) if checks > 0 else 0.0
    
    @staticmethod
    def _dict_diff(d1: dict, d2: dict) -> float:
        """Score similarity between two attribute dicts."""
        score = SequenceMatcher(None, tuple(d1.keys()), tuple(d2.keys())).ratio() * 0.5
        score += SequenceMatcher(None, tuple(d1.values()), tuple(d2.values())).ratio() * 0.5
        return score
    
    def save(self, element: HtmlElement, identifier: str):
        """Save element fingerprint to storage for adaptive relocation later."""
        if self._adaptive_enabled and self._storage:
            target = element
            if isinstance(target, Selector):
                target = target._root
            self._storage.save(target, identifier)
        else:
            raise RuntimeError("Adaptive mode not enabled on this Selector instance")
    
    def retrieve(self, identifier: str) -> dict | None:
        """Retrieve saved element fingerprint by identifier."""
        if self._adaptive_enabled and self._storage:
            return self._storage.retrieve(identifier)
        raise RuntimeError("Adaptive mode not enabled on this Selector instance")
    
    def json(self) -> dict:
        """Parse response body as JSON."""
        import json as _json
        if self._is_text_node(self._root):
            return _json.loads(str(self._root))
        text = self.text_content()
        if text:
            return _json.loads(text)
        return {}
    
    def re(self, pattern: str, *, case_sensitive: bool = True) -> list:
        """Apply regex to element text."""
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.findall(pattern, self.text_content(), flags)
    
    def re_first(self, pattern: str, default=None, *, case_sensitive: bool = True):
        """Apply regex, return first match or default."""
        matches = self.re(pattern, case_sensitive=case_sensitive)
        return matches[0] if matches else default
    
    def __repr__(self):
        if hasattr(self, '_text_value') and self._text_value is not None:
            return f"'{str(self._text_value)[:80]}'"
        text = self.text_content()[:80]
        return f"<Selector {self.tag} '{text}...'>" if text else f"<Selector {self.tag}>"
    
    def __bool__(self):
        return True if self._root is not None else False


def from_html(html: str | bytes, *, url: str = "", adaptive: bool = False) -> Selector:
    """Quick-create a Selector from HTML content."""
    return Selector(html, url=url, adaptive=adaptive)


def fetch_and_parse(url: str, *, headless: bool = True, 
                    impersonate: str = "chrome145",
                    timeout: int = 30) -> Selector:
    """Fetch a URL with TLS fingerprint spoofing and return parsed Selector.
    
    Uses curl_cffi for HTTP-level spoofing (fast, no browser).
    For JS-rendered pages, use playwright_fetch_and_parse() instead.
    """
    from curl_cffi.requests import Session
    session = Session(impersonate=impersonate, timeout=timeout)
    resp = session.get(url, headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    })
    resp.raise_for_status()
    return Selector(resp.content, url=url)


def playwright_fetch_and_parse(url: str, *, headless: bool = True,
                                timeout: int = 30000,
                                solve_cloudflare: bool = False,
                                wait_for_selector: str = None) -> Selector:
    """Fetch a JS-rendered page using Playwright and return parsed Selector.
    
    Uses official Playwright (NOT patchright) with stealth flags.
    Optionally solves Cloudflare Turnstile challenges.
    """
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
                "--disable-dev-shm-usage",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()
        
        # Stealth via JS injection (replaces patchright's driver-level patches)
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)
        
        page.goto(url, wait_until="networkidle" if headless else "load",
                  timeout=timeout)
        
        if solve_cloudflare:
            _solve_cloudflare(page)
        
        if wait_for_selector:
            page.wait_for_selector(wait_for_selector, timeout=10000)
        
        content = page.content()
        page_url = page.url
        browser.close()
    
    return Selector(content, url=page_url)


def _solve_cloudflare(page):
    """Solve Cloudflare Turnstile/interstitial challenges."""
    import re as _re
    from random import randint
    
    cf_pattern = _re.compile(r"^https?://challenges\.cloudflare\.com/cdn-cgi/challenge-platform/.*")
    
    page.wait_for_timeout(5000)
    content = page.content()
    
    if "<title>Just a moment...</title>" in content:
        # Non-interactive challenge
        while "<title>Just a moment...</title>" in page.content():
            page.wait_for_timeout(1000)
            page.wait_for_load_state()
        return
    
    # Detect turnstile type
    if "Verifying you are human" in content:
        while "Verifying you are human" in page.content():
            page.wait_for_timeout(500)
    
    # Try to find and click the Cloudflare iframe
    iframe = page.frame(url=cf_pattern)
    if iframe:
        page.wait_for_timeout(1000)
        box = iframe.frame_element().bounding_box()
        if box:
            x, y = box["x"] + randint(26, 28), box["y"] + randint(25, 27)
            page.mouse.click(x, y, delay=randint(100, 200), button="left")
            page.wait_for_timeout(2000)
            return
    
    # Fallback: find turnstile container
    for sel in ["#cf_turnstile div", "#cf-turnstile div", ".turnstile>div>div", ".main-content p+div>div>div"]:
        try:
            box = page.locator(sel).last.bounding_box()
            if box:
                x, y = box["x"] + randint(26, 28), box["y"] + randint(25, 27)
                page.mouse.click(x, y, delay=randint(100, 200), button="left")
                page.wait_for_timeout(2000)
                return
        except:
            pass
