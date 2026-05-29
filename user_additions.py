"""
Read/write helpers for `user_additions.txt` -- the file that stores literal
strings the UI's "Add a specific item to redact -> Save permanently" button
appends to.

Why this is a separate file from firm_config.py:
    * firm_config.py is curated by the firm's IT person via a text editor.
      It's Python source and one typo breaks the app.
    * user_additions.txt is appended/edited at runtime by the Streamlit UI
      for non-technical users. It must be safe to mutate.

Format:
    One entry per line. Blank lines and lines starting with '#' are ignored.
    Entries are matched case-insensitively, whole-word, in the same way as
    firm_config.ALWAYS_REDACT. Matched spans get the `<REDACTED>` tag.

The file may not exist on a fresh install. All read functions return an
empty list in that case; the file is created lazily on the first add.
"""

from __future__ import annotations

from pathlib import Path


# Anchored to this file's directory so it works regardless of CWD.
USER_ADDITIONS_PATH = Path(__file__).resolve().parent / "user_additions.txt"


def load_user_additions() -> list[str]:
    """Return the list of user-added persistent redaction terms.

    Returns [] if the file does not exist. Blank lines and lines starting
    with '#' are skipped.
    """
    if not USER_ADDITIONS_PATH.exists():
        return []
    items: list[str] = []
    for raw in USER_ADDITIONS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def add_user_addition(item: str) -> bool:
    """Append `item` to the persistent list if not already present.

    Returns True if the item was added, False if it was already there or
    if the trimmed item is empty.
    """
    cleaned = item.strip()
    if not cleaned:
        return False
    existing = load_user_additions()
    # Case-insensitive de-dupe; we store the form the user typed.
    if any(e.lower() == cleaned.lower() for e in existing):
        return False
    # Ensure trailing newline so concatenation stays clean.
    with USER_ADDITIONS_PATH.open("a", encoding="utf-8") as fh:
        if USER_ADDITIONS_PATH.stat().st_size > 0:
            # If the file does not already end with a newline, add one.
            # We can't easily seek-back-and-read on append mode portably, so
            # always start each new entry on its own line and accept that
            # we may end up with one extra blank line on rare occasions
            # (harmless -- load skips blanks).
            fh.write("\n")
        fh.write(cleaned + "\n")
    return True


def remove_user_addition(item: str) -> bool:
    """Remove `item` (case-insensitive) from the persistent list.

    Returns True if something was removed, False otherwise. Rewrites the
    whole file -- it's small.
    """
    target = item.strip().lower()
    if not target:
        return False
    existing = load_user_additions()
    kept = [e for e in existing if e.lower() != target]
    if len(kept) == len(existing):
        return False
    USER_ADDITIONS_PATH.write_text(
        "\n".join(kept) + ("\n" if kept else ""), encoding="utf-8"
    )
    return True
