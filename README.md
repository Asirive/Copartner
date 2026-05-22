# 🪐 Asirive Copartner

[![Gemini API](https://img.shields.io/badge/Brain-Gemini%202.5%20Pro%20%2F%20Flash-blueviolet?style=for-the-badge&logo=google-gemini&logoColor=white)](https://ai.google.dev/)
[![Tauri App](https://img.shields.io/badge/Framework-Tauri%20%26%20Rust-orange?style=for-the-badge&logo=tauri&logoColor=white)](https://tauri.app/)
[![Google Cloud Run](https://img.shields.io/badge/Cloud-Google%20Cloud%20Run-blue?style=for-the-badge&logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/License-Apache%202.0-green?style=for-the-badge)](LICENSE)

> **"Empower the Human."** Asirive Copartner is an ambient, OS-level AI harness that serves as a **Universal Semantic Bus**. It operates across any application, eliminating mechanical execution friction so a single human architect can work with the output capacity of an entire creative studio.

Built for the **Build with Gemini XPRIZE**, Copartner is a self-contained AI companion designed to observe, learn your behavioral style, and execute tasks autonomously through deep API integration, structured protocols, and direct computer control.

---

## 👁️ Core Philosophy: One Human, Infinite Studio

Most AI assistants are chatbots trapped in browser tabs or IDE sidebars. **Copartner is different.** It operates ambiently on your system, watching file changes, observing the screen state when you switch apps, and learning your creative and technical workflow style to offer proactive, self-learning automated help.

*   **Not a Replacement, an Exosuit**: Copartner handles low-level execution (scaffolding, file edits, testing, deployments, invoicing) so you can focus entirely on high-level architecture.
*   **Zero Glaze, Pure Weight**: Intrinsic reasoning and episodic memory, not prompt hacks. We leverage the SNAP-C1 architecture heritage—a System 2 recursive thought controller and a 4-tier vector memory hippocampus—coupled with the multi-model intelligence of **Gemini 2.5 Pro & Flash**.

---

## 🏗️ The Three-Layer Interaction Architecture

To operate seamlessly across all your daily apps (VS Code, Chrome, Terminal, Canva, Figma, etc.), Copartner employs a smart-escalating three-layer interaction system:

```
                  ┌──────────────────────────────────────────┐
                  │          ASIRIVE COPARTNER               │
                  └────────────────────┬─────────────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
      ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
      │  LAYER 1: MCP     │  │  LAYER 2: APIs    │  │  LAYER 3: DESKTOP │
      │  (Model Context)  │  │  (Connectors)     │  │  (Computer Use)   │
      ├───────────────────┤  ├───────────────────┤  ├───────────────────┤
      │ • Filesystem      │  │ • Stripe          │  │ • Screen Observer │
      │ • GitHub          │  │ • Vercel          │  │ • Vision Analyzer │
      │ • Brave Search    │  │ • Cloud Run       │  │ • pyautogui mouse │
      └───────────────────┘  └───────────────────┘  └───────────────────┘
```

1.  **Model Context Protocol (Layer 1 - Structured)**: Highly structured, ultra-fast local actions. Uses standard MCP servers to read/write directories, search GitHub, and query live web data.
2.  **Custom Connectors (Layer 2 - Direct APIs)**: Integrated triggers for external services. Includes Vercel for instant deployments, Google Cloud Run for container hosting, and Stripe for client invoicing and revenue tracking.
3.  **Desktop Computer Use (Layer 3 - Universal Visual)**: The universal fallback. When an app has no API (like Photoshop or local software), Copartner captures screenshots at key events, understands the UI using **Gemini Vision**, and executes mouse clicks and keyboard commands safely.

---

## 🧠 Brain Architecture (The SNAP-C1 Nervous System)

Copartner's cognitive engine is built on the proven architectural concepts of SNAP-C1, rewired for the Gemini API ecosystem:

*   **Recursive Thought Controller (System 2)**: An autonomous state machine (`Idle` ➔ `Thinking` ➔ `Researching` ➔ `Action` ➔ `Reflection` ➔ `Answering`) that enforces convergence pressure and prevents infinite execution loops.
*   **The Hippocampus (4-Tier Vector Memory)**: Powered by ChromaDB and Gemini Embeddings:
    1.  *Semantic Memory*: Long-term facts, technology concepts, and user information.
    2.  *Episodic Memory*: Structured logs of past sessions and contextual task history.
    3.  *Skill Memory*: Auto-generated executable workflows (`SKILL.md` files) created when Copartner successfully finishes a complex task.
    4.  *Preference Memory*: Learns your code formatting, style profile, and app settings dynamically.
*   **Behavioral Engine (TVM)**: Logs user actions to analyze sequences and proactively predict your next step with style adaptation.

---

## 📁 Repository Structure

```
Copartner/
├── README.md                       # Beautiful visual readme (You are here)
├── requirements.txt                # Python dependencies
├── .env.example                    # Template for API credentials
│
├── core/                           # Cognitive Hub (The Semantic Bus)
│   ├── gemini_client.py            # Gemini 2.5 API wrapper (Pro/Flash/Embeddings)
│   ├── thought_controller.py       # State-machine recursive thought processor
│   ├── intent_router.py            # Routes tasks dynamically to optimal models
│   ├── tool_executor.py            # Sandboxed action and execution controller
│   ├── token_budget.py             # Enforces spending limits and alerts
│   └── skill_learner.py            # Distills completed work traces into reusable skills
│
├── memory/                         # Vector Database Memory System
│   ├── memory_manager.py           # ChromaDB integration (Facts, Episodes, Preferences)
│   ├── behavioral_engine.py        # Logs action graphs and builds style profile
│   └── embeddings.py               # Handles Gemini Embedding generation
│
├── integration/                    # The Three Interaction Layers
│   ├── mcp/                        # Model Context Protocol servers
│   ├── connectors/                 # Stripe, Vercel, and Cloud Run integrations
│   └── computer_use/               # Screenshot pipeline, pyautogui actions, and safety
│
├── perception/                     # Ambient OS Monitoring
│   ├── screen_observer.py          # Screen change captures and event triggers
│   ├── ide_watcher.py              # Directory file watcher (watchdog)
│   └── clipboard_monitor.py        # Clipboard monitor
│
├── app/                            # Beautiful Tauri Desktop App
│   ├── src-tauri/                  # Rust backend (global hotkeys, system tray, IPC)
│   └── src/                        # HTML/CSS/JS frontend (minimalist glassmorphic UI)
│
└── config/                         # System prompts and settings
    └── prompts/
        └── system.yaml             # System 2 Recursive Loop instructions
```

---

## ⚡ Quickstart

### Prerequisites
*   Python 3.11+
*   Node.js & npm (for Tauri frontend)
*   Rust & Cargo (for Tauri backend compilation)
*   A Gemini API Key (set in `.env`)

### Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/Asirive/Copartner.git
    cd Copartner
    ```

2.  **Set up Python Virtual Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables**:
    Copy `.env.example` to `.env` and fill in your Gemini API key:
    ```bash
    cp .env.example .env
    ```

4.  **Run Tauri Desktop App**:
    ```bash
    cd app
    npm install
    npm run tauri dev
    ```

---

## 🏁 The 90-Day Build & Business Roadmap

Our sprint maps directly to the Build with Gemini XPRIZE timeline:

- [ ] **Phase 0 (Days 1-3)**: Project foundation, Gemini API connectivity, landing page release.
- [ ] **Phase 1 (Days 4-14)**: System 2 ThoughtController, memory engine, CLI prototype.
- [ ] **Phase 2 (Days 15-25)**: Screen observer, file system watchers, and behavioral preference cloning.
- [ ] **Phase 3 (Days 26-45)**: Scaffolding, container deployment, Stripe revenue integration, and Computer Use basics.
- [ ] **Phase 4 (Days 46-60)**: Tauri desktop app overlay, system tray client, and model visualizers.
- [ ] **Phase 5 (Days 61-75)**: Stripe invoicing agency production, B2B contract fulfillment.
- [ ] **Phase 6 (Days 76-90)**: Code hardening, performance profiling, video demo creation, and XPRIZE submission.

---

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Developed by <b>Haziq, Founder of Asirive</b> — Singapore. Empowering creators, one studio at a time.
</p>
