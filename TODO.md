# Copartner v2.0 — Implementation TODO

**Legend**: `[ ]` = Not started, `[-]` = In progress, `[x]` = Done, `[~]` = Blocked

---

## Week 1: Ambient Bar Foundation

### Day 1 — Tauri Frameless Bar
- [ ] Create new Tauri window config: frameless, always-on-top, 40px height, full width
- [ ] Set window position: top of screen
- [ ] Add drag support for bar repositioning
- [ ] Configure opacity transitions (30% idle → 100% active)
- [ ] Glassmorphism background style
- [ ] Test: bar stays on top of all windows

### Day 2 — Bar UI Components
- [ ] Play/Stop toggle button (left side)
- [ ] Scrolling status text component (center)
- [ ] Error badge (red circle with count)
- [ ] Glow indicator with animations:
  - [ ] Dim state (idle monitoring)
  - [ ] Pulse animation (processing)
  - [ ] Red pulse (urgent issue)
- [ ] Expand button → opens dashboard

### Day 3 — WebSocket Bridge (Port Existing)
- [ ] Port WebSocket client from old App.tsx
- [ ] Add new message types:
  - [ ] `ambient_status` — current analysis state
  - [ ] `urgency_alert` — interrupt notification
  - [ ] `voice_notify` — trigger TTS
- [ ] Keep existing types: stream, tools, memory, files, budget

### Day 4 — Auto-Expand Behavior
- [ ] Animate bar height: 40px → 600px on urgent alert
- [ ] Voice notification hook (Cartesia TTS integration placeholder)
- [ ] Escape key → collapse bar
- [ ] Click minimize → collapse bar
- [ ] Dashboard layout: chat left, context stream right

### Day 5 — Integration + Testing
- [ ] End-to-end test: mock alert → bar expands → shows content
- [ ] Test opacity transitions
- [ ] Test play/stop toggle
- [ ] Test window always-on-top behavior
- [ ] **Week 1 Deliverable**: Working ambient bar

---

## Week 2: Context Engine

### Day 1 — Screen Capture Pipeline
- [ ] `mss` capture loop (5s interval)
- [ ] PIL diff detection (>10% threshold)
- [ ] Rolling screenshot buffer (last 50 frames)
- [ ] Performance: <200ms per capture cycle

### Day 2 — OCR (easyocr)
- [ ] Install and configure easyocr
- [ ] Extract text + bounding boxes from screenshots
- [ ] OCR result caching (skip if no screen change)
- [ ] Return structured: `{text, regions: [{text, bbox}]}`

### Day 3 — App Detection
- [ ] `pygetwindow` integration
- [ ] Parse active window: app name + document title
- [ ] Classify: IDE vs Browser vs Terminal vs Other
- [ ] Store in session context

### Day 4 — Codebase Indexer (tree-sitter)
- [ ] Install tree-sitter + language parsers
- [ ] Index project: functions, classes, imports, types
- [ ] Watch file changes (enhanced IDEWatcher)
- [ ] Query API: "find function X", "find imports of Y"

### Day 5 — Terminal Parser + Session Memory
- [ ] Regex error patterns for TS, Python, Rust
- [ ] SQLite session memory schema
- [ ] Time-decayed recent files/actions/errors
- [ ] Context builder: assemble unified context object
- [ ] **Week 2 Deliverable**: Context object populated

---

## Week 3: Ambient Brain

### Day 1 — Urgency Scorer
- [ ] Score mapping (see IMPLEMENTATION_PLAN.md)
- [ ] Time decay for old events
- [ ] Level thresholds (L1-L4)
- [ ] Test with simulated events

### Day 2 — Intent Classifier
- [ ] gemini-3.1-flash-lite integration
- [ ] Classify: coding, debugging, researching, writing, idle
- [ ] Confidence scoring
- [ ] Cache recent classifications

### Day 3 — Action Planner
- [ ] Action types: notify, suggest, demonstrate, fix
- [ ] Destructive vs non-destructive detection
- [ ] Confirmation logic for destructive actions
- [ ] Action history tracking

### Day 4 — Interruption Manager
- [ ] DND mode respect
- [ ] Cooldown: max 1 interrupt per 60s
- [ ] Learning from dismissals
- [ ] Safety: L4 always interrupts

