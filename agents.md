# AI Agent Guidelines

> This file contains instructions and rules for AI assistantsinteracting with this repository.

> [strict!] always reference agents.md and README.MD!

## 0. Mandatory Initial Step

- **CRITICAL:** At the beginning of EVERY interaction or whenever you are prompted for a new task, you MUST read and analyze **agents.md**, **docs/artifacts/DESIGN.md** and **README.md**.
- You must use the context from these files to ensure your behavior aligns with the project's specific boundaries and that you do not repeat errors recorded in the log.
- **Artifact Scan:** List the `docs/artifacts/` directory and read the first 20 lines of each artifact file to understand available context before starting work. Do not read entire artifacts unless the task directly requires their content.

## 10. Build Documentation Maintenance

- **Post-Task Audit:** After completing a task or prompt execution, you MUST check if the changes you made should be reflected in the project's build and setup instructions in `BUILD.md` (root of the repository). This is the canonical manual setup guide for operators.
- **What belongs in BUILD.md:** Any step a human must perform manually to set up or configure the system — new required `.env` variables, new secrets to generate, new manual server-side steps, service configuration changes, or first-run procedures.
- **Keep it current:** If you introduce a new required env var (like `DASHBOARD_TOKEN`), add a numbered step in the appropriate Phase section of `BUILD.md` explaining how to generate, set, and verify it. Do not leave operators to discover missing config through 500 errors.
- Ensure that the setup, deployment, and architectural instructions in `BUILD.md` remain accurate and up-to-date with your latest modifications.

## 2. Editor & Syntax Best Practices

- **Indentation:** Use **TABS** for indentation (not spaces), except where rigidly required by a schema (like YAML). For all other code (HTML, CSS, JS, Markdown, etc.), use tabs.
- **Trailing Whitespace:** Remove trailing whitespace from modified lines.
- **File Endings:** Ensure all files end with a single newline character.

## 3. Documentation Standards

- **No Emojis:** Do not use emojis in any Markdown (`.md`) files. Documentation should remain clean and professional without decorative symbols.
- **Naming Convention:** Always spell the project name as **openZero** (lowercase 'o', uppercase 'Z'). Never use "OpenZero", "Openzero", or "OPENZERO".

## 4. Configuration & Example Files

- **Example Clones:** Many configuration files (like `.env` or `config.yaml`) have `.example` clones (e.g., .env.example, config.example.yaml). If you modify the structure or options of a configuration file, **you MUST apply those same structural changes to the corresponding example file.** This ensures that new users have an up-to-date template to follow.

## 5. Web Component Styling

- **Shadow DOM CSS Encapsulation:** Native Web Components in this project use `<style>` blocks populated via template literals directly inside their `.ts` definition wrappers. Do not extract this CSS into separate files. This single-file encapsulation pattern is intentional and considered the best practice for this repository to ensure isolated styling without a complex CSS bundling layer.

## 7. Local Resource Cleanup

- **Always terminate local development processes** (e.g., `dev.sh`, local Docker containers) before or immediately after a cloud deployment.
- This is critical to prevent conflicts, especially with the Telegram bot, which can only have one active polling instance at a time.


## 9. Data Sovereignty & Protection

- **NEVER overwrite data on remote servers.** Your synchronization focus must strictly be on application logic (code), not data.
- **Strict Rsync Exclusions:** When syncing to a remote server, you MUST exclude the following patterns to prevent overwriting cloud memories or private local data:
    - `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`
    - `.DS_Store`
    - `personal/` (All private local files)
    - Raw database files or Docker volume folders if mapped locally.
- **Volume Safety:** NEVER use commands that delete Docker volumes (like `docker compose down -v`) unless explicitly instructed for a specific reset task.

## 11. Secret & Privacy Protection

- **STRICT LEAK PREVENTION:** NEVER commit or include real secrets (API keys, passwords, tokens) or personal identifiers (real emails, public IPs, Tailscale IPs) in the repository's codebase, scripts, or documentation.
- **Use Placeholders:** Always use generic placeholders like `your_api_key`, `your_vps_ip`, or `admin@example.com` in `.example` files and shared scripts.
- **Verify Gitignore:** Before creating new files that might contain sensitive data (logs, temp state, credentials), ensure their pattern is covered in `.gitignore`.
- **Sanitize Scripts:** Ensure utility scripts (e.g., `sync.sh`) load sensitive configuration from environment variables or `.env` files rather than hardcoding them.
- **No Personal Data:** Avoid using the user's real name, company email, or specific location in any code comments or example data.
- **Audit Before Sync:** Always perform a quick audit for hardcoded secrets when preparing a deployment or large code change.
- **Environment Parity:** NEVER hardcode credentials (passwords, keys) directly in `docker-compose.yml` or service definitions. Always map them to variables in `.env` and use the `${VAR}` syntax in the YAML.
- **Post-Implementation Verification:** After finishing a task, you MUST perform a final check of all modified files to ensure no sensitive developer environment data (local paths, test credentials) was accidentally committed.

