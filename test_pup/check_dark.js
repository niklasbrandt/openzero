const puppeteer = require('puppeteer');

(async () => {
	const browser = await puppeteer.launch({args: ['--no-sandbox']});
	const page = await browser.newPage();

	// sails.io.js detects Node.js via typeof process && process.title !== 'browser'
	// Override this by making process.title === 'browser' before any scripts run
	await page.evaluateOnNewDocument(() => {
		if (typeof process !== 'undefined') {
			try { Object.defineProperty(process, 'title', {value: 'browser', configurable: true}); } catch (e) {}
		}
	});

	// Set a real browser User-Agent
	await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36');

	// Log errors and failures
	page.on('console', msg => { if (msg.type() === 'error') console.log(`[err]`, msg.text().substring(0, 100)); });
	page.on('requestfailed', req => console.log('[fail]', req.url().substring(0, 80), req.failure()?.errorText));

	// Do real form login on the SSH tunnel (bypasses Traefik, connects directly to Planka on localhost:18337)
	await page.goto('http://localhost:18337/login', {waitUntil: 'networkidle2', timeout: 15000});
	await new Promise(r => setTimeout(r, 2000));

	await page.type('input[name="emailOrUsername"]', 'mail@n1991.com', {delay: 50});
	await page.type('input[name="password"]', 'OpenZeroAdmin123$', {delay: 50});

	const btn = await page.$('button[type="submit"]') || await page.$('button');
	if (btn) await btn.click();
	else await page.keyboard.press('Enter');

	// Wait for URL to change (post-login redirect)
	await Promise.race([
		page.waitForNavigation({timeout: 10000}).catch(() => {}),
		new Promise(r => setTimeout(r, 10000)),
	]);
	console.log('After login URL:', page.url());

	// Navigate directly to board URL via the same tunnel (direct Planka port)
	const boardUrl = 'http://localhost:18337/boards/1717016120247977398';
	console.log('Navigating to board:', boardUrl);
	await page.goto(boardUrl, {waitUntil: 'networkidle2', timeout: 25000}).catch(e => console.log('Nav:', e.message));
	await new Promise(r => setTimeout(r, 10000));

	await page.screenshot({path: '/tmp/planka-board-dark.png', fullPage: false});

	const info = await page.evaluate(() => {
		const lightBgs = [];
		const allEls = document.querySelectorAll('*');
		for (const el of allEls) {
			const cs = window.getComputedStyle(el);
			const bg = cs.backgroundColor;
			const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)/);
			if (m) {
				const [r, g, b] = [+m[1], +m[2], +m[3]];
				if (r > 220 && g > 220 && b > 220) {
					lightBgs.push({cls: el.className.substring(0, 80), bg});
					if (lightBgs.length >= 15) break;
				}
			}
		}
		return {
			url: window.location.href,
			bodyClass: document.body.className,
			htmlLen: document.body.innerHTML.length,
			htmlSnippet: document.body.innerHTML.substring(0, 300),
			title: document.title,
			lightElements: lightBgs,
		};
	});
	console.log(JSON.stringify(info, null, 2));

	await browser.close();
})();
