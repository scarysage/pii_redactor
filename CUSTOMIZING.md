# Customizing what gets redacted

You have **two ways** to add things the redactor should strip out:

| Method                                | Who it's for                          | How                                            |
| ------------------------------------- | ------------------------------------- | ---------------------------------------------- |
| **The "Add" box in the app**          | Anyone using the redactor             | Click `➕ Add a specific item to redact` above the upload area. Pick "this session" or "save permanently". |
| **Edit `firm_config.py` in a text editor** | IT person setting up the baseline list | Open the file, edit a list, save.        |

Both methods work side-by-side and persist across restarts (except "this
session" — see below).

If you only want to add or remove a name / number, use the in-app box. If
you're setting up the firm's baseline list (the names that should be
caught for every user, on every machine), edit `firm_config.py`.

---

## Method 1: the "Add" box in the app (easiest)

Open the redactor (`START_HERE.bat` on Windows or `START_HERE.command` on Mac).
At the top of the page, click `➕ Add a specific item to redact`.

You'll see:

1. **A text box** — type the name, number, or phrase you want stripped out.
2. **A choice** — pick one:
    * **Just for this session** — applied until you close the browser tab.
      Use this when you want to redact something one time without committing
      to it forever.
    * **Save permanently** — written to disk. Every future upload (today,
      tomorrow, after a restart) will also redact this item.
3. **An "Add" button** — click it. The item appears in a list below.

To remove an item later, click the **Remove** button next to it.

### Notes

* Items are matched **whole-word, case-insensitive** — same rules as the
  lists in `firm_config.py`.
* Items get the `<REDACTED>` tag in the output.
* If you add a really common word ("the", "and"), every document will have a
  ton of redactions. Use **Remove** to undo.
* "Save permanently" entries live in a file called `user_additions.txt` in
  the same folder as the redactor. You can also open it in a text editor
  if you prefer — one entry per line, blank lines and `#` lines ignored.

---

## Method 2: editing `firm_config.py` (for IT / the baseline list)

Use this for the firm-wide baseline — names and items that should be caught
for **every user, on every machine**, before anyone touches the in-app
box. If you're just adding a one-off, use Method 1 above.

### Before you start

1. Make sure the redactor app is **closed**. (Close the browser tab and the
   black command window that opened when you double-clicked `START_HERE.bat`.)
2. Open `firm_config.py` in any text editor. Notepad works. So does VS Code,
   Notepad++, or anything else. The file is in the same folder as
   `START_HERE.bat`.

---

## Adding a name to always redact

Use this for last names (or first names) that you want gone every time they
appear in a document. Helpful when the regular detector misses an unusual
name.

### What to look for in `firm_config.py`

A block that looks like this:

```python
FIRM_NAMES: list[str] = [
    "Strassler",
    "Herbstman",
    # Add more names here, one per line, like this:
    # "YourNameHere",
]
```

### How to add a name

1. Find the line that says `# "YourNameHere",` (note the `#` — that means
   it's a comment, not active).
2. Above that line (or anywhere inside the `[ ... ]` brackets), add a new
   line with the name in quotes and a comma at the end:

```python
FIRM_NAMES: list[str] = [
    "Strassler",
    "Herbstman",
    "Goldberg",     <-- the new name
    # Add more names here, one per line, like this:
    # "YourNameHere",
]
```

3. Save the file.

### Rules to remember

- **Capitalization doesn't matter.** `"Strassler"` also catches `strassler`
  and `STRASSLER`.
- **Whole words only.** `"Smith"` catches `Smith` but NOT `Smithfield`.
- **One name per line, in quotes, with a comma at the end.** The comma at
  the end of the LAST name is also fine — Python doesn't mind.
- **Avoid common English words** like `"Brown"`, `"Green"`, `"May"`, unless
  you really want every occurrence redacted (including in normal sentences
  like "the leaves are brown").

---

## Adding a specific number or phrase to always redact

Use this for any literal text you want gone every time: a recurring account
number, an internal project code, a specific phone number, a recurring
phrase — anything.

### What to look for in `firm_config.py`

A block that looks like this:

```python
ALWAYS_REDACT: list[str] = [
    # "ACME-12345",
    # "Project Phoenix",
    # "555-0199",
]
```

The lines starting with `#` are **examples** — they're commented out and do
nothing.

### How to add an item

1. Add a new line inside the `[ ... ]` brackets with the item in quotes and
   a comma at the end. **Do NOT** put `#` at the start, or it won't work.

```python
ALWAYS_REDACT: list[str] = [
    "ACCT-99887766",     <-- new entry, actively used
    "Project Falcon",    <-- new entry, actively used
    # "ACME-12345",      <-- still commented out, ignored
    # "Project Phoenix",
    # "555-0199",
]
```

2. Save the file.

### Rules to remember

- **Capitalization doesn't matter.**
- **Whole words only.** `"ACCT-99887766"` catches `ACCT-99887766` but NOT
  `XACCT-99887766X`.
- Items in this list get replaced with `<REDACTED>` in the output (the
  generic tag). Names in `FIRM_NAMES` get replaced with `<PERSON>`.
- Keep the list focused — anything you add fires on EVERY upload. If you
  add a really common word by mistake, every document will have a bunch of
  unwanted redactions.

---

## After you save

1. Double-click `START_HERE.bat` to relaunch the redactor.
2. Upload a test document that contains the new name / phrase / number.
3. Confirm it shows up in the review screen as redacted (bold + red).

If your new entry **doesn't** show up:

- Did you save the file? (Easy to miss.)
- Did you spell it the same way it appears in the document?
- Is it inside the `[ ... ]` brackets, in quotes, with a comma after it?
- Does the line start with `#`? Remove the `#` — the `#` means "ignore
  this line".

---

## What NOT to edit in `firm_config.py`

The top of the file has a long comment block (lines starting with `"""` or
`#`) explaining each list. **You can change those words** if you want —
they're just notes for the next person.

The `FIRM_NAMES = [ ... ]` and `ALWAYS_REDACT = [ ... ]` lines are the
"live" parts. Edit the contents of the brackets, but **do NOT remove**:

- The variable name (`FIRM_NAMES` or `ALWAYS_REDACT`)
- The `: list[str]` annotation
- The `= [` at the start
- The `]` at the end

If something breaks: open `firm_config.py.bak` (a backup will exist if you
made one — always a good idea to copy the file before editing) or
re-download the tool from the shared link to get the original back.

---

## Need something more advanced?

The tool already detects these types automatically — you don't need to add
them to either list:

- Social Security numbers (SSN)
- ITINs (individual taxpayer ID numbers)
- EIN / Federal tax IDs (when dashed: `12-3456789`)
- Phone numbers (most US formats)
- Email addresses
- Credit card numbers
- Bank routing numbers (when "routing" or similar appears nearby)
- Bank account numbers (when "account" or similar appears nearby)
- Most people-names (via the language model; unusual names should go in
  `FIRM_NAMES`)
- US driver licenses, US passports
- Some addresses, dates

If you need a NEW type of pattern (e.g. a brand-new ID format the firm
starts using), that's a code change — contact whoever maintains this tool.
