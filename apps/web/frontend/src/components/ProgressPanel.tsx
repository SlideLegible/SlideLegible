import type { Job } from "../api";
import { useI18n } from "../i18n";

export function ProgressPanel({ job }: { job: Job | null }) {
  const { t } = useI18n();
  const value = Math.round((job?.progress ?? 0) * 100);
  const stage = job?.stage ?? "queued";
  return (
    <section className="panel progress-panel" aria-live="polite" aria-busy="true">
      <h2>{t("progress.title")}</h2>
      <p>{t(`stage.${stage}`)}</p>
      <progress max={100} value={value} aria-label={t(`stage.${stage}`)} />
    </section>
  );
}
