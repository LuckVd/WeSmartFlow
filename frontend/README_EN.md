**English | [中文](./README.md)**

# WeSmartFlow Frontend

A Vue 3 single-page application providing a complete interactive interface for adaptive learning.

## Module Structure

```
frontend/
├── public/              # Static assets
│   ├── logo.jpg         #   App logo
│   ├── logo.png         #   Browser tab icon (rounded)
│   └── icons.svg        #   SVG icon set
├── src/
│   ├── views/           # Page views
│   │   ├── LoginView.vue       # Login (email / GitHub / WeChat)
│   │   ├── DashboardView.vue   # Today's Learning (study plan + heatmap)
│   │   ├── ChatView.vue        # AI Tutoring (interactive + immersive)
│   │   ├── GraphView.vue       # Knowledge graph visualization
│   │   ├── KnowledgeBase.vue   # Knowledge base management
│   │   ├── QuizView.vue        # Quiz center
│   │   ├── DocumentsView.vue   # Document management
│   │   ├── SessionsView.vue    # Learning history
│   │   ├── DailyBrief.vue      # Daily brief
│   │   ├── LearningPath.vue    # Learning path
│   │   ├── ProfileView.vue     # User profile
│   │   └── SettingsView.vue    # System settings
│   ├── components/      # Reusable components
│   │   ├── EduViz/      #   Interactive visualization sandbox
│   │   │   ├── EduVizSandbox.vue  # iframe sandbox renderer
│   │   │   ├── eduviz-sdk.js      # EduViz SDK core library
│   │   │   └── sandboxTemplate.js # Sandbox HTML template
│   │   ├── HtmlCard/    #   HTML knowledge card renderer
│   │   │   └── HtmlCard.vue       # Safely renders Agent-generated HTML cards
│   │   ├── QuizCard/    #   Quiz card
│   │   │   └── QuizCard.vue       # Multi-type quiz interaction component
│   │   ├── VizCard/     #   Visualization card
│   │   │   └── VizCard.vue        # Visualization result display card
│   │   └── chat/        #   Chat helper components
│   │       ├── ThinkBlock.vue     # Agent thinking process display
│   │       └── ToolCallBlock.vue  # Tool call process display
│   ├── api/             # API client
│   │   ├── base.js      #   Base request wrapper (with token management)
│   │   ├── index.js     #   Unified exports
│   │   ├── auth.js      #   Auth API
│   │   ├── sessions.js  #   Session API (with SSE streaming)
│   │   ├── documents.js #   Document API
│   │   ├── nodes.js     #   Knowledge node API
│   │   ├── quizzes.js   #   Quiz API
│   │   ├── settings.js  #   Settings API
│   │   ├── brief.js     #   Brief API
│   │   └── user.js      #   User API
│   ├── composables/     # Vue composables
│   │   ├── useAuth.js   #   Auth state management
│   │   └── useTheme.js  #   Theme switching
│   ├── styles/          # Global styles
│   │   └── page-list.css#   List page common styles
│   ├── assets/          # Build-time processed assets
│   ├── App.vue          # Root component (sidebar layout)
│   ├── main.js          # App entry (router + global styles)
│   └── style.css        # Global CSS variables & base styles
├── index.html           # HTML entry
├── package.json         # Dependency config
├── vite.config.js       # Vite build config
├── eslint.config.js     # ESLint config
└── stylelint.config.cjs # Stylelint config
```

## Prerequisites

| Dependency | Version              | Description     |
| ---------- | -------------------- | --------------- |
| Node.js    | 24+                  | Runtime         |
| npm        | Bundled with Node.js | Package manager |

## Installation & Launch

