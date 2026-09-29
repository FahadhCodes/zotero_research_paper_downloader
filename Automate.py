#!/usr/bin/env python3
"""
Automate.py  ·  Zotero PDF Fetcher
Finds Zotero references without PDF attachments, retrieves open-access
PDFs via Unpaywall, and opens remaining DOIs in Brave for manual download.

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
from urllib.parse import quote

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


# ── Visible Length Helper for Box Alignment ───────────────────────
def _vlen(s):
    """Calculate visible string length excluding ANSI escape sequences."""
    return len(re.sub(r'\033\[[0-9;]*m', '', s))


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

    sub1 = f"  {GR}● ACTIVE{RS}  {WH}Zotero PDF Automation CLI{RS}  {DM}v2.2{RS}"
    sub1_r = f"{CY}DOWNLOAD RESEACH PAPERS FASTER{RS}  "
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
# ──────────────────────────────────────────────────────────────────

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ── Database helpers ───────────────────────────────────────────────

def connect_zotero_db(db_path):
    """
    Connect to Zotero SQLite. If Zotero holds the lock, snapshot the
    DB + WAL files to a temp dir. Always runs a WAL checkpoint.
    """
    def _open_and_checkpoint(path):
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        return conn

    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("SELECT 1 FROM collections LIMIT 1")
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        return conn, None
    except sqlite3.OperationalError:
        warn("Zotero is running — working on a safe snapshot of the database.")
        temp_dir = tempfile.mkdtemp(prefix="zotero_db_")
        temp_db = os.path.join(temp_dir, "zotero.sqlite")
        for ext in ["", "-wal", "-shm"]:
            src, dst = db_path + ext, temp_db + ext
            if os.path.exists(src):
                try:
                    shutil.copyfile(src, dst)
                except Exception:
                    pass
        return _open_and_checkpoint(temp_db), temp_dir


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


# ── Network helpers ────────────────────────────────────────────────

def query_unpaywall(doi, email):
    url = f"https://api.unpaywall.org/v2/{quote(doi)}?email={quote(email)}"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        return None
    return r.json()


def download_pdf(url, filename):
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code == 200 and 'application/pdf' in r.headers.get('Content-Type', ''):
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(1024 * 64):
                    f.write(chunk)
            return True
    except Exception as e:
        err(f"Download error: {e}")
    return False


# ── Browser ────────────────────────────────────────────────────────

def open_in_brave(url):
    if os.path.isfile(BRAVE_PATH):
        webbrowser.register('brave', None, webbrowser.BackgroundBrowser(BRAVE_PATH))
        webbrowser.get('brave').open(url)
    else:
        webbrowser.open(url)


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


# ── CSV export ─────────────────────────────────────────────────────

def save_failed_csv(failed_list, coll_name):
    """
    Save papers the user couldn't download to a CSV file.
    Location: ~/Downloads/zoteroCSV/<CollectionName>.csv
    """
    csv_dir = os.path.join(os.path.expanduser("~"), "Downloads", "zoteroCSV")
    os.makedirs(csv_dir, exist_ok=True)

    safe_name = re.sub(r'[\\/*?:"<>|]', '_', coll_name)[:100].strip()
    csv_path = os.path.join(csv_dir, f"{safe_name}.csv")

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["Title", "DOI", "DOI_URL"])
        writer.writeheader()
        for entry in failed_list:
            writer.writerow({
                "Title":   entry.get("title", ""),
                "DOI":     entry.get("doi", ""),
                "DOI_URL": f"https://doi.org/{entry['doi']}" if entry.get("doi") else "",
            })

    print(f"\n{CY}  ╔{'═'*56}╗")
    print(f"  ║{YL}{'  ⚠  FAILED DOWNLOADS REPORT':^56}{CY}║")
    print(f"  ╠{'═'*56}╣")
    print(f"  ║  {RD}{len(failed_list)} paper(s){RS} could not be downloaded{CY}{'':>20}║")
    print(f"  ║  {DM}Saved to:{RS}{CY}{'':>46}║")
    print(f"  ║  {WH}{csv_path[:54]}{CY}{'':>{max(0, 54-len(csv_path[:54]))}}║")
    print(f"  ╚{'═'*56}╝{RS}\n")
    return csv_path


# ── Main ───────────────────────────────────────────────────────────

def main():
    print_banner()

    if not os.path.isfile(ZOTERO_DB_PATH):
        err(f"Zotero DB not found at: {ZOTERO_DB_PATH}")
        return

    conn, temp_dir = connect_zotero_db(ZOTERO_DB_PATH)
    failed_list = []
    coll_name = None

    try:
        coll_id, coll_name = select_collection(conn)
        if not coll_id:
            warn("No collection selected. Exiting.")
            return

        unpaywall_email = get_unpaywall_email()

        item_ids = get_item_ids_in_collection(conn, coll_id)

        print(f"\n{CY}  ╔{'═'*56}╗")
        print(f"  ║{'  PROCESSING COLLECTION':^56}║")
        print(f"  ╚{'═'*56}╝{RS}")
        info(f"{MG}{coll_name[:60]}{RS}")
        info(f"Found {WH}{len(item_ids)}{RS} items total")
        sep()

        seen_dois = set()

        for item_id in item_ids:
            doi = get_doi_for_item(conn, item_id)
            title = get_title_for_item(conn, item_id)

            # ── Skip: PDF already exists in Zotero ────────────────
            if item_has_pdf_attachment(conn, item_id, doi=doi, title=title):
                skip(f"Item {item_id}: PDF already in Zotero library")
                continue

            if not doi:
                skip(f"Item {item_id}: no DOI found")
                continue
            doi = doi.strip()

            # ── Skip: duplicate DOI in this run ───────────────────
            if doi.lower() in seen_dois:
                skip(f"Item {item_id}: duplicate DOI in this run")
                continue
            seen_dois.add(doi.lower())

            # ── Skip: already in Downloads folder ─────────────────
            safe_name = doi.replace('/', '_').replace(':', '_')
            out_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.pdf")
            if os.path.isfile(out_path):
                skip(f"Item {item_id}: already downloaded previously")
                continue

            # ── Process this item ──────────────────────────────────
            print(f"\n{CY}  ┌{'─'*56}┐{RS}")
            print(f"{CY}  │{RS} {BL}Item {item_id}{RS}{CY}{'':>{max(0, 49-len(str(item_id)))}}{RS}{CY}│{RS}")
            if title:
                label = title[:54]
                print(f"{CY}  │{RS} {WH}{label}{RS}{CY}{'':>{max(0, 55-len(label))}}│{RS}")
            print(f"{CY}  │{RS} {DM}DOI:{RS} {MG}{doi}{RS}")
            print(f"{CY}  └{'─'*56}┘{RS}")

            # Copy title to clipboard before opening browser
            if title:
                copy_to_clipboard(title)
                info(f"Title copied to clipboard")

            # ── Query Unpaywall ────────────────────────────────────
            info("Querying Unpaywall…")
            data = query_unpaywall(doi, unpaywall_email)

            if data and data.get('best_oa_location') and data['best_oa_location'].get('url_for_pdf'):
                pdf_url = data['best_oa_location']['url_for_pdf']
                ok(f"Open-access PDF found: {DM}{pdf_url[:55]}{RS}")
                info("Downloading…")
                dl_ok = download_pdf(pdf_url, out_path)
                if dl_ok:
                    ok(f"Saved to: {DM}{out_path}{RS}")
                else:
                    warn("Auto-download failed — opening in Brave for manual download.")
                    open_in_brave(f"https://doi.org/{doi}")
                    downloaded = wait_for_captcha()
                    if not downloaded:
                        failed_list.append({"title": title or "", "doi": doi})
            else:
                warn("No open-access PDF on Unpaywall — opening DOI page in Brave.")
                open_in_brave(f"https://doi.org/{doi}")
                downloaded = wait_for_captcha()
                if not downloaded:
                    failed_list.append({"title": title or "", "doi": doi})

        sep()

    finally:
        conn.close()
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ── Summary ────────────────────────────────────────────────────
    if failed_list and coll_name:
        save_failed_csv(failed_list, coll_name)
    else:
        print(f"\n{GR}  ╔{'═'*56}╗")
        print(f"  ║{'  ✔  ALL DONE — NO FAILURES':^56}║")
        print(f"  ╚{'═'*56}╝{RS}\n")


if __name__ == "__main__":
    main()
