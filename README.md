# Kindle Clippings to Memos

Takes your Kindle `My Clippings.txt` file and uploads each highlight to your [Memos](https://usememos.com) account as its own memo.

Every memo gets three tags:

- `#clippings` (general tag, configurable)
- the book title
- the author

Titles and authors have spaces and punctuation replaced with hyphens, because Memos tags can't contain spaces. For example, `Political Philosophy of AI, The` becomes `#Political-Philosophy-of-AI-The`. The readable title and author are kept in the memo body.

## What it does

1. Splits the clippings file into individual highlights and notes. Bookmarks are skipped.
2. Fetches your existing memos tagged `clippings` and skips anything already uploaded.
3. Writes `upload_preview.md` with exactly what will be uploaded.
4. Waits for you to type `confirmed` in the terminal.
5. Creates one memo per remaining clipping.

## Requirements

- Python 3.10 or newer
- A Memos instance with an access token (Settings → Access Tokens in the Memos web app)
- Your `My Clippings.txt` file from the Kindle (connect the Kindle over USB, it's in the `documents` folder)

## Setup

Clone or download the project, then create your `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Description |
| --- | --- |
| `MEMOS_API_URL` | Base URL of the API, e.g. `https://memos.example.com/api/v1` (Memos 0.30/0.31) or `.../api` (Memos 26.10+) |
| `MEMOS_TOKEN` | Your personal access token, starts with `memos_pat_` |
| `CLIPPINGS_PATH` | Optional. Path to your clippings file, so you can run the script without arguments |
| `CLIPPING_TAG` | Optional. Defaults to `clippings` |
| `MEMO_VISIBILITY` | Optional. `PRIVATE` (default), `PROTECTED` or `PUBLIC` |

Never commit `.env`. It contains your token.

### Option A: pip and a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Option B: uv

[uv](https://docs.astral.sh/uv/) manages the Python version and the virtual environment for you:

```bash
uv venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

You can also skip the install step and let `uv` run the script in a temporary environment:

```bash
uv run --with requests --with python-dotenv kindle_to_memos.py
```

## Usage

If `CLIPPINGS_PATH` is set in `.env`:

```bash
python kindle_to_memos.py
```

Or pass the file explicitly (this overrides `.env` for that run):

```bash
python kindle_to_memos.py "/path/to/My Clippings.txt"
```

Check `upload_preview.md`. When you're happy with it, type `confirmed` at the prompt. Any other answer exits without uploading anything.

## Tests

```bash
python -m unittest -v
```

The tests cover parsing, tag generation and deduplication. They don't contact Memos.

## Notes

- Memos API paths follow the public docs, but the docs don't list every endpoint. If the first run fails when fetching existing memos, check the OpenAPI spec for your Memos version.
- Memos created by hand with identical text are not recognised as duplicates. Only memos created by this script carry the hidden key used for deduplication.