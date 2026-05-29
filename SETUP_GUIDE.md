# PII Redactor — Setup & User Guide

This tool strips sensitive information (names, Social Security numbers, tax
IDs, account numbers, phone numbers, etc.) from documents before you send
them to outside tools or share them with anyone else.

**Everything runs locally on your computer. Nothing is ever uploaded. The
tool does not connect to the internet.**

Pick your operating system below and follow the steps for that section.

---

## Mac Setup

### Step 1 — Move the folder to a permanent home

After unzipping, drag the `pii_redactor` folder somewhere stable like
`~/Documents/pii_redactor/`. **Do not leave it in Downloads or on the
Desktop.** The launcher scripts need a permanent location.

### Step 2 — Run the one-time setup

Double-click `setup_once.command`.

**The first time, macOS will block it.** This is normal. You'll see a
dialog that says something like *"setup_once.command can't be opened
because Apple cannot check it for malicious software"* or *"cannot verify
it doesn't have malware."* Here's how to get past it:

1. Click **Done** (or close the dialog).
2. Open the Apple menu → **System Settings**.
3. Click **Privacy & Security** in the sidebar.
4. Scroll all the way down to the **Security** section.
5. You'll see a yellow notice about `setup_once.command` being blocked,
   with an **Open Anyway** button next to it. Click it.
6. Enter your password or use Touch ID if prompted.
7. Double-click `setup_once.command` again. You'll see the warning
   **one more time** — but this time the dialog will have an **Open**
   button. Click it.

This Gatekeeper dance only happens the **first time you run each script**.
Future double-clicks work normally.

> **If the "Open Anyway" button isn't visible in System Settings** — it
> only shows for about an hour after the block. Just double-click
> `setup_once.command` again to re-trigger the block, then go straight
> back to Privacy & Security and the button will be there.

> **Fastest fallback if Gatekeeper keeps fighting you** — open the
> Terminal app (Spotlight: ⌘-Space, type "Terminal", Enter). Type `cd `
> with a trailing space, then drag the `pii_redactor` folder into the
> Terminal window and press Enter. Then type `bash setup_once.command`
> and press Enter. This bypasses Gatekeeper entirely.

A Terminal window will open and run the setup. **The first run takes a few
minutes** — it's installing the libraries the tool needs. When you see
"Setup complete", press Enter to close.

> **If setup says "No supported Python found"** — install Python 3.12
> from
> [python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/)
> (scroll down to "macOS 64-bit universal2 installer" and run it). Then
> run `setup_once.command` again.
>
> Why specifically 3.12? Some of the libraries this tool uses don't have
> versions that work with Python 3.13 yet, so we cap the supported
> versions at 3.10–3.12. If you already have an older 3.10 or 3.11, that
> works too.

### Step 3 — Launch the app

Double-click `START_HERE.command`. (You may need to repeat the Gatekeeper
ritual once for this file too — same steps as above.)

This opens:
1. A Terminal window — **leave it running.** Closing it stops the app.
2. Your default browser at `http://127.0.0.1:8501`. That's the redactor.

After this first setup, you only need `START_HERE.command` to launch from
now on. `setup_once.command` is one-time only.

---

## Windows Setup

### Step 1 — Move the folder to a permanent home

After unzipping, move the `pii_redactor` folder somewhere stable like
`C:\pii-redactor\`. **Do not leave it in Downloads.** The launcher scripts
need a permanent location.

### Step 2 — Unblock the scripts (Mark of the Web)

Windows tags files downloaded from the internet as potentially untrusted.
For each launcher:

1. Right-click `setup_once.bat` → **Properties**.
2. At the bottom of the General tab, if there's an **Unblock** checkbox,
   tick it → **OK**.
3. Repeat for `START_HERE.bat`.

If you don't see an Unblock checkbox, Windows isn't blocking them — skip
ahead.

### Step 3 — Run the one-time setup

Double-click `setup_once.bat`.

> **If you see "Windows protected your PC"** (SmartScreen) — click
> **More info** → **Run anyway**.

A black command window opens and starts installing things. **The first
run takes a few minutes.** When you see "Setup complete", press any key
to close the window.

> **If setup says "No supported Python found"** — download Python 3.12
> from
> [python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/)
> (scroll down to "Windows installer (64-bit)" and run it). When the
> installer opens, **tick "Add python.exe to PATH"** at the bottom of the
> first screen *before* clicking Install. Then run `setup_once.bat` again.
>
> Why specifically 3.12? Some of the libraries this tool uses don't have
> versions that work with Python 3.13 yet, so we cap the supported
> versions at 3.10–3.12. If you already have an older 3.10 or 3.11, that
> works too.

### Step 4 — Launch the app

Double-click `START_HERE.bat`. This opens:
1. A black command window — **leave it open.** Closing it stops the app.
2. Your default browser at `http://127.0.0.1:8501`. That's the redactor.

After this first setup, you only need `START_HERE.bat` to launch from now
on. `setup_once.bat` is one-time only.

---

## How to Use the App

Once the app is running in your browser:

### Redacting a document

1. **Drop a file** in the upload area (or click "Browse files"). Supported
   formats: `.txt`, `.pdf`, `.docx`, `.xlsx`.
2. The tool scans the file and shows you everything it found, with a live
   preview of the redacted output.
3. **Review the findings** in the left column. Each row tells you:
    - What kind of PII was detected (e.g. `PERSON`, `US_SSN`)
    - The exact text that matched
    - A confidence score
