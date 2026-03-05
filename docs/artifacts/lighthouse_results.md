# Lighthouse Audit Results

## Test Methodology

- **Tool**: Lighthouse CLI v12.8.2 (headless Chrome)
- **Target**: Production build served via `npx serve dist/ -l 4173` (`http://127.0.0.1:4173`)
- **Build**: Vite production bundle (single CSS + single JS + 14 woff2 font subsets)
- **Backend**: None -- all `/api/*` calls returned 404 (static file server only)
- **Note**: LCP is inflated because API failures cause components to render error states instead of real content. Re-test against production for meaningful LCP data.

---

## Run 4 (full audit -- a11y, SEO, best practices): Perf 92 / A11y 100 / SEO 100 / BP 96

Changes applied: fixed ARIA `role="list"` violations (dynamic role management on CalendarAgenda + BriefingHistory -- role only set when items present), fixed WCAG 2.5.3 label-content-name-mismatch (cmd-chip aria-labels now include visible text, tooltip spans marked `aria-hidden="true"`), fixed color contrast on `.cmd-chip` (CSS specificity fix: `.empty-state > span` instead of `.empty-state span`) and `.svc-detail` (changed from `--text-muted` 0.4 to `--text-secondary` 0.7 opacity), added `<meta name="description">` for SEO.

| Category            | Run 4  | Status |
|:--------------------|:-------|:-------|
| **Performance**     | **92** | Pass   |
| **Accessibility**   | **100**| Pass   |
| **Best Practices**  | **96** | Pass   |
| **SEO**             | **100**| Pass   |

| Metric                   | Run 1  | Run 2  | Run 3  | Run 4  | Delta (1->4) | Status |
|:-------------------------|:-------|:-------|:-------|:-------|:-------------|:-------|
| **Performance Score**    | **76** | **80** | **92** | **92** | **+16**      |        |
| First Contentful Paint   | 1.2 s  | 1.2 s  | 1.2 s  | 1.2 s  | 0            | Pass   |
| Largest Contentful Paint | 6.9 s  | 5.3 s  | 3.4 s  | 3.4 s  | -3.5 s       | Warn   |
| Speed Index              | 3.0 s  | 1.3 s  | 1.4 s  | 1.4 s  | -1.6 s       | Pass   |
| Total Blocking Time      | 40 ms  | 50 ms  | 20 ms  | 20 ms  | -20 ms       | Pass   |
| Cumulative Layout Shift  | 0      | 0      | 0      | 0      | 0            | Pass   |
| Time to Interactive      | 6.9 s  | 5.3 s  | 3.4 s  | 3.4 s  | -3.5 s       | Pass   |

### Remaining non-scoring audit: Best Practices 96

- Console errors from API 404s (no backend in test environment). Not addressable locally.

---

## Run 3 (unicode-range font splitting): 92 / 100 (+12)

Changes applied: split each font into Latin core (~29-31 KB) + extended (~47-92 KB) subsets with `unicode-range` in CSS. Browser only downloads extended subsets when non-Latin characters appear on the page. All glyphs (Cyrillic, Greek, Vietnamese, Latin Extended) preserved. Vite preload updated to target Latin subsets only.

| Metric                   | Run 1  | Run 2  | Run 3  | Delta (1->3) | Status |
|:-------------------------|:-------|:-------|:-------|:-------------|:-------|
| **Performance Score**    | **76** | **80** | **92** | **+16**      |        |
| First Contentful Paint   | 1.2 s  | 1.2 s  | 1.2 s  | 0            | Pass   |
| Largest Contentful Paint | 6.9 s  | 5.3 s  | 3.4 s  | -3.5 s       | Warn   |
| Speed Index              | 3.0 s  | 1.3 s  | 1.4 s  | -1.6 s       | Pass   |
| Total Blocking Time      | 40 ms  | 50 ms  | 20 ms  | -20 ms       | Pass   |
| Cumulative Layout Shift  | 0      | 0      | 0      | 0            | Pass   |
| Time to Interactive      | 6.9 s  | 5.3 s  | 3.4 s  | -3.5 s       | Pass   |

### Key changes (Run 3)

- Total byte weight: 888 KB -> 281 KB (-68%)
- Fonts loaded on Latin-only page: 6 (was 7) -- browser skips extended files when not needed
- Total requests: 51 (was 52)
- LCP still dominated by render delay (no backend), but almost halved from Run 2
- Cache: 8 resources flagged (local test, no cache middleware)

---

## Run 2 (post-optimization): 80 / 100 (+4)

Changes applied: font preload plugin (Inter 400 + 700), CacheHeaderMiddleware in main.py (immutable cache for `/dashboard-assets/`), `perf:audit:prod` npm script.

| Metric                   | Baseline | Post-opt | Delta   | Status |
|:-------------------------|:---------|:---------|:--------|:-------|
| **Performance Score**    | **76**   | **80**   | **+4**  |        |
| First Contentful Paint   | 1.2 s    | 1.2 s    | 0       | Pass   |
| Largest Contentful Paint | 6.9 s    | 5.3 s    | -1.6 s  | Fail   |
| Speed Index              | 3.0 s    | 1.3 s    | -1.7 s  | Pass   |
| Total Blocking Time      | 40 ms    | 50 ms    | +10 ms  | Pass   |
| Cumulative Layout Shift  | 0        | 0        | 0       | Pass   |
| Time to Interactive      | 6.9 s    | 5.3 s    | -1.6 s  | Warn   |

### LCP element (Run 2)

- **Element**: `span` inside `chat-prompt` Shadow DOM (empty-state text)
  - Selector: `div#messages > div.empty-state > span`
  - Text: "Ask anything -- manage tasks, query memories, or get briefed."
  - Dimensions: 343x46px at y=321
