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
from urllib.parse import urlsplit

import requests

from services.constants import PUBLISHER_DOMAIN_MAP
from services.logger import log
from services.normalization import Normalizer
from sources.anilist import AniListClient
from sources.base import MetadataSource, SourceFetchError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MANGABAKA_API_BASE = "https://api.mangabaka.org"
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
        self._anilist_client = AniListClient()

    def fetch(self, url: str) -> Dict[str, str]:
        """Fetch and normalize raw metadata from a MangaBaka URL.

        Args:
            url: MangaBaka series page URL, for example
                ``https://mangabaka.org/manga/7546/Toradora``.

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
        # The full v2 schema provides tag/genre classification and external links.
        api_url = f"{_MANGABAKA_API_BASE}/v2/series/{series_id}?schema=full"

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
        title = self._extract_display_title(series)
        if not title:
            raise SourceFetchError("[MangaBaka] Series has no usable title in the API response.")
        localized_series = self._extract_localized_series(series)

        summary_raw = str(series.get("description") or "")
        summary = self.normalizer.normalize_whitespace(
            self._strip_html(html.unescape(summary_raw))
        )

        year, month, day = self._extract_published_date(series.get("published"))

        mangabaka_authors = self._join_people(series.get("authors"))
        mangabaka_artists = self._join_people(series.get("artists"))
        anilist_metadata = self._fetch_anilist_metadata(series)

        writer = self._merge_people_strings(
            anilist_metadata.get("writer", ""),
            mangabaka_authors,
        )
        penciller = self._merge_people_strings(
            anilist_metadata.get("penciller", ""),
            mangabaka_artists,
        )
        inker = self._merge_people_strings(
            anilist_metadata.get("inker", ""),
            mangabaka_artists,
        )
        coverartist = self._merge_people_strings(
            anilist_metadata.get("coverartist", ""),
            mangabaka_artists,
        )
        letterer = anilist_metadata.get("letterer", "")

        publisher = self._extract_publisher(
            series.get("publishers"),
            series.get("links") or series.get("links_v2"),
        )

        # Prefer MangaBaka's own tags; use the already-fetched AniList data
        # only when the full schema does not provide a usable value.
        genre = self._extract_genres(series) or anilist_metadata.get("genre", "")
        tags = self._extract_tags(series) or anilist_metadata.get("tags", "")
        web = self._extract_web(series, anilist_metadata)

        age_rating = self._map_content_rating(series.get("content_rating"))

        # Only trust final_volume if the series is finished.
        status = (series.get("status") or "").lower()
        count = ""
        if status in {"completed", "cancelled"}:
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
            "writer": writer,
            "publisher": publisher,
            "genre": genre,
            "tags": tags,
            "web": web,
            "seriesgroup": "",
            "agerating": age_rating,
            "penciller": penciller,
            "inker": inker,
            "coverartist": coverartist,
            "letterer": letterer,
        }

    def _extract_display_title(self, series: Dict[str, Any]) -> str:
        """Select the preferred series title from MangaBaka's v2 titles.

        English titles take priority, followed by legacy display names and
        romanized names. When neither is available, use another primary title.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Preferred title, or an empty string when no title is available.
        """
        titles = series.get("titles")
        if isinstance(titles, list):
            english_titles = [
                entry
                for entry in titles
                if isinstance(entry, dict)
                and str(entry.get("language") or "").lower() == "en"
                and self.normalizer.normalize_whitespace(entry.get("title"))
            ]

            # Use the preferred English title when multiple variants exist.
            for entry in english_titles:
                if entry.get("is_primary"):
                    return self.normalizer.normalize_whitespace(entry.get("title"))
            for entry in english_titles:
                if "official" in (entry.get("traits") or []):
                    return self.normalizer.normalize_whitespace(entry.get("title"))
            if english_titles:
                return self.normalizer.normalize_whitespace(english_titles[0].get("title"))

        # Keep a legacy fallback for incomplete or transitional API payloads.
        legacy_title = self.normalizer.normalize_whitespace(series.get("title"))
        if legacy_title:
            return legacy_title

        romanized_title = self._extract_localized_series(series)
        if romanized_title:
            return romanized_title

        if isinstance(titles, list):
            for primary_only in (True, False):
                for entry in titles:
                    if not isinstance(entry, dict):
                        continue
                    title = self.normalizer.normalize_whitespace(entry.get("title"))
                    if title and bool(entry.get("is_primary")) == primary_only:
                        return title

        return ""

    def _extract_localized_series(self, series: Dict[str, Any]) -> str:
        """Extract the best localized/romanized series title.

        Preference order:
            1. Romanized Japanese, Korean, then Chinese titles from `titles`.
            2. Within each language, prefer primary + native, primary, native,
               then the first available entry.
            3. Legacy `romanized_title`, then `native_title`.

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
            1. English publisher inferred from external links via
               PUBLISHER_DOMAIN_MAP.
            2. Publisher with `language == "en"` in the v2 `publishers` list.
            3. First non-empty publisher as a fallback.

        Args:
            publishers: Raw `publishers` field from the API.
            external_links: Raw `links` (or legacy `links_v2`) field.

        Returns:
            Publisher name, or empty string if no suitable publisher is found.
        """
        english_name = ""
        fallback_name = ""

        # Prefer curated publisher-domain mappings from external_links, because these
        # usually point at the exact English publisher page when available.
        mapped_name = self._extract_publisher_from_links(external_links)
        if mapped_name:
            return mapped_name

        if isinstance(publishers, list):
            for entry in publishers:
                if not isinstance(entry, dict):
                    continue

                name = self.normalizer.normalize_whitespace(entry.get("name"))
                publisher_language = self.normalizer.normalize_whitespace(
                    entry.get("language")
                ).lower()
                legacy_publisher_type = self.normalizer.normalize_whitespace(
                    entry.get("type")
                ).lower()

                if not name:
                    continue

                if publisher_language == "en" or (
                    not publisher_language and legacy_publisher_type == "english"
                ):
                    english_name = name
                    break

                if not fallback_name:
                    fallback_name = name

        if english_name:
            return english_name

        return fallback_name

    def _extract_publisher_from_links(self, external_links: Any) -> str:
        """Infer publisher from MangaBaka v2/legacy external link hosts.

        Expects a list of dictionaries containing URL values.

        Matches link domains against PUBLISHER_DOMAIN_MAP and returns the mapped
        English publisher name when a match is found.

        Args:
            external_links: Raw `links` (or legacy `links_v2`) field.

        Returns:
            Mapped English publisher name, or empty string if no match is found.
        """
        if not isinstance(external_links, list):
            return ""

        for link in external_links:
            url = self._extract_link_v2_url(link)
            if not url:
                continue

            host = self._extract_url_host(url)
            if not host:
                continue

            for domain, publisher_name in PUBLISHER_DOMAIN_MAP.items():
                if host == domain or host.endswith(f".{domain}"):
                    return publisher_name

        return ""

    def _extract_genres(self, series: Dict[str, Any]) -> str:
        """Extract genres from v2 tags, with support for older payloads.

        In the v2 full schema, tags with `is_genre` set are genres.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Sorted comma-separated genre names.
        """
        tags = series.get("tags")
        if isinstance(tags, list) and any(
            isinstance(entry, dict) and "is_genre" in entry for entry in tags
        ):
            names = [
                self.normalizer.normalize_whitespace(entry.get("name"))
                for entry in tags
                if isinstance(entry, dict) and entry.get("is_genre")
            ]
            return ", ".join(sorted(set(name for name in names if name), key=str.lower))

        # Transitional schema: genres_v2 is a separate list of named objects.
        genres_v2 = series.get("genres_v2")
        if isinstance(genres_v2, list):
            names = [
                self.normalizer.normalize_whitespace(entry.get("name"))
                for entry in genres_v2
                if isinstance(entry, dict)
            ]
            return ", ".join(sorted(set(name for name in names if name), key=str.lower))

        # Old schema: genres is a list of strings.
        genres = series.get("genres")
        if isinstance(genres, list):
            cleaned = [
                self._title_case_loose(entry.strip().replace("_", " "))
                for entry in genres
                if isinstance(entry, str) and entry.strip()
            ]
            return ", ".join(sorted(set(cleaned), key=str.lower))

        return ""

    def _extract_tags(self, series: Dict[str, Any]) -> str:
        """Extract non-genre tags from the v2 or legacy tag fields.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Sorted comma-separated tag names.
        """
        tags = series.get("tags")
        if isinstance(tags, list):
            # The full v2 schema uses named objects with an is_genre flag.
            if any(isinstance(entry, dict) for entry in tags):
                names = [
                    self.normalizer.normalize_whitespace(entry.get("name"))
                    for entry in tags
                    if isinstance(entry, dict) and not entry.get("is_genre", False)
                ]
                return ", ".join(sorted(set(name for name in names if name), key=str.lower))

            # Legacy tags used plain strings.
            if tags and all(isinstance(entry, str) for entry in tags):
                cleaned = [
                    self.normalizer.normalize_whitespace(entry)
                    for entry in tags
                ]
                return ", ".join(sorted(set(name for name in cleaned if name), key=str.lower))

        tags_v2 = series.get("tags_v2")
        if isinstance(tags_v2, list):
            names = [
                self.normalizer.normalize_whitespace(entry.get("name"))
                for entry in tags_v2
                if isinstance(entry, dict)
            ]
            return ", ".join(sorted(set(name for name in names if name), key=str.lower))

        return ""

    def _extract_web(
        self,
        series: Dict[str, Any],
        anilist_metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build the ComicInfo Web field using curated source URLs.

        Included URLs are limited to the MangaBaka canonical URL, the linked
        AniList URL, and publisher-domain links from MangaBaka or AniList.

        Args:
            series: Raw MangaBaka series object.
            anilist_metadata: Already-fetched AniList fields, if available.

        Returns:
            Space-separated unique URLs.
        """
        curated_links: List[str] = []

        mangabaka_url = self._build_mangabaka_series_url(series)
        if mangabaka_url:
            curated_links.append(mangabaka_url)

        anilist_url = self._build_anilist_series_url(series)
        if anilist_url:
            curated_links.append(anilist_url)

        # v2 full schema contains `links`; preserve compatibility with `links_v2`.
        links = series.get("links")
        if not links:
            links = series.get("links_v2")
        if isinstance(links, list):
            for link in links:
                url = self._extract_link_v2_url(link)
                if url and self._is_publisher_domain_link(url):
                    curated_links.append(url)

        # Also reuse qualifying AniList INFO/ENGLISH publisher links,
        # without making a second AniList request.
        if anilist_metadata:
            for url in anilist_metadata.get("web", "").split():
                if self._is_publisher_domain_link(url):
                    curated_links.append(url)

        return " ".join(dict.fromkeys(curated_links))

    def _build_mangabaka_series_url(self, series: Dict[str, Any]) -> str:
        """Use MangaBaka's canonical URL, or reconstruct a valid page URL.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Canonical page URL, or an empty string for an invalid ID/type.
        """
        try:
            series_id = int(series.get("id"))
        except (TypeError, ValueError):
            return ""

        if series_id <= 0:
            return ""

        canonical_url = self.normalizer.normalize_whitespace(series.get("canonical_url"))
        if canonical_url and self._extract_id(canonical_url) == series_id:
            return canonical_url

        # Page URLs use three categories, even though series types can vary.
        series_type = str(series.get("type") or "").lower()
        if series_type == "novel":
            category = "novel"
        elif series_type == "other":
            category = "other"
        elif series_type in {"manga", "manhwa", "manhua", "oel"}:
            category = "manga"
        else:
            return ""

        return f"https://mangabaka.org/{category}/{series_id}"

    def _build_anilist_series_url(self, series: Dict[str, Any]) -> str:
        """Build the canonical AniList manga URL from the linked AniList ID.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            Canonical AniList manga URL, or an empty string if no valid ID exists.
        """
        anilist_id = self._extract_anilist_id(series)
        if anilist_id is None:
            return ""

        return f"https://anilist.co/manga/{anilist_id}"

    def _extract_link_v2_url(self, link: Any) -> str:
        """Extract a normalized URL from a MangaBaka external link entry.

        Args:
            link: Raw `links` or legacy `links_v2` entry.

        Returns:
            Normalized URL string, or an empty string if unavailable.
        """
        if not isinstance(link, dict):
            return ""

        return self.normalizer.normalize_whitespace(link.get("url"))

    def _is_publisher_domain_link(self, url: str) -> bool:
        """Return whether a URL belongs to one of the mapped publisher domains.

        Args:
            url: URL to check.

        Returns:
            True if the URL hostname matches a domain in PUBLISHER_DOMAIN_MAP.
        """
        host = self._extract_url_host(url)
        if not host:
            return False

        for domain in PUBLISHER_DOMAIN_MAP:
            if host == domain or host.endswith(f".{domain}"):
                return True

        return False

    @staticmethod
    def _extract_url_host(url: str) -> str:
        """Extract the hostname of a valid HTTP(S) URL.

        Args:
            url: URL to inspect.

        Returns:
            Lowercased hostname without `www.`, or an empty string.
        """
        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme.lower() not in {"http", "https"}:
                return ""
            return (parsed.hostname or "").lower().removeprefix("www.")
        except ValueError:
            return ""

    def _fetch_anilist_metadata(self, series: Dict[str, Any]) -> Dict[str, str]:
        """Fetch supplementary AniList staff, genres, tags, and external links.

        The linked ID comes from `source.anilist.id`. The single request enriches
        people fields and provides fallbacks when MangaBaka omits tags or links.
        AniList failures are non-fatal; MangaBaka data remains usable.

        Args:
            series: Raw MangaBaka series object.

        Returns:
            AniList people, genre, tag, and Web fields, or an empty dict.
        """
        anilist_id = self._extract_anilist_id(series)
        if anilist_id is None:
            return {}

        try:
            raw = self._anilist_client.fetch_by_id(anilist_id)
        except SourceFetchError as exc:
            log(
                "DEBUG",
                f"[MangaBaka] AniList enrichment failed for id={anilist_id}: {exc}",
            )
            return {}
        except Exception:
            log(
                "ERROR",
                f"[MangaBaka] Unexpected AniList enrichment error for id={anilist_id}",
                exc_info=True,
            )
            return {}

        return {
            "writer": raw.get("writer", ""),
            "penciller": raw.get("penciller", ""),
            "inker": raw.get("inker", ""),
            "coverartist": raw.get("coverartist", ""),
            "letterer": raw.get("letterer", ""),
            "genre": raw.get("genre", ""),
            "tags": raw.get("tags", ""),
            "web": raw.get("web", ""),
        }

    @staticmethod
    def _extract_anilist_id(series: Dict[str, Any]) -> Optional[int]:
        """Extract the linked AniList ID from a MangaBaka series object.

        Expected MangaBaka shape:
            ``source -> anilist -> id``

        Args:
            series: Raw MangaBaka series object.

        Returns:
            The AniList ID as an integer, or ``None`` if unavailable or invalid.
        """
        source = series.get("source")
        if not isinstance(source, dict):
            return None

        anilist = source.get("anilist")
        if not isinstance(anilist, dict):
            return None

        raw_id = anilist.get("id")
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _split_people_string(value: str) -> List[str]:
        """Split a comma-separated people field into cleaned name entries.

        Args:
            value: Comma-separated people string.

        Returns:
            A list of cleaned names in original order.
        """
        if not value:
            return []

        names: List[str] = []
        for part in value.split(","):
            name = part.strip()
            if name:
                names.append(name)
        return names

    def _merge_people_strings(self, primary: str, secondary: str) -> str:
        """Merge two comma-separated people strings with stable deduplication.

        The primary value is kept first. This is used so AniList's richer staff
        mapping can take precedence, while MangaBaka author and artist data still
        acts as fallback and supplement.

        Args:
            primary: Preferred comma-separated people string.
            secondary: Fallback comma-separated people string.

        Returns:
            A merged comma-separated string with duplicates removed.
        """
        primary_names = self._split_people_string(primary)
        secondary_names = self._split_people_string(secondary)

        merged_names = list(dict.fromkeys([*primary_names, *secondary_names]))
        return ", ".join(merged_names)

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
            "suggestive": "MA15+",
            "erotica": "Adults Only 18+",
            "pornographic": "X18+",
        }
        return mapping.get(rating, "Unknown")

    @staticmethod
    def _extract_id(url: str) -> Optional[int]:
        """Extract a MangaBaka series ID from new or legacy URLs.

        Supports `/manga/{id}`, `/novel/{id}`, `/other/{id}`, older `/{id}`
        links, and direct `/v2/series/{id}` API URLs. The hostname is checked
        explicitly so unrelated websites cannot supply a series ID.

        Args:
            url: MangaBaka series page or API URL.

        Returns:
            Positive series ID, or None for an unsupported URL.
        """
        try:
            parsed = urlsplit(url.strip())
            host = (parsed.hostname or "").lower()
        except ValueError:
            return None

        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        path_parts = [part for part in parsed.path.split("/") if part]
        raw_id = ""

        if host in {"mangabaka.org", "www.mangabaka.org"}:
            if len(path_parts) >= 2 and path_parts[0].lower() in {
                "manga", "novel", "other"
            }:
                raw_id = path_parts[1]
            elif path_parts and path_parts[0].isdigit():
                raw_id = path_parts[0]
        elif host == "api.mangabaka.org":
            if len(path_parts) == 3 and path_parts[:2] in (
                ["v1", "series"], ["v2", "series"]
            ):
                raw_id = path_parts[2]

        try:
            series_id = int(raw_id)
        except (TypeError, ValueError):
            return None

        return series_id if series_id > 0 else None

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