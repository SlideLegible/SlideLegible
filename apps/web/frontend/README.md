# SlideLegible Web Frontend

React + TypeScript app built with Vite. npm is the selected package manager; `package-lock.json` records the resolved dependency tree.

Requires Node.js 20.19+ or 22.12+. From this directory:

```sh
npm ci
npm run dev    # dev server; /api is proxied to http://127.0.0.1:8000
npm run build  # type-check and build to dist/, which the FastAPI app serves at /
```

The UI supports Traditional Chinese and English, and light/dark themes (following the system by default). Upload, mode selection, review with side-by-side previews, per-change selection, and downloads of the corrected `.pptx` and HTML report are implemented. Domain rules live in the Python core; the frontend only displays them.
