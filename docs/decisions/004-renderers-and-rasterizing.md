# ADR 004: Pluggable Renderers and PyMuPDF Rasterizing

**Status:** Accepted for the MVP

## Context

The MVP runs as a local web tool on contributors' own computers, including Windows laptops that have ONLYOFFICE Desktop Editors but not LibreOffice. ADR 002 named LibreOffice as the initial renderer. Rendered pages are needed for previews and for sampling picture and gradient backgrounds; the PDF must then be rasterized.

## Decision

* The renderer interface (`slidelegible.render.Renderer`) converts a PPTX to PDF. Two implementations ship:
  * `OnlyOfficeRenderer` drives the `x2t` converter bundled with ONLYOFFICE Desktop Editors through an XML task file (`m_nFormatTo` 513 = PDF) and the font cache the desktop app builds (`AllFonts.js`, `font_selection.bin`).
  * `LibreOfficeRenderer` uses `soffice --headless --convert-to pdf` with a private profile, exporting hidden slides.
* `SLIDELEGIBLE_RENDERER=auto` tries ONLYOFFICE first, then LibreOffice; `none` disables rendering. Paths can be overridden with `SLIDELEGIBLE_X2T`, `SLIDELEGIBLE_ONLYOFFICE_FONTS`, and `SLIDELEGIBLE_SOFFICE`.
* PDFs are rasterized with PyMuPDF (150 DPI by default).
* `python -m slidelegible.render [deck.pptx]` prints which renderers were found and runs a test conversion.

## Consequences

* `x2t` has no published command-line contract; its task-file format can change between ONLYOFFICE releases. The adapter reports failures and falls back to LibreOffice when present. It is covered by a fake-`x2t` test, not by a real ONLYOFFICE in CI.
* PyMuPDF is licensed under AGPL-3.0 (or a commercial license), so the project license was changed to AGPL-3.0-or-later.
* Renderer differences (fonts, effects) still apply; rendered samples are labelled `rendered_estimate`.
