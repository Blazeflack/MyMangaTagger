# services/constants.py

# Cover Cache
COVER_CACHE_SIZE = 50  # Set default LRU cache size for covers; None means unlimited

#GUI: Fonts
DEFAULT_FONT = ("Segoe UI", 9)
DEFAULT_FONT_BOLD = ("Segoe UI", 9, "bold")
DEFAULT_FONT_ITALIC = ("Segoe UI", 9, "italic")
FONT_LABEL = ("Segoe UI", 9)
FONT_LABEL_BOLD = ("Segoe UI", 9, "bold")
FONT_LARGE_LABEL = ("Segoe UI", 12)
FONT_TAB = ("Segoe UI", 11)
CONSOLE_FONT = ("Consolas", 10)

# GUI: Main Window
APP_TITLE = "MyMangaTagger"
APP_WIDTH = 1200
APP_HEIGHT = 1000
APP_MIN_WIDTH = 1200
APP_MIN_HEIGHT = 1000
LEFT_PANE_MIN_WIDTH = 500
RIGHT_PANE_MIN_WIDTH = 450
THUMBNAIL_WIDTH = 200
THUMBNAIL_HEIGHT = 300

#GUI: FileListPanel
FILELIST_DROP_LABEL = "📂 Drop files here or click to load folder"

# GUI: Log Viewer
LOG_VIEWER_TITLE = "Log Viewer"
LOG_VIEWER_WIDTH = 1100
LOG_VIEWER_HEIGHT = 800

# GUI: Settings
SETTINGS_TITLE = "Settings"
SETTINGS_WIDTH = 750
SETTINGS_HEIGHT = 850

# GUI: URL Dialog
URL_DIALOG_WIDTH = 800
URL_DIALOG_HEIGHT = 260

# GUI: Batch Apply Dialog
BATCH_APPLY_DIALOG_WIDTH = 660
BATCH_APPLY_DIALOG_HEIGHT = 360

# GUI: Fetch Mode constants
# Canonical values used in logic:
FETCH_MODE_PER_FILE: str = "per_file"
FETCH_MODE_SINGLE_APPLY: str = "single_apply"
# Human-friendly labels shown in the OptionMenu (label, value)
FETCH_MODE_OPTIONS: list[tuple[str, str]] = [
    ("Per-file", FETCH_MODE_PER_FILE),
    ("Single URL → Apply to all", FETCH_MODE_SINGLE_APPLY),
]

# Metadata: Genre
IGNORED_GENRE_VALUES = {"original", "original work"}
GENRE_REPLACEMENTS = [
    ("the idolmaster", "The iDOLM@STER"),
    ("the idolm@ster", "The iDOLM@STER"),
]

# Metadata: LanguageISO
LANGUAGES = [
    ("en", "English"),
    ("ja", "Japanese"),
    ("zh", "Chinese"),
    ("ko", "Korean"),
    ("fr", "French"),
    ("de", "German"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("id", "Indonesian"),
]
LANGUAGE_DISPLAY = [f"{code} - {name}" for code, name in LANGUAGES]
LANGUAGE_CODE_MAP = {f"{code} - {name}": code for code, name in LANGUAGES}
DEFAULT_LANGUAGE = ""

# Metadata: Manga
MANGA_VALUES = ["Unknown", "No", "Yes", "YesAndRightToLeft"]
DEFAULT_MANGA = "Yes"

# Metadata: AgeRating
AGERATING_VALUES = [
    "Unknown",
    "Rating Pending",
    "Early Childhood",
    "Everyone",
    "G",
    "Everyone 10+",
    "PG",
    "Kids to Adults",
    "Teen",
    "MA15+",
    "Mature 17+",
    "M",
    "R18+",
    "Adults Only 18+",
    "X18+",
]
DEFAULT_AGERATING = "Unknown"

# Metadata: Special value to indicate mixed values in fields (multi-select)
KEEP_ORIGINAL = "~~~"

# Metadata: Publishers
PUBLISHER_DOMAIN_MAP = {
    "sevenseasentertainment.com": "Seven Seas Entertainment",
    "yenpress.com": "Yen Press",
    "viz.com": "VIZ Media",
    "kodansha.us": "Kodansha USA",
    "onepeacebooks.com": "One Peace Books",
    "kaitenbooks.com": "Kaiten Books",
    "j-novel.club": "J-Novel Club",
}
