# sources/router.py
"""
RouterSource: a MetadataSource that routes a URL to the correct concrete source.

It reuses the base MetadataSource.fetch_metadata() loop (clipboard copy,
cover preview, URL dialog, skip/cancel), and overrides only `_fetch_from_url()`
to select a source based on either:
  - a forced choice of available sources, or
  - automatic detection from the URL's hostname ("Auto" mode).
"""

from typing import Any, Dict, Optional

from sources.base import MetadataSource
from sources.loader import load_all_sources
from services.logger import log

load_all_sources()  # Trigger self-registration of all sources

SourceKey = str


class RouterSource(MetadataSource):
    """Route URL-based metadata fetches to chosen source.

    This class subclasses MetadataSource so it can reuse the standard prompt loop
    and dialogs. It only decides *which* source should handle a given URL and
    delegates to that source's `fetch_from_url()`.

    Args:
        parent: Main GUI controller (must expose `root` for dialogs).
        cover_getter: Optional callable returning a PIL.Image.Image for cover preview.
        status_reporter: Optional callable for GUI status/progress updates.
        forced_source: If set, always use this source.
            If None, the source is auto-detected from each entered URL.
    """

    source_key = ""

    def __init__(
        self,
        parent: Any,
        cover_getter=None,
        status_reporter=None,
        forced_source: Optional[SourceKey] = None,
    ) -> None:
        super().__init__(
            parent=parent,
            title="Enter URL",
            cover_getter=cover_getter,
            status_reporter=status_reporter,
        )
        self.forced_source = forced_source
        self._instances: dict[str, MetadataSource] = {}

    def _get_instance(self, key: str) -> MetadataSource | None:
        """Lazy-instantiate source instances on demand."""
        if key not in self._instances:
            cls = MetadataSource._registry.get(key)
            if cls is None:
                log("WARN", f"[Router] No registered source found for key='{key}'")
                return None
            self._instances[key] = cls(
                parent=self.parent,
                cover_getter=self.cover_getter,
                status_reporter=self.status_reporter,
            )
        return self._instances[key]

    @staticmethod
    def detect_source(url: str) -> Optional[SourceKey]:
        """Infer a SourceKey from the URL via registered url_patterns.

        Args:
            url: The URL string to inspect.

        Returns:
            The detected source key, or None if not recognized.
        """
        return MetadataSource.detect_from_url(url)

    def _fetch_from_url(self, url: str) -> Dict[str, str]:
        """Delegate the real fetch to the appropriate concrete source.

        Args:
            url: The user-supplied URL.

        Returns:
            A raw metadata dict on success; {} on failure.
        """
        key = self.forced_source or self.detect_source(url)
        if not key:
            if self.status_reporter:
                self.status_reporter(
                    line2=f"[Router] Could not determine source for URL: {url}",
                    level2="WARN",
                )
            return {}

        src = self._get_instance(key)
        if src is None:
            return {}

        try:
            return src.fetch_from_url(url)
        except Exception:
            log("ERROR", f"[{key}] Error while fetching URL: {url}", exc_info=True)
            if self.status_reporter:
                self.status_reporter(
                    line2=f"[{key}] Error while fetching URL.",
                    level2="NONE",
                )
            return {}
