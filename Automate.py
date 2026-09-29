#!/usr/bin/env python3
"""
Automate.py  ·  Zotero PDF Fetcher v3.0
Finds Zotero references without PDF attachments, retrieves open-access
PDFs via Unpaywall (with multi-location fallback), validates downloads,
attaches PDFs to the correct Zotero items, and queues remaining DOIs
for manual browser-based retrieval.

Requirements:  pip install requests pyperclip colorama
"""

import os
import csv
import re
import shutil
import sqlite3
import tempfile
import requests
import webbrowser
import json
import time
import logging
import string
import random
import argparse
from urllib.parse import quote
from enum import Enum
from datetime import datetime, timezone

# ── Colorama (graceful fallback if not installed) ──────────────────
try:
    from colorama import Fore, Back, Style, init as _cinit
    _cinit(autoreset=True)
    _HAS_COLOR = True
except ImportError:
    class _Dummy:
        def __getattr__(self, _): return ""
    Fore = Back = Style = _Dummy()
    _HAS_COLOR = False

# ── Color shortcuts ────────────────────────────────────────────────
CY = Fore.CYAN + Style.BRIGHT   # cyan  – headers / borders
GR = Fore.GREEN + Style.BRIGHT   # green – success
YL = Fore.YELLOW + Style.BRIGHT   # yellow – prompts / warnings
RD = Fore.RED + Style.BRIGHT   # red   – errors / failures
MG = Fore.MAGENTA + Style.BRIGHT   # magenta – DOIs / highlights
WH = Fore.WHITE + Style.BRIGHT   # white – normal bright text
BL = Fore.BLUE + Style.BRIGHT   # blue  – info / sub-labels
DM = Style.DIM                     # dim   – secondary text
RS = Style.RESET_ALL               # reset

# ── Styled print helpers ───────────────────────────────────────────


def ok(msg): print(f"{GR}  ✔  {RS}{msg}")
def err(msg): print(f"{RD}  ✘  {RS}{msg}")
def info(msg): print(f"{CY}  ●  {RS}{msg}")
def warn(msg): print(f"{YL}  ⚠  {RS}{msg}")
def skip(msg): print(f"{DM}  ─  {msg}{RS}")
def sep(): print(f"{CY}{'─'*66}{RS}")


# ── Logging ────────────────────────────────────────────────────────
logger = logging.getLogger("zotero_fetcher")


def setup_logging(debug=False):
    """Configure structured logging.  Normal mode is silent; debug is verbose."""
    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    logger.setLevel(level)
    logger.addHandler(handler)


# ── Visible Length Helper for Box Alignment ───────────────────────
def _vlen(s):
    """Calculate visible string length excluding ANSI escape sequences."""
    return len(re.sub(r'\x1b\[[0-9;]*m', '', s))


def print_banner():
    """Print Antigravity CLI-style FAHAD Design & Development banner."""
    box_w = 77
    raw_lines = [
        "",
        f"                                            {WH}D{DM}esign{RS}",
        f"                                                           {WH}▄████▌ ▐██▌{RS}",
        f"                                  {CY}◆───────────────────────{WH}◄█◉██▌ ▐██▌{RS}",
        f"  {WH}███████{RS}      {WH}╱╲{RS}         {MG}╱{RS}   {CY}╭╯{RS}   {MG}╲{RS}        {WH}╱╲{RS}        {WH}██████▄{RS}  {WH}▀████▌ ▐██▌{RS}",
        f"  {WH}██{RS}          {WH}╱  ╲{RS}       {MG}╱{RS}    {CY}│{RS}     {MG}╲{RS}      {WH}╱  ╲{RS}       {WH}██   ▀██{RS}",
        f"  {WH}█████{RS}     {WH}╱    ╲{RS}     {MG}╱{RS}     {CY}│{RS}      {MG}╲{RS}    {WH}╱    ╲{RS}      {WH}██    ██{RS}",
        f"  {WH}██{RS}        {WH}╱──────╲{RS}   {MG}╲{RS}     {CY}│{RS}      {MG}╱{RS}   {WH}╱──────╲{RS}     {WH}██    ██{RS}",
        f"  {WH}██{RS}       {WH}╱        ╲{RS}   {MG}╲{RS}    {CY}│{RS}     {MG}╱{RS}   {WH}╱        ╲{RS}    {WH}██   ▄██{RS}",
        f"  {WH}██{RS}      {WH}╱          ╲{RS}   {MG}╲{RS}  {CY}╰╮{RS}   {MG}╱{RS}   {WH}╱          ╲{RS}   {WH}██████▀{RS}",
        f" {CY}◆───────────────────────────╯{RS}",
        f"  {WH}D{DM}evelopment{RS}",
        "",
    ]

    border_top = f"{CY}  ╔" + "═" * box_w + f"╗{RS}"
    border_mid = f"{CY}  ╠" + "═" * box_w + f"╣{RS}"
    border_bot = f"{CY}  ╚" + "═" * box_w + f"╝{RS}"

    print(border_top)
    for line in raw_lines:
        pad = box_w - _vlen(line)
        print(f"{CY}  ║{RS}{line}" + " " * max(0, pad) + f"{CY}║{RS}")
    print(border_mid)

    sub1 = f"  {GR}● ACTIVE{RS}  {WH}Zotero PDF Automation CLI{RS}  {DM}v3.0{RS}"
    sub1_r = f"{CY}DOWNLOAD RESEARCH PAPERS FASTER{RS}  "
    pad1 = box_w - _vlen(sub1) - _vlen(sub1_r)
    print(f"{CY}  ║{RS}{sub1}" + " " * max(0, pad1) + f"{sub1_r}{CY}║{RS}")

    sub2 = f"  {DM}Smart Duplicate Detection  •  Unpaywall Matcher  •  Brave Captcha Helper{RS}"
    pad2 = box_w - _vlen(sub2)
    print(f"{CY}  ║{RS}{sub2}" + " " * max(0, pad2) + f"{CY}║{RS}")

    print(border_bot)


# ── USER CONFIG ────────────────────────────────────────────────────
# Portable: automatically resolves to the current user's Zotero profile
ZOTERO_DB_PATH = os.path.join(os.path.expanduser("~"), "Zotero", "zotero.sqlite")


def find_brave_browser():
    possible_paths = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.join(os.path.expanduser("~"), r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for p in possible_paths:
        if os.path.isfile(p):
            return p
    return None


BRAVE_PATH = find_brave_browser() or r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
DEFAULT_UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "example123@gmail.com")
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "zotero_pdfs")
STATE_FILE = os.path.join(DOWNLOAD_DIR, "processing_state.json")
# ──────────────────────────────────────────────────────────────────

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Transient HTTP status codes worth retrying
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ══════════════════════════════════════════════════════════════════
#  Paper Processing States
# ══════════════════════════════════════════════════════════════════

