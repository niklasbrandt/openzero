const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
        await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });
        // wait for page to be ready
        await page.waitForTimeout(2000);

        // find the DiagnosticsWidget
        const diagWidget = await page.locator('diagnostics-widget');
await diagWidget.locator('button[data-tier="local"]').click();
        
        console.log("Clicked fast benchmark in DiagnosticsWidget...");
        await page.waitForTimeout(2000);
        
        let content = await diagWidget.innerHTML();
        console.log("Panel after click:", content.substring(content.indexOf('bench-results-list')));
        
    } catch (e) {
        console.log(e);
    }
    await browser.close();
})();
