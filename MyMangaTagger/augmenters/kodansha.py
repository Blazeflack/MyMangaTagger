# augmenters/kodansha.py

"""Kodansha USA volume metadata augmenter."""

import re
from typing import Any

from augmenters.base import (
    BaseVolumeAugmenter,
    VolumeAugmentationError,
    VolumeMetadataPatch,
    extract_all_links,
    extract_block_by_class,
    extract_extra_volume_title,
    extract_json_ld_objects,
    extract_title_tag,
    get_meta_content,
    make_absolute_url,
    normalize_number,
    parse_date_text,
    strip_html,
)


class KodanshaAugmenter(BaseVolumeAugmenter):
    """Scrape volume-specific metadata from Kodansha USA volume pages."""

    source_key = "kodansha"
    source_name = "Kodansha USA"
    url_patterns = ["kodansha.us/series/"]

    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a Kodansha USA series or volume URL.

        Args:
            url: Kodansha series URL, or a single volume URL.

        Returns:
            Mapping of normalized volume number to patch.

        Raises:
            VolumeAugmentationError: If no usable patches can be built.
        """
        volume_urls = self._get_volume_urls(url)
        if not volume_urls:
            raise VolumeAugmentationError("[Kodansha] No volume links found.")

        patches: dict[str, VolumeMetadataPatch] = {}
        for volume_url in volume_urls:
            patch = self._fetch_volume_patch(volume_url)
            if patch and patch.number:
                patches[patch.number] = patch

        if not patches:
            raise VolumeAugmentationError("[Kodansha] No usable volume metadata found.")
        return patches

    def _get_volume_urls(self, url: str) -> list[str]:
        """Return volume URLs from a series page or a single volume URL.

        Args:
            url: Kodansha URL.

        Returns:
            Deduplicated volume URLs.
        """
        if re.search(r"/volume-\d+/?", url, flags=re.IGNORECASE):
            return [url.split("#", 1)[0]]

        page_html = self._fetch_text(url)
        json_ld_links = self._extract_json_ld_volume_links(page_html)
        if json_ld_links:
            return json_ld_links

        volumes_block = extract_block_by_class(page_html, "volumes-section", "section")
        links = extract_all_links(volumes_block or page_html, url)
        volume_links = [link for link in links if re.search(r"/volume-\d+/?$", link, flags=re.IGNORECASE)]
        return list(dict.fromkeys(volume_links))

    def _fetch_volume_patch(self, url: str) -> VolumeMetadataPatch | None:
        """Fetch and parse one Kodansha volume page.

        Args:
            url: Volume page URL.

        Returns:
            Volume metadata patch, or None if no number can be found.
        """
        page_html = self._fetch_text(url)
        page_title = get_meta_content(page_html, "og:title") or extract_title_tag(page_html)
        number = self._extract_number(url, page_title)
        if not number:
            return None

        summary_block = extract_block_by_class(page_html, "volume__hero__description", "div")
        summary = strip_html(summary_block) or get_meta_content(page_html, "og:description")

        info_block = extract_block_by_class(page_html, "volume-info__content", "div") or page_html
        year, month, day = parse_date_text(info_block)

        return VolumeMetadataPatch(
            number=number,
            title=extract_extra_volume_title(page_title, number),
            summary=summary,
            year=year,
            month=month,
            day=day,
            source_url=url,
        )

    @staticmethod
    def _extract_json_ld_volume_links(page_html: str) -> list[str]:
        """Extract volume URLs from Kodansha JSON-LD hasPart data.

        Args:
            page_html: Full series page HTML.

        Returns:
            Deduplicated volume URLs.
        """
        links: list[str] = []
        seen: set[str] = set()
        for payload in extract_json_ld_objects(page_html):
            candidates = KodanshaAugmenter._walk_json_ld_for_has_part(payload)
            for candidate in candidates:
                url = str(candidate.get("url") or "").strip()
                if not url:
                    continue
                absolute = make_absolute_url("https://kodansha.us/", url).split("#", 1)[0]
                if absolute not in seen:
                    links.append(absolute)
                    seen.add(absolute)
        return links

    @staticmethod
    def _walk_json_ld_for_has_part(payload: Any) -> list[dict[str, Any]]:
        """Find JSON-LD objects listed under ``hasPart`` recursively.

        Args:
            payload: Parsed JSON-LD object.

        Returns:
            List of hasPart entries.
        """
        found: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            has_part = payload.get("hasPart")
            if isinstance(has_part, list):
                found.extend(item for item in has_part if isinstance(item, dict))
            elif isinstance(has_part, dict):
                found.append(has_part)

            for value in payload.values():
                found.extend(KodanshaAugmenter._walk_json_ld_for_has_part(value))
        elif isinstance(payload, list):
            for item in payload:
                found.extend(KodanshaAugmenter._walk_json_ld_for_has_part(item))
        return found

    @staticmethod
    def _extract_number(url: str, title: str) -> str:
        """Extract a volume number from a Kodansha URL or title.

        Args:
            url: Volume page URL.
            title: Page title text.

        Returns:
            Normalized number, or an empty string.
        """
        url_match = re.search(r"/volume-(\d+)/?", url, flags=re.IGNORECASE)
        if url_match:
            return normalize_number(url_match.group(1))

        title_match = re.search(r"\b(\d+)\s*\([^)]*\)", title)
        if title_match:
            return normalize_number(title_match.group(1))
        return ""