class PaperStatus(Enum):
    DISCOVERED = "DISCOVERED"
    NO_DOI = "NO_DOI"
    HAS_EXISTING_PDF = "HAS_EXISTING_PDF"
    DUPLICATE = "DUPLICATE"
    OA_SEARCHING = "OA_SEARCHING"
    OA_FOUND = "OA_FOUND"
    DOWNLOADING = "DOWNLOADING"
    PDF_VALIDATED = "PDF_VALIDATED"
    ZOTERO_ATTACHING = "ZOTERO_ATTACHING"
    COMPLETED = "COMPLETED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    INVALID_PDF = "INVALID_PDF"
    PAYWALL = "PAYWALL"
    CAPTCHA = "CAPTCHA"
    INSTITUTIONAL_ACCESS = "INSTITUTIONAL_ACCESS"
    NO_OA_COPY = "NO_OA_COPY"
    PUBLISHER_ERROR = "PUBLISHER_ERROR"


# ══════════════════════════════════════════════════════════════════
#  DOI Normalization
# ══════════════════════════════════════════════════════════════════

def normalize_doi(raw_doi):
    """
    Normalize a DOI string to its canonical form (``10.xxxx/suffix``).

    Strips common URL prefixes, whitespace, and the ``doi:`` scheme.
    Returns *None* if the value is missing or clearly malformed.
    """
    if not raw_doi:
        return None

    doi = raw_doi.strip()

    # Strip common URL / scheme prefixes (case-insensitive)
    _DOI_PREFIXES = [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ]
    lower = doi.lower()
    for prefix in _DOI_PREFIXES:
        if lower.startswith(prefix):
            doi = doi[len(prefix):]
            break

    doi = doi.strip().rstrip(".")

    # Basic validation – a DOI must start with 10.<registrant>/
    if not re.match(r"^10\.\d{4,}/", doi):
        logger.debug("Malformed DOI rejected: %s", raw_doi)
        return None

    return doi


def doi_to_safe_filename(doi):
    """Convert a DOI to a filesystem-safe base name (no extension)."""
    return re.sub(r'[\\/:*?"<>|]', "-", doi)


def doi_comparison_key(doi):
    """Lowercase key used for duplicate comparison only."""
    return doi.lower().strip() if doi else ""


# ══════════════════════════════════════════════════════════════════
#  PDF Validation
# ══════════════════════════════════════════════════════════════════

def validate_pdf_file(filepath):
    """
    Return True if *filepath* looks like a genuine PDF.

    Checks for the ``%PDF-`` magic bytes and rejects obvious HTML error
    pages masquerading as PDF files.
    """
    try:
        with open(filepath, "rb") as fh:
            header = fh.read(1024)
    except OSError:
        return False

    if not header:
        return False

    # Must start with the PDF magic bytes
    if not header.lstrip(b"\xef\xbb\xbf\x00").startswith(b"%PDF-"):
        logger.debug("File lacks %%PDF- header: %s", filepath)
        return False

    # Reject HTML error / login pages accidentally saved as .pdf
    lower = header[:512].lower()
    if b"<html" in lower or b"<!doctype html" in lower:
        logger.debug("File contains HTML content: %s", filepath)
        return False

    return True


# ══════════════════════════════════════════════════════════════════
#  Persistent Processing State
# ══════════════════════════════════════════════════════════════════

class ProcessingState:
    """Lightweight JSON-backed state for safe resume across runs."""

    def __init__(self):
        self.papers: dict = {}
        self.last_run = None

    # ── load / save ────────────────────────────────────────────────

    @classmethod
    def load(cls):
        state = cls()
        if os.path.isfile(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                state.papers = data.get("papers", {})
                state.last_run = data.get("last_run")
                logger.debug("Loaded processing state (%d papers)", len(state.papers))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load state file: %s", exc)
        return state

    def save(self):
        data = {
            "version": 1,
            "last_run": datetime.now(timezone.utc).isoformat(),
            "papers": self.papers,
        }
        tmp = STATE_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, STATE_FILE)
        except OSError as exc:
            logger.warning("Could not save state file: %s", exc)

    # ── query helpers ──────────────────────────────────────────────

    def _key(self, item_id):
        return f"item_{item_id}"

    def get_paper(self, item_id):
        return self.papers.get(self._key(item_id))

    def is_completed(self, item_id):
        p = self.get_paper(item_id)
        return p is not None and p.get("status") == PaperStatus.COMPLETED.value

    def is_pdf_validated(self, item_id):
        p = self.get_paper(item_id)
        return p is not None and p.get("status") == PaperStatus.PDF_VALIDATED.value

    def get_downloaded_path(self, item_id):
        p = self.get_paper(item_id)
        return p.get("downloaded_path") if p else None

    # ── update ─────────────────────────────────────────────────────

    def update_paper(self, item_id, *, doi=None, title=None, status=None,
                     failure_reason=None, downloaded_path=None,
                     oa_source=None, oa_url=None, attached=None):
        key = self._key(item_id)
        paper = self.papers.setdefault(key, {"item_id": item_id})
        if doi is not None:
            paper["doi"] = doi
        if title is not None:
            paper["title"] = title
        if status is not None:
            paper["status"] = status.value if isinstance(status, PaperStatus) else status
        if failure_reason is not None:
            paper["failure_reason"] = failure_reason
        if downloaded_path is not None:
            paper["downloaded_path"] = downloaded_path
        if oa_source is not None:
            paper["oa_source"] = oa_source
        if oa_url is not None:
            paper["oa_url"] = oa_url
        if attached is not None:
            paper["attached"] = attached
        paper["attempt_count"] = paper.get("attempt_count", 0) + 1
        paper["last_attempt"] = datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════
#  Database helpers
# ══════════════════════════════════════════════════════════════════

def connect_zotero_db(db_path):
    """
    Connect to Zotero SQLite safely.

    Returns ``(connection, temp_dir | None, is_live_db)``.

    * *is_live_db* is True when we connected directly (Zotero is closed)
      and we can safely write attachments.
    * When Zotero holds the lock we use the SQLite backup API to create a
      consistent read-only snapshot in a temp directory.
    """
    # ── Try direct connection first ────────────────────────────────
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("SELECT 1 FROM collections LIMIT 1")
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        return conn, None, True
    except sqlite3.OperationalError:
        pass

    # ── Zotero is running → safe snapshot via backup API ──────────
    warn("Zotero is running — creating a safe database snapshot.")
    temp_dir = tempfile.mkdtemp(prefix="zotero_db_")
    temp_db = os.path.join(temp_dir, "zotero.sqlite")

    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(temp_db)
        src.backup(dst)
        src.close()
        dst.close()
        logger.debug("Snapshot created via SQLite backup API")
    except Exception:
        # Fallback: plain file copy (less safe but better than nothing)
        logger.debug("Backup API failed; falling back to file copy")
        for ext in ["", "-wal", "-shm"]:
            s, d = db_path + ext, temp_db + ext
            if os.path.exists(s):
                try:
                    shutil.copyfile(s, d)
                except Exception:
                    pass

    conn = sqlite3.connect(temp_db)
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    return conn, temp_dir, False


