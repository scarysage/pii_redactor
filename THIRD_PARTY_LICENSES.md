# Third-Party Licenses

PII Redactor incorporates the following third-party open-source
components. Each is licensed to you under its own terms, reproduced or
linked below. Nothing in the PII Redactor commercial license (LICENSE)
restricts your rights under these third-party licenses.

If you redistribute PII Redactor in any form, this file must travel
with it.

---

## Runtime dependencies

| Component             | Version  | License    | Project URL                                            |
|-----------------------|----------|------------|--------------------------------------------------------|
| presidio-analyzer     | 2.2.355  | MIT        | https://github.com/microsoft/presidio                  |
| presidio-anonymizer   | 2.2.355  | MIT        | https://github.com/microsoft/presidio                  |
| spaCy                 | 3.7.5    | MIT        | https://github.com/explosion/spaCy                     |
| pdfplumber            | 0.11.9   | MIT        | https://github.com/jsvine/pdfplumber                   |
| python-docx           | 1.1.2    | MIT        | https://github.com/python-openxml/python-docx          |
| openpyxl              | 3.1.5    | MIT        | https://foss.heptapod.net/openpyxl/openpyxl            |
| Streamlit             | 1.58.0   | Apache 2.0 | https://github.com/streamlit/streamlit                 |

Transitive dependencies installed with the above (numpy, pandas,
pydantic, pdfminer.six, pillow, starlette, uvicorn, websockets, click,
regex, requests, etc.) are likewise licensed under permissive terms
(BSD, MIT, or Apache 2.0). A full machine-generated list can be produced
at any time by running:

    pip install pip-licenses
    pip-licenses --format=markdown --with-license-file --with-urls

against the installed environment, and is reproduced in
`vendor/licenses/` in this distribution.

---

## Bundled language model

PII Redactor ships with the spaCy English model **en_core_web_lg**
(version 3.7.1), vendored in the `en_core_web_lg/` directory.

* License: MIT
* Source: https://github.com/explosion/spacy-models
* Training data attributions: see
  `en_core_web_lg/LICENSES_SOURCES` and `en_core_web_lg/meta.json`
  inside this distribution. Those files cover OntoNotes 5,
  ClearNLP Constituent-to-Dependency Conversion, WordNet 3.0,
  and the GloVe Common Crawl vectors that the model was trained on.
  Do not remove those files when redistributing the model.

---

## Full license texts

### MIT License (applies to Presidio, spaCy, pdfplumber, python-docx,
### openpyxl, and the en_core_web_lg model)

    Permission is hereby granted, free of charge, to any person obtaining
    a copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to
    the following conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
    BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
    ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
    CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

Original copyright holders:
* Presidio:    Copyright (c) Microsoft Corporation.
* spaCy and en_core_web_lg: Copyright (c) ExplosionAI GmbH.
* pdfplumber:  Copyright (c) Jeremy Singer-Vine.
* python-docx: Copyright (c) Steve Canny.
* openpyxl:    Copyright (c) Eric Gazoni and contributors.

### Apache License 2.0 (applies to Streamlit)

Full text: https://www.apache.org/licenses/LICENSE-2.0

Streamlit is Copyright (c) Snowflake Inc. Per the Apache 2.0 license:
this distribution does not modify Streamlit, and the original NOTICE
file (if any) accompanies the installed package in your Python
environment under `streamlit-<version>.dist-info/`.

---

## Trademarks

"Microsoft" and "Presidio" are trademarks of Microsoft Corporation.
"spaCy" is a trademark of ExplosionAI GmbH. "Streamlit" is a
trademark of Snowflake Inc. PII Redactor uses these libraries under
their open-source licenses; nothing in this document grants any right
to use those trademarks. Marketing copy for PII Redactor should
describe these as "the open-source Presidio library", "the spaCy NLP
library", etc., rather than implying endorsement.
