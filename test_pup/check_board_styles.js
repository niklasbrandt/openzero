/**
 * Render a static mock of Planka's board/card HTML using its actual CSS
 * module classes, injected via the live Planka CSS bundle + index.ejs overrides.
 * This lets us visually verify dark mode without needing socket.io to work.
 */
const puppeteer = require('puppeteer');
const https = require('https');
const http = require('http');

function get(url) {
	return new Promise((resolve, reject) => {
		const mod = url.startsWith('https') ? https : http;
		mod.get(url, res => {
			let d = '';
			res.on('data', c => d += c);
			res.on('end', () => resolve(d));
		}).on('error', reject);
	});
}

(async () => {
	// Fetch Planka's CSS bundle so we get unmodified CSS module styles
	const css = await get('http://100.116.160.123/assets/index-CmagzRgw.css');

	// Fetch the override style block from the live index.ejs
	const ejs = await get('http://100.116.160.123/login');
	const overrideMatch = ejs.match(/<style>\s*\/\* openZero:([\s\S]*?)<\/style>/);
	const overrideCss = overrideMatch ? overrideMatch[0] : '';
	console.log('Override CSS found:', overrideMatch ? 'yes' : 'NO — check extraction');

	const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>${css}</style>
${overrideCss}
</head>
<body id="app" class="g-root g-root_theme_dark">
<div style="padding:20px;background:var(--g-color-base-background,rgb(34,29,34));min-height:100vh">

  <!-- Board header area -->
  <div class="_name_i28lr_66" style="font-size:24px;font-weight:700;margin-bottom:16px">Operator Board</div>

  <!-- Kanban columns row -->
  <div style="display:flex;gap:12px;align-items:flex-start">

    <!-- Column 1 -->
    <div class="_wrapper_4d1a2_46">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px 4px">
        <span class="_name_1v3zm_24">To Do</span>
        <span class="_count_1uxqm_5">3</span>
      </div>

      <!-- Card 1 -->
      <div class="_wrapper_36a26_43" style="margin-bottom:8px;cursor:pointer">
        <div style="padding:6px 8px">
          <div class="_name_q007q_16">Review product requirements</div>
          <div style="display:flex;gap:4px;margin-top:4px">
            <span class="_wrapper_1y12g_17" style="font-size:12px;padding:2px 6px">3/5</span>
            <span class="_wrapper_ylxnu_13" style="font-size:12px;padding:2px 6px">Apr 12</span>
          </div>
        </div>
      </div>

      <!-- Card 2 -->
      <div class="_wrapper_36a26_43" style="margin-bottom:8px;cursor:pointer">
        <div style="padding:6px 8px">
          <div class="_name_q007q_16">Deploy staging environment</div>
        </div>
      </div>

      <!-- Add card button -->
      <div class="_button_1v3zm_5" style="cursor:pointer">+ Add card</div>
    </div>

    <!-- Column 2 -->
    <div class="_wrapper_4d1a2_46">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px 4px">
        <span class="_name_1v3zm_24">In Progress</span>
        <span class="_count_1uxqm_5">1</span>
      </div>

      <!-- Card with author badge -->
      <div class="_wrapper_36a26_43" style="margin-bottom:8px;cursor:pointer">
        <div style="padding:6px 8px">
          <div class="_name_q007q_16">Fix dark mode in Planka</div>
          <div style="display:flex;gap:6px;margin-top:6px;align-items:center">
            <span class="_author_8hd9p_5">@admin</span>
            <span class="_wrapper_12wku_14" style="font-size:12px;padding:2px 6px">high priority</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Column 3 with card detail sidebar mock -->
    <div class="_wrapper_4d1a2_46">
      <div style="padding:8px 4px 4px">
        <span class="_name_1v3zm_24">Done</span>
      </div>
    </div>

    <!-- Card Detail / Modal sidebar -->
    <div class="_wrapper_1napt_5" style="width:340px;border-radius:4px;padding:16px">
      <div class="_name_fiqad_57">Fix dark mode in Planka</div>
      <div style="margin:12px 0 4px;font-weight:600;font-size:13px;color:var(--g-color-text-secondary)">Description</div>
      <textarea class="_field_1ba2a_9" rows="4"
        style="width:100%;box-sizing:border-box">Comprehensive CSS overrides for all hardcoded light colors in Planka 2.1.0 CSS modules.</textarea>
      <div style="margin:12px 0 4px;font-weight:600;font-size:13px;color:var(--g-color-text-secondary)">Checklist</div>
      <div class="_fieldWrapper_tpq9f_15" style="padding:8px">
        <span class="_text_170s0_69">[ ] Extract CSS module classes from bundle</span>
      </div>
      <div style="margin:12px 0 4px;font-weight:600;font-size:13px;color:var(--g-color-text-secondary)">Activity</div>
      <div style="display:flex;gap:8px;align-items:flex-start">
        <div class="_bubble_mycbd_8">
          <span class="_author_8hd9p_5">admin</span>
          <span class="_content_6qhns_5" style="display:block;margin-top:4px">Started work on the dark mode override.</span>
          <span class="_date_mycbd_34">2 hours ago</span>
        </div>
      </div>
    </div>

  </div>
</div>
</body></html>`;

	const browser = await puppeteer.launch({args: ['--no-sandbox']});
	const page = await browser.newPage();
	await page.setViewport({width: 1280, height: 900});
	await page.setContent(html, {waitUntil: 'networkidle2'});
	await new Promise(r => setTimeout(r, 1000));
	await page.screenshot({path: '/tmp/planka-board-mock.png', fullPage: true});

	const lightEls = await page.evaluate(() => {
		const results = [];
		for (const el of document.querySelectorAll('[class]')) {
			const cs = window.getComputedStyle(el);
			const bg = cs.backgroundColor;
			const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)/);
			if (m) {
				const [r, g, b] = [+m[1], +m[2], +m[3]];
				if (r > 220 && g > 220 && b > 220) {
					results.push({cls: el.className.substring(0, 80), bg});
					if (results.length >= 10) break;
				}
			}
		}
		return results;
	});
	console.log('Remaining light elements:', JSON.stringify(lightEls, null, 2));

	await browser.close();
})();
