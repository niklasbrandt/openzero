# Local Dify Crews and Loops (Conceptual Strategy)

- [Overview](#overview)
- [The Crew Ecosystem](#the-crew-ecosystem)
	- [Execution Lifecycle](#execution-lifecycle)
	- [Workflow vs. Agent Crews](#workflow-vs-agent-crews)
	- [Context & Parameter Injection](#context--parameter-injection)
	- [Data Grounding & Sources](#data-grounding--sources)
- [Canonical Crew Catalog](#canonical-crew-catalog)
	- [Universal Core](#universal-core)
	- [Business & Operations](#business--operations)
	- [Education & Pedagogy](#education--pedagogy)
	- [Private & Personal Management](#private--personal-management)
- [Detailed Walkthrough: Recipes Chef](#detailed-walkthrough-recipes-chef)
- [Agent Character Design](#agent-character-design)
	- [Character Anatomy](#character-anatomy)
	- [Best Practices for High-Quality Outcomes](#best-practices-for-high-quality-outcomes)
	- [Dify DSL & Zero-Config Auto-Provisioning](#dify-dsl--zero-config-auto-provisioning)
- [Architecture & Security](#architecture--security)
- [Resource Impact](#resource-impact)

---

## Overview

This plan integrates **Dify** as a local execution engine for **openZero**. It transforms Z from a conversational assistant into an **Agent Operator** capable of delegating complex, multi-step background tasks to specialized workflows (**Crews**) and establishing autonomous, recurring background tasks (**Loops**).

> [!NOTE]
> Only **Universal Core** crews are enabled by default. All domain-specific templates (Business, Education, Private) are provided as commented-out examples in `agent/crews.yaml` for optional activation by the operator.

---

## The Crew Ecosystem

Crews are the specialized cognitive units of the openZero environment. While Z manages the primary user interface and immediate tool-intent, Crews are spawned to handle long-running research, analysis, and maintenance tasks that would otherwise block the main conversation loop.

### Execution Lifecycle

Every crew execution follows a standardized 5-step lifecycle:

1. **Selection**: Z identifies a task requiring deep reasoning or a specific domain workflow and chooses a Crew from the Registry.
2. **Delegation**: Z emits a `[ACTION: RUN_CREW | CREW: <id> | INPUT: <text>]` tag. openZero intercepts this tag and resolves the crew ID to a live Dify App.
3. **Autonomous Work**: The Dify engine executes the workflow asynchronously. Z remains active for other user requests during this time. Depending on the crew type, this can involve multi-step tool calling, web search, PDF parsing, and iterative reasoning.
4. **Integration Callback**: Upon completion, the Crew uses the secured `Integration API` to write results back into the openZero ecosystem -- creating Planka cards, storing memories in Qdrant, or sending Telegram notifications.
5. **Synchronization**: The results are merged into Z's semantic memory, allowing Z to incorporate the "Crew's research" into future dialogue and decision-making.

### Workflow vs. Agent Crews

The `type` field in `crews.yaml` determines how Dify executes the crew:

- **Workflow Crews (`type: workflow`)**: Fixed, high-reliability sequences with deterministic node graphs. Best for structured processes where the steps are known in advance (e.g., "Scrape -> Extract -> Map to CRM -> Create Card"). Workflows guarantee consistent output format and are easier to debug.
- **Agent Crews (`type: agent`)**: Goal-oriented reasoning where the Crew autonomously selects its own tools and strategies to solve a problem. Best for open-ended research and analysis tasks where the execution path depends on intermediate results. Agents use ReAct (Reason + Act) or Function Calling strategies depending on the underlying model.

### Context & Parameter Injection

openZero is not just a trigger; it acts as a **context provider**. Every Crew call automatically injects:

- `user_name`: The operator's name from the personal context.
- `local_time`: The current timestamp and timezone.
- `memory_snapshot`: A curated snippet of recent relevant memories from Qdrant, retrieved via semantic search on the Crew's input query.

This ensures that even a "cold" Crew execution has awareness of the operator's identity, schedule, and recent context.

### Data Grounding & Sources

Specialized crews leverage diverse data sources for their reasoning:

1. **Semantic Memory (Qdrant)**: Z performs a vector search for relevant tags (e.g., `#allergy`, `#wellness`, `#diet_plan`) and injects the results into the Crew's reasoning context. This allows Crews to "remember" things the user has told Z in the past.
2. **External Direct Integrations**: Dify workflows can be configured with their own API tools (e.g., fetching data from Oura, Apple Health, or Google Fit via Dify's HTTP Tool). These are configured within Dify's "Tools" menu under "Create Custom Tool" using OpenAPI schemas.
3. **Uploaded Knowledge (RAG)**: Dify's "Knowledge Base" (Vector DB) can host static documents like medical health reports, allergy tests, recipe PDFs, or curriculum standards. Crews reference these during every run via "Knowledge Retrieval" nodes in their workflows.
4. **Personal Context Bridge**: A secure API endpoint in openZero that allows Dify Crews to read files directly from the operator's `/personal` directory. Supported formats: `.md`, `.txt`, `.docx`, `.pdf`, `.csv`, `.xlsx`. This ensures that updated personal requirements are always available to Crews without manual re-uploading.

### How-To: External Integrations (Dify Side)

For crews to fetch real-time data from external APIs:

1. **Native Tools**: Use Dify's built-in "Tools" menu to enable community-built connectors (Google Search, Wolfram Alpha, etc.).
2. **Custom HTTP Tools**: Under **Tools -> Create Custom Tool**, define a JSON schema for a REST API. Dify generates an "Action" block that can be dragged into any workflow.
3. **Workflow Webhooks**: Add a "Webhook" node to receive push data from external services (e.g., IFTTT/Zapier bridges).
4. **Secrets Management**: Store API keys for these tools in Dify's **Settings -> Tool Configuration** to ensure they never leak into the openZero environment.

### How-To: Uploaded Knowledge (PDFs)

For crews to reference personal PDFs (e.g., medical reports, diet plans, home manuals):

1. **Create Knowledge Base**: In Dify's "Knowledge" menu, create a new Dataset (e.g., "Personal Health Archive").
2. **Upload & Index**: Upload the PDFs. Dify automatically chunks and vectors the text using its internal embedding model.
3. **Refinement**: Use the "Synonyms" and "Q&A" features in Dify to improve retrieval for domain-specific terminology.
4. **Workflow Hookup**: In the Crew's workflow, add a "Knowledge Retrieval" node. Connect it to the relevant Dataset and use the `input` from openZero to retrieve the most relevant chunks before generating a response.

---

## Canonical Crew Catalog

### Universal Core (The Foundation)

These three crews are enabled by default and form the baseline agentic operating system:

- **`flow_optimizer` (Stagnation Auditor & Workflow Strategist)**: Acting as Z's internal project manager, this crew continuously scans Planka boards for stagnant activity. It identifies bottlenecks and generates "Unblocker" micro-tasks to keep the user's workflow alive.
- **`context_researcher` (Deep Intelligence Scholar & Synthesis Architect)**: Performs extreme-scale research across multi-vector knowledge sources. It digests web data and internal documentation to produce synthesized "White Papers" stored in Z's memory.
- **`structure_architect` (Systemic Workspace Architect)**: The onboarding engine. It takes a high-level goal and scaffolds entire digital workspaces (Boards, Lists, Cards) based on proven best-practice templates.

### Business & Operations

- **`market_scout` (Competitive Intelligence Scout)**: Monitors industry shifts and competitor signals for strategic logging.
- **`lead_engine` (CRM Conversion & Lead Pipeline Engine)**: Qualifies inbound signals and populates the strategic deal funnel.
- **`meeting_analyst` (Linguistic Transcription & Action Analyst)**: Transforms unstructured audio/text into actionable project deltas.
- **`brand_monitor` (Global Sentiment & Brand Health Monitor)**: Weekly cross-platform sentiment analysis and health reporting.
- **`strategic_planner` (Quarterly Vision & Roadmap Architect)**: Generates high-level roadmaps and aligns tasks with vision goals.
- **`finance_auditor` (Fiscal Auditor & Budgetary Integrity Engine)**: Receipt and invoice processing for tax alignment and budget tracking.

### Education & Pedagogy

- **`lesson_architect` (Pedagogical Unit & Lesson Architect)**: Design of instructional units aligning with international standards (IB, Common Core, etc.).
- **`assessment_strategist` (Diagnostic & Formative Assessment Strategist)**: Designs diverse formative/summative assessments and multi-layered feedback rubrics.
- **`pedagogical_researcher` (Evidence-Based Pedagogy Researcher)**: Synthesizes educational research to suggest peer-reviewed classroom interventions.
- **`differentiation_advisor` (Inclusive Education & Differentiation Advisor)**: Personalizes content for IEP/ESL/G&T learners while maintaining academic rigor.
- **`stakeholder_communicator` (Professional Stakeholder & Parent Liaison)**: Drafts professional, empathetic progress reports and newsletters for parents and school leadership.
- **`edu_admin_hub` (Educational Logistics & Admin Ops Hub)**: Manages administrative logistics, including field trip planning, internal scheduling, and supply tracking.

### Private & Personal Management

- **`wellbeing_monitor` (Holistic Wellbeing & Biometric Analyst)**: Analyzes biometric data trends for biophilic lifestyle improvements.
- **`asset_manager` (Personal Asset & Subscription Integrity Manager)**: Tracking of subscriptions, recurring bills, and portfolio performance with risk-mitigation insights.
- **`residence_steward` (Residence Integrity & Smart Domain Steward)**: IoT optimization and predictive home maintenance scheduling.
- **`experience_concierge` (Lifestyle Experience & Travel Architect)**: Planning of high-intent itineraries based on preference history and historical enjoyment patterns.
- **`life_alignment_coach` (Vision-Action Alignment & Life Auditor)**: Periodic reviews of long-term aspirations vs. actual time allocation on boards.
- **`recipes_chef` (Precision Culinary Architect & Nutritional Optimizer)**: High-rigor meal plan generation with medical-grade allergy checking. Generates tailored recipes and synchronized "Shopping Lists" in Planka.

---

## Detailed Walkthrough: Recipes Chef

### Usage Flow (Operator Perspective)

1. **Context Maintenance (Passive)**: You keep your `/personal/health.md` updated with "No Peanuts" and `/personal/requirements.md` with "High Protein, <30min prep".
2. **Trigger (Conversation)**: You tell Z: "Z, plan a quick high-protein dinner for tonight."
3. **Dispatch (Bridge)**: Z identifies the `recipes_chef` crew. Through the **Personal Context Bridge**, it automatically grabs your latest health and requirement files.
4. **Reasoning (Dify)**: The Crew searches its own recipe database, filters out everything with peanuts, calculates the macros for 2 people, and selects the most efficient "fast" recipe.
5. **Autonomous Output (Planka Sync)**:
	- The Crew creates a "Dinner Plan" card in your "Kitchen" board.
	- It adds the ingredients as checklist items ("Shopping List").
	- It attaches the recipe instructions as the card's description.
6. **Confirmation**: Z notifies you: "Recipes Chef has posted your allergen-safe, high-protein dinner plan to your Kitchen board."

### Multi-Agent Character Dynamics (The Internal "Crew")

Internally, the `recipes_chef` is a multi-agent collaboration of five specialists:

- **The Clinical Nutritionist**: Cross-references all ingredients against ground-truth health logs from `/personal/health.md`. Always prioritizes medical allergy data.
- **The Recipe Knowledge Archivist**: Extracts preparation sequences from the authorized PDF library (Dify Knowledge Base).
- **The Production Head Chef**: Synthesizes the final recipes into a standardized executive format, balancing nutrition targets with preparation constraints.
- **The Flavor Profile Analyst**: Analyzes the flavor profile of the recipe and makes modifications to optimize taste within the nutritional constraints.
- **The Shopping Logistics Officer**: Generates the Planka-synchronized ingredient checklist, formatted as a Markdown checklist for direct card creation.

---

## Agent Character Design

### Character Anatomy

In Dify, each specialized character within a crew is defined by four core dimensions:

1. **System Instructions (The Persona)**: Detailed personality and operational guardrails. Example: "Always cite medical sources. Never suggest high-sugar foods. If allergen data is missing, refuse to generate a recipe and request the operator to update their health profile."
2. **Toolsets (Capabilities)**: The specific actions an agent can take, such as "Search Web", "Read PDF", "Search Local Files", or "Create Planka Card". Each tool is defined as an OpenAPI schema in Dify.
3. **Knowledge Grounding (RAG)**: The specific datasets (Knowledge Bases) assigned to that character. This ensures they only source information from verified PDFs, logs, or curated datasets rather than hallucinating.
4. **Model Configuration**: Managed within Dify to ensure optimal performance tuning for each specific sub-task. This includes temperature, token limits, and model selection, all centralized in the Dify UI.

### Best Practices for High-Quality Outcomes

To achieve the highest quality results, follow these proven agentic design principles. These are codified in the `crews.yaml` preamble:

1. **Hyper-Specific Identities**: Avoid generic names. Instead of "Chef", use "Precision Culinary Architect". Instead of "Logistics", use "Planka Board Synchronizer". Specificity triggers better semantic grounding in most LLMs, causing them to adopt more rigorous reasoning patterns.
2. **The "Act-As" Framework**: Start system instructions with a clear professional archetype. "Act as a Senior Clinical Nutritionist with 15 years of experience in food allergy management." This primes the model for expert-level output.
3. **Constraint-First Logic**: Explicitly list what the character MUST NOT do. "Never suggest recipes containing peanuts. Never hallucinate ingredient substitutes; if unsure, escalate to the Nutritionist." Constraints reduce hallucination rates dramatically.
4. **Tool-Bound Instructions**: Tie the character's role to their specific tools. "Use the `Search_Recipe_PDFs` tool specifically for historical data, but use the `Web_Search` tool for current ingredient prices." This prevents tool misuse and improves accuracy.
5. **Output Format Anchoring**: Tell them exactly how to format their output. "Always output ingredients in a Markdown-friendly list format with checkboxes. Always include calorie count per serving as a parenthetical." This ensures consistent, machine-parseable output for downstream integration.

### Dify DSL & Zero-Config Auto-Provisioning

#### Standard DSL Imports

openZero ships standard Dify **DSL Exports** (`.yml` files) in the `agent.example/dify/` folder. These are complete workflow definitions that encode the node graphs, tool configurations, and prompt templates for each crew.

#### Zero-Config Auto-Provisioning

To achieve the "pre-wired" experience where the operator only comments/uncomments crews in `crews.yaml`:

1. **Setup**: The operator runs `cp -r agent.example agent` as part of the standard BUILD.md setup. This copies the registry and all DSL templates into their private `agent/` folder.
2. **DSL Discovery**: On startup, openZero scans the local `agent/dify/` folder for `.yml` workflow definitions.
3. **Automated Import**: openZero checks if these workflows already exist in the local Dify instance. If not, it automatically imports them via the Dify API.
4. **Dynamic Mapping**: The service maps each local `.yml` filename to the newly generated Dify App UUID and persists this mapping in `agent/.dify_app_ids.json`.
5. **Registry Resolution**: When the `CrewRegistry` loads `crews.yaml`, it resolves each crew's `dify_dsl_file` reference (e.g., `flow_optimizer.yml`) to the corresponding live Dify App ID using the persisted mapping.

This means the operator never needs to manually copy-paste UUIDs. The entire workflow is: uncomment a crew, restart, done.

---

## Architecture & Security

- **Registry System**: Data-driven YAML configuration with automatic DSL provisioning. Health checks exposed via the Diagnostics Widget.
- **Bi-Directional API**: Authenticated callbacks (`X-Integration-Token`) for Dify to write results back to openZero (Planka cards, Qdrant memories, Telegram notifications).
- **Personal Context Bridge**: Locked-down file server scoped to `/personal` with extension whitelisting. Registered as a Custom Tool in Dify.
- **Injection Protection**: Recursive sanitization prevents users from "smuggling" nested action tags into Crew inputs. The `RUN_CREW` handler scans input strings for `[ACTION: ...]` patterns and rejects them.
- **Token Security**: The Integration API requires a shared secret (`INTEGRATION_TOKEN`) configured in `.env`. Requests without a valid `X-Integration-Token` header receive a 401 response.

## Resource Impact

- **RAM**: +4-6 GB for the Dify stack (API server, worker, Redis, PostgreSQL, Weaviate).
- **Storage**: +5-8 GB for Docker images and database volumes.
- **CPU**: Burst activity during Crew runs; negligible idle cost. The Dify worker process is event-driven and sleeps between executions.
