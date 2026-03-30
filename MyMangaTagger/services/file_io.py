# services/file_io.py

"""
Module for handling input/output operations on CBZ archives, including reading and writing
ComicInfo.xml metadata, cover image conversion, image format normalization, and archive
manipulation utilities such as renaming and moving files.
"""
import shutil
import zipfile
import xml.etree.ElementTree as ET
import xml.dom.minidom

from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, List, Any

from PIL import Image

from services.constants import IGNORED_GENRE_VALUES
from services.config import DEFAULTS
from services.logger import log
from services.normalization import Normalizer

# The cherry-picked set of ComicInfo 2.1 fields (basic + people + additional)
FIELD_NAMES: List[str] = [
    "Title", "Series", "Number", "Count", "Summary",
    "Year", "Month", "Day", "Writer",
    "Publisher", "Imprint",
    "Genre", "Tags", "Web",
    "LanguageISO", "Manga", "AgeRating",
    "SeriesGroup", "LocalizedSeries",
    # --- People fields ---
    "Penciller", "Inker", "Colorist", "Letterer",
    "CoverArtist", "Editor", "Translator",
    # --- Relationship fields ---
    "Characters", "Teams", "Locations", "MainCharacterOrTeam",
    # --- Alternate / story fields ---
    "AlternateSeries", "AlternateNumber", "AlternateCount",
    "ScanInformation", "StoryArc", "StoryArcNumber", "Notes"
]