- **Phase split**:
  - TTFB: 461 ms (9%)
  - Load Delay: 0 ms (0%)
  - Load Time: 0 ms (0%)
  - Render Delay: 4,855 ms (91%) -- still dominant, but 1.6s faster than baseline

### Critical chains (Run 2)

Reduced from 8 chains to 1 chain. Longest: depth 3, duration 141 ms (was 440 ms).

The font preload moved Inter 400 + 700 out of the CSS-dependent chain. The remaining chain goes through a non-preloaded font (Inter 800) discovered via CSS.

### Cache (Run 2, local test -- no middleware)

7 resources flagged (was 9). The `npx serve` static server does not set cache headers, so this test does not reflect the `CacheHeaderMiddleware` deployed on the VPS. The Fira Code fonts dropped out of the flagged list.

| Resource                    | TTL  | Transfer Size |
|:----------------------------|:-----|:--------------|
| inter-800-BUaDDWMS.woff2    | 0 ms | 115,147 B     |
| inter-700-BOs3KVhN.woff2    | 0 ms | 115,131 B     |
| inter-600-BAEEcJ4E.woff2    | 0 ms | 115,103 B     |
| inter-500-CDhBSFyE.woff2    | 0 ms | 114,639 B     |
| inter-400-COLGFB3M.woff2    | 0 ms | 111,559 B     |
| index-DAd4XybI.js            | 0 ms | 54,595 B      |
| index-CyFrH-zg.css          | 0 ms | 5,926 B       |
| **Total wasted bytes**      |      | **632,100 B** |

### Main-thread work (Run 2 -- 1.4 s)

| Category           | Time    |
|:-------------------|:--------|
| Other              | 471 ms  |
| Style and Layout   | 432 ms  |
| Script Evaluation  | 335 ms  |
| Parse HTML and CSS | 72 ms   |
| Rendering          | 65 ms   |

---

## Run 1 (baseline): 76 / 100

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

### Phase 1: Font preload -- DONE (score 76 -> 80)

Added Vite `transformIndexHtml` plugin (`fontPreloadPlugin`) that injects `<link rel="preload" as="font" type="font/woff2" crossorigin>` for Inter 400 and Inter 700 at build time with correct content-hashed paths.

**Result**: LCP dropped from 6.9s to 5.3s (-1.6s). Speed Index dropped from 3.0s to 1.3s (-1.7s). Critical chains reduced from 8 to 1, duration 440ms to 141ms.

### Phase 2: Cache headers -- DONE (deployed, not reflected in local audit)

Added `CacheHeaderMiddleware` in `main.py` that sets `Cache-Control: public, max-age=31536000, immutable` for `/dashboard-assets/*` requests. Root HTML (`/home`, `/`) gets `no-cache`. Effect visible only against production VPS, not local `npx serve`.

### Phase 3: Production Lighthouse script -- DONE

Added `perf:audit:prod` npm script targeting `http://open.zero/home` for real-world LCP measurement with backend APIs responding.

### Phase 4: Unicode-range font splitting -- DONE (score 80 -> 92)

Split each font into Latin core (~29-31 KB) + extended (~47-92 KB) subsets using `pyftsubset` (fonttools). All glyphs preserved (Cyrillic, Greek, Vietnamese, Latin Extended). Added `unicode-range` declarations to `fonts.css` so the browser only downloads extended subsets when non-Latin characters appear on the page. Updated Vite preload plugin to target `inter-400-latin` and `inter-700-latin` instead of the full files.

**Result**: Total byte weight dropped from 888 KB to 281 KB (-68%). LCP dropped from 5.3s to 3.4s (-1.9s). Score jumped from 80 to 92. TTI dropped from 5.3s to 3.4s.

### Phase 5: Accessibility + SEO audit -- DONE (A11y 95 -> 100, SEO 90 -> 100)

Full-category Lighthouse audit revealed WCAG violations and missing SEO metadata:

- **ARIA required children**: `role="list"` on `#event-list` (CalendarAgenda) and `#briefing-list` (BriefingHistory) without `role="listitem"` children in error/loading states. Fix: removed static `role="list"` from template HTML, set it dynamically via JS only when items are present.
- **Label-content-name-mismatch (WCAG 2.5.3)**: 7 cmd-chip buttons had `aria-label` not containing visible text. Fix: prepended visible text (e.g. "/day --") to aria-labels. 4 bench buttons had tooltip text (`<span class="glass-tooltip">`) counted as visible content, making `aria-label` a subset mismatch. Fix: added `aria-hidden="true"` to all injected tooltip spans across SystemBenchmark, HardwareMonitor, and SoftwareStatus.
- **Color contrast (WCAG 1.4.3)**: `.cmd-chip` computed as 3.77:1 instead of 4.5:1 because `.empty-state span` (specificity 0-1-1) overrode `.cmd-chip` color (0-1-0). Fix: changed to `.empty-state > span` (direct child only). `.svc-detail` at 0.4 opacity white (3.77:1). Fix: changed to `--text-secondary` (0.7 opacity, ~6.5:1).
- **Missing meta description**: Added `<meta name="description">` to `index.html`.

**Result**: Accessibility 95 -> 100, SEO 90 -> 100. Best Practices holds at 96 (console errors from no-backend testing only).

### Phase 6 (deferred): Inline critical CSS

The render-blocking CSS audit flags only 150 ms savings (5.8 KB compressed). This is low priority -- the CSS file is small and benefits from separate caching. Score is already at 92/100 without this. The remaining LCP (3.4s) is entirely render delay from JS-driven Shadow DOM components with no backend -- not addressable via CSS inlining.