def get_all_collections(conn):
    """All non-deleted collections with item counts."""
    cur = conn.cursor()
    cur.execute("""
      SELECT c.collectionID, c.collectionName, COUNT(ci.itemID) AS itemCount
      FROM collections c
      LEFT JOIN deletedCollections dc ON c.collectionID = dc.collectionID
      LEFT JOIN collectionItems ci    ON c.collectionID = ci.collectionID
      WHERE dc.collectionID IS NULL
      GROUP BY c.collectionID, c.collectionName
      ORDER BY c.collectionName
    """)
    return cur.fetchall()


def select_collection(conn):
    """Interactive numbered menu to pick a Zotero collection."""
    collections = get_all_collections(conn)
    if not collections:
        err("No collections found in your Zotero database.")
        return None, None

    print(f"\n{CY}  ╔{'═'*56}╗")
    print(f"  ║{'  AVAILABLE ZOTERO COLLECTIONS':^56}║")
    print(f"  ╚{'═'*56}╝{RS}\n")
    for idx, (_, coll_name, count) in enumerate(collections, start=1):
        label = coll_name[:50] + "…" if len(coll_name) > 50 else coll_name
        print(f"  {YL}{idx:>2}{RS}) {WH}{label}{RS}  {DM}({count} items){RS}")

    print()
    while True:
        choice = input(f"{YL}  ❯ Select collection number (1-{len(collections)}) or 'q' to quit: {RS}").strip()
        if choice.lower() in ('q', 'quit'):
            return None, None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(collections):
                selected = collections[idx - 1]
                print(f"\n{GR}  ✔  Selected:{RS} {MG}{selected[1]}{RS}\n")
                return selected[0], selected[1]
        warn(f"Invalid — enter a number between 1 and {len(collections)}.")


def get_unpaywall_email():
    """Ask user for their Unpaywall API email."""
    print(f"\n{CY}  ╔{'═'*56}╗")
    print(f"  ║{'  UNPAYWALL API EMAIL':^56}║")
    print(f"  ╚{'═'*56}╝{RS}")
    hint = f" [{DEFAULT_UNPAYWALL_EMAIL}]" if DEFAULT_UNPAYWALL_EMAIL else ""
    while True:
        email = input(f"\n{YL}  ❯ Email{hint}: {RS}").strip()
        if not email and DEFAULT_UNPAYWALL_EMAIL:
            ok(f"Using default: {DM}{DEFAULT_UNPAYWALL_EMAIL}{RS}")
            return DEFAULT_UNPAYWALL_EMAIL
        if "@" in email and "." in email:
            ok(f"Using: {DM}{email}{RS}")
            return email
        warn("Please enter a valid email address (e.g. user@example.com).")


def get_item_ids_in_collection(conn, collection_id):
    cur = conn.cursor()
    cur.execute("SELECT itemID FROM collectionItems WHERE collectionID = ?", (collection_id,))
    return [r[0] for r in cur.fetchall()]


# ── Batch metadata loader ─────────────────────────────────────────

def batch_load_collection_metadata(conn, collection_id):
    """
    Load DOI, title, date, first-author, and direct-PDF status for every
    item in *collection_id* with minimal round-trips.

    Returns ``(items_list, library_dois_with_pdf_set)``.
    """
    cur = conn.cursor()

    # 1. Pivot DOI / title / date for every item in the collection
    cur.execute("""
        SELECT ci.itemID,
               MAX(CASE WHEN f.fieldName = 'DOI'   THEN idv.value END),
               MAX(CASE WHEN f.fieldName = 'title'  THEN idv.value END),
               MAX(CASE WHEN f.fieldName = 'date'   THEN idv.value END)
        FROM collectionItems ci
        LEFT JOIN itemData       id  ON ci.itemID  = id.itemID
        LEFT JOIN fields         f   ON id.fieldID = f.fieldID
        LEFT JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE ci.collectionID = ?
        GROUP BY ci.itemID
    """, (collection_id,))
    raw = cur.fetchall()
    item_ids = [r[0] for r in raw]

    # 2. Which of these items already have a direct PDF attachment?
    items_with_pdf = set()
    if item_ids:
        ph = ",".join("?" * len(item_ids))
        cur.execute(f"""
            SELECT DISTINCT ia.parentItemID
            FROM itemAttachments ia
            LEFT JOIN deletedItems di ON ia.itemID = di.itemID
            WHERE ia.parentItemID IN ({ph}) AND di.itemID IS NULL
              AND (ia.contentType = 'application/pdf'
                   OR LOWER(ia.path) LIKE '%.pdf')
        """, item_ids)
        items_with_pdf = {r[0] for r in cur.fetchall()}

    # 3. All DOIs *anywhere* in the library that already have a PDF
    cur.execute("""
        SELECT DISTINCT LOWER(TRIM(idv.value))
        FROM itemAttachments ia
        JOIN itemData       id  ON ia.parentItemID = id.itemID
        JOIN fields         f   ON id.fieldID      = f.fieldID
        JOIN itemDataValues idv ON id.valueID       = idv.valueID
        LEFT JOIN deletedItems di ON ia.itemID      = di.itemID
        WHERE f.fieldName = 'DOI' AND di.itemID IS NULL
          AND (ia.contentType = 'application/pdf'
               OR LOWER(ia.path) LIKE '%.pdf')
    """)
    library_dois_with_pdf = {r[0] for r in cur.fetchall()}

    # 4. First-author last name per item (orderIndex = 0)
    first_authors = {}
    if item_ids:
        ph = ",".join("?" * len(item_ids))
        cur.execute(f"""
            SELECT ic.itemID, c.lastName
            FROM itemCreators ic
            JOIN creators c ON ic.creatorID = c.creatorID
            WHERE ic.itemID IN ({ph}) AND ic.orderIndex = 0
        """, item_ids)
        for r in cur.fetchall():
            first_authors[r[0]] = r[1]

    # 5. Build item list
    items = []
    for row in raw:
        item_id, doi_raw, title, date_raw = row
        year = None
        if date_raw:
            m = re.search(r"\b(19|20)\d{2}\b", date_raw)
            year = m.group(0) if m else None

        items.append({
            "item_id":        item_id,
            "doi_raw":        doi_raw,
            "doi":            normalize_doi(doi_raw),
            "title":          title,
            "year":           year,
            "first_author":   first_authors.get(item_id),
            "has_direct_pdf": item_id in items_with_pdf,
        })

    return items, library_dois_with_pdf


# ── Per-item fallback queries (kept for edge cases) ───────────────

