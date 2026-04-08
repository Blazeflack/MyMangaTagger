# sources/mangabaka.py

"""MangaBaka metadata source for MyMangaTagger.

Provides two classes:
  - MangaBakaClient: Lightweight REST client that fetches and normalizes
    raw manga metadata from the MangaBaka API.
  - MangaBakaSource: MetadataSource adapter that maps MangaBakaClient output
    to ComicInfo-compatible fields and integrates with the fetch/dialog loop.
"""

import html
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from services.constants import PUBLISHER_DOMAIN_MAP
from services.logger import log
from services.normalization import Normalizer
from sources.base import MetadataSource, SourceFetchError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MANGABAKA_API_BASE = "https://api.mangabaka.dev"
_MANGABAKA_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class MangaBakaClient:
    """Lightweight REST client for fetching manga metadata from MangaBaka.

    Handles network I/O, response parsing, and light normalization.
    Consumers receive a flat dict of normalized fields ready for mapping
    into ComicInfo format by MangaBakaSource.

    Attributes:
        normalizer: Shared Normalizer instance for light text cleanup.
    """

    def __init__(self) -> None:
        """Initialize the MangaBaka client."""
        self.normalizer = Normalizer()

    def fetch(self, url: str) -> Dict[str, str]:
        """Fetch and normalize raw metadata from a MangaBaka URL.

        Args:
            url: MangaBaka series page URL, for example
                ``https://mangabaka.org/7546?q=Toradora&single_result_redirect=1``.

        Returns:
            A dict of normalized metadata fields using lowercase keys.

        Raises:
            SourceFetchError: If the series ID cannot be extracted, the request
                fails, or the response does not contain valid series data.
        """
        series_id = self._extract_id(url)
        if series_id is None:
            raise SourceFetchError(
                f"[MangaBaka] Could not extract series ID from URL: {url}"
            )

        series = self._fetch_series(series_id)

        # If the series was merged, follow the canonical replacement ID.
        if (
            isinstance(series, dict)
            and series.get("state") == "merged"
            and series.get("merged_with")
        ):
            merged_with = series.get("merged_with")
            try:
                merged_id = int(merged_with)
            except (TypeError, ValueError) as exc:
                raise SourceFetchError(
                    f"[MangaBaka] Invalid merged series ID for URL: {url}"
                ) from exc

            log("INFO", f"[MangaBaka] Series {series_id} merged into {merged_id}. Refetching.")
            series = self._fetch_series(merged_id)

        return self._parse(series)

    def _fetch_series(self, series_id: int) -> Dict[str, Any]:
        """Fetch a single MangaBaka series object from the API.

        Args:
            series_id: Numeric MangaBaka series ID.

        Returns:
            The raw ``data`` object from the MangaBaka API response.

        Raises:
            SourceFetchError: On request failure or invalid response payload.
        """
        api_url = f"{_MANGABAKA_API_BASE}/v1/series/{series_id}"

        try:
            log("DEBUG", f"[MangaBaka] GET -> {api_url}")
            response = requests.get(api_url, timeout=_MANGABAKA_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise SourceFetchError(
                f"[MangaBaka] Network/HTTP error for id={series_id}"
            ) from exc

        if not isinstance(payload, dict):
            raise SourceFetchError(
                f"[MangaBaka] Invalid response payload for id={series_id}"
            )

        status = payload.get("status")
        data = payload.get("data")
        message = payload.get("message")

        if status != 200 or not isinstance(data, dict):
            message_text = self.normalizer.normalize_whitespace(str(message or "Unknown API error"))
            raise SourceFetchError(
                f"[MangaBaka] API returned an invalid response for id={series_id}: {message_text}"
            )

        return data

    def _parse(self, series: Dict[str, Any]) -> Dict[str, str]:
        """Transform a raw MangaBaka series object into a flat metadata dict.

        Args:
            series: Raw series object from the MangaBaka API.

        Returns:
            Flat dict of normalized metadata fields.
        """
        title = self.normalizer.normalize_whitespace(series.get("title"))
        localized_series = self._extract_localized_series(series)

        summary_raw = str(series.get("description") or "")
        summary = self.normalizer.normalize_whitespace(
            self._strip_html(html.unescape(summary_raw))
        )

        year, month, day = self._extract_published_date(series.get("published"))

        authors = self._join_people(series.get("authors"))
        artists = self._join_people(series.get("artists"))

        publisher = self._extract_publisher(series.get("publishers"), series.get("links"))

        genre = self._extract_genres(series)
        tags = self._extract_tags(series)
        web = self._extract_web(series)

        age_rating = self._map_content_rating(series.get("content_rating"))

        count = self._normalize_numeric_string(series.get("final_volume"))

        return {
            "title": title,
            "series": title,
            "localizedseries": localized_series,
            "number": "",
            "count": count,
            "summary": summary,
            "year": year,
            "month": month,
            "day": day,
            "writer": authors,
            "publisher": publisher,
            "genre": genre,
            "tags": tags,
            "web": web,
            "seriesgroup": "",
            "agerating": age_rating,
            "penciller": artists,
            "inker": artists,
            "coverartist": artists,
            "letterer": "",
        }

    def _extract_localized_series(self, series: Dict[str, Any]) -> str:
        """Extract the best localized/romanized series title.

        Preference order:
            1. Primary title from `titles` for the first matching preferred
               language in priority order.
            2. Non-primary title from `titles` for the first matching preferred
               language in priority order.
            3. `romanized_title`
            4. `native_title`
            5. Empty string

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Best localized/romanized series title.
        """
        titles = series.get("titles")
        if isinstance(titles, list):
            # Ordered by priority. Earlier entries are preferred over later ones.
            preferred_languages = [
                "ja-Latn",
                "ko-Latn",
                "zh-Latn",
            ]

            for preferred_language in preferred_languages:
                primary_native_match = ""
                primary_match = ""
                native_match = ""
                fallback_match = ""

                for entry in titles:
                    if not isinstance(entry, dict):
                        continue

                    language = str(entry.get("language") or "")
                    if language != preferred_language:
                        continue

                    title = self.normalizer.normalize_whitespace(entry.get("title"))
                    if not title:
                        continue

                    is_primary = bool(entry.get("is_primary"))
                    traits = entry.get("traits") or []
                    is_native = isinstance(traits, list) and "native" in traits

                    # Priority 1: primary + native
                    if is_primary and is_native:
                        primary_native_match = title
                        break

                    # Priority 2: primary
                    if is_primary and not primary_match:
                        primary_match = title

                    # Priority 3: native
                    if is_native and not native_match:
                        native_match = title

                    # Priority 4: fallback
                    if not fallback_match:
                        fallback_match = title

                if primary_native_match:
                    return primary_native_match

                if primary_match:
                    return primary_match

                if native_match:
                    return native_match

                if fallback_match:
                    return fallback_match

        romanized_title = self.normalizer.normalize_whitespace(series.get("romanized_title"))
        if romanized_title:
            return romanized_title

        native_title = self.normalizer.normalize_whitespace(series.get("native_title"))
        return native_title

    def _extract_publisher(
            self,
            publishers: Any,
            external_links: Any,
    ) -> str:
        """Extract the most relevant publisher.

        Priority order:
            1. Officially declared English publisher from `publishers`.
            2. English publisher inferred from `external_links` via
               PUBLISHER_DOMAIN_MAP.
            3. First non-empty non-English publisher from `publishers`.

        Args:
            publishers: Raw `publishers` field from the API.
            external_links: Raw external links field from the API.

        Returns:
            Publisher name, or empty string if no suitable publisher is found.
        """
        english_name = ""
        fallback_name = ""

        if isinstance(publishers, list):
            for entry in publishers:
                if not isinstance(entry, dict):
                    continue

                name = self.normalizer.normalize_whitespace(entry.get("name"))
                publisher_type = self.normalizer.normalize_whitespace(
                    entry.get("type")
                ).lower()

                if not name:
                    continue

                if publisher_type == "english":
                    english_name = name
                    break

                if not fallback_name:
                    fallback_name = name

        if english_name:
            return english_name

        mapped_name = self._extract_publisher_from_links(external_links)
        if mapped_name:
            log("DEBUG", f"found publisher: {mapped_name}")
            return mapped_name

        return fallback_name

    def _extract_publisher_from_links(self, external_links: Any) -> str:
        """Infer publisher from external link hostnames.

        Expects MangaBaka API format:
            - list[str] containing URLs

        Matches external link domains against PUBLISHER_DOMAIN_MAP and returns
        the mapped English publisher name when a match is found.

        Args:
            external_links: Raw external links field from the API.

        Returns:
            Mapped English publisher name, or empty string if no match is found.
        """
        if not isinstance(external_links, list):
            return ""

        for url in external_links:
            if not isinstance(url, str):
                continue

            url = self.normalizer.normalize_whitespace(url)
            if not url:
                continue

            try:
                host = url.split("//", 1)[-1].split("/", 1)[0].lower()
            except Exception:
                continue

            host = host.removeprefix("www.")

            for domain, publisher_name in PUBLISHER_DOMAIN_MAP.items():
                if host.endswith(domain):
                    return publisher_name

        return ""

    def _extract_genres(self, series: Dict[str, Any]) -> str:
        """Extract and normalize genre names.

        Prefers `genres_v2` when present. Falls back to deprecated `genres`.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Comma-separated genre string.
        """
        genres_v2 = series.get("genres_v2")
        if isinstance(genres_v2, list):
            names: List[str] = []
            for entry in genres_v2:
                if not isinstance(entry, dict):
                    continue
                name = self.normalizer.normalize_whitespace(entry.get("name"))
                if name:
                    names.append(name)

            unique_names = sorted(set(names), key=str.lower)
            return ", ".join(unique_names)

        genres = series.get("genres")
        if isinstance(genres, list):
            cleaned: List[str] = []
            for entry in genres:
                if not isinstance(entry, str):
                    continue
                value = entry.strip().replace("_", " ")
                if not value:
                    continue
                cleaned.append(self._title_case_loose(value))

            unique_cleaned = sorted(set(cleaned), key=str.lower)
            return ", ".join(unique_cleaned)

        return ""

    def _extract_tags(self, series: Dict[str, Any]) -> str:
        """Extract and normalize tag names.

        Prefers `tags_v2` when present. Falls back to deprecated `tags`.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Comma-separated tag string.
        """
        tags_v2 = series.get("tags_v2")
        if isinstance(tags_v2, list):
            names: List[str] = []
            for entry in tags_v2:
                if not isinstance(entry, dict):
                    continue
                name = self.normalizer.normalize_whitespace(entry.get("name"))
                if name:
                    names.append(name)

            unique_names = sorted(set(names), key=str.lower)
            return ", ".join(unique_names)

        tags = series.get("tags")
        if isinstance(tags, list):
            cleaned = [
                self.normalizer.normalize_whitespace(tag)
                for tag in tags
                if isinstance(tag, str) and tag.strip()
            ]
            unique_cleaned = sorted(set(cleaned), key=str.lower)
            return ", ".join(unique_cleaned)

        return ""

    def _extract_web(self, series: Dict[str, Any]) -> str:
        """Build the ComicInfo Web field from the MangaBaka links list.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Space-separated URL string.
        """
        links = series.get("links")
        if not isinstance(links, list):
            return ""

        valid_links = [
            self.normalizer.normalize_whitespace(link)
            for link in links
            if isinstance(link, str) and link.strip()
        ]
        unique_links = list(dict.fromkeys(valid_links))
        return " ".join(unique_links)

    @staticmethod
    def _map_content_rating(content_rating: Any) -> str:
        """Map MangaBaka content_rating to ComicInfo AgeRating.

        Args:
            content_rating: MangaBaka content rating value.

        Returns:
            ComicInfo-compatible AgeRating string.
        """
        rating = str(content_rating or "").strip().lower()

        mapping = {
            "safe": "Unknown",
            "suggestive": "MA 15+",
            "erotica": "Adults Only 18+",
            "pornographic": "X18+",
        }
        return mapping.get(rating, "Unknown")

    @staticmethod
    def _extract_id(url: str) -> Optional[int]:
        """Extract the MangaBaka series ID from a supported URL.

        Supported examples:
            - https://mangabaka.org/7546
            - https://mangabaka.org/7546?q=Toradora

        Args:
            url: MangaBaka URL.

        Returns:
            Integer series ID if found, otherwise None.
        """
        patterns = [
            r"mangabaka\.org/(\d+)(?:[/?#]|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url, flags=re.IGNORECASE)
            if not match:
                continue
            try:
                return int(match.group(1))
            except ValueError:
                return None

        return None

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and replace line-break tags with spaces.

        Args:
            text: Input text that may contain HTML.

        Returns:
            Plain text with tags removed.
        """
        text = re.sub(r"<\s*br\s*/?>", " ", text, flags=re.IGNORECASE)
        return re.sub(r"<[^>]+>", "", text)

    @staticmethod
    def _extract_published_date(published: Any) -> Tuple[str, str, str]:
        """Extract zero-padded year, month, and day from `published`.

        Args:
            published: Raw `published` object from MangaBaka.

        Returns:
            Three-tuple ``(year, month, day)``.
        """
        if not isinstance(published, dict):
            return "", "", ""

        start_date = str(published.get("start_date") or "").strip()
        if not start_date:
            return "", "", ""

        match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", start_date)
        if not match:
            return "", "", ""

        year = match.group(1) or ""
        month = match.group(2) or ""
        day = match.group(3) or ""
        return year, month, day

    @staticmethod
    def _join_people(values: Any) -> str:
        """Join a list of people names into a comma-separated string.

        Args:
            values: Raw list of names.

        Returns:
            Comma-separated names, deduplicated in original order.
        """
        if not isinstance(values, list):
            return ""

        cleaned = []
        for value in values:
            if not isinstance(value, str):
                continue
            name = value.strip()
            if name:
                cleaned.append(name)

        unique_cleaned = list(dict.fromkeys(cleaned))
        return ", ".join(unique_cleaned)

    @staticmethod
    def _normalize_numeric_string(value: Any) -> str:
        """Normalize a numeric-like value into a plain string.

        Args:
            value: Raw numeric or string value.

        Returns:
            String representation, or empty string.
        """
        if value is None:
            return ""
        text = str(value).strip()
        return text

    @staticmethod
    def _title_case_loose(text: str) -> str:
        """Convert a loose snake/space string into a simple title-like form.

        Args:
            text: Input text.

        Returns:
            A lightly title-cased string.
        """
        words = text.split()
        return " ".join(word[:1].upper() + word[1:] for word in words if word)


# ---------------------------------------------------------------------------
# Source adapter
# ---------------------------------------------------------------------------

class MangaBakaSource(MetadataSource):
    """MetadataSource adapter for MangaBaka."""

    source_key = "mangabaka"
    source_name = "MangaBaka"
    url_patterns = ["mangabaka.org/"]
    dialog_title = "Fetch metadata from MangaBaka"

    def __init__(
        self,
        parent: Any,
        cover_getter: Optional[Callable[..., Any]] = None,
        status_reporter: Optional[Callable[..., None]] = None,
    ) -> None:
        """Initialize the MangaBaka source.

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
        self._client = MangaBakaClient()

    def _fetch_from_url(self, url: str) -> Dict[str, str]:
        """Fetch metadata from MangaBaka and map it to app fields.

        Args:
            url: MangaBaka series URL.

        Returns:
            ComicInfo-compatible metadata dict, or ``{}`` on failure.
        """
        try:
            raw = self._client.fetch(url)
            return self._map_meta(raw, url)
        except SourceFetchError as exc:
            log("WARN", str(exc))
        except Exception:
            log("ERROR", f"[MangaBaka] Unexpected error for URL: {url}", exc_info=True)
        return {}

    def _map_meta(self, raw: Dict[str, str], url: str) -> Dict[str, str]:
        """Convert MangaBakaClient output to ComicInfo-compatible metadata.

        Args:
            raw: Field dict returned by MangaBakaClient.
            url: Source URL used as a fallback for `web`.

        Returns:
            Dict of ComicInfo-style metadata keys.
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
            "genre": raw.get("genre", ""),
            "tags": raw.get("tags", ""),
            "web": raw.get("web", "") or url,
            "seriesgroup": raw.get("seriesgroup", ""),
            "languageiso": "en",
            "agerating": raw.get("agerating", ""),
            "penciller": raw.get("penciller", ""),
            "inker": raw.get("inker", ""),
            "coverartist": raw.get("coverartist", ""),
            "letterer": raw.get("letterer", ""),
        }