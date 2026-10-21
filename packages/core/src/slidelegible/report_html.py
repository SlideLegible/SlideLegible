"""Self-contained HTML report (no external resources)."""

from __future__ import annotations

import base64
from collections import defaultdict
from datetime import datetime
from html import escape

from .analyze import Finding, Status
from .apca import APCA_VERSION
from .api import AnalysisResult
from .correct import Suggestion
from .i18n import t
from .policy import Requirement

CSS = """
:root{--bg:#fbfbfa;--fg:#1c2622;--muted:#55635d;--line:#d9e0dc;--card:#fff;--accent:#1f6b52;
--bad:#a3261b;--ok:#1f6b38;--warn:#8a5a00;}
@media (prefers-color-scheme:dark){:root{--bg:#131715;--fg:#e8ece9;--muted:#a5b1ab;--line:#2c3531;
--card:#1a201d;--accent:#7cd0ae;--bad:#ff9b8f;--ok:#8fdc9f;--warn:#f0c46a;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 system-ui,-apple-system,"Segoe UI","Noto Sans TC","Microsoft JhengHei",sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;margin:0 0 8px}
h2{font-size:20px;margin:36px 0 12px}.meta{color:var(--muted);margin:0 0 4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card b{display:block;font-size:24px}.card span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
border-radius:10px;overflow:hidden;font-size:14px}th,td{text-align:left;padding:8px 10px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.sw{display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid var(--line);
vertical-align:-2px;margin-right:4px}.st-fail{color:var(--bad);font-weight:600}
.st-pass{color:var(--ok)}.st-other{color:var(--warn)}.mono{font-family:ui-monospace,Consolas,monospace}
.previews{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0 12px}
.previews figure{margin:0}.previews img{width:100%;border:1px solid var(--line);border-radius:6px}
figcaption{color:var(--muted);font-size:13px}.note{color:var(--muted);font-size:13px}
.sample{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:600}
@media (max-width:640px){.previews{grid-template-columns:1fr}td,th{padding:6px}}
"""


def _sw(hex_color: str | None) -> str:
    if not hex_color:
        return ""
    return f'<span class="sw" style="background:{escape(hex_color)}"></span>{escape(hex_color)}'


def _status(lang: str, f: Finding) -> str:
    cls = {"pass": "st-pass", "fail": "st-fail"}.get(f.status.value, "st-other")
    label = t(lang, f"status.{f.status.value}")
    if f.reason and f.status in (Status.DECORATIVE, Status.UNSUPPORTED):
        label += f" · {t(lang, 'reason.' + f.reason)}"
    return f'<span class="{cls}">{escape(label)}</span>'


def _fix_text(lang: str, s: Suggestion) -> str:
    label = t(lang, f"kind.{s.kind}")
    if s.strategy == "flip":
        label = t(lang, "strategy.flip")
    if s.kind == "scrim":
        return f"{escape(label)} {_sw('#' + s.proposed.hex)} {int((s.alpha or 0) * 100)}%"
    orig = f"#{s.original.hex}" if s.original else None
    return f"{escape(label)}<br>{_sw(orig)} → {_sw('#' + s.proposed.hex)}"


