# ⚡ Zotero PDF Automation CLI (`Automate.py`) — v3.0

<p align="center">
  <img src="image.png" alt="FAHAD Zotero Automation CLI Banner and Collection Selection" width="850">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Zotero-SQLite%20%7C%20WAL%20Aware-red?logo=zotero&logoColor=white" alt="Zotero">
  <img src="https://img.shields.io/badge/API-Unpaywall%20v2-green" alt="Unpaywall API">
  <img src="https://img.shields.io/badge/Browser-Brave-orange?logo=brave&logoColor=white" alt="Brave Browser">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Portable-informational?logo=windows&logoColor=white" alt="Platform">
  <img src="https://img.shields.io/badge/Version-3.0-blueviolet" alt="Version 3.0">
</p>

---

## 📖 Overview

**Zotero PDF Automation CLI** is a high-performance terminal utility engineered for researchers, scientists, and academics to automate the tedious process of locating, retrieving, validating, and organizing research paper full-text PDFs across large Zotero collections.

Whether papers are locked behind publisher paywalls or freely available as open-access preprints, this tool:

1. **Audits your local Zotero library** in real time (even while Zotero is actively running).
2. **Filters out existing attachments** using a comprehensive 3-tier duplicate detection algorithm (DOI → title+author/year → title-only).
3. **Normalizes DOIs** to ensure consistent, deduplicated, and valid identifiers.
4. **Fetches legal Open-Access PDFs** from all Unpaywall OA locations — not just the first — with automatic fallback.
5. **Downloads safely** using atomic `.part` files and validates every PDF (magic-byte check, HTML rejection).
6. **Attaches PDFs directly to Zotero** as linked-file attachments and verifies each attachment.
7. **Retries transient failures** (429, 5xx, timeouts) with exponential backoff — no more lost downloads.
8. **Queues paywalled/captcha-protected papers** for batch manual handling at the end, instead of blocking one-by-one.
9. **Detects manually downloaded PDFs** automatically after browser-based retrieval.
10. **Persists processing state** to `processing_state.json` for safe resume across crashes and re-runs.
11. **Logs unretrieved articles** to an enhanced CSV report with ItemID, Status, FailureReason, OA source, timestamps, and more.

---

## 📸 Visual Walkthrough

### 1. Startup & Interactive Collection Menu

Upon launching, the CLI initializes with a branded **FAHAD Design & Development** ASCII pixel banner and queries your local Zotero SQLite database to display all available collections along with live item counts:

<p align="center">
  <img src="image.png" alt="Zotero Collection Selection" width="800">
</p>

- **Dynamic Discovery**: Scans `collections` excluding soft-deleted folders in `deletedCollections`.
- **Numbered Navigation**: Select any collection instantly by entering its number (or `q` to quit).
- **Batch Metadata Loading**: All item metadata (DOI, title, date, author, PDF status) is loaded in bulk with minimal database round-trips.

---

### 2. Unpaywall Authentication & Collection Scan

Once a collection is chosen, the CLI configures your Unpaywall API email and prepares the items for automated processing:

<p align="center">
  <img src="image1.png" alt="Unpaywall Email Prompt and Collection Processing" width="800">
</p>

- **Default Email Support**: Remembers your preferred Unpaywall email; press <kbd>Enter</kbd> to accept or type an override.
- **Collection Counter**: Scans and displays the total number of references contained within the selected folder.
- **Resume Detection**: Automatically detects prior runs and resumes from where you left off.

---

### 3. Automated OA Resolution & Safe Download

For every paper lacking an attachment, the CLI resolves open-access sources, downloads safely, validates the PDF, and attaches it to Zotero:

<p align="center">
  <img src="image2.png" alt="Item Processing and Brave Browser Redirection" width="800">
</p>

- **Card Layout**: Visualizes the Item ID, full title, and normalized DOI.
- **Multi-Location OA Resolution**: Tries every Unpaywall OA location in priority order — not just `best_oa_location`.
- **Atomic Downloads**: PDFs are streamed to `.part` files, validated for `%PDF-` magic bytes, then atomically renamed.
- **Auto-Attach to Zotero**: Successfully downloaded PDFs are linked to the correct Zotero item as linked-file attachments and verified.
- **Clipboard Sync**: Copies a filesystem-safe version of the title (with `.pdf` extension) to your clipboard for quick manual saves.

---

### 4. Manual Queue & Smart Detection

When automatic retrieval fails (CAPTCHA, paywall, institutional access, no OA copy), papers are collected into a manual queue presented at the end — no more one-at-a-time interruptions:

<p align="center">
  <img src="image3.png" alt="Manual Queue and PDF Detection" width="800">
</p>

- **Batch-First Processing**: All automatic downloads complete before any manual interaction is needed.
- **Accurate Failure Classification**: Each paper is categorized as `NO_OA_COPY`, `PAYWALL`, `CAPTCHA`, `INSTITUTIONAL_ACCESS`, or `DOWNLOAD_FAILED` — not generically labeled.
- **Auto-Detect Downloads**: After you download a PDF in the browser, the tool scans your Downloads folder for new PDFs and validates them automatically.
- **Manual Path Fallback**: If automatic detection fails, you can paste the full path to the downloaded file.
- **Verification Loop**: Every manually obtained PDF is validated and attached to Zotero before marking complete.

