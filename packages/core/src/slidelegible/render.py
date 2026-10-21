"""Optional slide rendering: PPTX -> PDF (LibreOffice or ONLYOFFICE x2t) -> PNG (PyMuPDF).

Rendering is an infrastructure capability. Analysis still runs when no
renderer is installed; backgrounds that need pixels are then reported as
unknown instead of guessed.

Environment variables:

* ``SLIDELEGIBLE_RENDERER``: ``auto`` (default), ``onlyoffice``, ``libreoffice`` or ``none``.
* ``SLIDELEGIBLE_SOFFICE``: path to ``soffice`` / ``soffice.exe``.
* ``SLIDELEGIBLE_X2T``: path to ONLYOFFICE ``x2t`` / ``x2t.exe``.
* ``SLIDELEGIBLE_ONLYOFFICE_FONTS``: folder containing ``AllFonts.js`` and ``font_selection.bin``.
* ``SLIDELEGIBLE_RENDER_TIMEOUT``: seconds per conversion (default 300).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from xml.sax.saxutils import escape

import pymupdf

from .errors import RenderingFailure, RenderingUnavailable

DEFAULT_DPI = 150


@dataclass(frozen=True)
class RendererInfo:
    name: str
    available: bool
    path: str | None
    version: str | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "available": self.available,
            "path": self.path,
            "version": self.version,
            "detail": self.detail,
        }


class Renderer(Protocol):
    @property
    def info(self) -> RendererInfo: ...

    def to_pdf(self, source: Path, work_dir: Path) -> Path: ...


def _timeout() -> float:
    try:
        return float(os.environ.get("SLIDELEGIBLE_RENDER_TIMEOUT", "300"))
    except ValueError:
        return 300.0


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0


def _first_existing(candidates: list[str | None]) -> str | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


# --- LibreOffice ---------------------------------------------------------------------


class LibreOfficeRenderer:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or self.find()
        self._info: RendererInfo | None = None

    @staticmethod
    def find() -> str | None:
        env = os.environ.get("SLIDELEGIBLE_SOFFICE")
        candidates: list[str | None] = [env, shutil.which("soffice"), shutil.which("libreoffice")]
        if platform.system() == "Windows":
            for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
                if base:
                    candidates.append(str(Path(base) / "LibreOffice" / "program" / "soffice.exe"))
        elif platform.system() == "Darwin":
            candidates.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        return _first_existing(candidates)

    @property
    def info(self) -> RendererInfo:
        if self._info is None:
            if not self.executable:
                self._info = RendererInfo("libreoffice", False, None, None, "soffice not found")
            else:
                version = None
                try:
                    out = subprocess.run(
                        [self.executable, "--version"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=60,
                        creationflags=_no_window(),
                    )
                    version = (
                        (out.stdout or out.stderr).strip().splitlines()[0]
                        if (out.stdout or out.stderr)
                        else None
                    )
                except (OSError, subprocess.SubprocessError):
                    version = None
                self._info = RendererInfo(
                    "libreoffice", True, self.executable, version, "LibreOffice headless"
                )
        return self._info

    def to_pdf(self, source: Path, work_dir: Path) -> Path:
        if not self.executable:
            raise RenderingUnavailable("libreoffice_missing", "LibreOffice was not found.")
        profile = work_dir / "lo-profile"
        profile.mkdir(parents=True, exist_ok=True)
        out_dir = work_dir / "lo-out"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Hidden slides are exported so pages map 1:1 to slides (LibreOffice 7.4+ syntax);
        # older versions reject the JSON options, so retry with the plain filter.
        exports = [
            'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}',
            "pdf",
        ]
        pdf = out_dir / f"{source.stem}.pdf"
        detail = ""
        for export in exports:
            cmd = [
                self.executable,
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--headless",
                "--norestore",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                "--convert-to",
                export,
                "--outdir",
                str(out_dir),
                str(source),
            ]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_timeout(),
                    creationflags=_no_window(),
                )
            except subprocess.TimeoutExpired as exc:
                raise RenderingFailure(
                    "render_timeout", "LibreOffice conversion timed out."
                ) from exc
            except OSError as exc:
                raise RenderingFailure(
                    "render_launch_failed", f"Cannot start LibreOffice: {exc}"
                ) from exc
            if pdf.is_file():
                return pdf
            detail = (result.stderr or result.stdout or "").strip()[-400:]
        raise RenderingFailure("render_failed", f"LibreOffice produced no PDF. {detail}")


# --- ONLYOFFICE x2t ------------------------------------------------------------------


class OnlyOfficeRenderer:
    """Drives the ``x2t`` converter bundled with ONLYOFFICE Desktop Editors.

    x2t is configured with an XML task file. It needs the font cache that the
    desktop app builds on first launch (``AllFonts.js`` and ``font_selection.bin``).
    """

    PDF_FORMAT = 513  # AVS_OFFICESTUDIO_FILE_CROSSPLATFORM_PDF

    def __init__(self, executable: str | None = None, fonts_dir: str | None = None) -> None:
        self.executable = executable or self.find()
        self.fonts_dir = fonts_dir or self.find_fonts()
        self._info: RendererInfo | None = None

    @staticmethod
    def find() -> str | None:
        candidates: list[str | None] = [os.environ.get("SLIDELEGIBLE_X2T"), shutil.which("x2t")]
        system = platform.system()
        if system == "Windows":
            for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
                if base:
                    candidates.append(
                        str(Path(base) / "ONLYOFFICE" / "DesktopEditors" / "converter" / "x2t.exe")
                    )
        elif system == "Darwin":
            candidates.append("/Applications/ONLYOFFICE.app/Contents/Resources/converter/x2t")
        else:
            candidates += [
                "/opt/onlyoffice/desktopeditors/converter/x2t",
                "/usr/lib/onlyoffice/desktopeditors/converter/x2t",
            ]
        return _first_existing(candidates)

    @staticmethod
    def find_fonts() -> str | None:
        candidates: list[Path] = []
        env = os.environ.get("SLIDELEGIBLE_ONLYOFFICE_FONTS")
        if env:
            candidates.append(Path(env))
        system = platform.system()
        home = Path.home()
        if system == "Windows":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                candidates.append(Path(local) / "ONLYOFFICE" / "DesktopEditors" / "data" / "fonts")
        elif system == "Darwin":
            candidates.append(
                home
                / "Library"
                / "Application Support"
                / "asc.onlyoffice.ONLYOFFICE"
                / "data"
                / "fonts"
            )
        else:
            candidates.append(
                home / ".local" / "share" / "onlyoffice" / "desktopeditors" / "data" / "fonts"
            )
        for folder in candidates:
            if (folder / "AllFonts.js").is_file():
                return str(folder)
        return None

    @property
    def info(self) -> RendererInfo:
        if self._info is None:
            if not self.executable:
                self._info = RendererInfo("onlyoffice", False, None, None, "x2t not found")
            elif not self.fonts_dir:
                self._info = RendererInfo(
                    "onlyoffice",
                    False,
                    self.executable,
                    None,
                    "ONLYOFFICE font cache (AllFonts.js) not found; "
                    "open ONLYOFFICE Desktop Editors once",
                )
            else:
                self._info = RendererInfo(
                    "onlyoffice",
                    True,
                    self.executable,
                    None,
                    f"x2t with fonts from {self.fonts_dir}",
                )
        return self._info

    def task_xml(self, source: Path, target: Path, temp_dir: Path) -> str:
        assert self.fonts_dir is not None
        fonts = Path(self.fonts_dir)
        fields = {
            "m_sFileFrom": str(source.resolve()),
            "m_sFileTo": str(target.resolve()),
            "m_nFormatTo": str(self.PDF_FORMAT),
            "m_sFontDir": str(fonts.resolve()),
            "m_sAllFontsPath": str((fonts / "AllFonts.js").resolve()),
            "m_sTempDir": str(temp_dir.resolve()),
            "m_bIsNoBase64": "true",
            "m_bDontSaveAdditional": "true",
        }
        body = "".join(f"<{k}>{escape(v)}</{k}>" for k, v in fields.items())
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<TaskQueueDataConvert xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema">' + body + "</TaskQueueDataConvert>"
        )

    def to_pdf(self, source: Path, work_dir: Path) -> Path:
        if not self.info.available or not self.executable:
            raise RenderingUnavailable("onlyoffice_missing", self.info.detail)
        out_dir = work_dir / "x2t-out"
        temp_dir = work_dir / "x2t-temp"
        out_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{source.stem}.pdf"
        task = work_dir / "x2t-task.xml"
        task.write_text(self.task_xml(source, target, temp_dir), encoding="utf-8")
        try:
            result = subprocess.run(
                [self.executable, str(task.resolve())],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_timeout(),
                cwd=str(Path(self.executable).parent),
                creationflags=_no_window(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderingFailure("render_timeout", "ONLYOFFICE conversion timed out.") from exc
        except OSError as exc:
            raise RenderingFailure("render_launch_failed", f"Cannot start x2t: {exc}") from exc
        if not target.is_file() or target.stat().st_size == 0:
            detail = (result.stderr or result.stdout or "").strip()[-400:]
            raise RenderingFailure(
                "render_failed",
                f"x2t exited with code {result.returncode} and produced no PDF. {detail}",
            )
        return target


class _FallbackRenderer:
    """Try renderers in order; remember the first one that works."""

    def __init__(self, renderers: list[Renderer]) -> None:
        self.renderers = renderers
        self.last_errors: list[str] = []

    @property
    def info(self) -> RendererInfo:
        for renderer in self.renderers:
            if renderer.info.available:
                return renderer.info
        details = "; ".join(f"{r.info.name}: {r.info.detail}" for r in self.renderers)
        return RendererInfo("none", False, None, None, details or "no renderer configured")

    def to_pdf(self, source: Path, work_dir: Path) -> Path:
        self.last_errors = []
        for renderer in self.renderers:
            if not renderer.info.available:
                continue
            try:
                return renderer.to_pdf(source, work_dir / renderer.info.name)
            except (RenderingFailure, RenderingUnavailable) as exc:
                self.last_errors.append(f"{renderer.info.name}: {exc.message}")
        raise RenderingFailure(
            "render_failed", " | ".join(self.last_errors) or "No renderer available."
        )


def get_renderer(preference: str | None = None) -> Renderer | None:
    """Return a renderer honouring ``SLIDELEGIBLE_RENDERER``; ``None`` when disabled/unavailable."""
    choice = (preference or os.environ.get("SLIDELEGIBLE_RENDERER", "auto")).lower()
    if choice == "none":
        return None
    order: list[Renderer]
    if choice == "onlyoffice":
        order = [OnlyOfficeRenderer()]
    elif choice == "libreoffice":
        order = [LibreOfficeRenderer()]
    else:
        order = [OnlyOfficeRenderer(), LibreOfficeRenderer()]
    fallback = _FallbackRenderer(order)
    return fallback if fallback.info.available else None


def describe_renderers() -> list[RendererInfo]:
    return [OnlyOfficeRenderer().info, LibreOfficeRenderer().info]


# --- rasterizing ---------------------------------------------------------------------


@dataclass
class PageImage:
    width: int
    height: int
    samples: bytes  # packed RGB, row stride = width * 3
    png: bytes

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        i = (y * self.width + x) * 3
        return self.samples[i], self.samples[i + 1], self.samples[i + 2]


def rasterize(pdf_path: Path, dpi: int = DEFAULT_DPI) -> list[PageImage]:
    try:
        doc = pymupdf.Document(str(pdf_path))  # type: ignore[no-untyped-call]
    except Exception as exc:  # PyMuPDF raises several internal exception types
        raise RenderingFailure("pdf_unreadable", f"Cannot read rendered PDF: {exc}") from exc
    pages: list[PageImage] = []
    try:
        for index in range(doc.page_count):
            page = doc.load_page(index)  # type: ignore[no-untyped-call]
            pix = page.get_pixmap(dpi=dpi, alpha=False, colorspace=pymupdf.csRGB)
            raw = bytes(pix.samples)
            if pix.stride != pix.width * 3:
                raw = b"".join(
                    raw[y * pix.stride : y * pix.stride + pix.width * 3] for y in range(pix.height)
                )
            pages.append(PageImage(pix.width, pix.height, raw, bytes(pix.tobytes("png"))))
    finally:
        doc.close()  # type: ignore[no-untyped-call]
    return pages


def render_pptx(renderer: Renderer, data: bytes, dpi: int = DEFAULT_DPI) -> list[PageImage]:
    """Render a PPTX given as bytes to page images using a private temp directory."""
    with tempfile.TemporaryDirectory(
        prefix="slidelegible-render-", ignore_cleanup_errors=True
    ) as tmp:
        work = Path(tmp)
        source = work / "deck.pptx"
        source.write_bytes(data)
        pdf = renderer.to_pdf(source, work)
        return rasterize(pdf, dpi)


def thumbnail(png: bytes, shrink: int = 1) -> bytes:
    """Downscale a PNG by 2**shrink (used for embedding previews in reports)."""
    pix = pymupdf.Pixmap(png)  # type: ignore[no-untyped-call]
    if shrink > 0:
        pix.shrink(shrink)  # type: ignore[no-untyped-call]
    return bytes(pix.tobytes("png"))  # type: ignore[no-untyped-call]


def main(argv: list[str] | None = None) -> int:
    """Diagnose renderers: ``python -m slidelegible.render [deck.pptx]``."""
    import argparse
    import io
    import time

    parser = argparse.ArgumentParser(description="Check SlideLegible slide renderers.")
    parser.add_argument("deck", nargs="?", help="optional .pptx to convert as a test")
    parser.add_argument("--renderer", choices=["auto", "onlyoffice", "libreoffice"], default="auto")
    args = parser.parse_args(argv)

    for info in describe_renderers():
        state = "OK" if info.available else "--"
        print(f"[{state}] {info.name}: {info.detail}")
        if info.path:
            print(f"     path: {info.path}")
    renderer = get_renderer(args.renderer)
    if renderer is None:
        print("No usable renderer. Analysis still works for solid backgrounds.")
        return 1
    print(f"Selected: {renderer.info.name}")
    if args.deck:
        data = Path(args.deck).read_bytes()
    else:
        from pptx import Presentation
        from pptx.util import Inches

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        slide.shapes.add_textbox(
            Inches(1), Inches(1), Inches(6), Inches(1)
        ).text_frame.text = "SlideLegible 渲染測試"
        buf = io.BytesIO()
        prs.save(buf)
        data = buf.getvalue()
    start = time.monotonic()
    try:
        pages = render_pptx(renderer, data)
    except (RenderingFailure, RenderingUnavailable) as exc:
        print(f"FAILED: {exc.message}")
        return 2
    print(f"Rendered {len(pages)} page(s) in {time.monotonic() - start:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
