#sources/_template.py

"""
Template metadata source for MyMangaTagger.

How to use this template:
    1. Copy this file to a new module in the same folder, for example
       `mysource.py`.
    2. Rename `TemplateClient` and `TemplateSource` to match the new source.
    3. Set a unique `source_key`.
    4. Set a human-friendly `source_name` for the GUI.
    5. Update `url_patterns` so Auto mode can detect the source from URLs.
    6. Implement the client fetch/parsing logic.
    7. Update `_map_meta()` so the returned metadata matches the fields
       your source can provide.
    8. Save the file. The source will be auto-discovered by `load_all_sources()`
       because all source modules in `sources/` are imported automatically,
       except files that start with `_`.

Notes:
    - This file is intentionally named with a leading underscore so the loader
      ignores it.
    - Metadata keys returned by the source should use lowercase field names.
    - Always return an empty dict on failure instead of raising exceptions from
      `_fetch_from_url()`.
"""

from typing import Any, Callable, Dict, Optional

from services.logger import log
from sources.base import MetadataSource, SourceFetchError


class TemplateClient:
    """Template client for a metadata source.

    This class is responsible for source-specific fetching, parsing, and light
    normalization before the data is handed to the MetadataSource adapter.

    Replace this class with the real implementation for the new source.
    """

    def fetch(self, url: str) -> Dict[str, str]:
        """Fetch and return raw metadata for a single URL.

        Args:
            url: The source URL entered by the user.

        Returns:
            A dictionary containing source-specific raw metadata.

        Raises:
            SourceFetchError: Raised for expected fetch or parse failures.
        """
        raise SourceFetchError("TemplateClient.fetch() has not been implemented yet.")


class TemplateSource(MetadataSource):
    """Template MetadataSource adapter.

    This class connects a source-specific client to the shared MyMangaTagger
    source system. It participates in automatic source registration through
    `MetadataSource`, supports URL auto-detection through `url_patterns`, and
    maps fetched data into ComicInfo-compatible lowercase field names.
    """

    source_key = "template"
    source_name = "Template Source"
    url_patterns = [
        "example.com/title/",
        "example.com/item/",
    ]
    dialog_title = "Fetch metadata from Template Source"

    def __init__(
        self,
        parent: Any,
        cover_getter: Optional[Callable[..., Any]] = None,
        status_reporter: Optional[Callable[..., None]] = None,
    ) -> None:
        """Initialize the template source.

        Args:
            parent: Main GUI controller. Must expose `root` for dialogs.
            cover_getter: Optional callable used to get a cover preview image.
            status_reporter: Optional callable for GUI status/progress updates.
        """
        super().__init__(
            parent=parent,
            title=self.dialog_title,
            cover_getter=cover_getter,
            status_reporter=status_reporter,
        )
        self._client = TemplateClient()

    def _fetch_from_url(self, url: str) -> Dict[str, str]:
        """Fetch metadata from a single URL and map it to app fields.

        This method should never raise exceptions outward. Expected source
        failures should be logged as warnings. Unexpected failures should be
        logged as errors. In both cases, return an empty dict.

        Args:
            url: The source URL entered by the user.

        Returns:
            A metadata dictionary using lowercase ComicInfo-compatible keys,
            or an empty dict on failure.
        """
        try:
            raw = self._client.fetch(url)
            return self._map_meta(raw, url)
        except SourceFetchError as exc:
            log("WARN", str(exc))
        except Exception:
            log("ERROR", f"[{self.source_key}] Unexpected error for URL: {url}", exc_info=True)
        return {}

    def _map_meta(self, raw: Dict[str, str], url: str) -> Dict[str, str]:
        """Map source-specific raw metadata to app metadata fields.

        Update this method so the returned dict only contains the fields your
        source can provide.

        Common field names include:
            - title
            - series
            - localizedseries
            - number
            - count
            - summary
            - year
            - month
            - day
            - writer
            - publisher
            - imprint
            - genre
            - tags
            - web
            - seriesgroup
            - languageiso
            - agerating
            - penciller
            - inker
            - coverartist
            - letterer

        Args:
            raw: Raw metadata returned by the client.
            url: Original source URL. Can be used as a fallback for `web`.

        Returns:
            A dictionary containing lowercase ComicInfo-compatible field names.
        """
        return {
            "title": raw.get("title", ""),
            "series": raw.get("series", ""),
            "localizedseries": raw.get("localizedseries", ""),
            "number": raw.get("number", ""),
            "count": raw.get("count", ""),
            "summary": raw.get("summary", ""),
            "year": raw.get("year", ""),
            "month": raw.get("month", ""),
            "day": raw.get("day", ""),
            "writer": raw.get("writer", ""),
            "publisher": raw.get("publisher", ""),
            "imprint": raw.get("imprint", ""),
            "genre": raw.get("genre", ""),
            "tags": raw.get("tags", ""),
            "web": raw.get("web", "") or url,
            "seriesgroup": raw.get("seriesgroup", ""),
            "languageiso": raw.get("languageiso", ""),
            "agerating": raw.get("agerating", ""),
            "penciller": raw.get("penciller", ""),
            "inker": raw.get("inker", ""),
            "coverartist": raw.get("coverartist", ""),
            "letterer": raw.get("letterer", ""),
        }