---

## 🚀 Key Features

| Feature | Description |
| :--- | :--- |
| **🛡️ Safe Database Access** | Uses the SQLite **backup API** for consistent snapshots when Zotero is open. `PASSIVE` checkpointing avoids blocking Zotero. Write operations (attachments) only occur on the live database when Zotero is closed. |
| **🔍 3-Tier Duplicate Detection** | **Strong**: DOI match with existing PDF. **Reasonable**: normalized title + author/year match. **Weak**: title-only match (warns but processes). Prevents false skips from same-title, different-DOI papers. |
| **📐 DOI Normalization** | Strips `https://doi.org/`, `http://dx.doi.org/`, `doi:` prefixes. Validates format (`10.\d{4,}/…`). Rejects malformed DOIs before wasting network requests. |
| **📥 Atomic PDF Downloads** | Streams to `.part` file → validates `%PDF-` magic bytes → rejects HTML error pages → `os.replace()` atomic rename. Partial downloads are never mistaken for complete PDFs. |
| **✅ PDF Validation** | Checks for `%PDF-` header, rejects HTML login pages and error pages saved as `.pdf`. Applied to downloads, existing files, and manual acquisitions. |
| **🔄 Retry with Backoff** | Transient errors (429, 500–504, connection resets, timeouts) are retried up to 3 times with exponential backoff (2s → 4s → 8s). Non-retryable errors (403, 404) fail immediately. |
| **🌐 Multi-Location OA Resolution** | Queries all Unpaywall `oa_locations` (not just `best_oa_location`), tries each PDF URL in confidence order, validates each download, and continues to the next on failure. Extensible resolver architecture for future sources. |
| **📎 Zotero Auto-Attachment** | Downloads are linked to the correct Zotero item as **linked-file attachments** (linkMode=2). Safe, transactional, with rollback on error. Duplicate attachment prevention built in. |
| **✔️ Attachment Verification** | After attaching, verifies: (1) attachment row exists in DB, (2) file exists on disk, (3) file is a valid PDF. Only marks `COMPLETED` after all checks pass. |
| **💾 Persistent State & Resume** | `processing_state.json` tracks per-paper status, DOI, download path, attempt count, failure reason. Re-runs skip completed papers, resume pending ones, and attach validated PDFs. |
| **📋 Manual Queue** | Papers requiring human intervention are collected and presented as a numbered queue at the end. Process one-by-one, skip, or quit — no mid-batch interruptions. |
| **🔎 Manual PDF Detection** | Snapshots download directories before opening the browser. After you return, scans for new validated PDFs. Supports multiple detection and manual path entry as fallback. |
| **📊 Enhanced CSV Reporting** | Reports include: ItemID, Title, DOI, Status, FailureReason, OAFound, OAURL, Source, AttemptCount, Timestamp. Accurate failure categories replace generic labeling. |
| **🦁 Brave Browser Auto-Detection** | Automatically scans standard 64-bit, 32-bit, and user-local `AppData` paths for `brave.exe`. Falls back to the default system browser. |
| **📋 Smart Clipboard** | Copies a filesystem-safe version of the title with `.pdf` extension — ready to use as a save-as filename. Uses `pyperclip` with fallback to native `clip.exe`. |
| **📈 End-of-Run Summary** | Detailed statistics table: total papers, already had PDF, duplicates, downloaded, attached, manual required, failed, resumed. Numbers come from actual processing results. |
| **🐛 Debug Logging** | `--debug` flag enables structured per-paper logging (DOI, resolver, URL, attempt, validation, attachment, status). Normal mode stays clean. |
| **🛡️ Per-Paper Error Isolation** | One paper failing never crashes the batch. Errors are recorded and processing continues to the next paper. Only fatal configuration errors (missing DB, missing deps) halt execution. |
| **💻 Zero Hardcoding & Portability** | Resolves user home paths via `os.path.expanduser("~")`, allowing the script to run seamlessly on any machine without configuration edits. |

---

## 📦 Requirements & Installation

### 1. Prerequisites

- **Python 3.10+**
- **Zotero** (installed in standard location: `%USERPROFILE%\Zotero`)
- **Brave Browser** (or default system browser)

### 2. Dependencies

Install the required lightweight Python libraries:

```powershell
pip install requests pyperclip colorama
```

---

## 💻 Usage Guide

1. Open your terminal (PowerShell, Command Prompt, or Windows Terminal).
2. Navigate to the project root and launch the script:
   ```powershell
   python Automate.py
   ```
   For verbose debug output:
   ```powershell
   python Automate.py --debug
   ```