Run these commands from `frontend/`. The [main README](../README_EN.md#-quick-start) covers the Conda environment, currently using Node.js 25.

```bash
# Include ESLint, which is also used by backend EduViz validation
npm install --include=dev

# Dependencies for the Explore pre-build step
npm --prefix ../examples/Magic_English_Town install
npm --prefix ../examples/chemastry_lab install

# Development mode (port 5173)
npm run dev

# Production build
npm run build

# Preview production build
npm run preview
```

`npm run dev` and `npm run build` first build local Explore experiences from [the catalog](../examples/explore-catalog.json). Install the experience dependencies above before starting either command.

Development requests to `/api` and `/files` are proxied to `http://localhost:8080`; see [vite.config.js](vite.config.js). Production hosting needs its own API forwarding. `npm run preview` previews built assets and does not start the backend.

## Core Dependencies

| Package    | Version | Purpose                      |
| ---------- | ------- | ---------------------------- |
| vue        | ^3.5    | UI framework                 |
| vue-router | ^4.6    | Route management             |
| marked     | ^18.0   | Markdown rendering           |
| katex      | ^0.16   | LaTeX math formula rendering |
| dompurify  | ^3.3    | HTML sanitization            |
| pdfjs-dist | ^5.6    | PDF file rendering           |
| pdf-lib    | ^1.17   | PDF file manipulation        |

## Pages

| Page              | Route        | Features                                                               |
| ----------------- | ------------ | ---------------------------------------------------------------------- |
| Login             | `/login`     | Multi-method login (email / GitHub / WeChat)                           |
| AI Tutoring       | `/chat`      | Interactive tutoring conversations                                     |
| Today's Learning  | `/dashboard` | Personalized study plan, learning heatmap, nodes due for review        |
| Knowledge Graph   | `/graph`     | Force-directed graph visualization, node details, mastery display      |
| Knowledge Base    | `/knowledge` | Legacy route; redirects to `/graph`                                    |
| Quiz              | `/quiz`      | Multi-type quizzes (MCQ / fill-in-the-blank / true-false / open-ended) |
| Documents         | `/documents` | Document upload & knowledge extraction                                 |
| Learning History  | `/sessions`  | Historical session list                                                |
| Daily Brief       | `/brief`     | AI-generated daily learning news                                       |
| Profile           | `/profile`   | User profile & learning statistics                                     |
| Settings          | `/settings`  | LLM configuration, system settings                                     |
| Landing           | `/`          | Public introduction                                                    |
| Explore           | `/explore`   | Independent interactive learning experiences                           |
| Immersive courses | `/immersive` | Chapter materials, narration and exercises                             |
| WeChat assistant  | `/weclaw`    | WeClaw binding and channel management                                  |

Routes use hash history: `/chat` is accessed as `http://localhost:5173/#/chat`. The landing and login pages are public; learning pages require sign-in.

## Features

- **SSE Streaming Conversations** — Real-time AI responses with Markdown + LaTeX + code highlighting
- **HTML Knowledge Cards** — Displays backend-normalized HTML cards in an iframe, with formulas and illustrations
- **EduViz Interactive Visualization** — iframe-sandboxed Agent-generated educational visualizations (algorithm demos, parameter exploration, etc.)
- **Quiz Cards** — Inline multi-type quizzes with instant feedback and grading
- **Immersive Learning** — Progressive multi-chapter slide presentation with audio playback
- **Knowledge Graph Visualization** — Force-directed graph + 3D mastery display
- **Agent Transparency** — Displays Agent thinking process and tool call details
- **Dark Theme** — Light / dark theme switching
- **Leave Confirmation** — Confirmation prompt when leaving during generation to prevent accidental interruption
- **Responsive Layout** — Optimized for desktop browsers

## Streaming generation and rendering

| Entry                           | Transport / result                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Tutoring tools                  | `/api/sessions/{session_id}/chat/stream` sends SSE tool progress and final results                                  |
| Direct HTML card generation     | `/api/cards/generate-html` sends SSE progress and results                                                           |
| Direct visualization generation | `/api/viz/generate` returns JSON `{ok, viz_id, error}` after consuming the backend tool stream                      |
| Saved content                   | `/api/documents/{id}/raw` reads the main file; `/asset/{asset_path}` reads companion assets under the same document |

[HtmlCard.vue](src/components/HtmlCard/HtmlCard.vue) loads the generated document into an iframe. [VizCard.vue](src/components/VizCard/VizCard.vue) loads JavaScript for [EduVizSandbox.vue](src/components/EduViz/EduVizSandbox.vue), which injects the SDK and sandbox template.

EduViz renders at an internal width of approximately 900px and scales the whole frame to fit the card. It waits for both execution readiness and dimensions before displaying the content. Runtime errors are shown in the card, and theme changes are sent into the iframe. A backend 600px reflow warning is advisory; changing that viewport is not how the host adapts to a narrow card.

Changing SDK APIs also requires updating [CORE.md](../backend/agents/prompts/skills/eduviz_sdk/CORE.md), [the registry](../backend/agents/tools/viz_registry.py) and relevant browser checks. Keep frontend assets and backend validation on the same version. See [backend validation and limitations](../backend/README_EN.md#content-generation-tools).

## Checks and troubleshooting

From `frontend/`:

```bash
npm run validate:examples
npx eslint src/components/EduViz/EduVizSandbox.vue src/components/EduViz/sandboxTemplate.js src/components/EduViz/eduviz-sdk.js
```

- If Explore builds report missing Vite, install dependencies in the corresponding experience directory.
- If API calls fail, check the backend health endpoint and development proxy or production reverse proxy.
- For blank visualizations, inspect the card error and browser console; regeneration and retrying the existing code are different actions.
- Browser regression commands and Chromium installation are in the [backend guide](../backend/README_EN.md#validation).

## Development Guidelines

- ESLint + Prettier code formatting
- Stylelint CSS linting
- Components use `<script setup>` Composition API
- CSS variables for unified theme color management
