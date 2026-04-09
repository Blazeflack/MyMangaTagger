"""
AniList metadata source for MyMangaTagger.

Provides two classes:
  - AniListClient: Lightweight GraphQL client that fetches and normalizes
    raw manga metadata from the AniList API.
  - AniListSource: MetadataSource adapter that maps AniListClient output
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

_ANILIST_ENDPOINT = "https://graphql.anilist.co"

_ANILIST_QUERY = """
query ($id: Int!, $type: MediaType) {
  Media (id: $id, type: $type) {
    title {
      english
      romaji
    }
    format
    description
    isAdult
    genres
    siteUrl
    source
    status
    tags {
      name
    }
    staff {
      edges {
        role
        node {
          name {
            full
          }
        }
      }
    }
    externalLinks {
      url
      type
      language
    }
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    studios {
      nodes {
        name
        siteUrl
      }
    }
  }
}
""".strip()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class AniListClient:
    """Lightweight GraphQL client for fetching manga metadata from AniList.

    Handles all network I/O, response parsing, and field normalization.
    Consumers receive a plain dict of pre-normalized fields ready for
    mapping into ComicInfo format by AniListSource.

    Attributes:
        normalizer: Shared Normalizer instance for light text cleanup.
    """

    def __init__(self) -> None:
        self.normalizer = Normalizer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, url: str) -> Dict[str, str]:
        """Fetch and normalize raw metadata from an AniList manga URL.

        Args:
            url: AniList manga page URL, e.g. ``https://anilist.co/manga/30013/``.

        Returns:
            A dict of pre-normalized metadata fields (lower-cased keys).
            See field list below.

        Raises:
            SourceFetchError: If the media ID cannot be extracted, the
                network request fails, or no Media node is returned.

        Fields returned:
            - ``title``: Preferred display title (English → Romaji fallback).
            - ``series``: English title if available, else Romaji.
            - ``localizedseries``: Romaji title (can be empty).
            - ``writer``: Comma-separated story/creator staff.
            - ``penciller`` / ``inker`` / ``coverartist`` / ``letterer``:
              Derived from staff roles.
            - ``tags``: Deduplicated, alphabetically sorted AniList tags.
            - ``genre``: Deduplicated, alphabetically sorted AniList genres.
            - ``web``: AniList siteUrl plus INFO/ENGLISH external links.
            - ``year`` / ``month`` / ``day``: Zero-padded startDate fields.
            - ``description``: Plain-text description with HTML stripped.
            - ``seriesgroup``: Empty string (reserved for future use).
            - ``publisher``: From studios, or inferred from external link domains.
            - ``is_adult``: ``"true"`` or ``"false"`` based on AniList isAdult flag.
        """
        media_id = self._extract_id(url)
        if media_id is None:
            raise SourceFetchError(
                f"[AniList] Could not extract media ID from URL: {url}"
            )

        return self.fetch_by_id(media_id)

    def fetch_by_id(self, media_id: int) -> Dict[str, str]:
        """Fetch and normalize raw metadata from an AniList media ID.

        This is useful when another source already provides a linked AniList ID,
        so the caller does not need to construct an AniList URL first.

        Args:
            media_id: Numeric AniList manga/media ID.

        Returns:
            A dict of pre-normalized metadata fields using lowercase keys.

        Raises:
            SourceFetchError: If the network request fails or no Media node is
                returned for the provided ID.
        """
        media = self._fetch_media(media_id)
        return self._parse(media)

    # ------------------------------------------------------------------
    # Private: network
    # ------------------------------------------------------------------

    def _fetch_media(self, media_id: int) -> Dict[str, Any]:
        """POST the GraphQL query and return the Media node.

        Args:
            media_id: Numeric AniList media ID.

        Returns:
            The ``Media`` dict from the API response.

        Raises:
            SourceFetchError: On network error or missing Media node.
        """
        variables = {"id": media_id, "type": "MANGA"}
        try:
            log("DEBUG", f"[AniList] POST -> {_ANILIST_ENDPOINT} (id={media_id})")
            resp = requests.post(
                _ANILIST_ENDPOINT,
                json={"query": _ANILIST_QUERY, "variables": variables},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise SourceFetchError(
                f"[AniList] Network/HTTP error for id={media_id}"
            ) from exc

        media = (data or {}).get("data", {}).get("Media")
        if not media:
            raise SourceFetchError(
                f"[AniList] No Media node returned for id={media_id}"
            )
        return media

    # ------------------------------------------------------------------
    # Private: parsing
    # ------------------------------------------------------------------

    def _parse(self, media: Dict[str, Any]) -> Dict[str, str]:
        """Transform a raw AniList Media node into a flat metadata dict.

        Args:
            media: The ``Media`` dict as returned by the AniList GraphQL API.

        Returns:
            Flat dict of normalized metadata fields.
        """
        # --- Titles ---
        titles = media.get("title") or {}
        t_en = self.normalizer.normalize_whitespace(titles.get("english") or "")
        t_ro = self.normalizer.normalize_whitespace(titles.get("romaji") or "")
        best_title = t_en or t_ro

        # --- Description ---
        desc_raw: str = media.get("description") or ""
        description = self.normalizer.normalize_whitespace(
            self._strip_html(html.unescape(desc_raw))
        )

        # --- Dates (prefer startDate) ---
        year, month, day = self._extract_date(media.get("startDate"))

        # --- Genres ---
        raw_genres: List[str] = [
            g.strip()
            for g in (media.get("genres") or [])
            if isinstance(g, str) and g.strip()
        ]
        genre = ", ".join(sorted(set(raw_genres), key=str.lower))

        # --- Tags ---
        raw_tags: List[str] = [
            (t or {}).get("name", "").strip()
            for t in (media.get("tags") or [])
            if isinstance(t, dict)
        ]
        unique_tags = list(dict.fromkeys(t for t in raw_tags if t))
        tags = ", ".join(sorted(unique_tags, key=str.lower))

        # --- Staff ---
        staff_map = self._map_staff_fields(media.get("staff", {}))
        writer      = ", ".join(staff_map.get("writer", []))
        penciller   = ", ".join(staff_map.get("penciller", []))
        inker       = ", ".join(staff_map.get("inker", []))
        coverartist = ", ".join(staff_map.get("coverartist", []))
        letterer    = ", ".join(staff_map.get("letterer", []))

        # --- Publisher ---
        publisher = self._extract_publisher(media)

        # --- Web ---
        web = self._extract_web(media)

        # --- Adult flag ---
        is_adult = "true" if bool(media.get("isAdult", False)) else "false"

        return {
            "title":          best_title,
            "series":         t_en or t_ro,
            "localizedseries": t_ro,
            "writer":         writer,
            "penciller":      penciller,
            "inker":          inker,
            "coverartist":    coverartist,
            "letterer":       letterer,
            "tags":           tags,
            "genre":          genre,
            "web":            web,
            "year":           year,
            "month":          month,
            "day":            day,
            "description":    description,
            "seriesgroup":    "",
            "publisher":      publisher,
            "is_adult":       is_adult,
        }

    def _extract_publisher(self, media: Dict[str, Any]) -> str:
        """Derive publisher from studios or external link domains.

        Prefers the first studio node's name. Falls back to matching
        external link hostnames against PUBLISHER_DOMAIN_MAP.

        Args:
            media: Raw AniList Media node.

        Returns:
            Publisher name string, or empty string if undetermined.
        """
        studios = (media.get("studios") or {}).get("nodes") or []
        if studios and isinstance(studios[0], dict):
            name = (studios[0].get("name") or "").strip()
            if name:
                return name

        for link in (media.get("externalLinks") or []):
            if not isinstance(link, dict):
                continue
            url = (link.get("url") or "").strip()
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

    def _extract_web(self, media: Dict[str, Any]) -> str:
        """Build the Web field from siteUrl and INFO/ENGLISH external links.

        Args:
            media: Raw AniList Media node.

        Returns:
            Space-separated URL string.
        """
        site_url = (media.get("siteUrl") or "").strip()
        extra: List[str] = []
        for link in (media.get("externalLinks") or []):
            if not isinstance(link, dict):
                continue
            url       = (link.get("url")      or "").strip()
            link_type = (link.get("type")      or "").upper()
            language  = (link.get("language")  or "").upper()
            if url and link_type == "INFO" and language == "ENGLISH":
                extra.append(url)
        return " ".join(u for u in [site_url, *extra] if u)

    # ------------------------------------------------------------------
    # Private: static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_id(url: str) -> Optional[int]:
        """Extract the numeric AniList manga ID from a URL.

        Only recognizes the ``anilist.co/manga/<id>`` path pattern.

        Args:
            url: AniList manga page URL.

        Returns:
            Integer ID if found; ``None`` otherwise.
        """
        match = re.search(r"anilist\.co/manga/(\d+)", url, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and replace ``<br>`` elements with spaces.

        Args:
            text: Input string possibly containing HTML markup.

        Returns:
            Plain text with tags removed.
        """
        text = re.sub(r"<\s*br\s*/?>", " ", text, flags=re.IGNORECASE)
        return re.sub(r"<[^>]+>", "", text)

    @staticmethod
    def _extract_date(dt: Optional[Dict[str, Any]]) -> Tuple[str, str, str]:
        """Extract zero-padded year, month and day from an AniList date dict.

        Args:
            dt: Dict with optional integer keys ``year``, ``month``, ``day``.

        Returns:
            Three-tuple of strings ``(year, month, day)``;
            each is empty string when the value is absent or zero.
        """
        if not isinstance(dt, dict):
            return "", "", ""
        y = dt.get("year")
        m = dt.get("month")
        d = dt.get("day")
        year  = f"{int(y):04d}" if isinstance(y, int) and y > 0 else ""
        month = f"{int(m):02d}" if isinstance(m, int) and m > 0 else ""
        day   = f"{int(d):02d}" if isinstance(d, int) and d > 0 else ""
        return year, month, day

    @staticmethod
    def _map_staff_fields(
        staff_obj: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """Map AniList staff role edges to ComicInfo people fields.

        Role mapping rules (substring match, case-insensitive):

        +------------------------------+-------------------------------+
        | Role pattern                 | Mapped to                     |
        +==============================+===============================+
        | "Story & Art" / "Story and   | Writer only (art skipped)     |
        | Art"                         |                               |
        +------------------------------+-------------------------------+
        | "Original Story" /           | Writer                        |
        | "Original Creator"           |                               |
        +------------------------------+-------------------------------+
        | "Story" (alone)              | Writer                        |
        +------------------------------+-------------------------------+
        | "Character Design"           | Penciller                     |
        +------------------------------+-------------------------------+
        | "Lettering" + "English"      | Letterer                      |
        +------------------------------+-------------------------------+
        | "Touch-up Art & Lettering"   | Penciller + Inker +           |
        | + "English"                  | CoverArtist + Letterer        |
        +------------------------------+-------------------------------+
        | "Touch-up Art & Lettering"   | Penciller + Inker + CoverArtist|
        | (without "English")          |                               |
        +------------------------------+-------------------------------+
        | "Art" (standalone)           | Penciller + Inker + CoverArtist|
        +------------------------------+-------------------------------+

        Roles containing any of these substrings are always excluded:
        ``translator``, ``translation``, ``editor``, ``assistant``,
        ``assistance``.

        Args:
            staff_obj: AniList ``staff`` object containing an ``edges`` list.

        Returns:
            Dict with keys ``writer``, ``penciller``, ``inker``,
            ``coverartist``, ``letterer``; each value is a deduplicated,
            insertion-ordered list of name strings.
        """
        edges = (staff_obj or {}).get("edges") or []

        writer:     List[str] = []
        penciller:  List[str] = []
        inker:      List[str] = []
        coverartist: List[str] = []
        letterer:   List[str] = []

        _EXCLUDED = (
            "translator", "translation", "editor", "assistant", "assistance"
        )

        for edge in edges:
            if not isinstance(edge, dict):
                continue

            role   = (edge.get("role") or "").strip()
            role_l = role.lower()

            if any(excl in role_l for excl in _EXCLUDED):
                continue

            node = edge.get("node") or {}
            name = ((node.get("name") or {}).get("full") or "").strip()
            if not name:
                continue

            # Pre-compute role flags for readability
            is_story_and_art  = "story & art" in role_l or "story and art" in role_l
            is_original_story = "original story" in role_l
            is_original_creator = "original creator" in role_l
            has_story         = "story" in role_l
            has_art           = "art" in role_l
            has_character_design = "character design" in role_l
            has_letter        = "letter" in role_l
            has_english       = "english" in role_l
            has_touchup       = "touch-up art" in role_l or "touch up art" in role_l

            # "Story & Art" → Writer only; skip all art roles for this edge
            if is_story_and_art:
                writer.append(name)
                continue

            # Writer roles
            if is_original_story or is_original_creator:
                writer.append(name)
            elif has_story:
                writer.append(name)

            # Character Design → Penciller
            if has_character_design:
                penciller.append(name)

            # Lettering (English only, not part of touch-up)
            if has_letter and has_english and not has_touchup:
                letterer.append(name)

            # Touch-up Art & Lettering
            if has_touchup and has_letter:
                penciller.append(name)
                inker.append(name)
                coverartist.append(name)
                if has_english:
                    letterer.append(name)
                continue

            # Standalone Art → Penciller + Inker + CoverArtist
            if has_art and not is_story_and_art and not has_touchup:
                penciller.append(name)
                inker.append(name)
                coverartist.append(name)

        dedup = lambda xs: list(dict.fromkeys(x for x in xs if x))
        return {
            "writer":     dedup(writer),
            "penciller":  dedup(penciller),
            "inker":      dedup(inker),
            "coverartist": dedup(coverartist),
            "letterer":   dedup(letterer),
        }


# ---------------------------------------------------------------------------
# Source adapter
# ---------------------------------------------------------------------------

class AniListSource(MetadataSource):
    """MetadataSource adapter for AniList (GraphQL-backed).

    Wraps AniListClient and maps its output to ComicInfo-compatible fields.
    Plugs into the standard fetch/dialog loop defined in MetadataSource.

    Attributes:
        source_key: Registry key used by the plugin loader (``"anilist"``).
        source_name: Human-friendly source name shown in the GUI.
        url_patterns: URL substrings used for auto-detection.
        dialog_title: Title shown in the URL entry dialog.
    """

    source_key   = "anilist"
    source_name = "AniList"
    url_patterns = ["anilist.co/manga/"]
    dialog_title = "Fetch metadata from AniList"

    def __init__(
        self,
        parent: Any,
        cover_getter: Optional[Callable] = None,
        status_reporter: Optional[Callable[..., None]] = None,
    ) -> None:
        """Initialise AniListSource.

        Args:
            parent: Main GUI controller (must expose ``root`` for dialogs).
            cover_getter: Optional callable ``(Path) -> PIL.Image.Image | None``
                used to display a cover preview in the URL dialog.
            status_reporter: Optional callable for sending status/progress
                messages to the GUI.
        """
        super().__init__(
            parent=parent,
            title=self.dialog_title,
            cover_getter=cover_getter,
            status_reporter=status_reporter,
        )
        self._client = AniListClient()

    # ------------------------------------------------------------------
    # MetadataSource interface
    # ------------------------------------------------------------------

    def _fetch_from_url(self, url: str) -> Dict[str, str]:
        """Fetch raw metadata from AniList and map to ComicInfo fields.

        Args:
            url: AniList manga page URL.

        Returns:
            ComicInfo-compatible metadata dict, or ``{}`` on failure.
        """
        try:
            raw = self._client.fetch(url)
            return self._map_meta(raw, url)
        except SourceFetchError as exc:
            log("WARN", str(exc))
        except Exception:
            log("ERROR", f"[AniList] Unexpected error for URL: {url}", exc_info=True)
        return {}

    # ------------------------------------------------------------------
    # Private: field mapping
    # ------------------------------------------------------------------

    def _map_meta(self, raw: Dict[str, str], url: str) -> Dict[str, str]:
        """Convert AniListClient output to ComicInfo-compatible metadata.

        Age rating is derived from the ``is_adult`` flag:
        ``"true"`` → ``"X18+"``, otherwise ``"Unknown"``.

        Args:
            raw: Field dict returned by AniListClient (lower-cased keys).
            url: Source URL (used as Web fallback if client returns none).

        Returns:
            Dict of ComicInfo-style metadata keys (all lowercase).
        """
        age_rating = "X18+" if raw.get("is_adult") == "true" else "Unknown"

        return {
            "title":           raw.get("title", ""),
            "writer":          raw.get("writer", ""),
            "tags":            raw.get("tags", ""),
            "web":             raw.get("web", "") or url,
            "series":          raw.get("series", ""),
            "localizedseries": raw.get("localizedseries", ""),
            "number":          raw.get("number", ""),
            "year":            raw.get("year", ""),
            "month":           raw.get("month", ""),
            "day":             raw.get("day", ""),
            "genre":           raw.get("genre", ""),
            "summary":         raw.get("description", ""),
            "seriesgroup":     raw.get("seriesgroup", ""),
            "publisher":       raw.get("publisher", ""),
            "agerating":       age_rating,
            "languageiso":     "en",
            "penciller":       raw.get("penciller", ""),
            "inker":           raw.get("inker", ""),
            "coverartist":     raw.get("coverartist", ""),
            "letterer":        raw.get("letterer", ""),
        }