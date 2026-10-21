import { useMemo, useState } from "react";
import {
  artifactUrl,
  previewUrl,
  reportUrl,
  type Analysis,
  type Correction,
  type Finding,
  type Job,
  type Suggestion,
} from "../api";
import { useI18n, type Translate } from "../i18n";

interface Props {
  analysis: Analysis;
  onCorrect: (analysis: Analysis, ids: string[], onJob: (job: Job) => void) => Promise<Correction>;
  onReset: () => void;
  onError: (error: unknown) => void;
}

const fmt = (value: number | null | undefined) => (value == null ? "—" : value.toFixed(2));

/** Select a suggestion with its dependencies, or clear it together with its dependents. */
function toggleWithDependencies(
  selected: Set<string>,
  id: string,
  on: boolean,
  all: Suggestion[],
): Set<string> {
  const next = new Set(selected);
  const byId = new Map(all.map((s) => [s.id, s]));
  if (on) {
    const stack = [id];
    while (stack.length) {
      const current = stack.pop()!;
      if (next.has(current)) continue;
      next.add(current);
      stack.push(...(byId.get(current)?.depends_on ?? []));
    }
  } else {
    const stack = [id];
    while (stack.length) {
      const current = stack.pop()!;
      if (!next.has(current) && current !== id) continue;
      next.delete(current);
      for (const s of all) if (s.depends_on.includes(current) && next.has(s.id)) stack.push(s.id);
    }
  }
  return next;
}

