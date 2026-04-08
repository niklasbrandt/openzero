const puppeteer = require('puppeteer');

(async () => {
	const browser = await puppeteer.launch({args: ['--no-sandbox']});
	const page = await browser.newPage();

	// Track all network responses to catch the auth token
	page.on('response', async resp => {
		if (resp.url().includes('/api/access-tokens') && resp.status() === 200) {
			try {
				const body = await resp.json();
				console.log('AUTH RESPONSE token:', body.item ? body.item.substring(0, 40) + '...' : 'none');
			} catch (e) {}
		}
	});

	await page.goto('http://100.116.160.123/login', {waitUntil: 'networkidle2', timeout: 15000});
	await new Promise(r => setTimeout(r, 2000));

	await page.type('input[name="emailOrUsername"]', 'mail@n1991.com', {delay: 50});
	await page.type('input[name="password"]', 'OpenZeroAdmin123$', {delay: 50});

	const btn = await page.$('button[type="submit"]') || await page.$('button');
	if (btn) await btn.click();
	else await page.keyboard.press('Enter');

	// Wait for either navigation away from /login OR any network activity to settle
	await Promise.race([
		page.waitForNavigation({timeout: 10000}).catch(() => {}),
		new Promise(r => setTimeout(r, 10000)),
	]);

	const url = page.url();
	console.log('URL after login:', url);

	// Dump all localStorage keys and values (truncated)
	const storage = await page.evaluate(() => {
		const result = {};
		for (let i = 0; i < localStorage.length; i++) {
			const k = localStorage.key(i);
			const v = localStorage.getItem(k);
			result[k] = v ? v.substring(0, 80) : v;
		}
		return result;
	});
	console.log('localStorage keys:', JSON.stringify(storage, null, 2));

	await browser.close();
})();
