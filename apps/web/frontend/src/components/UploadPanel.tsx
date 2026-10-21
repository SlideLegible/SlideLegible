import { useId, useRef, useState, type DragEvent } from "react";
import type { Capabilities, PolicyName } from "../api";
import { useI18n } from "../i18n";

const POLICIES: PolicyName[] = ["comfortable", "projector", "strict_aaa"];

interface Props {
  caps: Capabilities | null | undefined;
  onAnalyze: (file: File, policy: PolicyName, soften: boolean) => void;
}

export function UploadPanel({ caps, onAnalyze }: Props) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [policy, setPolicy] = useState<PolicyName>("comfortable");
  const [soften, setSoften] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const softenId = useId();
  const allowSoften = caps?.policies.find((p) => p.name === policy)?.allow_soften ?? policy !== "strict_aaa";

  const choose = (candidate: File | undefined) => {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pptx")) {
      setProblem(t("upload.wrongType"));
      setFile(null);
      return;
    }
    setProblem(null);
    setFile(candidate);
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  };

  return (
    <section className="upload" aria-labelledby="upload-title">
      <div className="upload-intro">
        <h1 id="upload-title">{t("upload.title")}</h1>
        <p>{t("upload.intro")}</p>
        <ContrastDemo />
      </div>

      <form
        className="panel upload-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (file) onAnalyze(file, policy, soften && allowSoften);
        }}
      >
        <button
          type="button"
          className={`dropzone${dragging ? " dragging" : ""}${file ? " has-file" : ""}`}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          {file ? t("upload.selected", { name: file.name }) : t("upload.drop")}
        </button>
        <input
          ref={input}
          type="file"
          accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
          className="visually-hidden"
          tabIndex={-1}
          onChange={(e) => choose(e.target.files?.[0])}
        />
        {problem && (
          <p className="field-error" role="alert">
            {problem}
          </p>
        )}

        <fieldset className="modes">
          <legend>{t("mode.title")}</legend>
          {POLICIES.map((name) => (
            <label key={name} className={`mode${policy === name ? " selected" : ""}`}>
              <input
                type="radio"
                name="policy"
                value={name}
                checked={policy === name}
                onChange={() => setPolicy(name)}
              />
              <span className="mode-name">{t(`mode.${name}`)}</span>
              <span className="mode-desc">{t(`mode.${name}.desc`)}</span>
            </label>
          ))}
        </fieldset>

        <div className="soften">
          <input
            id={softenId}
            type="checkbox"
            checked={soften && allowSoften}
            disabled={!allowSoften}
            onChange={(e) => setSoften(e.target.checked)}
          />
          <label htmlFor={softenId}>
            <span>{t("soften.label")}</span>
            <small>{allowSoften ? t("soften.desc") : t("soften.disabled")}</small>
          </label>
        </div>

        {caps !== undefined && (
          <p className={`renderer-line${caps?.renderer ? "" : " warn"}`} role="status">
            {caps?.renderer
              ? t("renderer.ok", {
                  name: `${caps.renderer.name}${caps.renderer.version ? ` (${caps.renderer.version})` : ""}`,
                })
              : t("renderer.missing")}
          </p>
        )}

        <button type="submit" className="primary" disabled={!file}>
          {t("analyze.button")}
        </button>
        <p className="privacy">{t("upload.privacy")}</p>
      </form>
    </section>
  );
}

/** The product's idea in one picture: the same words before and after correction. */
function ContrastDemo() {
  const { lang } = useI18n();
  const text = lang === "zh-TW" ? "深藍底配深藍字" : "Navy on navy";
  return (
    <div className="demo" aria-hidden="true">
      <span className="demo-chip" style={{ background: "#2E3B4E", color: "#4A5A75" }}>
        {text}
        <small>1.63:1</small>
      </span>
      <span className="demo-chip" style={{ background: "#2E3B4E", color: "#AFC2E1" }}>
        {text}
        <small>6.28:1</small>
      </span>
    </div>
  );
}
