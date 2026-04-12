---
name: theme-builder
description: "Create a new HSLA theme for the openZero dashboard with full 4-token primitive chains and register it in the theme catalogue."
---

# Theme Builder Skill

Creates a new colour theme following the openZero HSLA token chain architecture.

## Reference

See `references/token-chain-pattern.md` for the full token structure.

## Steps

1. **Ask** for:
   - Theme name (e.g. "Arctic Aurora").
   - Category (Nature, Urban, Cosmic, Vintage, etc.).
   - Primary accent colour (HSLA or hex).
   - Secondary accent colour (HSLA or hex).
   - Tertiary accent colour (HSLA or hex).

2. **Decompose each colour** into the 4-token primitive chain:
   - `-h` (hue: 0-360)
   - `-s` (saturation: 0%-100%)
   - `-l` (lightness: 0%-100%)
   - `-rgb` ("R, G, B" triplet)
   - Composite: `hsla(H, S%, L%, 1)`

3. **Build the theme object** for `UserCard.ts`:
   ```typescript
   {
       name: 'Arctic Aurora',
       category: 'Nature',
       primary: 'hsla(180, 70%, 45%, 1)',
       secondary: 'hsla(220, 60%, 50%, 1)',
       tertiary: 'hsla(280, 50%, 55%, 1)',
   }
   ```

4. **Register in UserCard.ts** theme catalogue array.

5. **Verify** the theme renders correctly:
   - Open dashboard, select the theme from the dropdown.
   - Check both dark and light modes.
   - Verify contrast ratios meet WCAG 2.1 AA (4.5:1 for text, 3:1 for UI).

## Guidelines
- Themes must NEVER set `data-theme`. Dark/light mode is user-controlled.
- Always update the full token chain (H, S, L, RGB, composite, aliases).
