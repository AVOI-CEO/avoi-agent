"""SQLite-based storage for adaptive element tracking.

Extracted from Scrapling (D4Vinci) - MIT License.
Uses stdlib json instead of orjson to eliminate the dependency.
"""

import json
import sqlite3
from hashlib import sha256
from threading import RLock
from functools import lru_cache
from abc import ABC, abstractmethod
from lxml.html import HtmlElement


class _StorageTools:
    """Converts lxml HtmlElements to/from dicts for similarity comparison."""

    @staticmethod
    def _clean_attributes(element: HtmlElement, forbidden: tuple = ()) -> dict:
        if not element.attrib:
            return {}
        return {k: v.strip() for k, v in element.attrib.items()
                if v and v.strip() and k not in forbidden}

    @classmethod
    def element_to_dict(cls, element: HtmlElement) -> dict:
        """Serialize an lxml element to a dict for storage/comparison."""
        parent = element.getparent()
        result = {
            "tag": str(element.tag),
            "attributes": cls._clean_attributes(element),
            "text": element.text.strip() if element.text else None,
            "path": cls._get_element_path(element),
        }
        if parent is not None:
            result.update({
                "parent_name": parent.tag,
                "parent_attribs": dict(parent.attrib),
                "parent_text": parent.text.strip() if parent.text else None,
            })
            siblings = [child.tag for child in parent.iterchildren() if child != element]
            if siblings:
                result.update({"siblings": tuple(siblings)})

        children = [child.tag for child in element.iterchildren()
                    if not isinstance(child, HtmlElement.HtmlComment)]
        if children:
            result.update({"children": tuple(children)})

        return result

    @classmethod
    def _get_element_path(cls, element: HtmlElement):
        parent = element.getparent()
        return tuple((element.tag,) if parent is None
                     else (cls._get_element_path(parent) + (element.tag,)))


class StorageSystemMixin(ABC):
    """Abstract base for storage backends used by adaptive element tracking."""

    def __init__(self, url: str | None = None):
        self.url = url.lower() if (url and isinstance(url, str)) else None

    @staticmethod
    @lru_cache(128, typed=True)
    def _get_hash(identifier: str) -> str:
        _id = identifier.lower().strip().encode("utf-8")
        h = sha256(_id).hexdigest()
        return f"{h}_{len(_id)}"

    @abstractmethod
    def save(self, element: HtmlElement, identifier: str) -> None:
        ...

    @abstractmethod
    def retrieve(self, identifier: str) -> dict | None:
        ...


@lru_cache(1, typed=True)
class SQLiteStorageSystem(StorageSystemMixin):
    """Thread-safe SQLite storage for adaptive element fingerprints."""

    def __init__(self, storage_file: str, url: str | None = None):
        super().__init__(url)
        self.storage_file = storage_file
        self.lock = RLock()
        self.connection = sqlite3.connect(self.storage_file, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.cursor = self.connection.cursor()
        self._setup_database()

    def _setup_database(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS storage (
                id INTEGER PRIMARY KEY,
                identifier_hash TEXT UNIQUE NOT NULL,
                identifier TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_identifier_hash ON storage(identifier_hash)
        """)
        self.connection.commit()

    def save(self, element: HtmlElement, identifier: str):
        data = _StorageTools.element_to_dict(element)
        h = self._get_hash(identifier)
        with self.lock:
            self.cursor.execute(
                "INSERT OR REPLACE INTO storage (identifier_hash, identifier, data) VALUES (?, ?, ?)",
                (h, identifier, json.dumps(data)),
            )
            self.connection.commit()

    def retrieve(self, identifier: str) -> dict | None:
        h = self._get_hash(identifier)
        with self.lock:
            self.cursor.execute(
                "SELECT data FROM storage WHERE identifier_hash = ?", (h,)
            )
            row = self.cursor.fetchone()
            if row:
                return json.loads(row[0])
        return None

    def close(self):
        self.connection.close()