4. If the tool got something wrong (false positive), **uncheck the box**
   next to that finding. The preview on the right updates live to show
   what your final output will look like.
5. **Download** the redacted file using the button at the bottom of the
   review section.

For DOCX and XLSX files, redacted spans are styled **bold and red** so
they're easy to spot in the output. PDFs are output as plain text files
(`.txt`).

### Adding your own things to redact

Above the upload area, click the **➕ Add a specific item to redact**
expander. Type any name, account number, project code, or phrase you want
stripped from your documents.

Then pick one of two modes:
- **Just for this session** — applies only until you close the browser tab.
  Good for one-off redactions.
- **Save permanently** — written to disk. Applies to every future document
  on this computer until you remove it.

To remove an item later, click **Remove** next to it in the list.

See `CUSTOMIZING.md` for a longer walkthrough and the editing-by-text-file
method (for the IT person setting up firm-wide defaults).

---

## What the Tool Detects

The tool automatically catches:

| Category              | Examples                                                  |
| --------------------- | --------------------------------------------------------- |
| Social Security #s    | `456-78-9012`                                             |
| Tax IDs (ITIN / EIN)  | ITIN format, dashed EINs like `12-3456789`                |
| Bank routing numbers  | 9-digit (fires when "routing", "wire", etc. is nearby)    |
| Bank account numbers  | 6–17 digit (fires when "account", "checking", etc. nearby) |
| Phone numbers         | Most US formats                                           |
| Email addresses       | Any standard email format                                 |
| Credit card numbers   | Visa/MC/Amex/etc.                                         |
| Passports / Licenses  | US passport and driver license numbers                    |
| Names                 | See "Names policy" below                                  |
| Addresses             | US street addresses (`123 Main Street`), PO Boxes (`P.O. Box 1234`), cities, states |
| Dates                 | Dates and times                                           |
| IBAN                  | International bank account numbers                        |
| Your custom items     | Anything you add via the ➕ box, plus `<REDACTED>` items  |

Each detection is replaced with a `<TYPE>` tag like `<US_SSN>`,
`<PERSON>`, or `<REDACTED>`. The tag tells the reviewer what kind of PII
was caught.

### Names policy (important)

To honor the firm's "no first names" rule:

- The surnames **Strassler** and **Herbstman** are always redacted
  (curated in `firm_config.py`).
- Multi-word names like "Jane Doe" become "Jane `<PERSON>`" — only the
  last word is redacted.
- A first name alone (e.g. "Maria called yesterday") is **not** redacted.
- A bare surname not in `firm_config.py` is also **not** redacted, because
  the tool can't tell first from last without context. If you need a
  particular surname always caught, add it to `firm_config.py` (see
  `CUSTOMIZING.md`).

### Excel sheets

Excel gets an extra layer: any column whose header looks like `SSN`,
`Tax ID`, `Account #`, `Client Name`, `DOB`, `Address`, `Email`, `Phone`,
etc. gets the whole column masked. Columns named `Notes`, `Comments`,
`Description`, etc. are exempt — those get cell-by-cell scanning so
incidental PII still gets caught without nuking the free-text column.

---

## Troubleshooting

### Mac: "setup_once.command was blocked"
Follow Step 2 in the Mac section. The **Open Anyway** button under
**System Settings → Privacy & Security → Security** is the fix. If the
button isn't there, double-click the file again to re-trigger the block,
then go straight to Privacy & Security.

### Mac: "No supported Python found"
You need Python 3.10, 3.11, or 3.12 — Python 3.13 is not supported. Get
3.12 here:
[python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/)
(scroll down to "macOS 64-bit universal2 installer"). After installing,
run `setup_once.command` again.

### Windows: "Windows protected your PC"
Click **More info** → **Run anyway**. This is SmartScreen — same warning
Windows shows for any uncommon `.bat` or `.exe`.

### Windows: "No supported Python found"
You need Python 3.10, 3.11, or 3.12 — Python 3.13 is not supported. Get
3.12 here:
[python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/)
(scroll down to "Windows installer (64-bit)"). When running the
installer, **tick "Add python.exe to PATH"** at the bottom of the first
screen *before* clicking Install. Then run `setup_once.bat` again.

### The browser didn't open
Manually open `http://127.0.0.1:8501` in any browser.

### Nothing happens when I drop a file
Check the command window for an error message. If you see one, save it
and send it to whoever maintains the tool, along with the type of file
that didn't work.

### I accidentally added something to "Save permanently"
Click **Remove** next to it in the "Saved permanently" list inside the
➕ expander.

### Where do I find what got saved permanently?
A file called `user_additions.txt` in the same folder as the launcher
scripts. Each line is one entry. You can open it in any text editor.

### I want to redact a brand-new type of pattern (not just specific text)
That's a code change — talk to whoever maintains the tool.

---

## Privacy & Offline Guarantee

This tool **never** connects to the internet. It does not send your
documents anywhere. It does not phone home for updates or analytics. The
language model it uses for name detection is bundled with the tool
itself, so even that does not require a download.

The browser at `http://127.0.0.1:8501` is just the way you interact with
the tool — that address (`127.0.0.1`) only works on your own computer.
Nobody else on your network or on the internet can reach it.

If you ever see a "no internet" warning while using the tool, ignore it.
That's correct behavior — the tool isn't supposed to use the internet.
