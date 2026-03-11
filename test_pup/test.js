const puppeteer = require('puppeteer');
(async () => {
    const browser = await puppeteer.launch();
    const page = await browser.newPage();
    page.on('console', msg => console.log('BROWSER_LOG:', msg.text()));
    page.on('pageerror', err => console.log('BROWSER_ERROR:', err.toString()));
    await page.goto('http://localhost:5173', { waitUntil: 'load' });
    await new Promise(r => setTimeout(r, 2000));

    // Evaluate in page
    const res = await page.evaluate(() => {
        const diag = document.querySelector('system-benchmark');
        if (!diag) return 'no diag';
        const instantBtn = diag.shadowRoot.querySelector('button[id="bench-instant"]');
        if (!instantBtn) return 'no instant btn';
        instantBtn.click();
        return 'clicked diag instant';
    });
    console.log(res);

    await new Promise(r => setTimeout(r, 5000)); // wait for fetch

    // read bench html
    const html = await page.evaluate(() => {
        const diag = document.querySelector('system-benchmark');
        const list = diag.shadowRoot.querySelector('#bench-results');
        return list ? list.innerHTML : 'no list';
    });
    console.log("RESULTS HTML HEAD:", html.substring(0, 150));

    await browser.close();
})();