def item_has_pdf_attachment(conn, item_id, doi=None, title=None):
    """
    Return True if a PDF already exists in Zotero for this paper.
    Checks: (1) direct attachment, (2) same DOI on another entry,
            (3) same title on another entry.
    Excludes items in the Zotero Trash (deletedItems).
    """
    cur = conn.cursor()

    # 1. Direct attachment
    cur.execute("""
      SELECT COUNT(*) FROM itemAttachments ia
      LEFT JOIN deletedItems di ON ia.itemID = di.itemID
      WHERE ia.parentItemID = ? AND di.itemID IS NULL
        AND (ia.contentType = 'application/pdf' OR LOWER(ia.path) LIKE '%.pdf')
    """, (item_id,))
    if cur.fetchone()[0] > 0:
        return True

    # 2. Same DOI elsewhere
    if doi:
        cur.execute("""
          SELECT COUNT(*) FROM itemAttachments ia
          JOIN itemData id   ON ia.parentItemID = id.itemID
          JOIN fields f      ON id.fieldID = f.fieldID
          JOIN itemDataValues idv ON id.valueID = idv.valueID
          LEFT JOIN deletedItems di ON ia.itemID = di.itemID
          WHERE f.fieldName = 'DOI'
            AND LOWER(TRIM(idv.value)) = LOWER(TRIM(?)) AND di.itemID IS NULL
            AND (ia.contentType = 'application/pdf' OR LOWER(ia.path) LIKE '%.pdf')
        """, (doi,))
        if cur.fetchone()[0] > 0:
            return True

    # 3. Same title elsewhere
    if title and len(title.strip()) > 5:
        cur.execute("""
          SELECT COUNT(*) FROM itemAttachments ia
          JOIN itemData id   ON ia.parentItemID = id.itemID
          JOIN fields f      ON id.fieldID = f.fieldID
          JOIN itemDataValues idv ON id.valueID = idv.valueID
          LEFT JOIN deletedItems di ON ia.itemID = di.itemID
          WHERE f.fieldName = 'title'
            AND LOWER(TRIM(idv.value)) = LOWER(TRIM(?)) AND di.itemID IS NULL
            AND (ia.contentType = 'application/pdf' OR LOWER(ia.path) LIKE '%.pdf')
        """, (title,))
        if cur.fetchone()[0] > 0:
            return True

    return False


def get_doi_for_item(conn, item_id):
    cur = conn.cursor()
    cur.execute("""
      SELECT idv.value FROM itemData id
      JOIN fields f ON id.fieldID = f.fieldID
      JOIN itemDataValues idv ON id.valueID = idv.valueID
      WHERE id.itemID = ? AND f.fieldName = 'DOI'
    """, (item_id,))
    row = cur.fetchone()
    return row[0] if row else None


def get_title_for_item(conn, item_id):
    cur = conn.cursor()
    cur.execute("""
      SELECT idv.value FROM itemData id
      JOIN fields f ON id.fieldID = f.fieldID
      JOIN itemDataValues idv ON id.valueID = idv.valueID
      WHERE id.itemID = ? AND f.fieldName = 'title'
    """, (item_id,))
    row = cur.fetchone()
    return row[0] if row else None


# ══════════════════════════════════════════════════════════════════
#  Improved Duplicate Detection
# ══════════════════════════════════════════════════════════════════

def check_duplicate(item, library_dois_with_pdf, all_items_by_title):
    """
    Three-tier duplicate detection.

    Returns ``(is_duplicate, match_strength, message)``.

    * *strong*   — same DOI already has a PDF somewhere in the library
    * *reasonable* — same normalised title + matching author or year
    * *weak*     — same title only → warn but do **not** auto-skip
    """
    doi = item.get("doi")
    if doi and doi_comparison_key(doi) in library_dois_with_pdf:
        return True, "strong", "Another item with this DOI already has a PDF"

    title = (item.get("title") or "").strip()
    if not title or len(title) <= 5:
        return False, None, None

    title_key = title.lower()
    matches = all_items_by_title.get(title_key, [])
    for other in matches:
        if other["item_id"] == item["item_id"]:
            continue
        if not other.get("has_direct_pdf"):
            continue

        # Same title + shared author or year → reasonable
        same_author = (
            item.get("first_author") and other.get("first_author")
            and item["first_author"].lower() == other["first_author"].lower()
        )
        same_year = (
            item.get("year") and other.get("year")
            and item["year"] == other["year"]
        )
        if same_author or same_year:
            return True, "reasonable", (
                f"Likely duplicate (title + {'author' if same_author else 'year'} match "
                f"item {other['item_id']})"
            )

        # Title-only match → weak, just warn
        return False, "weak", (
            f"Possible duplicate (title matches item {other['item_id']}) — processing anyway"
        )

    return False, None, None


# ── Clipboard ──────────────────────────────────────────────────────

def copy_to_clipboard(text):
    if not text:
        return False
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        try:
            import subprocess
            subprocess.run(['clip'], input=text.strip().encode('utf-16'), check=True)
            return True
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════
#  Network helpers  (retry + backoff)
# ══════════════════════════════════════════════════════════════════

def _request_with_retry(method, url, *, max_retries=3, base_delay=2, **kwargs):
    """
    HTTP request with exponential back-off for transient errors.

    Only retries on connection errors, timeouts, and 429/5xx status codes.
    """
    kwargs.setdefault("timeout", 30)
    last_exc = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
            if resp.status_code not in _RETRYABLE_STATUS_CODES:
                return resp
            logger.debug("Retryable %d from %s (attempt %d)", resp.status_code, url, attempt)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            logger.debug("Network error on %s (attempt %d): %s", url, attempt, exc)
            resp = None

        if attempt < max_retries:
            delay = base_delay * (2 ** (attempt - 1))
            logger.debug("Waiting %.1fs before retry…", delay)
            time.sleep(delay)

    # Exhausted retries
    if resp is not None:
        return resp
    if last_exc is not None:
        raise last_exc
    raise requests.ConnectionError(f"Failed after {max_retries} retries: {url}")


def query_unpaywall(doi, email):
    url = f"https://api.unpaywall.org/v2/{quote(doi)}?email={quote(email)}"
    try:
        r = _request_with_retry("GET", url, max_retries=2, timeout=20)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as exc:
        logger.debug("Unpaywall query failed for %s: %s", doi, exc)
        return None


# ══════════════════════════════════════════════════════════════════
#  OA Resolution — extensible multi-source architecture
# ══════════════════════════════════════════════════════════════════

def resolve_open_access_paper(doi, email):
    """
    Find legitimate open-access PDF URLs for *doi*.

    Returns a list of dicts sorted by descending confidence::

        [{"source", "url", "is_pdf", "confidence", "host_type", "version"}, …]

    Currently uses Unpaywall; architecture supports adding resolvers.
    """
    results = []
    results.extend(_resolve_unpaywall(doi, email))
    # Future resolvers can be appended here:
    # results.extend(_resolve_openalex(doi))
    # results.extend(_resolve_pmc(doi))
    results.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    return results


def _resolve_unpaywall(doi, email):
    """Query Unpaywall and return ALL legitimate OA locations."""
    data = query_unpaywall(doi, email)
    if not data:
        return []

    results = []
    seen_urls = set()

    # Gather all OA locations, including best_oa_location
    oa_locations = list(data.get("oa_locations") or [])
    best = data.get("best_oa_location")
    if best:
        oa_locations.insert(0, best)

    for loc in oa_locations:
        for url_type, key in [("pdf_url", "url_for_pdf"),
                               ("landing_page", "url_for_landing_page"),
                               ("generic", "url")]:
            url = loc.get(key)
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append({
                    "source":    "unpaywall",
                    "url":       url,
                    "url_type":  url_type,
                    "is_pdf":    url_type == "pdf_url",
                    "confidence": 0.95 if url_type == "pdf_url" else 0.4,
                    "host_type": loc.get("host_type", ""),
                    "version":   loc.get("version", ""),
                })

    return results


