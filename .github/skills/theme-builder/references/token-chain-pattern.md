# HSLA Token Chain Pattern

## Architecture

Every accent colour in openZero is decomposed into four primitive tokens plus a composite:

```css
--accent-primary-h:     180           /* hue: 0-360 */
--accent-primary-s:     70%           /* saturation: 0%-100% */
--accent-primary-l:     45%           /* lightness: 0%-100% */
--accent-primary-rgb:   51, 163, 163  /* "R, G, B" triplet for rgba() */
--accent-primary:       hsla(180, 70%, 45%, 1)  /* composite */
```

## Why This Exists

This decomposition enables:
- Per-component alpha overrides: `rgba(var(--accent-primary-rgb), 0.3)`
- Theme switching without full CSS recalculation
- Programmatic colour manipulation (lighten/darken via L adjustment)

## The Full Chain

For a complete theme, you need three colours with all tokens:

| Token suffix | Primary | Secondary | Tertiary |
|-------------|---------|-----------|----------|
| `-h`        | hue     | hue       | hue      |
| `-s`        | sat%    | sat%      | sat%     |
| `-l`        | light%  | light%    | light%   |
| `-rgb`      | R, G, B | R, G, B  | R, G, B  |
| (composite) | hsla()  | hsla()    | hsla()   |

## Legacy Aliases

Also update these if they exist:
- `--accent-color` (alias for primary composite)
- `--accent-glow` (alias for primary with reduced alpha)

## Conversion

Use the `parseColor()` and `hslToRgb()` helpers in `UserCard.ts` for conversions.
Hex inputs: `parseColor('#1A73E8')` returns `{ h, s, l, a }`.
HSL to RGB: `hslToRgb(h, s, l)` returns `"R, G, B"` triplet string.
