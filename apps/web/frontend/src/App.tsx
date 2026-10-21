import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  waitForJob,
  type Analysis,
  type Capabilities,
  type Correction,
  type Job,
  type PolicyName,
} from "./api";
import { I18nContext, makeTranslator, type Lang } from "./i18n";
import { UploadPanel } from "./components/UploadPanel";
import { ProgressPanel } from "./components/ProgressPanel";
import { Review } from "./components/Review";

type Theme = "system" | "light" | "dark";

type Phase =
  | { name: "idle" }
  | { name: "working"; job: Job | null }
  | { name: "review"; analysis: Analysis }
  | { name: "error"; message: string };

function readSetting<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function saveSetting(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage may be unavailable (private mode); settings then last for this visit only
  }
}

export default function App() {
  const [lang, setLang] = useState<Lang>(() =>
    readSetting("slidelegible.lang", ["zh-TW", "en"] as const, "zh-TW"),
  );
  const [theme, setTheme] = useState<Theme>(() =>
    readSetting("slidelegible.theme", ["system", "light", "dark"] as const, "system"),
  );
  const [caps, setCaps] = useState<Capabilities | null | undefined>(undefined);
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const t = useMemo(() => makeTranslator(lang), [lang]);

  useEffect(() => {
    document.documentElement.lang = lang;
    saveSetting("slidelegible.lang", lang);
  }, [lang]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    saveSetting("slidelegible.theme", theme);
  }, [theme]);

  useEffect(() => {
    api.capabilities().then(setCaps, () => setCaps(null));
  }, []);

  const fail = (error: unknown) => {
    const message =
      error instanceof ApiError ? `${error.message} (${error.code})` : String(error);
    setPhase({ name: "error", message });
  };

  const analyze = useCallback(async (file: File, policy: PolicyName, soften: boolean) => {
    setPhase({ name: "working", job: null });
    try {
      const upload = await api.upload(file);
      const { job_id } = await api.analyze(upload.id, policy, soften);
      const job = await waitForJob(job_id, (j) => setPhase({ name: "working", job: j }));
      if (job.status === "failed" || !job.result?.analysis_id) {
        throw new ApiError(job.error?.code ?? "failed", job.error?.message ?? "Analysis failed");
      }
      const analysis = await api.analysis(job.result.analysis_id);
      setPhase({ name: "review", analysis });
    } catch (error) {
      fail(error);
    }
  }, []);

  const correct = useCallback(
    async (analysis: Analysis, ids: string[], onJob: (job: Job) => void): Promise<Correction> => {
      const { job_id } = await api.correct(analysis.id, ids);
      const job = await waitForJob(job_id, onJob);
      if (job.status === "failed" || !job.result?.correction) {
        throw new ApiError(job.error?.code ?? "failed", job.error?.message ?? "Correction failed");
      }
      return job.result.correction;
    },
    [],
  );

  return (
    <I18nContext.Provider value={{ lang, t }}>
      <div className="page">
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              <span>A</span>
              <span>a</span>
            </span>
            <span className="brand-name">SlideLegible</span>
            <span className="brand-tag">{t("tagline")}</span>
          </div>
          <div className="topbar-actions">
            <label className="select-label">
              <span className="visually-hidden">{t("theme.label")}</span>
              <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
                <option value="system">{t("theme.system")}</option>
                <option value="light">{t("theme.light")}</option>
                <option value="dark">{t("theme.dark")}</option>
              </select>
            </label>
            <button
              type="button"
              className="link-button"
              lang={lang === "zh-TW" ? "en" : "zh-TW"}
              onClick={() => setLang(lang === "zh-TW" ? "en" : "zh-TW")}
            >
              {t("lang.switch")}
            </button>
          </div>
        </header>

        <main className="content">
          {phase.name === "idle" && <UploadPanel caps={caps} onAnalyze={analyze} />}
          {phase.name === "working" && <ProgressPanel job={phase.job} />}
          {phase.name === "error" && (
            <section className="panel error-panel" role="alert">
              <h2>{t("error.title")}</h2>
              <p>{phase.message}</p>
              <button type="button" className="primary" onClick={() => setPhase({ name: "idle" })}>
                {t("error.retry")}
              </button>
            </section>
          )}
          {phase.name === "review" && (
            <Review
              analysis={phase.analysis}
              onCorrect={correct}
              onReset={() => setPhase({ name: "idle" })}
              onError={fail}
            />
          )}
        </main>

        <footer className="footer">
          {t("footer", {
            version: caps?.version ?? "",
            apca: caps?.policies[0]?.apca_version ?? "",
          })}
        </footer>
      </div>
    </I18nContext.Provider>
  );
}
