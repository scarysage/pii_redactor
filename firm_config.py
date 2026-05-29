# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
================================================================================
firm_config.py  --  THE FILE THE FIRM EDITS
================================================================================

This is the ONLY file you need to edit to:
    * Add a name that should always be redacted (e.g. a partner or a client).
    * Add a specific number, code, or phrase that should always be redacted
      (e.g. a recurring account number, an internal reference code).

You do NOT need to know any Python to edit this file. Just follow the examples
in the lists below.

After you save your changes, restart the redactor app (close the browser tab,
close the command window, double-click START_HERE.bat again). The new entries
take effect on the next file you upload.

See CUSTOMIZING.md for step-by-step instructions with screenshots-worth of
detail.

--------------------------------------------------------------------------------
1) Names to always redact
--------------------------------------------------------------------------------
Add any last name (or first name) that the regular detector tends to miss.

Rules:
    * Put each name on its own line, in quotes, with a comma at the end.
    * Capitalization does NOT matter -- "Strassler" will also catch
      "strassler" and "STRASSLER".
    * Whole-word match -- "Smith" will catch "Smith" but NOT "Smithfield".
    * Avoid common English words ("Brown", "Green", "May") unless you really
      want EVERY occurrence redacted, including in normal sentences.
"""

FIRM_NAMES: list[str] = [
    "Strassler",
    "Herbstman",
    # Add more names here, one per line, like this:
    # "YourNameHere",
]


"""
--------------------------------------------------------------------------------
2) Specific things to always redact (exact strings)
--------------------------------------------------------------------------------
Use this for anything that isn't caught by the regular detectors but you want
gone every time it appears: a particular account number, an internal reference,
a project code, anything literal.

Rules:
    * Put each item on its own line, in quotes, with a comma at the end.
    * Capitalization does NOT matter.
    * Whole-word match (a punctuation or space must surround the item).
    * Replacement tag is <REDACTED>.

Examples (uncomment by removing the leading # to use them):
"""

ALWAYS_REDACT: list[str] = [
    # "ACME-12345",
    # "Project Phoenix",
    # "555-0199",
]


# ============================================================================
# DO NOT EDIT BELOW THIS LINE
# ============================================================================
# Anything below is structural code that wires the lists above into the rest
# of the application. Editing it can break the app.

# (No code below -- this file is pure configuration. Recognizers in
# recognizers.py read the FIRM_NAMES and ALWAYS_REDACT lists from here.)
