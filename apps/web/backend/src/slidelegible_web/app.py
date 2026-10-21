"""FastAPI adapter for the SlideLegible core (local single-user deployment).

Run from the repository root::

    uv run uvicorn slidelegible_web.app:app

then open http://127.0.0.1:8000 (after ``npm run build`` in apps/web/frontend),
or use the Vite dev server (``npm run dev``) which proxies ``/api`` here.
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slidelegible import __version__
from slidelegible.api import AnalysisResult, analyze_presentation, apply_corrections
from slidelegible.errors import RenderingFailure, RenderingUnavailable, SlideLegibleError
from slidelegible.i18n import LANGS
from slidelegible.policy import PRESETS, PolicyName, get_policy
from slidelegible.pptx.package import PptxPackage
from slidelegible.render import (
    DEFAULT_DPI,
    describe_renderers,
    get_renderer,
    render_pptx,
    thumbnail,
)
from slidelegible.report_html import build_html_report

from .store import AnalysisRecord, CorrectionRecord, Job, Store, Upload, new_id

PPTX_MEDIA = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
STATUS_FOR_CATEGORY = {
    "invalid_input": 400,
    "unsupported_content": 422,
    "correction_conflict": 409,
    "unsafe_modification": 422,
    "resource_limit_exceeded": 413,
    "rendering_unavailable": 503,
    "rendering_failure": 502,
    "artifact_access_failure": 404,
}

store: Store
executor: ThreadPoolExecutor


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global store, executor
    store = Store()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="slidelegible-job")
    try:
        yield
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        store.cleanup()


app = FastAPI(title="SlideLegible", version=__version__, lifespan=lifespan)


@app.exception_handler(SlideLegibleError)
async def core_error_handler(_request: Request, exc: SlideLegibleError) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_FOR_CATEGORY.get(exc.category, 500), content={"error": exc.to_dict()}
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=404, detail={"code": "not_found", "message": f"{what} not found"}
    )


def _safe_name(name: str) -> str:
    stem = Path(name).stem or "presentation"
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", stem).strip(" .") or "presentation"
    return stem[:120]


# --- capabilities --------------------------------------------------------------------


@app.get("/api/v1/capabilities")
def capabilities() -> dict[str, Any]:
    renderer = get_renderer()
    return {
        "version": __version__,
        "renderer": renderer.info.to_dict() if renderer else None,
        "renderers": [r.to_dict() for r in describe_renderers()],
        "policies": [
            {**PRESETS[name].to_dict(), "allow_soften": PRESETS[name].allow_soften}
            for name in PolicyName
        ],
        "languages": list(LANGS),
    }


# --- uploads -------------------------------------------------------------------------


@app.post("/api/v1/presentations")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    data = await file.read()
    package = PptxPackage(data)  # validates; raises InvalidInput
    upload_id = new_id()
    path = store.root / f"upload-{upload_id}.pptx"
    path.write_bytes(data)
    record = Upload(upload_id, file.filename or "presentation.pptx", path, len(package.slide_parts))
    with store.lock:
        store.uploads[upload_id] = record
    return {"id": upload_id, "filename": record.filename, "slides": record.slides}


# --- jobs ----------------------------------------------------------------------------


def _job_view(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "stage": job.stage,
        "progress": round(job.progress, 3),
        "error": job.error,
        "result": job.result,
    }


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = store.jobs.get(job_id)
    if job is None:
        raise _not_found("job")
    return _job_view(job)


def _run(job: Job, work: Any) -> None:
    job.status = "running"
    try:
        job.result = work(job)
        job.status = "completed"
        job.stage = "done"
        job.progress = 1.0
    except SlideLegibleError as exc:
        job.status = "failed"
        job.error = exc.to_dict()
    except Exception as exc:  # report unexpected failures without crashing the worker
        job.status = "failed"
        job.error = {"category": "internal", "code": "internal_error", "message": str(exc)}


def _preview_artifacts(pages: list[Any], slides: int) -> dict[int, str]:
    if len(pages) != slides:
        return {}
    result: dict[int, str] = {}
    for index, page in enumerate(pages, start=1):
        result[index] = store.write_artifact(page.png, ".png", "image/png").id
    return result


def _correct(
    record: AnalysisRecord, selected: list[str] | None, job: Job | None
) -> CorrectionRecord:
    analysis = record.result
    upload = store.uploads[record.upload_id]
    if job:
        job.stage, job.progress = "apply", 0.2
    outcome = apply_corrections(analysis, selected, fingerprint=analysis.package.fingerprint)
    pptx = store.write_artifact(
        outcome.data, ".pptx", PPTX_MEDIA, f"{_safe_name(upload.filename)}-slidelegible.pptx"
    )
    correction = CorrectionRecord(new_id(), record.id, outcome, pptx.id)
    renderer = get_renderer()
    if renderer is not None and outcome.applied:
        if job:
            job.stage, job.progress = "render_corrected", 0.5
        try:
            pages = render_pptx(renderer, outcome.data, DEFAULT_DPI)
            correction.previews = _preview_artifacts(pages, len(analysis.inspection.slides))
        except (RenderingFailure, RenderingUnavailable) as exc:
            correction.render_error = exc.message
    elif not outcome.applied:
        correction.previews = dict(record.original_previews)
    with store.lock:
        store.corrections[correction.id] = correction
    return correction


def _correction_view(c: CorrectionRecord) -> dict[str, Any]:
    return {
        "id": c.id,
        "pptx_artifact": c.pptx_artifact,
        "previews": {str(k): v for k, v in c.previews.items()},
        "render_error": c.render_error,
        **c.result.to_dict(),
    }


class AnalysisRequest(BaseModel):
    policy: PolicyName = PolicyName.COMFORTABLE
    soften: bool = False


@app.post("/api/v1/presentations/{upload_id}/analysis")
def start_analysis(upload_id: str, body: AnalysisRequest) -> dict[str, Any]:
    upload = store.uploads.get(upload_id)
    if upload is None:
        raise _not_found("presentation")
    policy = get_policy(body.policy, soften=body.soften)
    job = store.new_job("analysis")

    def work(j: Job) -> dict[str, Any]:
        def progress(stage: str, fraction: float) -> None:
            j.stage, j.progress = stage, fraction * 0.7

        data = upload.path.read_bytes()
        result: AnalysisResult = analyze_presentation(
            data, upload.filename, policy, get_renderer(), progress=progress
        )
        record = AnalysisRecord(new_id(), upload_id, result)
        record.original_previews = _preview_artifacts(
            result.original_pages.pages, len(result.inspection.slides)
        )
        result.original_pages.pages = []  # free memory; previews are on disk
        with store.lock:
            store.analyses[record.id] = record
        j.stage, j.progress = "render_proposed", 0.75
        record.proposed = _correct(record, None, None)
        return {"analysis_id": record.id}

    executor.submit(_run, job, work)
    return {"job_id": job.id}


@app.get("/api/v1/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict[str, Any]:
    record = store.analyses.get(analysis_id)
    if record is None:
        raise _not_found("analysis")
    report = record.result.report()
    return {
        "id": record.id,
        "report": report,
        "original_previews": {str(k): v for k, v in record.original_previews.items()},
        "proposed": _correction_view(record.proposed) if record.proposed else None,
    }


class CorrectionRequest(BaseModel):
    suggestion_ids: list[str] = Field(default_factory=list)


@app.post("/api/v1/analyses/{analysis_id}/corrections")
def start_correction(analysis_id: str, body: CorrectionRequest) -> dict[str, Any]:
    record = store.analyses.get(analysis_id)
    if record is None:
        raise _not_found("analysis")
    job = store.new_job("correction")

    def work(j: Job) -> dict[str, Any]:
        correction = _correct(record, body.suggestion_ids, j)
        return {"correction": _correction_view(correction)}

    executor.submit(_run, job, work)
    return {"job_id": job.id}


@app.get("/api/v1/corrections/{correction_id}/report", response_class=HTMLResponse)
def correction_report(
    correction_id: str, lang: str = "zh-TW", download: bool = True
) -> HTMLResponse:
    correction = store.corrections.get(correction_id)
    if correction is None:
        raise _not_found("correction")
    record = store.analyses[correction.analysis_id]
    previews: dict[int, tuple[bytes | None, bytes | None]] = {}
    for slide in record.result.inspection.slides:
        before_id = record.original_previews.get(slide.index)
        after_id = correction.previews.get(slide.index)
        before = thumbnail(store.artifacts[before_id].path.read_bytes()) if before_id else None
        after = thumbnail(store.artifacts[after_id].path.read_bytes()) if after_id else None
        if before or after:
            previews[slide.index] = (before, after)
    html = build_html_report(
        record.result, correction.result.applied, lang if lang in LANGS else "zh-TW", previews
    )
    upload = store.uploads[record.upload_id]
    headers = {}
    if download:
        name = f"{_safe_name(upload.filename)}-report.html"
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{_quote(name)}"
    return HTMLResponse(html, headers=headers)


def _quote(value: str) -> str:
    return quote(value, safe="")


@app.get("/api/v1/previews/{artifact_id}")
def get_preview(artifact_id: str) -> FileResponse:
    artifact = store.artifacts.get(artifact_id)
    if artifact is None or artifact.media_type != "image/png":
        raise _not_found("preview")
    return FileResponse(artifact.path, media_type="image/png")


@app.get("/api/v1/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> FileResponse:
    artifact = store.artifacts.get(artifact_id)
    if artifact is None:
        raise _not_found("artifact")
    return FileResponse(
        artifact.path, media_type=artifact.media_type, filename=artifact.download_name
    )


# --- frontend ------------------------------------------------------------------------


def _frontend_dist() -> Path | None:
    env = os.environ.get("SLIDELEGIBLE_FRONTEND_DIST")
    candidates = [Path(env)] if env else []
    candidates.append(Path(__file__).resolve().parents[3] / "frontend" / "dist")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


_dist = _frontend_dist()
if _dist is not None:
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse)
    def frontend_missing() -> str:
        return (
            "<!doctype html><meta charset='utf-8'><title>SlideLegible</title>"
            "<p>SlideLegible API is running. Build the frontend with "
            "<code>npm run build</code> in <code>apps/web/frontend</code>, "
            "or run <code>npm run dev</code> and open the Vite URL.</p>"
        )
