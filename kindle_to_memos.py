#!/usr/bin/env python3
"""Upload Kindle highlights from "My Clippings.txt" to a Memos instance.

Workflow
--------
1. Split the clippings file into individual clippings. Bookmarks are skipped.
2. Fetch the memos that already carry the clippings tag and collect their keys.
3. Drop duplicates, both against Memos and within the clippings file.
4. Write a preview file (PREVIEW_PATH) that contains exactly what will be uploaded.
5. Wait until you type ``confirmed`` in the terminal.
6. Create one memo per remaining clipping.

Configuration lives in a ``.env`` file next to this script (see ``.env.example``).

Usage
-----
    python kindle_to_memos.py                          # uses CLIPPINGS_PATH from .env
    python kindle_to_memos.py "/path/to/My Clippings.txt"
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

CLIPPING_TAG_RAW = os.getenv("CLIPPING_TAG", "clippings").strip()
MEMOS_API_URL = os.getenv("MEMOS_API_URL", "").strip().rstrip("/")
MEMOS_TOKEN = os.getenv("MEMOS_TOKEN", "").strip()
MEMO_VISIBILITY = os.getenv("MEMO_VISIBILITY", "PRIVATE").strip().upper()
CLIPPINGS_PATH = os.getenv("CLIPPINGS_PATH", "Kindle Clippings.txt").strip()
PREVIEW_PATH = os.getenv("PREVIEW_PATH", "upload_preview.md").strip()

REQUEST_TIMEOUT = 30  # seconds
UPLOAD_PAUSE = 0.2  # seconds between POSTs, to be gentle on the server

# Kindle separates clippings with a line of equals signs.
SEPARATOR_RE = re.compile(r"^=+\s*$", re.MULTILINE)
KIND_RE = re.compile(r"Your\s+(Highlight|Note|Bookmark)\b", re.IGNORECASE)
LOCATION_RE = re.compile(r"location\s+(\d+(?:-\d+)?)", re.IGNORECASE)
PAGE_RE = re.compile(r"page\s+(\d+)", re.IGNORECASE)
# Old Kindle format: the author sits in parentheses at the end of the header line.
TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
# Hidden marker stored in every memo so we can recognise it on the next run.
KEY_MARKER_RE = re.compile(r"<!--\s*kindle-key:([0-9a-f]+)\s*-->")
# A literal "#word" in the highlight would become a Memos tag; escape it.
HASHTAG_IN_TEXT_RE = re.compile(r"#(?=\w)")


@dataclass(frozen=True)
class Clipping:
    """One highlight or note taken from the Kindle clippings file."""

    title: str
    author: str
    kind: str  # "Highlight" or "Note"
    location: str
    page: str | None
    text: str

    @property
    def key(self) -> str:
        """Stable identifier used for de-duplication (title, author, location, text)."""
        parts = [self.title, self.author, self.location, self.text]
        normalized = "\n".join(" ".join(part.lower().split()) for part in parts)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @property
    def tags(self) -> list[str]:
        """Tags for the memo: the general clippings tag, the book title and the author."""
        candidates = [CLIPPING_TAG_RAW, self.title, self.author]
        tags: list[str] = []
        for candidate in candidates:
            tag = to_tag(candidate)
            if tag and tag not in tags:
                tags.append(tag)
        return tags


def to_tag(text: str) -> str:
    """Turn free text into a valid Memos tag.

    Memos hashtags cannot contain spaces or most punctuation, so spaces become
    hyphens and everything except letters, digits, ``_``, ``-`` and ``/`` is dropped.
    The readable title and author stay in the memo body.
    """
    tag = re.sub(r"\s+", "-", text.strip())
    tag = re.sub(r"[^\w\-/]", "", tag)
    tag = re.sub(r"-{2,}", "-", tag)
    return tag.strip("-/")


def split_title_author(header: str) -> tuple[str, str]:
    """Split a Kindle header line into (title, author).

    Two formats occur in the wild:

    * new: ``Title - Author (Author)``  -> split on the last `` - ``
    * old: ``Title (Author)``           -> author is the final parenthesised group

    Limitation: a title that itself contains `` - `` with an author in parentheses
    (e.g. ``Book - Subtitle (Author)``) will be split at the subtitle.
    """
    header = header.strip()
    if " - " in header:
        title, _, author = header.rpartition(" - ")
        return title.strip(), author.strip()
    match = TRAILING_PAREN_RE.search(header)
    if match:
        return header[: match.start()].strip(), match.group(1).strip()
    return header, ""


def parse_clippings(raw: str) -> list[Clipping]:
    """Parse the full text of a Kindle clippings file. Bookmarks and empty clippings are dropped."""
    clippings: list[Clipping] = []
    raw = raw.lstrip("﻿")  # byte-order mark, if the file was not read as utf-8-sig
    for block in SEPARATOR_RE.split(raw):
        lines = [line.rstrip() for line in block.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        if len(lines) < 2:
            continue

        header, meta = lines[0], lines[1]
        kind_match = KIND_RE.search(meta)
        if not kind_match:
            continue  # not a clipping block
        kind = kind_match.group(1).capitalize()
        if kind == "Bookmark":
            continue

        text = "\n".join(lines[2:]).strip()
        if not text:
            continue

        location_match = LOCATION_RE.search(meta)
        page_match = PAGE_RE.search(meta)
        title, author = split_title_author(header)
        clippings.append(
            Clipping(
                title=title,
                author=author,
                kind=kind,
                location=location_match.group(1) if location_match else "?",
                page=page_match.group(1) if page_match else None,
                text=text,
            )
        )
    return clippings


def format_memo(clipping: Clipping) -> str:
    """Build the exact memo content that is previewed and uploaded."""
    body = HASHTAG_IN_TEXT_RE.sub(r"\\#", clipping.text)

    meta_parts = [f"*{clipping.title}*"]
    if clipping.author:
        meta_parts.append(clipping.author)
    if clipping.page:
        meta_parts.append(f"page {clipping.page}")
    meta_parts.append(f"location {clipping.location}")
    meta = " · ".join(meta_parts)

    tags_line = " ".join(f"#{tag}" for tag in clipping.tags)
    return "\n".join(
        [
            body,
            "",
            meta,
            "",
            tags_line,
            f"<!-- kindle-key:{clipping.key} -->",
        ]
    )


def resolve_path(value: str) -> Path:
    """Relative paths from .env are relative to this script, not to the current directory."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else SCRIPT_DIR / path


