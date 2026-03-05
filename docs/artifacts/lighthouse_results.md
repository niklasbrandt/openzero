# Lighthouse Performance Baseline

## Test Methodology

- **Tool**: Lighthouse CLI v12.8.2 (headless Chrome)
- **Target**: Production build served via `npx serve dist/ -l 4173` (`http://127.0.0.1:4173`)
- **Build**: Vite production bundle (single CSS + single JS + 7 woff2 fonts)
- **Backend**: None -- all `/api/*` calls returned 404 (static file server only)
- **Note**: LCP is inflated because API failures cause components to render error states instead of real content. Re-test against production for meaningful LCP data.

## Performance Score: 76 / 100

| Metric                   | Value  | Status |
|:-------------------------|:-------|:-------|
| First Contentful Paint   | 1.2 s  | Pass   |
| Largest Contentful Paint | 6.9 s  | Fail   |
| Speed Index              | 3.0 s  | Pass   |
| Total Blocking Time      | 40 ms  | Pass   |
| Cumulative Layout Shift  | 0      | Pass   |
| Time to Interactive      | 6.9 s  | Warn   |

## LCP Breakdown

- **Element**: `div.error` inside `life-overview` Shadow DOM
  - Selector: `div.card > div#overview-container > div.error`
  - Text: "Unable to load Life Overview. Check backend connection."
  - Dimensions: 478x121px at y=717
- **Phase split**:
  - TTFB: 458 ms (7%)
  - Load Delay: 0 ms (0%)
  - Load Time: 0 ms (0%)
  - Render Delay: 6,481 ms (93%) -- dominant bottleneck
- **Root cause**: LCP target is a text `div` inside a Shadow DOM component that only renders after JS loads, parses, registers the Web Component, runs `connectedCallback()`, makes an API fetch that 404s, and renders the error state. This 6.5s render delay is an artifact of no-backend testing.

## Critical Request Chains

8 chains identified, longest: depth 3, duration 440 ms.

```
/ (HTML) -- 5,001 B
  |-- index-CyFrH-zg.css -- 5,926 B
  |     |-- inter-400.woff2     -- 111,559 B
  |     |-- inter-500.woff2     -- 114,639 B
  |     |-- inter-600.woff2     -- 115,103 B
  |     |-- inter-700.woff2     -- 115,131 B
  |     |-- inter-800.woff2     -- 115,147 B
  |     |-- firacode-400.woff2  -- 103,534 B
  |     |-- firacode-700.woff2  -- 108,082 B
  |-- index-DAd4XybI.js -- 54,595 B
```

Fonts are discovered at chain depth 3 (HTML -> CSS -> fonts). No `<link rel="preload">` hints exist in the HTML head.

## Audit Findings

### Render-blocking resources (Fail -- 150 ms savings)

| Resource                            | Transfer Size | Duration |
|:------------------------------------|:--------------|:---------|
| `/dashboard-assets/index-CyFrH-zg.css` | 5,926 B       | 158 ms   |

The CSS bundle is loaded as a `<link>` injected by Vite at build time. Estimated FCP/LCP savings: 150 ms each.

### Cache policy (Warn -- 9 resources, 0 TTL)

All 9 hashed assets served with `Cache-Control` unset (cache lifetime: 0 ms). These are content-hashed filenames safe for immutable caching.

| Resource                          | Transfer Size |
|:----------------------------------|:--------------|
| inter-800-BUaDDWMS.woff2          | 115,147 B     |
| inter-700-BOs3KVhN.woff2          | 115,131 B     |
| inter-600-BAEEcJ4E.woff2          | 115,103 B     |
| inter-500-CDhBSFyE.woff2          | 114,639 B     |
| inter-400-COLGFB3M.woff2          | 111,559 B     |
| firacode-700-DzhvDiv4.woff2       | 108,082 B     |
| firacode-400-jAL9VymT.woff2       | 103,534 B     |
| index-DAd4XybI.js                 | 54,595 B      |
| index-CyFrH-zg.css                | 5,926 B       |
| **Total wasted bytes**            | **843,716 B** |

### Main-thread work (Pass -- 1,266 ms)

| Category          | Time    | Share |
|:------------------|:--------|:------|
| Style and Layout   | 485 ms  | 38%   |
| Other             | 371 ms  | 29%   |
| Script Evaluation | 259 ms  | 21%   |
| Rendering         | 85 ms   | 7%    |
| Parse HTML and CSS | 64 ms   | 5%    |

### Diagnostics

| Metric              | Value    |
|:---------------------|:---------|
| Total requests       | 52       |
| Scripts              | 1        |
| Stylesheets          | 1        |
| Fonts                | 7        |
| DOM elements         | 719      |
| Tasks > 10 ms        | 7        |
| Tasks > 50 ms        | 0        |
| Total byte weight    | 888 KB   |

### Passing audits

- Minify CSS: Pass
- Minify JavaScript: Pass
- Text compression: Pass
- DOM size: 719 elements (Pass)
- Non-composited animations: Pass
- font-display: swap on all @font-face: Pass
- Avoids enormous network payloads: 867 KiB (Pass)

---

## Improvement Plan

### Phase 1: Font preload (estimated impact: -200-400 ms FCP/LCP)

Add `<link rel="preload" as="font" type="font/woff2" crossorigin>` for Inter 400 and Inter 700 in the HTML `<head>`. These are the two weights used on first paint (body text and bold headings). This moves them from chain depth 3 (HTML -> CSS -> font) to depth 1 (HTML -> font), eliminating one waterfall hop.

A Vite `transformIndexHtml` plugin injects the correct content-hashed font paths at build time, since filenames change on every build (e.g., `inter-400-COLGFB3M.woff2`).

### Phase 2: Cache headers for hashed assets (estimated impact: repeat visit time halved)

Add ASGI middleware in `main.py` that sets `Cache-Control: public, max-age=31536000, immutable` for requests under `/dashboard-assets/`. All files there have content hashes, making them safe for immutable caching. The root HTML keeps `no-cache` so reloads always fetch the latest asset references.

This eliminates the "9 resources found" cache audit warning and saves 844 KB of wasted transfer on repeat visits.

### Phase 3: Production Lighthouse script (estimated impact: accurate LCP measurement)

Add a `perf:audit:prod` npm script targeting the real VPS URL. Current LCP (6.9s) is inflated by API 404 error states. Real production LCP should be significantly lower since components render actual content instead of error messages.

### Phase 4 (deferred): Font subsetting

All 5 Inter weights (400-800) are actively used across 22 declarations. Subsetting to Latin-only could reduce each font file from ~115 KB to ~30-40 KB, saving ~400 KB total. This requires `pyftsubset` or `glyphhanger` tooling and is deferred until Phases 1-3 are measured.

### Phase 5 (deferred): Inline critical CSS

The render-blocking CSS audit flags only 150 ms savings (5.9 KB compressed). This is low priority -- the CSS file is small and benefits from separate caching. Only revisit if the score still falls short after Phases 1-3.
