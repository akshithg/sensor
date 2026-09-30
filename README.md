# SENSOR Lite

SENSOR Lite analyzes how API usage changes across source-code revisions. The included example compares `gnttab_dma_alloc_pages()` before and after a Linux kernel integer-overflow fix, builds API-usage and change graphs from Clang's JSON AST, and reports the validation guard missing from the earlier revision.

This repository reconstructs one part of an internship prototype developed in the context of DARPA's [SocialCyber program](https://www.darpa.mil/research/programs/hybrid-ai-to-protect-integrity-of-open-source-code). It is not the original SRI International system or its evaluation. The demo uses public Linux kernel source and contains no original internship code or data.

## What the demo shows

- The public kernel revision that [introduced DMA-capable grant buffers](https://github.com/torvalds/linux/commit/9bdc7304f536f3f77f0a69e7c3a8f5afda561a68).
- The change to [`kvcalloc()`](https://github.com/torvalds/linux/commit/b3f7931f5c61ba39e81a5c958bf5d65ebb1838af) cited as the enabling condition for larger allocations.
- The upstream [`e9ea0b30ada0`](https://github.com/torvalds/linux/commit/e9ea0b30ada008f4e65933f449db6894832cb242) integer-overflow fix.
- API-usage graphs derived from Clang's JSON AST.
- A before/after change graph with added and removed nodes.
- Two target-selection views: stable revisions and a fix-derived pattern.
- A small custom-source analyzer for trying variants in the browser.

## Run it

Requirements: [uv](https://docs.astral.sh/uv/) and `clang` on `PATH`.

```bash
uv sync
uv run sensor-lite
```

Open <http://127.0.0.1:8000>. Use a different port with `uv run sensor-lite --port 8080`.

## GitHub Pages

The `docs/` directory contains a static version for GitHub Pages. It supports revision, graph, and
source views using generated analysis data. Editing and reanalyzing source requires the local
server.

Regenerate the static files after changing the analyzer, fixture, or web interface:

```bash
uv run sensor-lite-build-pages
```

In the repository's Pages settings, choose **Deploy from a branch**, select `main`, and use the
`/docs` folder.

## Validate it

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run ty check
node --check src/sensor_lite/web/app.js
node --check docs/app.js
```

## Scope

The original concept compiled large projects to LLVM IR and mined graph patterns over real revision histories. This demo narrows the problem: Clang parses one isolated kernel function with local type stubs, graph edges approximate source-order control flow and variable use, and pattern mining combines ordered API-call pairs with a fix-derived guard.

The code fixtures under `src/sensor_lite/fixtures/linux/` retain their upstream GPL-2.0-only designation. That directory includes commit-level provenance and the complete upstream GPL-2.0 license text. No license is asserted for the separately authored demo code in this repository.
