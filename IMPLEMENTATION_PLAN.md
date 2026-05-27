# Copartner v2.0 — Ambient-First Implementation Plan

**Status**: Week 1 In Progress  
**Started**: 2026-05-27  
**Target MVP**: 2026-07-08 (6 weeks)  
**Competition Deadline**: Gemini XPRIZE — August 17, 2026

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AMBIENT BAR (Tauri, always-on-top)                  │
│  [▶/⏸] │ Status: "Analyzing VS Code + Chrome" │ Errors: 2 │ 🔴 Think      │
│                              ↓ Click to expand                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Dashboard: Chat | Context Stream | Actions | Voice | Settings        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ WebSocket (ws://127.0.0.1:8765)
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PYTHON AMBIENT BRAIN                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │Context Engine│  │Ambient Brain │  │Computer Use  │  │Smart Router  │   │
│  │              │  │              │  │              │  │              │   │
│  │• Screen OCR  │  │• Urgency     │  │• Mouse       │  │• Task Class  │   │
│  │• App Detect  │  │• Intent      │  │• Keyboard    │  │• Cost Track  │   │
│  │• Code Index  │  │• Action Plan │  │• Annotate    │  │• Budget Enf  │   │
│  │• Terminal    │  │• Interrupt   │  │• Guide/Show  │  │• Fallback    │   │
│  │• Session Mem │  │• Proactive   │  │• Auto        │  │              │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Voice Engine (Cartesia)                                             │   │
│  │  TTS: Sonic 3.5 WebSocket ──→ Real-time speech (90ms latency)      │   │
│  │  STT: Ink 2 WebSocket ──────→ Continuous listening + turn detect   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Principles

1. **Ambient-First**: AI watches continuously, builds context, interrupts intelligently
2. **Show, Don't Tell**: Mouse guidance, screenshot annotation, not text dumps
3. **Voice-Native**: Cartesia TTS/STT for natural spoken interaction
4. **Cost-Conscious**: Smart router minimizes API spend (~$3-5/day target)
5. **User in Control**: Play/Stop ambient, confirmation for destructive actions

---

## Week-by-Week Plan

### Week 1: Ambient Bar Foundation

**Goal**: Replace Spotlight with an always-visible ambient bar

#### Day 1-2: Tauri Frameless Bar
- [ ] Create new Tauri window: frameless, always-on-top, height 40px, full width
- [ ] Position: top of screen, z-index above all windows
- [ ] Drag support (move bar if needed)
- [ ] Opacity: 100% active, 30% idle (configurable)
- [ ] Background: dark glassmorphism (`rgba(6,6,6,0.85)` + `backdrop-filter: blur`)

#### Day 3: Bar UI Components
- [ ] Play/Stop button (left) — toggle ambient monitoring
- [ ] Status text (center) — scrolling/marquee showing current analysis
- [ ] Error badge — red circle with count
- [ ] Glow indicator (right) — animated pulse showing AI state
  - Dim = idle
  - Pulse = processing
  - Red = urgent
- [ ] Expand button — click to open full dashboard

#### Day 4: WebSocket Bridge (reuse current)
- [ ] Port existing WebSocket client from old App.tsx
- [ ] Message types for bar: `ambient_status`, `urgency_alert`, `voice_notify`
- [ ] Keep all existing message types (stream, tools, memory, files)

#### Day 5: Auto-Expand + Voice Hook
- [ ] On `urgency_alert` with score > 80: animate bar height 40px → 600px
- [ ] Trigger voice notification via Cartesia TTS
- [ ] Press Escape or click minimize → collapse back to 40px
- [ ] Full dashboard layout (chat on left, context stream on right)

**Deliverable**: Bar stays on top, shows live status, expands on urgent issues

---

### Week 2: Context Engine

**Goal**: AI "sees" the user's screen, code, and environment continuously

#### Day 1: Screen Capture Pipeline
- [ ] `mss` capture loop (5s interval when ambient ON)
- [ ] PIL diff detection: compare current vs last frame
- [ ] Trigger threshold: >10% pixel change → process
- [ ] Save screenshots to `data/screenshots/` (rolling buffer, keep last 50)

#### Day 2: OCR (easyocr)
- [ ] Install `easyocr` (or `rapidocr` if too slow)
- [ ] Extract visible text from screenshots
- [ ] Cache OCR results (don't re-OCR if screen hasn't changed)
- [ ] Return: `{text: str, regions: [{text, bbox}]}`

#### Day 3: App Detection + Window Title
- [ ] `pygetwindow` to get active window title
- [ ] Parse: "AppName — Document.ext"
- [ ] Detect IDE (VS Code, PyCharm, etc.) vs Browser vs Terminal
- [ ] Store: `{app: str, window_title: str, is_ide: bool, is_browser: bool}`

#### Day 4: Codebase Indexer (tree-sitter)
- [ ] Install `tree-sitter`, language parsers (typescript, python, rust)
- [ ] Index project files: functions, classes, imports, exports
- [ ] Watch file changes (improved from current IDEWatcher)
- [ ] Query: "find all functions named X", "find imports of Y"

#### Day 5: Terminal Parser + Session Memory
- [ ] Parse common error patterns: TypeScript, Python traceback, Rust compiler
- [ ] Regex for: `error TS\d+`, `File "...", line \d+`, etc.
- [ ] SQLite session memory: recent files, errors, actions (time-decayed)
- [ ] Context builder: assemble unified context object for Brain

**Deliverable**: Context object contains: screen text, active app, codebase state, recent errors, session history

---

### Week 3: Ambient Brain

**Goal**: AI thinks proactively, interrupts intelligently

#### Day 1: Urgency Scorer
- [ ] Score events 0-100:
  - Build failure: +50
  - Runtime crash: +40
  - New type error: +20
  - Existing type error: +5
  - Unused import: +2
  - Repeated error ×3: +15
  - User switching apps rapidly: +10
- [ ] Time decay: old events lose score over time
- [ ] Thresholds: 0-20 (L1), 20-50 (L2), 50-80 (L3), 80-100 (L4)

#### Day 2: Intent Classifier
- [ ] Use gemini-3.1-flash-lite (cheapest)
- [ ] Input: Context object + recent actions
- [ ] Output: `{intent: str, confidence: float, expected_action: str}`
- [ ] Intents: coding, debugging, researching, writing, browsing, idle

#### Day 3: Action Planner
- [ ] Based on intent + urgency, pick action type:
  - `notify`: Update bar status
  - `suggest`: Glow + "Want me to fix?"
  - `demonstrate`: Move mouse, annotate screen
  - `fix`: Auto-apply (requires confirmation if destructive)
- [ ] Action confirmation: non-destructive = auto, destructive = prompt

#### Day 4: Interruption Manager
- [ ] Respect user DND mode (toggled via bar)
  - L1-L2: Silenced (no voice, no expand)
  - L3: Visual only (glow, no voice)
  - L4: Always notify (safety critical)
- [ ] Cooldown: max 1 interruption per 60s (configurable)
- [ ] Learning: track user dismissals, reduce similar suggestions

#### Day 5: Proactive Pipeline Integration
- [ ] Wire Context Engine → Ambient Brain → Bar UI
- [ ] Test: Open VS Code with type error → bar glows → voice notification
- [ ] Test: Build fails → bar auto-expands → shows error + suggestion

**Deliverable**: AI proactively detects issues and interrupts appropriately

---

### Week 4: Voice Integration (Cartesia)

**Goal**: Natural spoken interaction via Sonic 3.5 + Ink 2

#### Day 1: Cartesia TTS Client (Sonic 3.5)
- [ ] Install `cartesia[websockets]` Python package
- [ ] Create `voice/cartesia_tts.py`:
  - WebSocket connection manager
  - Context-based streaming (continuations)
  - Voice: Katie (f786b574-daa5-4673-aa0c-cbe3e8534c02) or Jameson
  - Output: PCM f32le, 44100Hz
- [ ] Play audio via Tauri or Python `sounddevice`/`pyaudio`

#### Day 2: Cartesia STT Client (Ink 2)
- [ ] Create `voice/cartesia_stt.py`:
  - WebSocket connection to `/stt/turns/websocket`
  - Built-in turn detection (no VAD needed)
  - Stream mic audio (16kHz, 16-bit PCM)
  - Receive transcript events
- [ ] Use `sounddevice` for microphone input

#### Day 3: Voice Commands
- [ ] Map spoken commands to actions:
  - "Copartner, fix this" → trigger fix action
  - "Copartner, what is this error?" → explain current error
  - "Copartner, stop" → pause ambient mode
  - "Copartner, show me" → expand bar
- [ ] Command parser: keyword detection + intent classification

#### Day 4: Voice Notifications
- [ ] When L3/L4 interrupt: generate concise notification text
- [ ] Examples:
  - "Build failed in App.tsx, line 45"
  - "Type error: property name doesn't exist on User"
  - "I've noticed three unused imports"
- [ ] Stream to Cartesia TTS → play immediately

#### Day 5: Continuous Listening + Push-to-Talk
- [ ] When ambient ON: continuous STT listening
- [ ] Push-to-talk mode: hold bar button to speak (privacy)
- [ ] Toggle between modes in settings
- [ ] Visual indicator: mic icon pulses when listening

**Deliverable**: Speak to Copartner, it speaks back, understands commands

---

### Week 5: Computer Use

**Goal**: AI moves mouse, annotates screen, guides user

#### Day 1: Mouse Controller (pyautogui)
- [ ] `action/computer_use/mouse.py`:
  - `move_to(x, y, duration=0.5)` — smooth movement
  - `click(x, y)` — left click
  - `right_click(x, y)`
  - `scroll(lines, x, y)`
  - Safety: clip to screen bounds, don't move if user is actively typing

#### Day 2: Keyboard Injector (pynput)
- [ ] `action/computer_use/keyboard.py`:
  - `type_text(text, interval=0.01)` — human-like typing
  - `press_hotkey(*keys)` — Ctrl+C, Ctrl+V, etc.
  - Safety: only type in confirmed windows (check active window matches target)

#### Day 3: Screenshot Annotator (PIL)
- [ ] `action/computer_use/annotate.py`:
  - `draw_arrow(img, start, end, color="red")`
  - `draw_box(img, bbox, color="red", label="")`
  - `draw_highlight(img, bbox, color="yellow")`
  - `draw_text(img, text, position, color="white")`
- [ ] Overlay: semi-transparent Tauri window showing annotation

#### Day 4: Guide Mode Implementation
- [ ] Given target (x, y), move mouse there smoothly
- [ ] Show tooltip: "Click here to add the missing property"
- [ ] Wait for user click, then proceed
- [ ] If user moves mouse elsewhere, cancel guidance

#### Day 5: Show Mode + Auto Mode
- [ ] Show mode: capture screen → annotate → display in overlay
- [ ] Auto mode: execute sequence (move → click → type) with confirmation
- [ ] Confirmation UI: "Copartner wants to type 'name: string'. Allow? [Yes] [No]"
- [ ] Demo: Fix TypeScript error end-to-end (detect → annotate → guide → confirm)

**Deliverable**: AI can guide mouse, annotate screens, and perform actions

---

### Week 6: Smart Router + Integration + Polish

**Goal**: Cost optimization, integration, demo-ready

#### Day 1: Smart Model Router
- [ ] `core/smart_router.py`:
  - Task classifier (local heuristics + flash-lite fallback)
  - Model selection table (see architecture)
  - Cost tracking per call (store in SQLite)
  - Budget enforcement: daily limit, per-model limit
  - Fallback chains: Pro exhausted → Flash → Flash-lite → Local only

#### Day 2: Cost Dashboard
- [ ] Bar widget: "$3.20 / $5.00 today"
  - Color: green (<50%), yellow (50-80%), red (>80%)
- [ ] Detailed view: breakdown by model, by hour
- [ ] Alerts: "Budget at 80%", "Switched to Flash-lite to save cost"

#### Day 3: Integration Testing
- [ ] Full flow: Type error in IDE → detect → classify → plan → voice notify → expand → guide mouse → fix
- [ ] Test all interruption levels
- [ ] Test DND mode
- [ ] Test budget exhaustion fallback
- [ ] Performance: ensure <2s from error detection to voice notification

#### Day 4: Settings Panel
- [ ] Bar position: top/bottom (top default)
  - Opacity: 30-100% (30% default idle)
  - Auto-expand threshold: 50-100 (80 default)
  - Interruption cooldown: 30-300s (60 default)
  - DND mode toggle
  - Computer use default: Guide/Show/Auto (Guide default)
  - Voice: continuous listening vs push-to-talk
  - Budget limit: $1-20/day ($5 default)

#### Day 5: Polish + Demo Prep
- [ ] Error handling: graceful failures for all components
- [ ] Logging: structured logs for debugging
- [ ] First-run onboarding: "Hi, I'm Copartner. I'll watch your screen and help. Click play to start."
- [ ] Demo script: 3 scenarios (coding error, proactive suggestion, voice command)

**Deliverable**: Demo-ready ambient AI partner

---

## File Structure

```
Copartner/
├── app/                          # Tauri frontend
│   ├── src/
│   │   ├── main.tsx              # Entry point
│   │   ├── AmbientBar.tsx        # NEW: 40px always-on-top bar
│   │   ├── Dashboard.tsx         # NEW: expanded dashboard
│   │   ├── VoiceControls.tsx     # NEW: mic button, TTS/STT status
│   │   ├── ChatPanel.tsx         # ADAPT: existing chat
│   │   ├── ContextStream.tsx     # NEW: live context feed
│   │   ├── ActionPanel.tsx       # NEW: computer use confirmations
│   │   ├── SettingsPanel.tsx     # NEW: configuration
│   │   └── App.css               # Global styles
│   └── src-tauri/
│       ├── Cargo.toml
│       ├── tauri.conf.json       # Frameless window config
│       └── src/main.rs           # Always-on-top, global shortcut
│
├── core/                         # Python backend
│   ├── copartner_server.py       # ADAPT: WebSocket server
│   ├── thought_controller.py     # ADAPT: reasoning loop
│   ├── smart_router.py           # NEW: cost-optimized model routing
│   ├── ambient_brain.py          # NEW: urgency + intent + planner
│   ├── intent_router.py          # KEEP: existing (enhance)
│   ├── token_budget.py           # KEEP: existing (enhance)
│   ├── gemini_client.py          # KEEP: existing
│   └── tool_executor.py          # ADAPT: add computer_use tags
│
├── context/                      # NEW: Context Engine
│   ├── __init__.py
│   ├── screen_analyzer.py        # mss + PIL diff + OCR
│   ├── app_detector.py           # pygetwindow
│   ├── codebase_indexer.py       # tree-sitter indexing
│   ├── terminal_parser.py        # Error pattern regexes
│   └── session_memory.py         # SQLite context store
│
├── voice/                        # NEW: Cartesia Integration
│   ├── __init__.py
│   ├── cartesia_tts.py           # Sonic 3.5 WebSocket client
│   ├── cartesia_stt.py           # Ink 2 WebSocket client
│   ├── voice_manager.py          # Orchestrates TTS/STT
│   └── audio_player.py           # PCM playback (sounddevice)
│
├── action/                       # ADAPT: Existing + new
│   ├── file_ops.py               # KEEP: safe file CRUD
│   ├── shell_executor.py         # KEEP: sandboxed shell
│   ├── code_scaffolder.py        # KEEP: project scaffolding
│   └── computer_use/             # NEW: GUI automation
│       ├── __init__.py
│       ├── mouse.py              # pyautogui wrapper
│       ├── keyboard.py           # pynput wrapper
│       ├── annotate.py           # PIL screenshot annotation
│       └── safety.py             # Confirmation dialogs, bounds checking
│
├── memory/                       # KEEP: ChromaDB memory
│   └── memory_manager.py
│
├── perception/                   # ADAPT: Enhanced watchers
│   ├── screen_observer.py        # ADAPT: use context/screen_analyzer
│   └── ide_watcher.py            # ADAPT: use context/codebase_indexer
│
├── data/                         # Runtime data
│   ├── screenshots/              # Rolling screenshot buffer
│   ├── memory_store/             # ChromaDB persistence
│   ├── session.db                # SQLite session memory
│   ├── cost_log.db               # SQLite cost tracking
│   └── chat_history.jsonl        # Chat persistence
│
├── config/
│   └── prompts/
│       └── system.yaml           # ADAPT: ambient-first system prompt
│
├── .env                          # API keys (gitignored)
├── IMPLEMENTATION_PLAN.md        # This file
├── TODO.md                       # Task tracking
└── requirements.txt              # Updated dependencies
```

---

## Dependencies

### Python (add to requirements.txt)

```
# Core
google-genai>=1.0.0
websockets>=12.0
pyyaml>=6.0
python-dotenv>=1.0.0

# Context Engine
mss>=9.0
easyocr>=1.7.0
Pillow>=10.0.0
pygetwindow>=0.0.9
tree-sitter>=0.20.0
tree-sitter-python>=0.20.0
tree-sitter-typescript>=0.20.0
tree-sitter-rust>=0.20.0

# Voice (Cartesia)
cartesia[websockets]>=1.0.0
sounddevice>=0.4.6
numpy>=1.24.0

# Computer Use
pyautogui>=0.9.54
pynput>=1.7.6

# Data
chromadb>=0.4.0
sqlite3

# Existing (keep)
openai>=1.0.0
requests>=2.31.0
```

### Rust/Tauri (Cargo.toml)

Keep existing. Add if needed:
- Global shortcut (already configured for Ctrl+Space)
- Always-on-top window flag

---

## Model Cost Reference

| Model | Input | Output | Use Case |
|-------|-------|--------|----------|
| gemini-3.1-flash-lite | $0.25/M | $1.50/M | Classification, quick tasks |
| gemini-2.5-flash | $0.30/M | $2.50/M | Error analysis, reasoning |
| gemini-3.5-flash | $1.50/M | $9.00/M | Complex coding, debugging |
| gemini-3.1-pro-preview | $2.00/M | $12.00/M | Deep architecture |
| Cartesia Sonic 3.5 | 15 credits/sec | — | Voice notifications |
| Cartesia Ink 2 | 1 credit/sec | — | Speech recognition |

**Cartesia Pricing** (Pro plan = $4/month, 100K credits):
- TTS: ~111 minutes of speech per month
- STT: ~27.7 hours of listening per month
- Cost: ~$0.001/sec TTS, ~$0.0001/sec STT

**Daily Budget Target**: $5.00
- ~$2.00 Gemini (flash-lite + flash)
- ~$2.00 Gemini (flash + occasional pro)
- ~$0.50 Cartesia voice
- ~$0.50 Buffer

---

## Safety & Permissions

| Action | Default | Confirmation |
|--------|---------|--------------|
| File read | Auto | None |
| File write | Auto | None (non-destructive) |
| File overwrite | Blocked | Always prompt |
| Shell exec | Blocked | Always prompt (whitelist only) |
| Mouse move | Guide mode | None |
| Mouse click | Guide mode | User clicks |
| Keyboard type | Auto | Prompt if >50 chars or destructive |
| Delete file | Blocked | Always prompt |

---

## Success Criteria

By end of Week 6, Copartner should:

1. ✅ Stay as a thin bar at the top of screen, always visible
2. ✅ Continuously monitor screen, code, and terminal
3. ✅ Detect errors within 5 seconds of occurrence
4. ✅ Proactively notify via voice + visual when issues found
5. ✅ Guide mouse to problematic code with annotations
6. ✅ Understand voice commands ("fix this", "what's wrong")
7. ✅ Respond via natural voice (Sonic 3.5)
8. ✅ Stay under $5/day API cost
9. ✅ Never act destructively without confirmation
10. ✅ Feel like a partner, not a chatbot

---

## Notes

- **This is a rebuild, not an extension.** The chat-first UI and simple proactive heuristics are replaced entirely.
- **Reusable components:** WebSocket bridge, file_ops, shell_executor, memory_manager, gemini_client will be adapted but kept.
- **Testing strategy:** Each week ends with a manual test of that week's deliverable. Week 6 is full integration testing.
- **Competition angle:** The ambient, proactive, voice-native experience is the differentiator for Gemini XPRIZE.

---

*Plan created: 2026-05-27*  
*Next: Start Week 1, Day 1*
