import { defineConfig, Plugin } from 'vite'

/**
 * Vite plugin: inject <link rel="preload"> for critical fonts.
 * Inter 400 + 700 are used on first paint (body text + bold headings).
 * The plugin resolves content-hashed filenames at build time so the
 * preload href always matches the actual asset path.
 */
function fontPreloadPlugin(): Plugin {
	// Preload only Latin subsets of Inter 400 + 700 (first-paint weights).
	// These are ~29-30 KB each vs the original ~112 KB full fonts.
	const criticalFonts = ['inter-400-latin', 'inter-700-latin']
	return {
		name: 'openzero-font-preload',
		enforce: 'post',
		transformIndexHtml(html, ctx) {
			if (!ctx.bundle) return html
			const tags: { tag: string; attrs: Record<string, string>; injectTo: 'head' }[] = []
			for (const [fileName] of Object.entries(ctx.bundle)) {
				for (const font of criticalFonts) {
					if (fileName.includes(font) && fileName.endsWith('.woff2')) {
						tags.push({
							tag: 'link',
							attrs: {
								rel: 'preload',
								as: 'font',
								type: 'font/woff2',
								crossorigin: '',
								href: '/' + fileName,
							},
							injectTo: 'head',
						})
					}
				}
			}
			return tags.length ? tags : html
		},
	}
}

const LAZY_COMPONENTS = [
	'ProjectTree', 'MemorySearch', 'BriefingHistory', 'EmailRules',
	'CircleManager', 'CreateProject', 'CalendarAgenda', 'CalendarManager',
	'WelcomeOnboarding', 'HardwareMonitor', 'SoftwareStatus',
	'SystemBenchmark', 'ZPersonality', 'AmbientWidget',
]

export default defineConfig({
	root: '.',
	build: {
		outDir: 'dist',
		assetsDir: 'dashboard-assets',
		emptyOutDir: true,
		rollupOptions: {
			output: {
				manualChunks(id: string) {
					if (id.includes('node_modules')) return 'vendor'
					if (LAZY_COMPONENTS.some((c) => id.includes(`/components/${c}`))) {
						return 'lazy-components'
					}
				},
			},
		},
	},
	plugins: [fontPreloadPlugin()],
	server: {
		proxy: {
			'/api': {
				target: 'http://localhost:8000',
				changeOrigin: true,
			},
		},
	},
})