### Day 5 — Integration
- [ ] Context Engine → Brain → Bar UI
- [ ] Test: IDE type error → detect → glow → voice
- [ ] Test: Build fail → expand → show error
- [ ] **Week 3 Deliverable**: Proactive intelligence working

---

## Week 4: Voice Integration (Cartesia)

### Day 1 — Cartesia TTS (Sonic 3.5)
- [ ] Install `cartesia[websockets]`
- [ ] WebSocket TTS client
- [ ] Voice selection (Katie/Jameson)
- [ ] PCM audio playback (sounddevice)

### Day 2 — Cartesia STT (Ink 2)
- [ ] WebSocket STT client
- [ ] Turn detection integration
- [ ] Microphone input stream
- [ ] Transcript event handling

### Day 3 — Voice Commands
- [ ] Keyword detection: "Copartner, ..."
- [ ] Command parser
- [ ] Map to actions: fix, explain, stop, show
- [ ] Test command recognition

### Day 4 — Voice Notifications
- [ ] Concise notification text generation
- [ ] Stream to TTS on interrupt
- [ ] Priority: L3 whisper, L4 full voice
- [ ] Test: error → voice notification

### Day 5 — Listening Modes
- [ ] Continuous listening (ambient ON)
- [ ] Push-to-talk toggle
- [ ] Mic visual indicator
- [ ] **Week 4 Deliverable**: Voice interaction working

---

## Week 5: Computer Use

### Day 1 — Mouse Controller
- [ ] pyautogui wrapper
- [ ] Smooth movement animation
- [ ] Click, right-click, scroll
- [ ] Screen bounds safety

### Day 2 — Keyboard Injector
- [ ] pynput wrapper
- [ ] Human-like typing (variable interval)
- [ ] Hotkey support (Ctrl+C, etc.)
- [ ] Active window verification

### Day 3 — Screenshot Annotator
- [ ] PIL draw: arrows, boxes, highlights, text
- [ ] Overlay window (Tauri semi-transparent)
- [ ] Annotation positioning logic
- [ ] Clear/timeout annotations

### Day 4 — Guide Mode
- [ ] Mouse guidance to target
- [ ] Tooltip display
- [ ] User click detection
- [ ] Cancel on user mouse movement

### Day 5 — Show + Auto Modes
- [ ] Show mode: annotate screenshot → overlay
- [ ] Auto mode: execute sequence with confirmation
- [ ] Confirmation UI component
- [ ] End-to-end demo: fix TS error
- [ ] **Week 5 Deliverable**: Computer use working

---

## Week 6: Smart Router + Polish

### Day 1 — Smart Model Router
- [ ] Task classifier (local + flash-lite)
- [ ] Model selection table
- [ ] Cost tracking per call (SQLite)
- [ ] Budget enforcement + fallback chains

### Day 2 — Cost Dashboard
- [ ] Bar cost widget
- [ ] Detailed cost breakdown view
- [ ] Budget alerts (80%, 100%)
- [ ] Model switch notifications

### Day 3 — Integration Testing
- [ ] Full flow test: error → detect → notify → guide → fix
- [ ] All interruption levels
- [ ] DND mode test
- [ ] Budget exhaustion test
- [ ] Performance: <2s detection→notification

### Day 4 — Settings Panel
- [ ] Bar position (top/bottom)
- [ ] Opacity, threshold, cooldown
- [ ] DND toggle
- [ ] Computer use default mode
- [ ] Voice mode (continuous/PTT)
- [ ] Budget limit

### Day 5 — Polish + Demo Prep
- [ ] Error handling: graceful failures
- [ ] Structured logging
- [ ] First-run onboarding
- [ ] Demo script (3 scenarios)
- [ ] **Week 6 Deliverable**: Demo-ready MVP

---

## Backlog (Post-MVP)

- [ ] Multi-workspace support
- [ ] Chat export (PDF/Markdown)
- [ ] Keyboard shortcuts reference
- [ ] Mobile/responsive layout
- [ ] Plugin system for custom tools
- [ ] Team collaboration features
- [ ] Cloud sync for memory/settings

---

*Last updated: 2026-05-27*  
*Current: Starting Week 1, Day 1*