# ══════════════════════════════════════════════════════════════════
#  Safe PDF Download
# ══════════════════════════════════════════════════════════════════

def download_pdf_safe(url, final_path, *, max_retries=3):
    """
    Download a PDF to *final_path* using atomic rename.

    1. Streams into ``<final_path>.part``
    2. Validates the content is actually PDF
    3. Renames to *final_path* via ``os.replace()``

    Returns ``(success, failure_reason)``.
    """
    part_path = final_path + ".part"

    try:
        resp = _request_with_retry("GET", url, max_retries=max_retries,
                                   stream=True, timeout=60)

        if resp.status_code == 403:
            return False, "PAYWALL"
        if resp.status_code == 429:
            return False, "RATE_LIMITED"
        if resp.status_code != 200:
            return False, f"HTTP_{resp.status_code}"

        # Stream to .part file
        try:
            with open(part_path, "wb") as fh:
                for chunk in resp.iter_content(64 * 1024):
                    fh.write(chunk)
        except Exception as exc:
            _safe_remove(part_path)
            return False, f"WRITE_ERROR: {exc}"

        # Validate actual PDF content
        if not validate_pdf_file(part_path):
            _safe_remove(part_path)
            return False, "INVALID_PDF"

        # Atomic rename
        os.replace(part_path, final_path)
        return True, None

    except (requests.ConnectionError, requests.Timeout) as exc:
        _safe_remove(part_path)
        return False, f"NETWORK_ERROR: {exc}"
    except Exception as exc:
        _safe_remove(part_path)
        return False, f"UNEXPECTED: {exc}"


def _safe_remove(path):
    """Remove a file if it exists, ignoring errors."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# Legacy wrapper so old call-sites still work
def download_pdf(url, filename):
    success, _ = download_pdf_safe(url, filename)
    return success


# ── Browser ────────────────────────────────────────────────────────

def open_in_brave(url):
    if os.path.isfile(BRAVE_PATH):
        webbrowser.register('brave', None, webbrowser.BackgroundBrowser(BRAVE_PATH))
        webbrowser.get('brave').open(url)
    else:
        webbrowser.open(url)


# ══════════════════════════════════════════════════════════════════
#  Zotero Attachment (linked-file, safe + transactional)
# ══════════════════════════════════════════════════════════════════

def _generate_zotero_key(conn):
    """Generate a unique 8-character key compatible with Zotero's format."""
    chars = string.ascii_uppercase + string.digits
    cur = conn.cursor()
    for _ in range(100):
        key = "".join(random.choices(chars, k=8))
        cur.execute("SELECT COUNT(*) FROM items WHERE key = ?", (key,))
        if cur.fetchone()[0] == 0:
            return key
    raise RuntimeError("Could not generate a unique Zotero item key")