def memos_session() -> requests.Session:
    """Create an authenticated HTTP session for the Memos API."""
    if not MEMOS_API_URL or not MEMOS_TOKEN:
        sys.exit("MEMOS_API_URL and MEMOS_TOKEN must be set in .env")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {MEMOS_TOKEN}"
    return session


def fetch_existing_keys(session: requests.Session) -> set[str]:
    """Return the dedupe keys of all memos that already carry the clippings tag."""
    keys: set[str] = set()
    params: dict[str, str | int] = {
        "filter": f'tag in ["{to_tag(CLIPPING_TAG_RAW)}"]',
        "pageSize": 100,
    }
    url = f"{MEMOS_API_URL}/memos"

    while True:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        for memo in data.get("memos", []):
            match = KEY_MARKER_RE.search(memo.get("content", ""))
            if match:
                keys.add(match.group(1))
        next_token = data.get("nextPageToken")
        if not next_token:
            break
        params["pageToken"] = next_token
    return keys


def deduplicate(clippings: list[Clipping], existing_keys: set[str]) -> list[Clipping]:
    """Remove clippings already in Memos and repeats within the file, keeping first occurrences."""
    seen = set(existing_keys)
    unique: list[Clipping] = []
    for clipping in clippings:
        if clipping.key in seen:
            continue
        seen.add(clipping.key)
        unique.append(clipping)
    return unique


def write_preview(clippings: list[Clipping], path: Path) -> None:
    """Write the memos that will be uploaded so they can be checked by hand."""
    header = (
        f"# Upload preview: {len(clippings)} new clippings\n\n"
        "Everything below is uploaded exactly as shown. "
        "Type `confirmed` in the terminal to start the upload.\n"
    )
    sections = [format_memo(clipping) for clipping in clippings]
    path.write_text(header + "\n\n---\n\n" + "\n\n---\n\n".join(sections) + "\n", encoding="utf-8")


def upload(session: requests.Session, clippings: list[Clipping]) -> list[str]:
    """Create one memo per clipping. Returns a list of failure messages."""
    url = f"{MEMOS_API_URL}/memos"
    failures: list[str] = []
    for index, clipping in enumerate(clippings, start=1):
        payload = {"content": format_memo(clipping), "visibility": MEMO_VISIBILITY}
        try:
            response = session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            failures.append(f"{clipping.title}: {exc}")
            print(f"  [{index}/{len(clippings)}] FAILED: {clipping.title}")
        else:
            print(f"  [{index}/{len(clippings)}] uploaded: {clipping.title}")
        time.sleep(UPLOAD_PAUSE)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload Kindle clippings to Memos.")
    parser.add_argument(
        "clippings",
        nargs="?",
        help="path to 'My Clippings.txt' (defaults to CLIPPINGS_PATH from .env)",
    )
    args = parser.parse_args()

    clippings_path = Path(args.clippings).expanduser() if args.clippings else resolve_path(CLIPPINGS_PATH)
    if not clippings_path.is_file():
        print(f"Clippings file not found: {clippings_path}", file=sys.stderr)
        return 1

    raw = clippings_path.read_text(encoding="utf-8-sig")
    clippings = parse_clippings(raw)
    print(f"Parsed {len(clippings)} highlights and notes (bookmarks skipped).")

    session = memos_session()
    try:
        print(f"Fetching existing memos tagged #{to_tag(CLIPPING_TAG_RAW)} ...")
        existing_keys = fetch_existing_keys(session)
    except requests.RequestException as exc:
        print(f"Could not read from Memos: {exc}", file=sys.stderr)
        return 1

    new_clippings = deduplicate(clippings, existing_keys)
    print(
        f"{len(existing_keys)} clippings already in Memos, "
        f"{len(clippings) - len(new_clippings)} duplicates skipped, "
        f"{len(new_clippings)} new."
    )
    if not new_clippings:
        print("Nothing new to upload.")
        return 0

    preview_path = resolve_path(PREVIEW_PATH)
    write_preview(new_clippings, preview_path)
    print(f"Preview written to: {preview_path}")
    print(f"Check it, then type 'confirmed' to upload {len(new_clippings)} memos.")

    answer = input("> ").strip().lower()
    if answer != "confirmed":
        print("Not confirmed. Nothing was uploaded.")
        return 1

    failures = upload(session, new_clippings)
    print(f"Done: {len(new_clippings) - len(failures)} uploaded, {len(failures)} failed.")
    for failure in failures:
        print(f"  - {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