class IOService:
    """
    Provides file I/O operations for CBZ archives, including reading/writing ComicInfo.xml,
    converting image formats, and utility methods for file renaming and movement.

    Attributes:
        defaults (Dict[str, Any]): Default field values for ComicInfo.xml.
    """

    FIELD_NAMES = FIELD_NAMES

    def __init__(self) -> None:
        """Initialize an IOService instance."""
        self.defaults: Dict[str, Any] = dict(DEFAULTS)
        self.normalizer = Normalizer()

    def load_cbz_files(self, folder: Path) -> List[Path]:
        """
        Scan a directory non-recursively for .cbz files, renaming any .zip files to .cbz.

        Args:
            folder (Path): Directory to scan for archives.

        Returns:
            List[Path]: Sorted list of .cbz file paths (including renamed archives).
        """
        cbz_files: List[Path] = list(folder.glob("*.cbz"))
        for zip_file in folder.glob("*.zip"):
            cbz = zip_file.with_suffix(".cbz")
            try:
                zip_file.rename(cbz)
                cbz_files.append(cbz)
            except Exception:
                log("ERROR", f"Unable to rename {zip_file} to .cbz", exc_info=True)
        return sorted(cbz_files)

    def extract_comicinfo(self, cbz_path: Path) -> Dict[str, str]:
        """
        Read and parse ComicInfo.xml from a CBZ archive.

        Args:
            cbz_path (Path): Path to the CBZ archive to inspect.

        Returns:
            Dict[str, str]: Mapping of lowercased ComicInfo field names to their values.
                Returns an empty dict if no valid XML is found.
        """
        data: Dict[str, str] = {}
        with zipfile.ZipFile(cbz_path, "r") as zf:
            if "ComicInfo.xml" not in zf.namelist():
                log("DEBUG", f"No ComicInfo.xml found in {cbz_path.name}")
                return data

            raw_xml = zf.read("ComicInfo.xml").decode("utf-8", errors="replace")
            raw_xml = self.normalizer.sanitize_xml_text(raw_xml)
            try:
                log("DEBUG", f"Loading ComicInfo.xml from {cbz_path.name}")
                root = ET.fromstring(raw_xml)
            except ET.ParseError as e:
                log("WARN", f"Error parsing ComicInfo.xml in {cbz_path}: {e}", exc_info=True)
                return data

            for field in FIELD_NAMES:
                # Try to find element case-insensitively
                elem = root.find(field)
                if elem is None:
                    # Try lower case, in case source uses all lowercase
                    elem = root.find(field.lower())
                if elem is None:
                    # Try fully uppercase
                    elem = root.find(field.upper())
                if elem is not None and elem.text is not None:
                    if field in {"Summary", "Web"}:
                        value = elem.text.strip()
                        log("DEBUG", f"Found field {field}: {value}")
                    elif field == "Genre":
                        genres = []
                        for genre in elem.text.split(","):
                            genre_clean = genre.strip()
                            if genre_clean and genre_clean.lower() not in IGNORED_GENRE_VALUES:
                                titled = genre_clean.title()
                                replaced = self.normalizer.apply_genre_replacements(titled)
                                genres.append(replaced)
                        value = ", ".join(genres) if genres else ""
                        value = self.normalizer.normalize_whitespace(value)
                        log("DEBUG", f"Found field Genre: {elem.text}")
                        if elem.text and value != self.normalizer.normalize_whitespace(elem.text):
                            log("DEBUG", f"Filtered genre. New value: {value}")
                    else:
                        value = self.normalizer.normalize_whitespace(elem.text)
                        log("DEBUG", f"Found field {field}: {value}")
                    data[field.lower()] = value
        return data

    @staticmethod
    def prettify_xml(elem: ET.Element) -> str:
        """
        Generate a pretty-printed XML string for an ElementTree element.

        Args:
            elem (ET.Element): Root XML element to format.

        Returns:
            str: UTF-8 encoded, indented XML with declaration and expanded empty tags.
        """
        rough_string = ET.tostring(
            elem,
            encoding="utf-8",
            xml_declaration=True,
            short_empty_elements=False
        )
        reparsed = xml.dom.minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    # ----------------------------
    # New: smart writer (auto-mode)
    # ----------------------------

    def update_cbz_metadata(
        self,
        cbz_path: Path,
        data: Dict[str, str],
        dest_dir: Optional[Path] = None,
        custom_cover_path: Optional[Path] = None,
        overwrite_existing_cover: bool = False,
        metadata_only: Optional[bool] = None,
    ) -> Path:
        """
        Write ComicInfo.xml (and optionally a new cover) using the fastest safe path.

        Auto-selection:
            • Metadata-only fast path when no new cover, no overwrite requested,
              and the archive contains no .webp images.
            • Streamed rebuild otherwise (cover provided, overwrite requested, or .webp present).

        Behavior:
            • Streamed rebuild copies entries without extracting to disk.
            • Images are written with ZIP_STORED (no recompression).
            • ComicInfo.xml is written with ZIP_DEFLATED.
            • Any `.webp` images (including a provided cover) are converted to `.png`.

        Komga notes:
            • Komga computes a file-level and a page-level hash. The file-level hash will
              change because the container changes. Page-level hashes (based on decoded
              image bytes) remain stable in metadata-only mode because page bytes don't change.

        Args:
            cbz_path: Source CBZ path.
            data: ComicInfo fields (lowercased keys).
            dest_dir: If provided, write the output CBZ here; otherwise replace in-place.
            custom_cover_path: Optional path to a new cover image to inject.
            overwrite_existing_cover: If True, replace the first image with the cover (as .png).
                                      If False and a cover is provided, add `00000!__cover.png` at root.
            metadata_only: Force mode selection. None = auto; True = force metadata-only; False = force streamed.

        Returns:
            Path to the written CBZ (replaces original unless dest_dir is provided).
        """
        # 1) Build pretty ComicInfo.xml
        merged = {**self.defaults, **data}
        root = ET.Element("ComicInfo")
        for key in FIELD_NAMES:
            child = ET.SubElement(root, key)
            child.text = merged.get(key.lower(), "")
        pretty_xml = self.prettify_xml(root)
        xml_bytes = pretty_xml.encode("utf-8")

        # 2) Scan source zip for images and .webp presence
        with zipfile.ZipFile(cbz_path, "r") as zin:
            names = zin.namelist()
            image_names = [n for n in names if self._is_image_name(n)]
            has_webp = any(n.lower().endswith(".webp") for n in image_names)
            first_image_name = image_names[0] if image_names else None

        # 3) Decide path
        auto_can_metadata_only = (
            custom_cover_path is None and
            not overwrite_existing_cover and
            not has_webp
        )
        use_metadata_only = (
            (metadata_only is True) or
            (metadata_only is None and auto_can_metadata_only)
        )

        # 4) Destination
        if dest_dir:
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / cbz_path.name
        else:
            out_path = cbz_path.with_suffix(".cbz.tmp")

        if use_metadata_only:
            # FAST PATH: only replace ComicInfo.xml (no image bytes change)
            self._rewrite_zip_streamed(
                src=cbz_path,
                dst=out_path,
                xml_bytes=xml_bytes,
                custom_cover_path=None,
                overwrite_first_image=False,
                add_cover_filename=None,
                convert_webp=False,  # guaranteed no webp by selection
            )
        else:
            # STREAMED REBUILD (cover and/or .webp normalization to .png)
            add_cover_filename: Optional[str] = None
            if custom_cover_path and not overwrite_existing_cover:
                add_cover_filename = "00000!__cover.png"

            self._rewrite_zip_streamed(
                src=cbz_path,
                dst=out_path,
                xml_bytes=xml_bytes,
                custom_cover_path=custom_cover_path,
                overwrite_first_image=bool(overwrite_existing_cover and first_image_name),
                add_cover_filename=add_cover_filename,
                convert_webp=True,
            )

        # 5) Replace in-place if needed
        if out_path.name.endswith(".cbz.tmp"):
            shutil.move(str(out_path), str(cbz_path))
            return cbz_path
        return out_path

    # ----------------------------
    # Streamed rebuild internals
    # ----------------------------

    def _rewrite_zip_streamed(
        self,
        src: Path,
        dst: Path,
        xml_bytes: bytes,
        custom_cover_path: Optional[Path],
        overwrite_first_image: bool,
        add_cover_filename: Optional[str],
        convert_webp: bool,
    ) -> None:
        """
        Stream source ZIP to destination ZIP, optionally:
          - Overwriting the first image with a custom cover (as `.png`),
          - Injecting a `00000!__cover.png` at root,
          - Converting any `.webp` entries to `.png`.

        Images are written with ZIP_STORED; non-images are deflated.
        `ComicInfo.xml` is written last with ZIP_DEFLATED.

        Args:
            src: Source CBZ.
            dst: Destination CBZ (temp or final).
            xml_bytes: Serialized ComicInfo.xml bytes to write.
            custom_cover_path: Optional new cover image path (any readable format).
            overwrite_first_image: If True, replace the first image with the cover.
            add_cover_filename: If set, write a new cover `.png` with this name.
            convert_webp: If True, convert any `.webp` pages (and a WebP cover) to `.png`.
        """
        # Prepare cover bytes (PNG) if provided
        cover_png_bytes: Optional[bytes] = None
        if custom_cover_path:
            cover_png_bytes = self._image_file_to_png_bytes(custom_cover_path)

        with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w") as zout:
            first_image_written = False

            for info in zin.infolist():
                name = info.filename

                # Skip old ComicInfo.xml (we will write our new one at the end)
                if name == "ComicInfo.xml":
                    continue

                # Drop any old injected 00000!__cover.* when adding a new injected cover
                if add_cover_filename and name.lower().startswith("00000!__cover."):
                    continue

                # Overwrite first image with provided cover?
                if self._is_image_name(name) and overwrite_first_image and not first_image_written and cover_png_bytes:
                    arcname = self._change_ext(name, ".png")
                    self._writestr_stored(zout, arcname, cover_png_bytes)
                    first_image_written = True
                    continue

                # Copy or convert current entry
                with zin.open(info, "r") as src_fp:
                    data = src_fp.read()

                if self._is_image_name(name):
                    first_image_written = first_image_written or True
                    if name.lower().endswith(".webp") and convert_webp:
                        log("DEBUG", f"Converting to PNG: {name}")
                        arcname = self._change_ext(name, ".png")
                        png_bytes = self._image_bytes_to_png_bytes(data)
                        self._writestr_stored(zout, arcname, png_bytes)
                    else:
                        # Keep original image name and bytes; store (no compression)
                        self._writestr_stored(zout, name, data)
                else:
                    # Non-image: keep compressed
                    zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

            # Add cover in "Add" mode
            if add_cover_filename and cover_png_bytes:
                self._writestr_stored(zout, add_cover_filename, cover_png_bytes)

            # Finally write ComicInfo.xml
            zout.writestr("ComicInfo.xml", xml_bytes, compress_type=zipfile.ZIP_DEFLATED)

    @staticmethod
    def _is_image_name(name: str) -> bool:
        """Return True if filename appears to be an image page in the archive."""
        lower = name.lower()
        return lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))

    @staticmethod
    def _change_ext(name: str, new_ext: str) -> str:
        """Return filename with its extension changed to `new_ext`."""
        p = Path(name)
        return str(p.with_suffix(new_ext))

    @staticmethod
    def _writestr_stored(zout: zipfile.ZipFile, arcname: str, data: bytes) -> None:
        """
        Write bytes to a ZIP entry using ZIP_STORED (no compression).

        Args:
            zout: Destination ZipFile.
            arcname: Path within archive.
            data: Raw bytes to write.
        """
        zi = zipfile.ZipInfo(filename=arcname)
        zi.compress_type = zipfile.ZIP_STORED
        zout.writestr(zi, data)

    @staticmethod
    def _image_bytes_to_png_bytes(data: bytes) -> bytes:
        """
        Convert arbitrary image bytes to PNG bytes using Pillow.

        Args:
            data: Source image bytes (any format Pillow can read).

        Returns:
            PNG bytes.
        """
        from io import BytesIO
        with Image.open(BytesIO(data)) as im:
            im = im.convert("RGB")
            out = BytesIO()
            # PNG is lossless; Pillow will choose an appropriate compression level
            im.save(out, format="PNG", optimize=True)
            return out.getvalue()

    @staticmethod
    def _image_file_to_png_bytes(path: Path) -> bytes:
        """
        Convert an image file on disk to PNG bytes.

        Args:
            path: Path to the source image file.

        Returns:
            PNG bytes.
        """
        with Image.open(path) as im:
            im = im.convert("RGB")
            out = BytesIO()
            im.save(out, format="PNG", optimize=True)
            return out.getvalue()

    def rename_cbz(self, cbz_path: Path, new_name: str) -> Path:
        """
        Rename a CBZ file.

        Args:
            cbz_path (Path): Original CBZ file path.
            new_name (str): New filename (without path).

        Returns:
            Path: New file path after renaming.
        """
        new_path = cbz_path.with_name(new_name)
        if new_path != cbz_path:
            cbz_path.rename(new_path)
        return new_path

    def move_cbz(self, cbz_path: Path, dest_dir: Path) -> Path:
        """
        Move a CBZ file to a new directory.

        Args:
            cbz_path (Path): Path of the file to move.
            dest_dir (Path): Destination directory path.

        Returns:
            Path: New path of the moved CBZ file.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        new_location = dest_dir / cbz_path.name
        if new_location != cbz_path:
            shutil.move(str(cbz_path), str(new_location))
        return new_location