## 12. Accessibility & Progressive Enhancement

All code written for the openZero dashboard **MUST** conform to **WCAG 2.1 Level AA** and **EN 301 549** (the European accessibility standard). This is a non-negotiable baseline for every new component, feature, and bug fix.

- **Native Elements First**: Always prioritize native HTML elements (buttons, inputs, links) over custom `div` or `span` listeners to ensure built-in keyboard support and screen reader compatibility.
- **Keyboard Navigability**: Ensure all interactive elements are focusable (`tabindex="0"` if not native) and have visible focus states (`:focus-visible` ring, minimum 2px solid #14B8A6).
- **ARIA Standards**: Use appropriate ARIA roles and labels (`aria-label`, `aria-expanded`, `role="status"`, `role="dialog"`, etc.) for purely visual or complex custom components. Every interactive element and landmark region must have a meaningful accessible name.
- **Semantic Hierarchy**: Maintain a logical heading structure (H1 -> H2 -> H3) to aid screen reader navigation.
- **Contrast & Clarity**: Maintain high color contrast for text and ensure touch/click targets are sufficiently sized (min 44x44px where possible).
- **Color Independence**: Never use color as the only visual means of conveying information. Always pair color indicators with text, icons, or `aria-label` alternatives.
- **Live Regions**: Use `aria-live="polite"` for dynamic content updates. Use `aria-live="assertive"` only for urgent alerts. Add `role="status"` for status messages.
- **Multilingual Accessible Text**: ALL user-facing strings in ARIA attributes (`aria-label`, `aria-describedby`, `placeholder`, screen-reader-only text) MUST use the component's `this.tr('key', 'English fallback')` translation helper -- never hardcode English strings directly. Add new keys to `_EN` and `_DE` in `src/backend/app/services/translations.py` under the `Accessibility / ARIA labels` section.
- **tr() in Every Component**: Every Shadow DOM Web Component MUST include the translation boilerplate (`private t`, `loadTranslations()`, `tr()` method) so accessible text can be localized. Call `loadTranslations()` inside `connectedCallback()`.
- **Skip Navigation**: The global layout includes a skip link (`#main-content`). Do not remove it.
- **Reduced Motion & Forced Colors**: Include `@media (prefers-reduced-motion: reduce)` and `@media (forced-colors: active)` blocks in every Shadow DOM component stylesheet.
- **sr-only Utility**: Each Shadow DOM component must define a local `.sr-only` CSS class for screen-reader-only text since Shadow DOM CSS is encapsulated.

## 13. Artifact Management & Consistency

- **Proactive Artifact Creation**: For any significant architectural change, complex feature implementation, or strategic shift, you MUST proactively create or update a dedicated artifact (typically in `docs/artifacts/`).
- **Summarize into Artifacts**: Artifacts should capture requirements, design decisions, technical constraints, and phased implementation plans.
- **Context Adherence**: Always refer to existing artifacts before starting a task. They represent the project's ground truth and help prevent context drift over long interactions.
- **Persistence of Knowledge**: Use artifacts to "save" complex states or long-term goals that might otherwise be lost in chat history. If a task spans multiple sessions, the artifact is your primary source of continuity.

## 14. Global Intelligence & Privacy

- **Unified Context Persistence**: Always use the GlobalMessage mechanism to sync conversations across all channels (e.g. Telegram and Dashboard). This ensures Z maintains a consistent 'Universal Context' regardless of where the interaction occurs.
- **Semantic Memory Filtering**: Before storing user input to the long-term memory (Qdrant), you must perform a logic check to distinguish between factual data worth keeping (preferences, people, plans) and transient chatter (greetings, status updates).
- **Intelligence Scaling**: Prioritize response velocity by default (e.g. 3B models). Automatically scale to more complex reasoning models (e.g. 8B models) only when user requests involve strategic analysis, planning, or large data blocks.
- **Status Transparency**: The dashboard MUST always reflect the current intelligence state of the system, including the model currently in use, memory point counts, and identity health status.
- **Context Grounding**: Every response must be relateable to the current system time. Do not report progress on a timeframe that has already elapsed according to the internal clock.

## 15. Firewall & Port 53 Protection

- **Port 53 is Tailscale-only:** DNS (port 53) MUST only be reachable via the Tailscale interface (`tailscale0`) from the CGNAT range `100.64.0.0/10`. This is enforced by UFW rules. NEVER add raw iptables rules that open port 53 to `0.0.0.0/0`.
- **No Public DNS Exposure:** Pi-hole runs with `network_mode: host`, meaning port 53 is bound directly on the host. Any firewall misconfiguration exposes it to the entire internet, enabling DNS amplification attacks and FTL resource exhaustion.
- **Pre-Deploy Firewall Audit:** Before any change that touches `docker-compose.yml` pihole config, UFW rules, or iptables, verify that `sudo iptables -L INPUT -n | grep 'dpt:53'` shows NO rules accepting from `0.0.0.0/0`. Only `tailscale0`-scoped UFW rules should exist.
- **Post-Incident Verification:** If DNS stops working, run `ss -ulnp | grep 53` to confirm FTL is actually listening, and check `FTL.log` for `FATAL: realloc_shm` errors indicating a flood.

## 16. Dependency Management & Version Awareness

- **Respect Installed Versions:** Always verify and respect the specific version of a dependency (e.g., Pi-hole v6, specific Docker images, Node modules) installed in the project before suggesting changes or configurations.
- **Study Relevant Documentation:** Configuration keys and behaviors often change between major versions (such as the removal or modification of constants like `DNSMASQ_LISTENING` in Pi-hole v6). Do not assume old configuration patterns apply to new versions.
- **Fail Gracefully:** If an expected configuration file or constant is missing, investigate the version-specific documentation or the actual container environment rather than repeatedly trying the same command.

## 17. Commit & Deploy Workflow

- **Always Push:** After committing changes to git, you MUST push to the remote repository. Never leave commits local-only.
- **Always Sync VPS:** After pushing, you MUST run `scripts/sync.sh` to deploy the changes to the VPS. Code changes are not complete until they are live on the server.
- **Single Step:** Treat commit, push, and VPS sync as one atomic workflow. Do not stop after committing without pushing and syncing.

## 18. Design System & CSS Architecture

- **Canonical Reference:** All visual decisions are documented in `docs/artifacts/DESIGN.md`. Read it before modifying any component styling.
- **Design Tokens:** Never use hardcoded hex colors in component CSS. Always reference `:root` custom properties via `var(--token, fallback)`. The fallback value ensures standalone functionality.
- **Shared Style Modules:** Reusable CSS lives in `src/dashboard/services/*Styles.ts` as exported template string constants. Components interpolate them via `${MODULE_NAME}` inside `<style>` blocks. Do not duplicate sr-only, reduced-motion, scrollbar, or section-header CSS.
- **rem Not em:** Use `rem` for all spacing (margin, padding, gap, width, height). The only acceptable use of `em` is `letter-spacing`.
- **Class Naming:** Section header icons use `.h-icon`. Status indicators use `.status-dot`. Empty placeholders use `.empty-state`. Never use generic `.icon` or `.empty`.
- **Shadow DOM Encapsulation:** Component styles stay inside their `.ts` template wrappers. Never extract into separate CSS files.
- **Easing Rules:** Standard GSAP easing: `expo.out` (entrance), `expo.inOut` (transition), `power2.in` (exit), `power2.out` (micro). `elastic.out` and `bounce.out` are only permitted in goo mode (`oz-goo-*` scoped).
- **Accessibility per Component:** Every Shadow DOM component must include `${ACCESSIBILITY_STYLES}` (providing `.sr-only`, `@media(prefers-reduced-motion)`, and `@media(forced-colors:active)`). Component-specific animation suppression goes in a separate reduced-motion block after the module.

## 19. Localization Hygiene

- **Never Hardcode English:** Every user-visible string in TypeScript components — including `aria-label`, `placeholder`, `title`, and visible text between HTML tags — MUST go through `this.tr('key', 'English fallback')`. The fallback argument is the only permitted place for a raw English string.
- **Synchronise on Every Change:** When adding, renaming, or removing a UI string, immediately update `src/backend/app/services/translations.py`:
  - Adding a string: add the key to `_EN` and `_DE` at minimum.
  - Renaming a key: update it everywhere it is used in TS components AND in all language dicts.
  - Removing a feature: remove the orphaned keys from `_EN`, `_DE`, and every other language dict to prevent drift and bloat.
- **No Stub Languages in Selector:** If a language code is listed in the UserCard selector it MUST have a non-empty dict in `_TRANSLATIONS`. Do not add a language to the selector until its dict is populated. This is enforced by `TestSelectorCoverage` in `tests/test_i18n_coverage.py`.
- **Key Parity is Required:** Every key in `_EN` must exist in every non-empty language dict. Partial dicts are CI-blocked by `TestKeyCompleteness`. When filling out a language, use `_EN` as the canonical reference — never add keys to a language dict that do not exist in `_EN`.
- **Umlaut / Unicode Correctness:** Language-specific characters (ä, ö, ü, ß, accents, non-Latin scripts) must be stored as literal Unicode in the source file, not as ASCII transliterations (`ae`, `oe`, `ue`) or escape sequences (`\u00e4`). This is enforced for `_DE` by `TestDE_NoAsciiUmlauts`; apply the same standard to any other language dict you write.
- **Run the i18n Gate:** After any translation-related change, run `pytest tests/test_i18n_coverage.py -v` locally before committing. All six tests must pass (or intentional known-gap failures for partially translated languages must be explicitly documented).
