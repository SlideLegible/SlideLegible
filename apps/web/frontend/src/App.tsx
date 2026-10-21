export default function App() {
  return (
    <main className="page-shell">
      <header className="brand-row">
        <span className="brand-mark" aria-hidden="true">
          S
        </span>
        <span>SlideLegible</span>
      </header>

      <section className="welcome-panel" aria-labelledby="welcome-title">
        <p className="eyebrow">PowerPoint contrast review</p>
        <h1 id="welcome-title">Make every slide easier to read.</h1>
        <p className="intro-copy">
          SlideLegible will help you find contrast issues and review suggested fixes for your
          presentation.
        </p>
        <div className="setup-note" role="status">
          The review workspace is being built. Upload and analysis are not available yet.
        </div>
      </section>

      <footer>Clearer slides start with readable text.</footer>
    </main>
  );
}
