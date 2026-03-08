import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	testDir: './tests',
	timeout: 30_000,
	expect: { timeout: 10_000 },

	// Run tests serially -- CI runners are single-core VMs and the preview
	// server only binds one port.
	workers: 1,
	fullyParallel: false,

	// Retry once on CI to account for slow container startup.
	retries: process.env.CI ? 1 : 0,

	reporter: process.env.CI
		? [['github'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
		: [['list'], ['html', { open: 'on-failure' }]],

	use: {
		baseURL: 'http://localhost:4173',
		// Capture screenshot + trace only on failure to keep CI artifacts small.
		screenshot: 'only-on-failure',
		trace: 'on-first-retry',
	},

	projects: [
		{
			name: 'chromium',
			use: {
				...devices['Desktop Chrome'],
				// Force empty storage state per context so the index.html
				// instant-theme script doesn't restore a stale cached palette
				// (z_theme in localStorage) from a previous developer session.
				storageState: { cookies: [], origins: [] },
			},
		},
	],

	// Serve the production build during tests.
	// `npm run build` is executed as a separate CI step before `playwright test`
	// runs, so we only need `vite preview` here.
	webServer: {
		command: 'npm run preview -- --port 4173',
		port: 4173,
		reuseExistingServer: !process.env.CI,
		timeout: 60_000,
	},
});