def attach_pdf_to_zotero_item(conn, item_id, pdf_path):
    """
    Create a **linked-file** attachment (linkMode=2) in the Zotero database.

    This is the safest write operation: the PDF stays in the download
    directory and Zotero simply records a reference to it.

    Returns ``(success, detail)`` where *detail* is the new attachment
    itemID on success or an error message on failure.
    """
    cur = conn.cursor()

    # ── Look up the attachment itemTypeID from Zotero's schema ─────
    cur.execute("SELECT itemTypeID FROM itemTypes WHERE typeName = 'attachment'")
    row = cur.fetchone()
    if not row:
        return False, "Cannot locate 'attachment' itemType in Zotero schema"
    attachment_type_id = row[0]

    # ── Parent item's libraryID ────────────────────────────────────
    cur.execute("SELECT libraryID FROM items WHERE itemID = ?", (item_id,))
    row = cur.fetchone()
    if not row:
        return False, f"Parent item {item_id} not found in items table"
    library_id = row[0]

    # ── Check we are not creating a duplicate attachment ───────────
    abs_path = os.path.abspath(pdf_path)
    cur.execute("""
        SELECT COUNT(*) FROM itemAttachments
        WHERE parentItemID = ? AND path = ?
    """, (item_id, abs_path))
    if cur.fetchone()[0] > 0:
        logger.debug("Attachment already exists for item %d → %s", item_id, abs_path)
        return True, "already_attached"

    # ── Generate unique key & timestamp ────────────────────────────
    key = _generate_zotero_key(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        cur.execute("""
            INSERT INTO items
                (itemTypeID, dateAdded, dateModified, clientDateModified,
                 libraryID, key, version, synced)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        """, (attachment_type_id, now, now, now, library_id, key))
        new_id = cur.lastrowid

        cur.execute("""
            INSERT INTO itemAttachments
                (itemID, parentItemID, linkMode, contentType, path, syncState)
            VALUES (?, ?, 2, 'application/pdf', ?, 0)
        """, (new_id, item_id, abs_path))

        conn.commit()
        logger.debug("Attached PDF to item %d as linked file (new itemID=%d)", item_id, new_id)
        return True, new_id

    except Exception as exc:
        conn.rollback()
        logger.warning("Failed to attach PDF to item %d: %s", item_id, exc)
        return False, str(exc)


def verify_zotero_attachment(conn, item_id, pdf_path):
    """
    Verify that *item_id* has an attachment pointing to *pdf_path*
    and that the file exists and is a valid PDF.
    """
    abs_path = os.path.abspath(pdf_path)
    cur = conn.cursor()

    # 1. Attachment row exists?
    cur.execute("""
        SELECT ia.itemID FROM itemAttachments ia
        WHERE ia.parentItemID = ? AND ia.path = ?
    """, (item_id, abs_path))
    if not cur.fetchone():
        return False, "No attachment row found in database"

    # 2. File exists on disk?
    if not os.path.isfile(abs_path):
        return False, "PDF file does not exist on disk"

    # 3. File is a valid PDF?
    if not validate_pdf_file(abs_path):
        return False, "File on disk is not a valid PDF"

    return True, "OK"


def _attach_and_verify(conn, item_id, pdf_path, state, is_live):
    """Attach + verify helper used by the main loop and manual queue."""
    if not is_live:
        state.update_paper(item_id, status=PaperStatus.PDF_VALIDATED,
                           downloaded_path=os.path.abspath(pdf_path))
        return False  # cannot attach when using snapshot

    state.update_paper(item_id, status=PaperStatus.ZOTERO_ATTACHING)
    att_ok, att_detail = attach_pdf_to_zotero_item(conn, item_id, pdf_path)
    if not att_ok:
        warn(f"Attachment failed: {att_detail}")
        state.update_paper(item_id, status=PaperStatus.PDF_VALIDATED,
                           failure_reason=f"ATTACH_FAILED: {att_detail}")
        return False

    ver_ok, ver_msg = verify_zotero_attachment(conn, item_id, pdf_path)
    if not ver_ok:
        warn(f"Verification failed: {ver_msg}")
        state.update_paper(item_id, status=PaperStatus.PDF_VALIDATED,
                           failure_reason=f"VERIFY_FAILED: {ver_msg}")
        return False

    state.update_paper(item_id, status=PaperStatus.COMPLETED, attached=True)
    return True


# ── Interactive prompts ────────────────────────────────────────────

def wait_for_captcha():
    """
    Ask the user to solve the captcha, then ask if they downloaded the PDF.
    Returns True if downloaded, False if not (logs to CSV).
    """
    print()
    while True:
        choice = input(f"  {YL}❯ Did you solve the captcha? (Y/N): {RS}").strip().lower()
        if choice == 'y':
            break
        elif choice == 'n':
            print(f"  {DM}  Waiting… solve the captcha in your browser.{RS}")
        else:
            warn("Please enter 'Y' or 'N'.")

    while True:
        downloaded = input(f"  {YL}❯ Did you download the PDF?       (Y/N): {RS}").strip().lower()
        if downloaded == 'y':
            ok("Downloaded — moving to next paper.")
            print()
            return True
        elif downloaded == 'n':
            warn("Noted — this paper will be saved to the failed list.")
            print()
            return False
        else:
            warn("Please enter 'Y' or 'N'.")


# ══════════════════════════════════════════════════════════════════
#  Manual Queue Processing
# ══════════════════════════════════════════════════════════════════

def _snapshot_download_dirs():
    """Return a set of existing PDF paths in common download directories."""
    dirs = [DOWNLOAD_DIR, os.path.join(os.path.expanduser("~"), "Downloads")]
    known = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.lower().endswith(".pdf"):
                known.add(os.path.join(d, f))
    return known


def _detect_new_pdfs(known_before):
    """Return validated new PDFs that appeared since *known_before* snapshot."""
    current = _snapshot_download_dirs()
    new_files = current - known_before
    return [p for p in sorted(new_files) if validate_pdf_file(p)]


def process_manual_queue(queue, conn, is_live, state):
    """
    Present the manual queue and let the user handle papers one-by-one.
    Automatically detects new PDFs in the download directories.
    """
    if not queue:
        return 0

    print(f"\n{CY}  ╔{'═'*56}╗")
    print(f"  ║{'  MANUAL QUEUE':^56}║")
    print(f"  ╚{'═'*56}╝{RS}\n")
    print(f"  {WH}{len(queue)}{RS} paper(s) require manual attention:\n")

    for i, paper in enumerate(queue, 1):
        reason = paper.get("reason", "UNKNOWN")
        title = (paper.get("title") or "Unknown")[:50]
        print(f"  {YL}{i:>2}{RS}) {WH}{title}{RS}  {DM}— {reason}{RS}")

    print()
    choice = input(f"  {YL}❯ Process manual queue now? (Y/N): {RS}").strip().lower()
    if choice != "y":
        info("Manual queue saved to CSV.  Re-run to process later.")
        return 0

    completed = 0

    for idx, paper in enumerate(queue, 1):
        item_id = paper["item_id"]
        doi = paper.get("doi")
        title = paper.get("title") or "Unknown"

        sep()
        print(f"\n  {BL}[{idx}/{len(queue)}]{RS}  {WH}{title[:60]}{RS}")
        if doi:
            print(f"  {DM}DOI:{RS}  {MG}{doi}{RS}")
        print(f"  {DM}Reason:{RS} {paper.get('reason', 'UNKNOWN')}")

        # Copy title as safe filename to clipboard
        if title:
            safe_title = re.sub(r'[\\/:*?"<>|]', '-', title).strip()
            copy_to_clipboard(f"{safe_title}.pdf")
            info("Title copied to clipboard (as filename)")

        # Snapshot downloads before opening browser
        known_before = _snapshot_download_dirs()

        # Open DOI / publisher page
        if doi:
            doi_url = f"https://doi.org/{doi}"
            info(f"Opening: {DM}{doi_url}{RS}")
            open_in_brave(doi_url)
        else:
            warn("No DOI available — please search manually.")

        print()
        action = input(
            f"  {YL}❯ Press Enter when done, 's' to skip, 'q' to quit queue: {RS}"
        ).strip().lower()

        if action == "q":
            info("Leaving manual queue.")
            break
        if action == "s":
            skip(f"Skipped item {item_id}")
            continue

        # ── Detect newly downloaded PDFs ───────────────────────────
        new_pdfs = _detect_new_pdfs(known_before)

        pdf_path = None
        if new_pdfs:
            if len(new_pdfs) == 1:
                pdf_path = new_pdfs[0]
                ok(f"PDF detected: {DM}{os.path.basename(pdf_path)}{RS}")
            else:
                print(f"\n  {WH}Multiple new PDFs detected:{RS}")
                for j, p in enumerate(new_pdfs, 1):
                    print(f"  {YL}{j}{RS}) {os.path.basename(p)}")
                while True:
                    pick = input(
                        f"  {YL}❯ Select the correct PDF (1-{len(new_pdfs)}): {RS}"
                    ).strip()
                    if pick.isdigit() and 1 <= int(pick) <= len(new_pdfs):
                        pdf_path = new_pdfs[int(pick) - 1]
                        break
                    warn("Invalid selection.")
        else:
            warn("No new PDF detected automatically.")
            downloaded = input(
                f"  {YL}❯ Did you download the PDF? (Y/N): {RS}"
            ).strip().lower()
            if downloaded == "y":
                # Ask user to provide the path
                manual_path = input(
                    f"  {YL}❯ Paste the full path to the PDF (or Enter to skip): {RS}"
                ).strip().strip('"').strip("'")
                if manual_path and os.path.isfile(manual_path) and validate_pdf_file(manual_path):
                    pdf_path = manual_path
                elif manual_path:
                    err("File not found or not a valid PDF.")

        if pdf_path:
            # Move / copy to our download dir if it's outside
            safe_name = doi_to_safe_filename(doi) if doi else f"manual_{item_id}"
            final_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.pdf")
            if os.path.abspath(pdf_path) != os.path.abspath(final_path):
                try:
                    shutil.copy2(pdf_path, final_path)
                except OSError:
                    final_path = pdf_path  # use in-place if copy fails

            state.update_paper(item_id, status=PaperStatus.PDF_VALIDATED,
                               downloaded_path=os.path.abspath(final_path))
            if _attach_and_verify(conn, item_id, final_path, state, is_live):
                ok("PDF attached to Zotero and verified!")
                completed += 1
            else:
                if is_live:
                    warn("PDF downloaded but Zotero attachment could not be verified.")
                else:
                    info("PDF saved. Close Zotero and re-run to attach.")
                completed += 1
        else:
            state.update_paper(item_id, status=PaperStatus.MANUAL_REQUIRED,
                               failure_reason=paper.get("reason"))

    return completed


# ── CSV export ─────────────────────────────────────────────────────

def save_failed_csv(failed_list, coll_name):
    """
    Save papers the user couldn't download to an enhanced CSV file.
    Location: ~/Downloads/zoteroCSV/<CollectionName>.csv
    """
    csv_dir = os.path.join(os.path.expanduser("~"), "Downloads", "zoteroCSV")
    os.makedirs(csv_dir, exist_ok=True)

    safe_name = re.sub(r'[\\/*?:"<>|]', '_', coll_name)[:100].strip()
    csv_path = os.path.join(csv_dir, f"{safe_name}.csv")

    fieldnames = [
        "ItemID", "Title", "DOI", "Status", "FailureReason",
        "OAFound", "OAURL", "Source", "AttemptCount", "Timestamp",
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in failed_list:
            writer.writerow({
                "ItemID":        entry.get("item_id", ""),
                "Title":         entry.get("title", ""),
                "DOI":           entry.get("doi", ""),
                "Status":        entry.get("status", "MANUAL"),
                "FailureReason": entry.get("reason", ""),
                "OAFound":       entry.get("oa_found", ""),
                "OAURL":         entry.get("oa_url", ""),
                "Source":        entry.get("source", ""),
                "AttemptCount":  entry.get("attempt_count", 1),
                "Timestamp":     datetime.now(timezone.utc).isoformat(),
            })

    print(f"\n{CY}  ╔{'═'*56}╗")
    print(f"  ║{YL}{'  ⚠  FAILED DOWNLOADS REPORT':^56}{CY}║")
    print(f"  ╠{'═'*56}╣")
    print(f"  ║  {RD}{len(failed_list)} paper(s){RS} could not be downloaded{CY}{'':{' '}>20}║")
    print(f"  ║  {DM}Saved to:{RS}{CY}{'':{' '}>46}║")
    print(f"  ║  {WH}{csv_path[:54]}{CY}{'':{' '}>{max(0, 54-len(csv_path[:54]))}}║")
    print(f"  ╚{'═'*56}╝{RS}\n")
    return csv_path


# ── CLI Summary ────────────────────────────────────────────────────

def print_summary(counters):
    """Print a detailed end-of-run summary table."""
    total = counters.get("total", 0)

    rows = [
        ("Total papers",              total),
        ("Already had PDF",           counters.get("has_pdf", 0)),
        ("Duplicates skipped",        counters.get("duplicate", 0)),
        ("No DOI",                    counters.get("no_doi", 0)),
        ("Downloaded automatically",  counters.get("downloaded", 0)),
        ("Reused existing download",  counters.get("reused", 0)),
        ("Attached to Zotero",        counters.get("attached", 0)),
        ("Manual required",           counters.get("manual", 0)),
        ("Failed",                    counters.get("failed", 0)),
        ("Resumed (already done)",    counters.get("resumed", 0)),
    ]

    w = 56
    print(f"\n{CY}  ╔{'═'*w}╗")
    print(f"  ║{'  PROCESSING COMPLETE':^{w}}║")
    print(f"  ╠{'═'*w}╣{RS}")
    for label, count in rows:
        if count > 0 or label == "Total papers":
            val = str(count)
            pad = w - 4 - len(label) - len(val)
            print(f"{CY}  ║{RS}  {WH}{label}{RS}{'·' * max(1, pad)}{GR if count > 0 else DM}{val}{RS}  {CY}║{RS}")
    print(f"{CY}  ╚{'═'*w}╝{RS}\n")


# ══════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════

def main():
    # ── CLI arguments ──────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Zotero PDF Fetcher — automate research-paper retrieval"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    setup_logging(debug=args.debug)

    print_banner()

    if not os.path.isfile(ZOTERO_DB_PATH):
        err(f"Zotero DB not found at: {ZOTERO_DB_PATH}")
        return

    conn, temp_dir, is_live = connect_zotero_db(ZOTERO_DB_PATH)

    if not is_live:
        info(f"Read-only snapshot.  PDF attachments will be deferred until Zotero is closed.")

    coll_name = None
    failed_list = []
    counters = {
        "total": 0, "has_pdf": 0, "duplicate": 0, "no_doi": 0,
        "downloaded": 0, "reused": 0, "attached": 0,
        "manual": 0, "failed": 0, "resumed": 0,
    }

    try:
        coll_id, coll_name = select_collection(conn)
        if not coll_id:
            warn("No collection selected. Exiting.")
            return

        unpaywall_email = get_unpaywall_email()

        # ── Load persistent state ──────────────────────────────────
        state = ProcessingState.load()

        # ── Batch-load metadata ────────────────────────────────────
        info("Loading collection metadata…")
        items, library_dois_with_pdf = batch_load_collection_metadata(conn, coll_id)
        counters["total"] = len(items)

        # Build title index for duplicate detection
        title_index = {}
        for it in items:
            t = (it.get("title") or "").strip().lower()
            if t and len(t) > 5:
                title_index.setdefault(t, []).append(it)

        print(f"\n{CY}  ╔{'═'*56}╗")
        print(f"  ║{'  PROCESSING COLLECTION':^56}║")
        print(f"  ╚{'═'*56}╝{RS}")
        info(f"{MG}{coll_name[:60]}{RS}")
        info(f"Found {WH}{len(items)}{RS} items total")
        if state.last_run:
            info(f"Resuming from previous run ({DM}{state.last_run[:19]}{RS})")
        sep()

        seen_dois = set()
        manual_queue = []

        # ══════════════════════════════════════════════════════════
        #  Phase 1 — Automatic processing
        # ══════════════════════════════════════════════════════════

        for item in items:
            item_id = item["item_id"]
            doi = item["doi"]          # already normalised
            title = item.get("title")

            # ── Resume: already completed in a prior run ──────────
            if state.is_completed(item_id):
                skip(f"Item {item_id}: completed in a previous run")
                counters["resumed"] += 1
                continue

            # ── Resume: PDF validated but not yet attached ─────────
            if state.is_pdf_validated(item_id):
                prev_path = state.get_downloaded_path(item_id)
                if prev_path and os.path.isfile(prev_path) and validate_pdf_file(prev_path):
                    info(f"Item {item_id}: attaching previously downloaded PDF…")
                    if _attach_and_verify(conn, item_id, prev_path, state, is_live):
                        ok(f"Item {item_id}: attached and verified!")
                        counters["attached"] += 1
                    else:
                        counters["reused"] += 1
                    continue

            # ── Skip: direct PDF already in Zotero ────────────────
            if item["has_direct_pdf"]:
                skip(f"Item {item_id}: PDF already in Zotero library")
                state.update_paper(item_id, doi=doi, title=title,
                                   status=PaperStatus.HAS_EXISTING_PDF)
                counters["has_pdf"] += 1
                continue

            # ── No DOI ─────────────────────────────────────────────
            if not doi:
                skip(f"Item {item_id}: no DOI found")
                state.update_paper(item_id, title=title,
                                   status=PaperStatus.NO_DOI)
                counters["no_doi"] += 1
                continue

            # ── Run-level duplicate DOI ────────────────────────────
            dk = doi_comparison_key(doi)
            if dk in seen_dois:
                skip(f"Item {item_id}: duplicate DOI in this run")
                state.update_paper(item_id, doi=doi, title=title,
                                   status=PaperStatus.DUPLICATE)
                counters["duplicate"] += 1
                continue
            seen_dois.add(dk)

            # ── Library-wide duplicate / cross-check ──────────────
            is_dup, strength, dup_msg = check_duplicate(
                item, library_dois_with_pdf, title_index
            )
            if is_dup:
                skip(f"Item {item_id}: {dup_msg}")
                state.update_paper(item_id, doi=doi, title=title,
                                   status=PaperStatus.DUPLICATE)
                counters["duplicate"] += 1
                continue
            if strength == "weak" and dup_msg:
                warn(f"Item {item_id}: {dup_msg}")

            # ── Check existing download on disk ───────────────────
            safe_fname = doi_to_safe_filename(doi)
            out_path = os.path.join(DOWNLOAD_DIR, f"{safe_fname}.pdf")
            if os.path.isfile(out_path) and validate_pdf_file(out_path):
                ok(f"Item {item_id}: valid PDF already in download folder")
                state.update_paper(item_id, doi=doi, title=title,
                                   downloaded_path=os.path.abspath(out_path),
                                   status=PaperStatus.PDF_VALIDATED)
                if _attach_and_verify(conn, item_id, out_path, state, is_live):
                    ok(f"Item {item_id}: attached and verified!")
                    counters["attached"] += 1
                counters["reused"] += 1
                continue

            # ── Print item header ─────────────────────────────────
            try:
                print(f"\n{CY}  ┌{'─'*56}┐{RS}")
                lbl_id = f" Item {item_id}"
                print(f"{CY}  │{RS} {BL}{lbl_id}{RS}{CY}{'':{' '}>{max(0, 55-len(lbl_id))}}{RS}{CY}│{RS}")
                if title:
                    lbl_t = title[:54]
                    print(f"{CY}  │{RS} {WH}{lbl_t}{RS}{CY}{'':{' '}>{max(0, 55-len(lbl_t))}}│{RS}")
                print(f"{CY}  │{RS} {DM}DOI:{RS} {MG}{doi}{RS}")
                print(f"{CY}  └{'─'*56}┘{RS}")

                # Copy title as safe filename to clipboard
                if title:
                    safe_title = re.sub(r'[\\/:*?"<>|]', '-', title).strip()
                    copy_to_clipboard(f"{safe_title}.pdf")
                    info("Title copied to clipboard (as filename)")

                # ── OA Resolution ─────────────────────────────────
                state.update_paper(item_id, doi=doi, title=title,
                                   status=PaperStatus.OA_SEARCHING)
                info("Resolving open-access sources…")
                oa_results = resolve_open_access_paper(doi, unpaywall_email)

                logger.debug("Item %d: %d OA candidate(s) found", item_id, len(oa_results))

                dl_success = False

                if oa_results:
                    # Try each OA location that claims to be a PDF
                    pdf_candidates = [r for r in oa_results if r.get("is_pdf")]
                    if pdf_candidates:
                        state.update_paper(item_id, status=PaperStatus.OA_FOUND)

                    for oa in pdf_candidates:
                        oa_url = oa["url"]
                        ok(f"OA PDF: {DM}{oa_url[:55]}{RS}")
                        info("Downloading…")

                        state.update_paper(item_id, status=PaperStatus.DOWNLOADING,
                                           oa_source=oa.get("source"),
                                           oa_url=oa_url)

                        success, reason = download_pdf_safe(oa_url, out_path)

                        if success:
                            ok(f"Saved to: {DM}{out_path}{RS}")
                            state.update_paper(item_id, status=PaperStatus.PDF_VALIDATED,
                                               downloaded_path=os.path.abspath(out_path))

                            if _attach_and_verify(conn, item_id, out_path, state, is_live):
                                ok(f"Attached to Zotero and verified!")
                                counters["attached"] += 1

                            counters["downloaded"] += 1
                            dl_success = True
                            break
                        else:
                            logger.debug("OA candidate failed (%s): %s", reason, oa_url)
                            warn(f"Download failed ({reason}) — trying next source…")

                if not dl_success:
                    # Determine accurate failure reason
                    if not oa_results:
                        reason_label = "NO_OA_COPY"
                    else:
                        # Check the last failure reason
                        reason_label = "DOWNLOAD_FAILED"

                    state.update_paper(item_id, doi=doi, title=title,
                                       status=PaperStatus.MANUAL_REQUIRED,
                                       failure_reason=reason_label)
                    manual_queue.append({
                        "item_id": item_id,
                        "doi":     doi,
                        "title":   title,
                        "reason":  reason_label,
                        "oa_found": len(oa_results) > 0,
                    })
                    counters["manual"] += 1
                    warn(f"Added to manual queue ({reason_label})")

            except Exception as exc:
                # Per-paper error: record and continue
                err(f"Item {item_id}: unexpected error — {exc}")
                logger.exception("Error processing item %d", item_id)
                state.update_paper(item_id, doi=doi, title=title,
                                   status=PaperStatus.DOWNLOAD_FAILED,
                                   failure_reason=f"ERROR: {exc}")
                counters["failed"] += 1

        sep()

        # ══════════════════════════════════════════════════════════
        #  Phase 2 — Manual queue
        # ══════════════════════════════════════════════════════════

        manual_completed = process_manual_queue(manual_queue, conn, is_live, state)
        if manual_completed:
            counters["attached"] += manual_completed
            counters["manual"] -= manual_completed

        # ── Build CSV failure list from state ─────────────────────
        for paper in manual_queue:
            p = state.get_paper(paper["item_id"])
            if p and p.get("status") not in (
                PaperStatus.COMPLETED.value, PaperStatus.PDF_VALIDATED.value
            ):
                failed_list.append({
                    "item_id":       paper["item_id"],
                    "title":         paper.get("title", ""),
                    "doi":           paper.get("doi", ""),
                    "status":        p.get("status", "MANUAL"),
                    "reason":        p.get("failure_reason", paper.get("reason", "")),
                    "oa_found":      "Yes" if paper.get("oa_found") else "No",
                    "oa_url":        p.get("oa_url", ""),
                    "source":        p.get("oa_source", ""),
                    "attempt_count": p.get("attempt_count", 1),
                })

    finally:
        # ── Save state before cleanup ──────────────────────────────
        try:
            state.save()
            logger.debug("Processing state saved to %s", STATE_FILE)
        except Exception:
            pass

        conn.close()
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ── Summary ────────────────────────────────────────────────────
    print_summary(counters)

    if failed_list and coll_name:
        save_failed_csv(failed_list, coll_name)
    elif counters["manual"] == 0 and counters["failed"] == 0:
        print(f"\n{GR}  ╔{'═'*56}╗")
        print(f"  ║{'  ✔  ALL DONE — NO FAILURES':^56}║")
        print(f"  ╚{'═'*56}╝{RS}\n")

    if not is_live and (counters["downloaded"] > 0 or counters["reused"] > 0):
        unattached = counters["downloaded"] + counters["reused"] - counters["attached"]
        if unattached > 0:
            warn(
                f"{unattached} PDF(s) downloaded but not attached to Zotero.\n"
                f"       Close Zotero and re-run to attach them automatically."
            )


if __name__ == "__main__":
    main()
