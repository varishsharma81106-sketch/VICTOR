# Prompt: Build a Website for Victor — Research Intelligence System

Paste everything below this line into GLM 5.2 (or any AI that can generate a website).

---

You are building a **single-page website** for a project called **Victor**. The website should serve as the project's landing page / interface documentation — NOT a functional web app. It is a static HTML file with embedded CSS and JavaScript. No frameworks, no build tools, no dependencies. Just one `index.html` file.

---

## 1. WHAT VICTOR IS

Victor is a **local-first research intelligence system**. It converts raw inputs (PDFs, notes, experiment logs, sensor observations) into typed, provenance-tracked knowledge artifacts stored in a persistent knowledge graph. It answers research queries by retrieving and reasoning over those artifacts — entirely on-device, with no cloud dependency.

**One-line pitch:** Victor tracks where every claim comes from, how confident you should be in it, and what evidence contradicts it — all running locally on your machine.

---

## 2. VISUAL DESIGN — SPACE / RESEARCH THEME

The website must feel like a **mission control dashboard for scientific research**. Think NASA JPL meets academic journal meets deep space exploration.

### Color Palette
- **Background:** Deep space black (#0a0a0f) with subtle blue-purple gradient
- **Primary accent:** Cosmic blue (#4fc3f7) — used for headings, borders, highlights
- **Secondary accent:** Nebula purple (#7c4dff) — used for cards, gradients
- **Tertiary accent:** Stardust gold (#ffd54f) — used for badges, callouts, important numbers
- **Text primary:** Lunar white (#e8eaf6)
- **Text secondary:** Dust gray (#9e9e9e)
- **Success:** Mars green (#66bb6a)
- **Error:** Solar red (#ef5350)
- **Card backgrounds:** Dark panels with subtle border glow (#1a1a2e with rgba(79, 195, 247, 0.1) border)

### Background Effects (CSS only, no canvas)
- Animated starfield using CSS `radial-gradient` dots scattered across the background
- Subtle floating particle effect using CSS `@keyframes` animations
- Parallax-like scroll effect on the hero section
- A subtle grid pattern overlay (like a star chart or constellation map)

### Typography
- **Headings:** Use a monospace or technical font (e.g., 'JetBrains Mono', 'Fira Code', or 'Courier New' as fallback)
- **Body text:** Clean sans-serif (e.g., 'Inter', 'Segoe UI', system-ui)
- **Code snippets:** Monospace with syntax-highlighted terminal blocks
- **All text should have subtle text-shadow for a glowing screen effect**

---

## 3. PAGE STRUCTURE

### 3.1 — Hero Section
- Full viewport height
- "VICTOR" in massive monospace text with a subtle glow/scan-line animation
- Tagline: "Local-First Research Intelligence with Epistemic Provenance"
- Subtitle: "Track where every claim comes from. Surface contradictions. Never confuse a hypothesis with a measurement."
- Animated terminal-style typing effect showing a Victor CLI session:
  ```
  $ victor ingest paper.pdf
  > 4 chunks, 13 claims extracted
  
  $ victor ask "What is the main finding?"
  > Based on 3 supporting experiments...
  
  $ victor gaps
  > 2 unconfirmed claims found
  ```
- Floating orb / planet graphic in the background (CSS-generated, like a glowing sphere with gradient)
- Scroll-down indicator at the bottom

### 3.2 — Problem Section ("Why Victor?")
- Title: "The Problem"
- 3 cards in a row:
  1. **Fragmented Knowledge** — "Papers, notes, experiments, observations. All disconnected. No memory of where knowledge came from."
  2. **Unverified Claims** — "Hypotheses look the same as measurements. Nobody tracks confidence. Contradictions go unnoticed."
  3. **No Provenance** — "When you cite a claim 6 months later, do you remember which paper said it? Which experiment confirmed it?"
- Each card should have a subtle icon (use CSS/Unicode: 🧩, ⚠️, 🔍)

### 3.3 — How It Works ("The Epistemic Artifact")
- Title: "Every Piece of Knowledge Has 6 Properties"
- Show a visual diagram/card of the Epistemic Artifact with these 6 properties:
  1. **Origin** — Where it came from (sensor, paper, experiment, LLM)
  2. **Type** — Epistemic tier (MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS)
  3. **Confidence** — 0.0-1.0, computed from evidence
  4. **Contradictions** — Which experiments disagree
  5. **Gaps** — What evidence is missing
  6. **Age** — Timestamp + temporal decay
- Show the Epistemic Status Hierarchy as a vertical stacked bar or tower:
  ```
  MEASUREMENT  (1.00)  ← directly observed
  EXPERIMENT   (0.85)  ← controlled test
  LITERATURE   (0.70)  ← published paper
  NOTE         (0.50)  ← personal annotation
  HYPOTHESIS   (0.25)  ← speculative
  ```
- Higher tiers override lower tiers in retrieval scoring

### 3.4 — Architecture Overview ("Under the Hood")
- Title: "Architecture"
- Show 7 layers as a vertical stack diagram with connecting lines:
  - **Layer 0: Persistence** — NetworkX knowledge graph + ChromaDB vectors
  - **Layer 1: Ingestion** — PDF, Markdown, Experiment JSON plugins
  - **Layer 2: Retrieval** — HybridRetriever + AgenticRetriever (bounded agent loop)
  - **Layer 3: Reasoning** — ConflictDetector, NLI Cross-Encoder, GapDetector, PatternDetector
  - **Layer 4: Computation** — StatisticsKernel, uncertainty propagation
  - **Layer 5: Sovereignty** — Freeze, Mask, Audit Log
  - **Layer 6: Reality** — Camera + Audio sensor pipeline
- Each layer should be a card that expands on hover to show details

### 3.5 — Benchmark Results ("How Accurate Is It?")
- Title: "SciFact Benchmark"
- Show the results table:
  ```
  Run | Mode                          | n   | Accuracy
  1   | Pure LLM, free-form          | 50  | 68.0%
  2   | Structured JSON output        | 50  | 58.0%
  3   | Qwen2.5-7b, no NLI           | 100 | 59.0%
  4   | DeBERTa NLI primary (bug)     | 100 | 8.0%  ← fixed
  5   | DeBERTa NLI cross-check       | 100 | 71.0% ← current best
  ```
- Show a progress bar or gauge visualization for the 71% vs 85% target
- Note: "DoD #4 target: 85%. Root cause of Run 4 failure identified and fixed."
- Show the confusion matrix visually with color-coded cells (green = correct, red = wrong)

### 3.6 — Features Grid
- Title: "What Victor Can Do"
- 2x3 or 3x3 grid of feature cards with icons:
  1. 📄 **Ingest Any Source** — PDFs, markdown, experiment logs, sensor data
  2. 🔍 **Agentic Search** — Bounded agent loop with 8 tools, max 5 calls
  3. ⚖️ **Conflict Detection** — NLI cross-encoder catches contradictions
  4. 🕸️ **Knowledge Graph** — 8 node types, 12 edge types, typed relationships
  5. 🔒 **Sovereignty Layer** — Freeze, mask, audit log. Embedding channel closure.
  6. 📊 **Statistics Kernel** — Cohen's d, confidence intervals, reproducibility hashes
  7. 🎤 **Audio Ingestion** — Microphone + LibROSA feature classification
  8. 📷 **Vision Pipeline** — CLIP-based zero-shot classification from camera
  9. 🧠 **Self-Learning** — Pattern detection surfaces insights unprompted

### 3.7 — CLI Demo Section
- Title: "Command Line Interface"
- Show a dark terminal-style box with realistic Victor CLI output:
  ```
  $ victor ingest paper.pdf --type paper
  > Extracted 4 chunks, 13 claims, 13 concepts
  > Source ID: 0f0300f4-ced8-4a7b-9f3e-2d1a8b5c6e7f

  $ victor ask "What is the main finding?"
  > The paper proposes Selective Chain-of-Thought (SCoT)...
  > Confidence: 0.70 (LITERATURE tier)
  > Sources: 3 supporting, 1 contradicting experiment

  $ victor gaps
  > Priority gaps (sorted by importance):
  > 1. No experimental validation of SCoT on multi-hop reasoning
  > 2. No comparison with full-chain CoT on medical benchmarks

  $ victor inspect 0f0300f4
  > Node: PAPER
  > Claims: 13 | Experiments: 0 | Confidence: 0.00
  > Status: Has claims but no confirming experiments → GAP
  ```

### 3.8 — Technology Stack
- Title: "Built With"
- Show tech logos/names in a horizontal strip:
  - Python 3.14
  - NetworkX (knowledge graph)
  - ChromaDB (vector store)
  - Sentence Transformers (embeddings)
  - Ollama (local LLM inference)
  - PyMuPDF (PDF extraction)
  - LibROSA (audio analysis)
  - CLIP (vision)
  - Rich (CLI UI)
  - pytest (196+ tests)

### 3.9 — Open Source / Project Status
- Title: "Project Status"
- Show version badge: "v5.3.0"
- Show status indicators:
  - ✅ Knowledge graph (8 node types, 12 edge types)
  - ✅ Ingestion pipeline (PDF, Markdown, Experiment JSON)
  - ✅ Agentic retrieval (bounded agent loop)
  - ✅ NLI conflict detection (DeBERTa cross-encoder)
  - ✅ Sovereignty layer (freeze, mask, audit)
  - ✅ Sensor pipeline (camera + audio)
  - 🔄 SciFact accuracy optimization (71% → targeting 85%)
  - 📋 MCP server (planned)
  - 📋 Raspberry Pi field prototype (planned)

### 3.10 — Footer
- "Victor: Local-First Research Intelligence"
- "Built with epistemic provenance. Every claim has a source."
- Links: GitHub, Documentation, Paper (placeholder)
- Small animated constellation/star connecting lines

---

## 4. ANIMATIONS & INTERACTIONS

- **Scroll-triggered animations:** Elements fade in and slide up as they enter the viewport (use Intersection Observer API)
- **Terminal typing effect:** The CLI demo types out characters one by one with a blinking cursor
- **Glow effects:** Key elements (headings, cards on hover) have a subtle blue glow
- **Card hover:** Cards lift up slightly with a brighter border glow on hover
- **Smooth scrolling:** Clicking nav links smoothly scrolls to sections
- **Star twinkle:** Background stars randomly twinkle using CSS animation delays
- **Progress bar animation:** The accuracy gauge animates from 0 to 71% when scrolled into view
- **Floating particles:** Small dots drift slowly across the background (CSS only, 10-15 particles)

---

## 5. NAVIGATION

Fixed top navigation bar with:
- "VICTOR" logo text on the left (monospace, glowing)
- Section links: Overview | Architecture | Benchmarks | Features | CLI | Status
- Dark transparent background that becomes solid on scroll
- Mobile hamburger menu (responsive)

---

## 6. RESPONSIVE DESIGN

- Desktop: Full layout with side-by-side cards, large hero
- Tablet (768px-1024px): 2-column grids become 1-column, smaller hero text
- Mobile (<768px): Single column, hamburger nav, stacked cards, reduced animations for performance

---

## 7. TECHNICAL REQUIREMENTS

- **Single file:** Everything in one `index.html` (HTML + CSS + JS)
- **No external dependencies:** No CDN links, no frameworks. Pure HTML/CSS/JS.
- **No images:** All graphics are CSS-generated (gradients, shapes, Unicode symbols)
- **Performance:** Use `will-change` and `transform` for animations, avoid layout thrashing
- **Accessibility:** Proper heading hierarchy, alt text where applicable, keyboard navigation
- **SEO:** Proper `<title>`, `<meta description>`, semantic HTML5 elements

---

## 8. FILE OUTPUT

Generate a single file: `index.html`

The file should be complete, self-contained, and ready to open in any browser. No build step required.

---

## WRITING INSTRUCTIONS

- Make it visually stunning. This is the first impression of the project.
- Every section should feel like a mission briefing at a space research center.
- Use CSS variables for the color palette so it's easy to modify.
- Add comments in the CSS for major sections.
- The terminal demo should use realistic Victor CLI output (provided above).
- Don't use placeholder text — use the actual Victor content provided in this prompt.
- Make the starfield subtle, not overwhelming. The content should be the focus.
- The overall feel should be: "This is a serious research tool built by someone who cares about epistemic rigor."