export function Review({ analysis, onCorrect, onReset, onError }: Props) {
  const { t, lang } = useI18n();
  const report = analysis.report;
  const suggestions = report.plan.suggestions;
  const [selected, setSelected] = useState<Set<string>>(() => new Set(suggestions.map((s) => s.id)));
  const [current, setCurrent] = useState<Correction | null>(analysis.proposed);
  const [updating, setUpdating] = useState<Job | null>(null);
  const [onlyIssues, setOnlyIssues] = useState(false);

  const byRun = useMemo(() => {
    const map = new Map<string, Suggestion[]>();
    for (const s of suggestions)
      for (const run of s.runs) map.set(run, [...(map.get(run) ?? []), s]);
    return map;
  }, [suggestions]);
  const unfixed = useMemo(
    () => new Map(report.plan.unfixed.map((u) => [u.run, u.reason])),
    [report.plan.unfixed],
  );
  const findingsBySlide = useMemo(() => {
    const map = new Map<number, Finding[]>();
    for (const f of report.findings) map.set(f.run.slide, [...(map.get(f.run.slide) ?? []), f]);
    return map;
  }, [report.findings]);

  const applied = new Set(current?.applied ?? []);
  const stale =
    current !== null &&
    (applied.size !== selected.size || [...selected].some((id) => !applied.has(id)));
  const summary = report.summary;
  const slides = Array.from({ length: report.source.slides }, (_, i) => i + 1).filter(
    (n) => !onlyIssues || (findingsBySlide.get(n) ?? []).some((f) => f.status === "fail"),
  );

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => toggleWithDependencies(prev, id, on, suggestions));

  const update = async () => {
    setUpdating({ id: "", kind: "correction", status: "queued", stage: "apply", progress: 0, error: null, result: null });
    try {
      const ordered = suggestions.filter((s) => selected.has(s.id)).map((s) => s.id);
      const correction = await onCorrect(analysis, ordered, setUpdating);
      setCurrent(correction);
    } catch (error) {
      onError(error);
    } finally {
      setUpdating(null);
    }
  };

  return (
    <div className="review">
      <section className="review-head" aria-labelledby="review-title">
        <div>
          <h1 id="review-title">{report.source.filename}</h1>
          <p className="muted">
            {t(`mode.${report.policy.name}`)}
            {report.policy.soften_extremes ? `${t("sep")}${t("soften.label")}` : ""}
          </p>
        </div>
        <button type="button" className="secondary" onClick={onReset}>
          {t("review.newFile")}
        </button>
      </section>

      <dl className="stats">
        <Stat label={t("summary.slides")} value={summary.slides} />
        <Stat label={t("summary.issues")} value={summary.fail} tone={summary.fail ? "bad" : "ok"} />
        <Stat label={t("summary.suggestions")} value={summary.suggestions} />
        <Stat label={t("summary.unfixed")} value={summary.unfixed} tone={summary.unfixed ? "warn" : undefined} />
        <Stat label={t("summary.unsupported")} value={report.unsupported.length} />
      </dl>
      {summary.fail === 0 && <p className="good-news">{t("summary.noIssues")}</p>}

      {(report.warnings.length > 0 || report.render_error) && (
        <details className="notes">
          <summary>{t("review.warnings")}</summary>
          <ul>
            {report.render_error && <li>{report.render_error}</li>}
            {report.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}
      {report.unsupported.length > 0 && (
        <details className="notes">
          <summary>{t("review.unsupported")}</summary>
          <ul>
            {report.unsupported.map((u, i) => (
              <li key={i}>
                {t("unsupported.item", {
                  slide: t("slide.title", { n: u.slide }),
                  shape: u.shape,
                  kind: t(`unsupported.${u.kind}`),
                })}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="toolbar" role="region" aria-label={t("review.update")}>
        <div className="toolbar-row">
          <label className="check">
            <input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} />
            {t("review.filterIssues")}
          </label>
          {suggestions.length > 0 && (
            <>
              <button type="button" className="link-button" onClick={() => setSelected(new Set(suggestions.map((s) => s.id)))}>
                {t("review.selectAll")}
              </button>
              <button type="button" className="link-button" onClick={() => setSelected(new Set())}>
                {t("review.selectNone")}
              </button>
            </>
          )}
        </div>
        <div className="toolbar-row actions">
          {suggestions.length > 0 && (
            <button type="button" className="primary" onClick={update} disabled={updating !== null || !stale}>
              {updating ? `${t("review.updating")} ${t(`stage.${updating.stage}`)}` : t("review.update")}
            </button>
          )}
          {current && (
            <>
              <a className="button secondary" href={artifactUrl(current.pptx_artifact)} download>
                {t("review.download")}
              </a>
              <a className="button secondary" href={reportUrl(current.id, lang)}>
                {t("review.report")}
              </a>
            </>
          )}
        </div>
        {stale && <p className="stale" role="status">{t("review.stale")}</p>}
      </div>

      {suggestions.length > 0 && (
        <details className="all-changes">
          <summary>{t("review.allChanges", { n: suggestions.length })}</summary>
          <p className="muted">{t("review.allChangesHint")}</p>
          <ul className="suggestion-list">
            {suggestions.map((s) => (
              <li key={s.id}>
                <SuggestionItem s={s} checked={selected.has(s.id)} onToggle={toggle} t={t} showSlides />
              </li>
            ))}
          </ul>
        </details>
      )}

      {slides.map((n) => {
        const findings = findingsBySlide.get(n) ?? [];
        const issues = findings.filter((f) => f.status === "fail").length;
        const before = analysis.original_previews[String(n)];
        const after = current?.previews[String(n)];
        return (
          <section key={n} className="slide" aria-labelledby={`slide-${n}`}>
            <header className="slide-head">
              <h2 id={`slide-${n}`}>{t("slide.title", { n })}</h2>
              {issues > 0 && <span className="pill bad">{t("slide.issueCount", { n: issues })}</span>}
            </header>
            <div className="previews">
              <Preview src={before ? previewUrl(before) : null} label={t("slide.original")} t={t} />
              <Preview src={after ? previewUrl(after) : null} label={t("slide.corrected")} t={t} />
            </div>
            {findings.length === 0 ? (
              <p className="muted">{t("slide.noText")}</p>
            ) : (
              <ul className="findings">
                {findings.map((f) => (
                  <FindingRow
                    key={f.run.id}
                    f={f}
                    suggestions={byRun.get(f.run.id) ?? []}
                    unfixed={unfixed.get(f.run.id)}
                    selected={selected}
                    onToggle={toggle}
                    t={t}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "bad" | "ok" | "warn" }) {
  return (
    <div className={`stat${tone ? ` ${tone}` : ""}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Preview({ src, label, t }: { src: string | null; label: string; t: Translate }) {
  return (
    <figure className="preview">
      {src ? <img src={src} alt={label} loading="lazy" /> : <div className="preview-empty">{t("slide.noPreview")}</div>}
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function Specimen({ text, fg, bg, ratio }: { text: string; fg: string; bg: string | null; ratio: string }) {
  return (
    <span className="specimen" style={{ color: fg, background: bg ?? "transparent" }}>
      <span className="specimen-text">{text}</span>
      <span className="specimen-ratio">{ratio}</span>
    </span>
  );
}

function FindingRow({
  f,
  suggestions,
  unfixed,
  selected,
  onToggle,
  t,
}: {
  f: Finding;
  suggestions: Suggestion[];
  unfixed: string | undefined;
  selected: Set<string>;
  onToggle: (id: string, on: boolean) => void;
  t: Translate;
}) {
  const textFix = suggestions.find((s) => s.kind === "text_color" || s.kind === "soften_text");
  const bgFix = suggestions.find((s) => s.target && (s.kind === "background_color" || s.kind === "saturation" || s.kind === "soften_background"));
  const afterFg = textFix && selected.has(textFix.id) ? textFix.proposed : f.effective_color;
  const afterBg = bgFix && selected.has(bgFix.id) ? bgFix.proposed : f.worst_background;
  const textOn = textFix !== undefined && selected.has(textFix.id);
  const bgOn = bgFix !== undefined && selected.has(bgFix.id);
  const afterRatio = textOn ? textFix.after.ratio : bgOn ? bgFix.after.ratio : f.ratio;
  const statusTone = f.status === "fail" ? "bad" : f.status === "pass" ? "ok" : "warn";
  const reason = f.reason ? t(`reason.${f.reason}`) : null;
  const bg = f.run.background;
  return (
    <li className={`finding ${f.status}`}>
      <div className="finding-main">
        <Specimen text={f.run.excerpt} fg={f.effective_color} bg={f.worst_background} ratio={`${fmt(f.ratio)}:1`} />
        {(textFix || bgFix) && (
          <>
            <span className="arrow" aria-hidden="true">
              ⟶
            </span>
            <Specimen text={f.run.excerpt} fg={afterFg} bg={afterBg} ratio={`${fmt(afterRatio)}:1`} />
          </>
        )}
      </div>
      <div className="finding-meta">
        <span className={`pill ${statusTone}`}>
          {t(`status.${f.status}`)}
          {reason && f.status !== "fail" ? `${t("colon")}${reason}` : ""}
        </span>
        <span>
          {t("finding.contrast", { ratio: fmt(f.ratio) })}
          {f.apca_lc != null ? `${t("sep")}Lc ${Math.round(f.apca_lc)}` : ""}
        </span>
        <span className="muted">
          {t("finding.need", { ratio: f.requirement.min_ratio })}
          {f.requirement.min_apca_lc != null ? `${t("sep")}|Lc| ≥ ${f.requirement.min_apca_lc}` : ""}
          {f.large_text ? t("paren", { text: t("finding.large") }) : ""}
        </span>
        <span className="muted">
          {t("finding.bg", { kind: t(`bg.${bg.kind}`), cert: t(`cert.${bg.certainty}`) })}
        </span>
      </div>
      {suggestions.length > 0 && (
        <ul className="suggestion-list">
          {suggestions.map((s) => (
            <li key={s.id}>
              <SuggestionItem s={s} checked={selected.has(s.id)} onToggle={onToggle} t={t} />
            </li>
          ))}
        </ul>
      )}
      {unfixed && f.status === "fail" && <p className="unfixed">{t(`reason.${unfixed}`)}</p>}
    </li>
  );
}

function Swatch({ color }: { color: string | null }) {
  if (!color) return null;
  return (
    <span className="swatch-wrap">
      <span className="swatch" style={{ background: color }} aria-hidden="true" />
      <code>{color}</code>
    </span>
  );
}

function SuggestionItem({
  s,
  checked,
  onToggle,
  t,
  showSlides = false,
}: {
  s: Suggestion;
  checked: boolean;
  onToggle: (id: string, on: boolean) => void;
  t: Translate;
  showSlides?: boolean;
}) {
  const label = s.strategy === "flip" ? t("strategy.flip") : t(`kind.${s.kind}`);
  return (
    <label className={`suggestion${checked ? " on" : ""}`}>
      <input type="checkbox" checked={checked} onChange={(e) => onToggle(s.id, e.target.checked)} />
      <span className="suggestion-body">
        <span className="suggestion-title">
          <span>{label}</span>
          {s.major && <span className="pill warn">{t("badge.major")}</span>}
          {s.estimate && <span className="pill">{t("badge.estimate")}</span>}
          {showSlides && <span className="muted">{s.slides.map((n) => t("slide.title", { n })).join(t("listSep"))}</span>}
        </span>
        <span className="suggestion-colors">
          {s.kind === "scrim" ? (
            <>
              <Swatch color={s.proposed} />
              {t("suggestion.scrim", { alpha: Math.round((s.alpha ?? 0) * 100) })}
            </>
          ) : (
            <>
              <Swatch color={s.original} />
              <span aria-hidden="true">→</span>
              <Swatch color={s.proposed} />
            </>
          )}
          {s.before.ratio != null && s.after.ratio != null && (
            <span className="muted">{t("suggestion.ratio", { before: fmt(s.before.ratio), after: fmt(s.after.ratio) })}</span>
          )}
        </span>
        {s.depends_on.length > 0 && <small className="muted">{t("suggestion.depends", { ids: s.depends_on.join(", ") })}</small>}
        {s.target?.shared && s.affected_slides.length > 1 && (
          <small className="muted">{t("suggestion.shared", { slides: s.affected_slides.join(", ") })}</small>
        )}
      </span>
    </label>
  );
}
