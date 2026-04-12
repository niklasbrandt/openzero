---
name: new-component
description: "Scaffold a new openZero dashboard Web Component with Shadow DOM, i18n, accessibility, and lazy-load registration."
---

# New Component Skill

Creates a complete Web Component scaffold following openZero conventions.

## Steps

1. **Ask** for the component name (PascalCase, e.g. `WeatherWidget`).

2. **Create the component file** at `src/dashboard/components/<Name>.ts` using the template in `references/component-template.ts`. Replace all `__COMPONENT_NAME__` placeholders with the actual name and `__TAG_NAME__` with the kebab-case custom element name (e.g. `weather-widget`).

3. **Register lazy-load** in `src/dashboard/vite.config.ts`:
   - Add to the `manualChunks` function or the lazy component import map.

4. **Add i18n key stubs** in `src/backend/app/services/translations.py`:
   - Add at least a title key to both `_EN` and `_DE` dicts.
   - Example: `"weather_widget_title": "Weather Widget"` in `_EN`, `"weather_widget_title": "Wetter Widget"` in `_DE`.

5. **Verify** by running:
   ```bash
   cd src/dashboard && npx tsc --noEmit
   pytest tests/test_i18n_coverage.py -v
   ```
