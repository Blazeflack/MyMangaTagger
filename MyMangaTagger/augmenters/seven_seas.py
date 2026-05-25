# augmenters/seven_seas.py

"""Seven Seas Entertainment volume metadata augmenter."""

import re

from augmenters.base import (
    BaseVolumeAugmenter,
    VolumeAugmentationError,
    VolumeMetadataPatch,
    extract_all_links,
    extract_block_by_class,
    extract_block_by_id,
    extract_extra_volume_title,
    extract_title_tag,
    get_meta_content,
    normalize_number,
    normalize_whitespace,
    parse_date_text,
    strip_html,
)


class SevenSeasAugmenter(BaseVolumeAugmenter):
    """Scrape volume-specific metadata from Seven Seas volume pages."""

    source_key = "seven_seas"
    source_name = "Seven Seas Entertainment"
    url_patterns = [
        "sevenseasentertainment.com/series/",
        "sevenseasentertainment.com/books/",
    ]

    def fetch_patches(self, url: str) -> dict[str, VolumeMetadataPatch]:
        """Fetch volume patches from a Seven Seas series or volume URL.

        Args:
            url: Seven Seas series URL, or a single volume URL.

        Returns:
            Mapping of normalized volume number to patch.

        Raises:
            VolumeAugmentationError: If no usable patches can be built.
        """
        volume_urls = self._get_volume_urls(url)
        if not volume_urls:
            raise VolumeAugmentationError("[Seven Seas] No volume links found.")

        patches: dict[str, VolumeMetadataPatch] = {}
        for volume_url in volume_urls:
            patch = self._fetch_volume_patch(volume_url)
            if patch and patch.number:
                patches[patch.number] = patch

        if not patches:
            raise VolumeAugmentationError("[Seven Seas] No usable volume metadata found.")
        return patches

    def _get_volume_urls(self, url: str) -> list[str]:
        """Return volume URLs from a series page or a single volume URL.

        Args:
            url: Seven Seas URL.

        Returns:
            Deduplicated volume URLs.
        """
        if "/books/" in url.lower():
            return [url]

        page_html = self._fetch_text(url)
        volumes_block = extract_block_by_class(page_html, "volumes-container", "div")
        links = extract_all_links(volumes_block or page_html, url)
        return [link for link in links if "/books/" in link.lower()]

    def _fetch_volume_patch(self, url: str) -> VolumeMetadataPatch | None:
        """Fetch and parse one Seven Seas volume page.

        Seven Seas stores the volume-specific subtitle and summary together in
        ``div.description-content``. The first paragraph is usually a short
        volume title or promotional heading, while the remaining paragraphs are
        the real summary.

        Args:
            url: Volume page URL.

        Returns:
            Volume metadata patch, or None if no number can be found.
        """
        page_html = self._fetch_text(url)
        page_title = extract_title_tag(page_html)
        number = self._extract_number(url, page_title)
        if not number:
            return None

        description_block = extract_block_by_class(page_html, "description-content", "div")
        volume_title, summary = self._extract_title_and_summary(description_block)

        # Fall back to the browser title only when the description block does
        # not contain a usable volume-specific title.
        if not volume_title:
            volume_title = extract_extra_volume_title(page_title, number)

        # Only use the meta description if the dedicated description block is
        # missing entirely. When the block exists but only contains one paragraph,
        # that paragraph is usually a heading, not a summary.
        if not description_block and not summary:
            summary = get_meta_content(page_html, "description")

        volume_meta = extract_block_by_id(page_html, "volume-meta") or page_html
        year, month, day = parse_date_text(volume_meta)

        return VolumeMetadataPatch(
            number=number,
            title=volume_title,
            summary=summary,
            year=year,
            month=month,
            day=day,
            source_url=url,
        )

    @staticmethod
    def _extract_title_and_summary(description_block: str) -> tuple[str, str]:
        """Extract Seven Seas volume title and summary from description content.

        Seven Seas volume pages usually place an optional short subtitle or
        promotional heading before the real summary. Some pages, however, only
        contain a single summary paragraph and no volume-specific title.

        Args:
            description_block: HTML fragment from ``div.description-content``.

        Returns:
            Two-tuple containing the volume title and summary. Either value may
            be empty if it is not available.
        """
        if not description_block:
            return "", ""

        paragraph_matches = re.findall(
            r"<p\b[^>]*>(.*?)</p>",
            description_block,
            flags=re.IGNORECASE | re.DOTALL,
        )

        paragraphs = [
            normalize_whitespace(strip_html(paragraph))
            for paragraph in paragraph_matches
        ]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]

        if not paragraphs:
            return "", ""

        first_paragraph = paragraphs[0]

        # A single long/narrative paragraph is the summary, not a title.
        if len(paragraphs) == 1:
            if SevenSeasAugmenter._looks_like_summary(first_paragraph):
                return "", first_paragraph
            return first_paragraph, ""

        # Some pages have no heading and start directly with the summary.
        if SevenSeasAugmenter._looks_like_summary(first_paragraph):
            return "", "\n\n".join(paragraphs).strip()

        volume_title = first_paragraph
        summary = "\n\n".join(paragraphs[1:]).strip()

        return volume_title, summary

    @staticmethod
    def _looks_like_summary(text: str) -> bool:
        """Return whether a paragraph looks like descriptive summary text.

        Seven Seas subtitles and promo headings are usually short. Real summaries
        tend to be longer, contain multiple words, and often include sentence
        punctuation. This heuristic prevents a summary-only description block
        from being appended to the fetched title as a false volume subtitle.

        Args:
            text: Plain paragraph text to inspect.

        Returns:
            True if the text is likely a summary paragraph.
        """
        cleaned_text = normalize_whitespace(text)
        if not cleaned_text:
            return False

        words = cleaned_text.split()
        sentence_marks = sum(cleaned_text.count(mark) for mark in ".!?")

        # Long paragraphs are almost certainly summaries.
        if len(words) >= 18:
            return True

        # Multiple sentence endings are also a strong summary signal.
        if sentence_marks >= 2:
            return True

        return False

    @staticmethod
    def _extract_number(url: str, title: str) -> str:
        """Extract a volume number from a Seven Seas URL or title.

        Args:
            url: Volume page URL.
            title: Page title text.

        Returns:
            Normalized number, or an empty string.
        """
        for value in (url, title):
            match = re.search(r"\bvol(?:ume)?[-.\s]*(\d+)\b", value, flags=re.IGNORECASE)
            if match:
                return normalize_number(match.group(1))
        return ""