def build_html_report(
    result: AnalysisResult,
    applied: list[str],
    lang: str = "zh-TW",
    previews: dict[int, tuple[bytes | None, bytes | None]] | None = None,
) -> str:
    report_policy = result.policy
    summary = result.summary()
    suggestions = result.plan.suggestions
    by_run: dict[str, list[Suggestion]] = defaultdict(list)
    for s in suggestions:
        for rid in s.run_ids:
            by_run[rid].append(s)
    unfixed = {u.run_id: u for u in result.plan.unfixed}
    findings_by_slide: dict[int, list[Finding]] = defaultdict(list)
    for f in result.findings:
        findings_by_slide[f.run.slide_index].append(f)
    applied_set = set(applied)
    renderer = (
        f"{result.renderer.name} {result.renderer.version or ''}".strip()
        if result.renderer
        else t(lang, "renderer.none")
    )

    out: list[str] = []
    out.append(f'<!doctype html><html lang="{escape(lang)}"><head><meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    out.append(f"<title>{escape(t(lang, 'title'))} · {escape(result.inspection.filename)}</title>")
    out.append(f"<style>{CSS}</style></head><body><main>")
    out.append(f"<h1>{escape(t(lang, 'title'))}</h1>")
    out.append(f'<p class="meta">{t(lang, "file")}: {escape(result.inspection.filename)}</p>')
    out.append(
        f'<p class="meta">{t(lang, "generated")}: {datetime.now().strftime("%Y-%m-%d %H:%M")}'
        f" · {t(lang, 'policy')}: {t(lang, 'policy.' + report_policy.name.value)}"
        f" · {t(lang, 'soften')}: {t(lang, 'on' if report_policy.soften else 'off')}"
        f" · {t(lang, 'renderer')}: {escape(renderer)}</p>"
    )
    req_n, req_l = report_policy.normal, report_policy.large

    def req(r: Requirement) -> str:
        text = f"WCAG ≥ {r.min_ratio}:1"
        if r.min_apca is not None:
            text += f" · APCA |Lc| ≥ {r.min_apca:g}"
        return text

    out.append(
        f'<p class="meta">{t(lang, "requirements")}: {t(lang, "normal_text")} {req(req_n)}；'
        f"{t(lang, 'large_text')} {req(req_l)}</p>"
    )
    issues = summary.get("fail", 0)
    out.append('<div class="cards">')
    for value, key in (
        (summary["slides"], "slides"),
        (summary["total_runs"], "runs"),
        (issues, "issues"),
        (len(applied_set), "applied"),
        (len(result.plan.unfixed), "unfixed"),
    ):
        out.append(f'<div class="card"><b>{value}</b><span>{t(lang, key)}</span></div>')
    out.append("</div>")
    out.append(
        f'<p class="note">{t(lang, "apca_note", v=APCA_VERSION)} {t(lang, "estimate_note")}</p>'
    )

    if result.inspection.unsupported:
        out.append(f"<h2>{t(lang, 'unsupported')}</h2><ul>")
        for u in result.inspection.unsupported:
            out.append(
                f"<li>{t(lang, 'slide', n=u.slide_index)} · {escape(u.shape_name)} · "
                f"{t(lang, 'unsupported.' + u.kind)}</li>"
            )
        out.append("</ul>")
    warnings = list(dict.fromkeys(result.inspection.warnings))
    if warnings:
        out.append(f"<h2>{t(lang, 'warnings')}</h2><ul>")
        out.extend(f"<li>{escape(w)}</li>" for w in warnings)
        out.append("</ul>")

    for slide in result.inspection.slides:
        out.append(f"<h2>{t(lang, 'slide', n=slide.index)}</h2>")
        if previews and slide.index in previews:
            before, after = previews[slide.index]
            out.append('<div class="previews">')
            for label, png in ((t(lang, "before"), before), (t(lang, "after"), after)):
                if png:
                    data = base64.b64encode(png).decode()
                    out.append(
                        f'<figure><img alt="{escape(label)}" src="data:image/png;base64,{data}">'
                        f"<figcaption>{escape(label)}</figcaption></figure>"
                    )
            out.append("</div>")
        rows = findings_by_slide.get(slide.index, [])
        if not rows:
            out.append(f'<p class="note">{t(lang, "no_findings")}</p>')
            continue
        out.append(
            f"<table><thead><tr><th>{t(lang, 'text')}</th><th>{t(lang, 'status')}</th>"
            f"<th>{t(lang, 'colors')}</th><th>{t(lang, 'contrast')}</th>"
            f"<th>{t(lang, 'background')}</th><th>{t(lang, 'fix')}</th></tr></thead><tbody>"
        )
        for f in rows:
            run = f.run
            bg = run.background
            bg_hex = f"#{f.worst_bg.hex}" if f.worst_bg else None
            sample = (
                f'<span class="sample" style="color:#{f.effective_fg.hex};'
                f'background:{bg_hex or "transparent"}">{escape(run.excerpt)}</span>'
            )
            contrast = "—"
            if f.ratio is not None:
                contrast = f"{f.ratio:.2f}:1"
                if f.apca is not None:
                    contrast += f"<br>Lc {f.apca:.0f}"
            star = "＊" if bg.certainty.value == "rendered_estimate" else ""
            bg_text = (
                f"{t(lang, 'bg.' + bg.kind.value)} · {t(lang, 'cert.' + bg.certainty.value)}{star}"
            )
            fixes: list[str] = []
            for s in by_run.get(run.id, []):
                mark = "✓ " if s.id in applied_set else f"({t(lang, 'not_applied')}) "
                text = mark + _fix_text(lang, s)
                if s.target is not None and s.target.shared and len(s.affected_slides) > 1:
                    slides_text = ", ".join(map(str, s.affected_slides))
                    note = escape(t(lang, "shared_target", slides=slides_text))
                    text += f'<br><span class="note">{note}</span>'
                fixes.append(text)
            if run.id in unfixed and f.status == Status.FAIL:
                fixes.append(escape(t(lang, "reason." + unfixed[run.id].reason)))
            out.append(
                f"<tr><td>{sample}</td><td>{_status(lang, f)}</td>"
                f"<td>{_sw('#' + f.effective_fg.hex)}<br>{_sw(bg_hex)}</td>"
                f'<td class="mono">{contrast}</td><td>{bg_text}</td>'
                f"<td>{'<hr>'.join(fixes) or '—'}</td></tr>"
            )
        out.append("</tbody></table>")
    out.append("</main></body></html>")
    return "".join(out)