3. **Select your Collection**: Input the index number corresponding to your target collection.
4. **Confirm Unpaywall Email**: Press <kbd>Enter</kbd> to accept your default email or provide a new one.
5. **Sit Back & Download**:
   - Open-access papers are downloaded, validated, and attached to Zotero automatically.
   - Processing continues without interruption — manual papers are queued for later.
6. **Handle Manual Queue**: After automatic processing, review and handle papers that need manual attention (CAPTCHA, paywall, institutional login).
7. **Review Reports**: Check downloaded PDFs in `Downloads/zotero_pdfs`, failed items in `Downloads/zoteroCSV`, and state in `processing_state.json`.
8. **Resume Anytime**: Stop the program at any point. Re-run it to pick up exactly where you left off — completed papers are skipped, pending papers are resumed.

---

## 📂 Output File Structure

```text
C:\Users\<YourUsername>\
├── Downloads\
│   ├── zotero_pdfs\                          ← Direct OA PDF downloads
│   │   ├── 10.1038-s41467-023-38192-3.pdf
│   │   ├── 10.1021-acs.jcim.4c02403.pdf
│   │   └── processing_state.json             ← Persistent per-paper state
│   └── zoteroCSV\                            ← Enhanced failure reports
│       └── My Collection.csv
└── Zotero\
    ├── zotero.sqlite                         ← Live Zotero database
    ├── zotero.sqlite-wal                     ← Live Write-Ahead Log
    └── zotero.sqlite-shm                     ← Shared memory index
```

---

## 🔄 Processing Pipeline

```text
                    ZOTERO DATABASE
                         │
                         ▼
                Collection Selection
                         │
                         ▼
              Batch Metadata Loading
                         │
                         ▼
               DOI Normalization
                         │
                         ▼
              Existing PDF Check
                  /            \
                YES             NO
                 │               │
                 ▼               ▼
               SKIP        OA Resolution
                            (all locations)
                                │
                     ┌──────────┴──────────┐
                     │                     │
                  PDF FOUND            NO PDF
                     │                     │
                     ▼                     ▼
             Safe Download (.part)    Manual Queue
                     │                     │
                     ▼                     ▼
              PDF Validation          Browser / DOI
                     │                     │
                     ▼                     ▼
             Attach to Zotero       Auto-detect PDF
                     │                     │
                     ▼                     ▼
             Verify Attachment      Validate & Attach
                     │                     │
                     ▼                     ▼
                 COMPLETED             COMPLETED
```

---

## 🛠️ Technical Deep Dive: SQLite WAL Concurrency

Zotero utilizes SQLite in **WAL (Write-Ahead Logging)** mode. While Zotero is open:

- Updates and newly added attachments reside in `zotero.sqlite-wal` and are not immediately checkpointed to the main `zotero.sqlite` database file.
- Standard read connections may experience stale reads or throw `sqlite3.OperationalError: database is locked`.

**How `Automate.py` v3.0 Solves This:**

1. **Attempts direct connection** with a 2-second timeout and uses `PRAGMA wal_checkpoint(PASSIVE)` (non-blocking) to flush recent transactions.
2. **If Zotero holds the lock**, creates a consistent snapshot using the **SQLite backup API** (`sqlite3.Connection.backup()`), which guarantees atomicity — no more manual triple-file copies that could be inconsistent.
3. **Falls back to file copy** of the triple-file set (`.sqlite`, `.sqlite-wal`, `.sqlite-shm`) only if the backup API fails.
4. **Tracks live vs. snapshot mode**: PDF attachments (database writes) are only performed when connected directly to the live database. On a snapshot, PDFs are downloaded and validated but attachment is deferred until Zotero is closed and the tool is re-run.

---

## 📊 Paper Processing States

The tool tracks each paper through a clear state machine:

| State | Meaning |
| :--- | :--- |
| `DISCOVERED` | Item found in collection |
| `NO_DOI` | No DOI available — skipped |
| `HAS_EXISTING_PDF` | PDF already attached in Zotero |
| `DUPLICATE` | DOI or title+author duplicate detected |
| `OA_SEARCHING` | Querying Unpaywall for OA locations |
| `OA_FOUND` | At least one OA PDF URL found |
| `DOWNLOADING` | PDF download in progress |
| `PDF_VALIDATED` | Downloaded file confirmed as valid PDF |
| `ZOTERO_ATTACHING` | Creating linked-file attachment in Zotero |
| `COMPLETED` | PDF attached and verified ✓ |
| `MANUAL_REQUIRED` | Needs human intervention |
| `DOWNLOAD_FAILED` | All download attempts failed |
| `INVALID_PDF` | Downloaded file was not a valid PDF |
| `PAYWALL` | Publisher returned 403 / paywall |
| `CAPTCHA` | CAPTCHA challenge detected |
| `INSTITUTIONAL_ACCESS` | Institutional login required |
| `NO_OA_COPY` | No open-access version exists |
| `PUBLISHER_ERROR` | Publisher server error |

---

## 👨‍💻 Author & Credits

- **Developer**: [@FahadhCodes](https://github.com/fahadhcodes)
