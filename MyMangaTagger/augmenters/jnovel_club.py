# augmenters/jnovel_club.py

"""J-Novel Club volume metadata augmenter."""

from typing import Any
from urllib.parse import urlparse

from augmenters.base import (
    BaseVolumeAugmenter,
    VolumeAugmentationError,
    VolumeMetadataPatch,
    extract_extra_volume_title,
    normalize_number,
    normalize_whitespace,
    parse_date_text,
)


class JNovelClubAugmenter(BaseVolumeAugmenter):
    """Fetch volume-specific metadata from J-Novel Club's JSON API."""

    source_key = "jnovel_club"
    source_name = "J-Novel Club"
    url_patterns = [
        "j-novel.club/series/",
        "labs.j-novel.club/app/v2/series/",
    ]

    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a J-Novel Club series URL.

        Args:
            url: J-Novel Club series URL or labs API URL.

        Returns:
            Mapping of normalized volume number to patch.

        Raises:
            VolumeAugmentationError: If the URL, API response, or volume data is invalid.
        """
        slug = self._extract_slug(url)
        if not slug:
            raise VolumeAugmentationError(
                "[J-Novel Club] Could not extract series slug from URL."
            )

        api_url = f"https://labs.j-novel.club/app/v2/series/{slug}/volumes?format=json"
        payload = self._fetch_json(api_url)
        volumes = self._extract_volume_items(payload)
        if not volumes:
            raise VolumeAugmentationError(
                "[J-Novel Club] No volume data found in API response."
            )

        patches: dict[str, VolumeMetadataPatch] = {}
        for item in volumes:
            volume = item.get("volume", item) if isinstance(item, dict) else {}
            if not isinstance(volume, dict):
                continue

            number = normalize_number(volume.get("number"))
            if not number:
                continue

            year, month, day = parse_date_text(volume.get("publishing", ""))
            full_title = normalize_whitespace(volume.get("title"))
            short_title = normalize_whitespace(volume.get("shortTitle"))
            title = ""
            if short_title and normalize_number(short_title) != number:
                title = short_title
            else:
                title = extract_extra_volume_title(full_title, number)

            patches[number] = VolumeMetadataPatch(
                number=number,
                title=title,
                summary=normalize_whitespace(volume.get("description")),
                year=year,
                month=month,
                day=day,
                source_url=api_url,
            )

        if not patches:
            raise VolumeAugmentationError(
                "[J-Novel Club] No usable numbered volume patches found."
            )
        return patches

    @staticmethod
    def _extract_slug(url: str) -> str:
        """Extract a J-Novel Club series slug from a web or API URL.

        Args:
            url: User-supplied URL.

        Returns:
            Series slug, or an empty string if it cannot be found.
        """
        parsed = urlparse(url.strip())
        parts = [part for part in parsed.path.split("/") if part]

        if "series" not in parts:
            return ""

        series_index = parts.index("series")
        if series_index + 1 >= len(parts):
            return ""

        slug = parts[series_index + 1].strip()
        if slug in {"app", "v2"}:
            return ""
        return slug

    @staticmethod
    def _extract_volume_items(payload: Any) -> list[dict[str, Any]]:
        """Extract a flexible list of volume objects from the API payload.

        Args:
            payload: Parsed JSON payload.

        Returns:
            List of volume dictionaries.
        """
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            return []

        for key in ("volumes", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return []