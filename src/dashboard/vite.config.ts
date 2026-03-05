import { defineConfig, Plugin } from 'vite'

/**
 * Vite plugin: inject <link rel="preload"> for critical fonts.
 * Inter 400 + 700 are used on first paint (body text + bold headings).
 * The plugin resolves content-hashed filenames at build time so the
 * preload href always matches the actual asset path.
 */
function fontPreloadPlugin(): Plugin {
	const criticalFonts = ['inter-400', 'inter-700']
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

export default defineConfig({
	root: '.',
	build: {
		outDir: 'dist',
		assetsDir: 'dashboard-assets',
		emptyOutDir: true,
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
