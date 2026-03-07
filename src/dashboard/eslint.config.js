import tseslint from 'typescript-eslint';

export default tseslint.config(
	...tseslint.configs.recommended,
	{
		files: ['src/**/*.ts', 'components/**/*.ts', 'services/**/*.ts'],
		rules: {
			// Downgrade to warn so legacy "any" usage doesn't block CI
			// until a dedicated cleanup pass is done.
			'@typescript-eslint/no-explicit-any': 'warn',
			// Unused vars are an error — use _prefix to intentionally ignore.
			'@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
			// Non-null assertions are hard to avoid in DOM code; warn only.
			'@typescript-eslint/no-non-null-assertion': 'warn',
			// Empty functions appear in stub/default implementations.
			'@typescript-eslint/no-empty-function': 'warn',
		},
	},
);
