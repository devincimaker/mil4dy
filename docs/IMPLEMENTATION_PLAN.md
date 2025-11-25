# AI DJ - Implementation Plan

This document outlines the step-by-step implementation plan for the AI DJ project. Each step is designed to be atomic and testable.

---

## Phase 0: Project Setup

### Step 0.1: Initialize Project Structure ✅

- [x] Create folder structure (`src/`, `public/`, `data/`)
- [x] Initialize `package.json` with TypeScript
- [x] Configure `tsconfig.json`
- [x] Set up ESLint and Prettier
- [x] Add `.gitignore`
- [x] Create initial `README.md`
- [x] Transform `music.json` → `data/library.json` with energy values

**Deliverable**: Empty project that compiles TypeScript, music library ready

---

## Phase 1: Core Backend Foundation ✅

### Step 1.1: Music Library Module ✅

- [x] Create `src/music/types.ts` with `Track` interface
- [x] Create `src/music/library.ts` with `MusicLibrary` class
- [x] Implement `load(path)` to read `library.json`
- [x] Implement `getAll()`, `getById(id)`, `getByEnergyRange(min, max)`
- [ ] Write unit tests for library queries

**Deliverable**: Can load and query track metadata ✅

---

### Step 1.2: Mood Types & Random Detector ✅

- [x] Create `src/mood/types.ts` with `MoodState`, `MoodLevel` types
- [x] Create `src/mood/detector.ts` with abstract `MoodDetector` interface
- [x] Create `src/mood/random-detector.ts` implementing random mood generation
- [x] Random detector should drift gradually (not jump wildly)
- [ ] Write unit tests

**Deliverable**: Can generate plausible random mood states ✅

---

### Step 1.3: Song Selector ✅

- [x] Create `src/selection/selector.ts` with `SongSelector` class
- [x] Implement mood-to-energy mapping
- [x] Implement `selectNext(currentTrack, mood)` method
- [x] Track play history to avoid repeats
- [x] Prefer similar BPM when possible
- [ ] Write unit tests with mock library

**Deliverable**: Given a mood, returns appropriate next track ✅

---

### Step 1.4: HTTP Server Setup ✅

- [x] Install `express` and `ws` (WebSocket)
- [x] Create `src/server/index.ts` as HTTP server entry point
- [x] Serve static files from `public/`
- [x] Create `/api/tracks` endpoint to list all tracks
- [x] Create `/api/tracks/:id/audio` endpoint to stream audio files
- [x] Set up CORS for local development

**Deliverable**: Server runs, can fetch track list and stream audio via HTTP ✅

---

### Step 1.5: WebSocket Communication ✅

- [x] Add WebSocket server to existing HTTP server
- [x] Define message protocol (JSON messages with `type` field)
- [x] Implement server-side message handlers:
  - `mood_update` (receive from browser)
  - `play_track` (send to browser)
  - `status` (send current state to browser)
- [x] Create `src/server/connection.ts` to manage client connections

**Deliverable**: Browser can connect via WebSocket, send/receive messages ✅

---

## Phase 2: Browser Audio Playback ✅

### Step 2.1: Basic HTML Shell ✅

- [x] Create `public/index.html` with minimal structure
- [x] Create `public/styles.css` with basic styling
- [x] Create `public/js/main.js` as entry point
- [x] Add placeholders for: now playing, mood display, camera preview

**Deliverable**: Browser shows basic UI shell ✅

---

### Step 2.2: WebSocket Client ✅

- [x] Create `public/js/websocket.js` for server communication
- [x] Implement auto-reconnect on disconnect
- [x] Implement message send/receive with JSON parsing
- [x] Dispatch custom events for received messages

**Deliverable**: Browser connects to server, logs messages ✅

---

### Step 2.3: Single-Deck Audio Player ✅

- [x] Create `public/js/audio-player.js` using Web Audio API
- [x] Implement `loadTrack(url)` to fetch and decode audio
- [x] Implement `play()`, `pause()`, `stop()`
- [x] Implement volume control
- [x] Track playback position and duration
- [x] Emit events: `ended`, `timeupdate`
- [x] Display current track info in UI

**Deliverable**: Can play a single track from server, shows progress ✅

---

### Step 2.4: Two-Deck Crossfade System ✅

- [x] Create `public/js/mixer.js` with dual-deck architecture
- [x] Implement deck A and deck B as separate audio players
- [x] Implement `crossfade(fromDeck, toDeck, duration)` method
- [x] Use `GainNode` for smooth volume transitions
- [x] Automatically switch active deck after crossfade completes
- [x] Calculate when to trigger next track (based on remaining time)

**Deliverable**: Smooth crossfade between two tracks ✅

---

### Step 2.5: Integrate Playback with Server ✅

- [x] Listen for `play_track` WebSocket messages
- [x] Queue incoming track on inactive deck
- [x] Trigger crossfade when current track nears end
- [x] Send `track_started`, `track_ending` events to server
- [x] Handle edge cases (track load failure, etc.)

**Deliverable**: Server controls playback, browser executes ✅

---

## Phase 3: DJ Controller (Orchestration) ✅

### Step 3.1: DJ Controller State Machine ✅

- [x] Create `src/controller/dj-controller.ts`
- [x] Implement state machine: `IDLE` → `STARTING` → `PLAYING` → `STOPPING`
- [x] Implement `start()`, `stop()`, `pause()`, `resume()` methods
- [x] Track current state, current track, next track

**Deliverable**: State machine transitions correctly ✅

---

### Step 3.2: Main Control Loop ✅

- [x] Subscribe to mood updates from WebSocket
- [x] Subscribe to track events from browser (`track_ending`, etc.)
- [x] When track ending: select next track, send to browser
- [x] When mood changes significantly: log but don't interrupt current track
- [x] Implement minimum track play time (don't skip too fast)

**Deliverable**: Full automatic flow — mood → selection → playback ✅

---

### Step 3.3: Entry Point & CLI ✅

- [x] Create `src/index.ts` as main entry point
- [x] Wire up all modules (library, server, controller)
- [x] Add CLI arguments: `--port`, `--library`, `--music-dir`
- [x] Add graceful shutdown handling
- [x] Create `npm start` script

**Deliverable**: `npm start` runs the full system with random mood ✅

---

## Phase 4: Camera-Based Mood Detection

### Step 4.1: Camera Capture

- [ ] Create `public/js/camera.js`
- [ ] Request camera permission via `getUserMedia`
- [ ] Display live preview in `<video>` element
- [ ] Handle permission denied / no camera errors
- [ ] Allow camera device selection (if multiple)

**Deliverable**: Camera feed visible in browser

---

### Step 4.2: Motion Detection Algorithm

- [ ] Create `public/js/motion-detector.js`
- [ ] Capture frames to hidden `<canvas>`
- [ ] Convert to grayscale
- [ ] Implement background model (rolling average)
- [ ] Calculate frame difference from background
- [ ] Threshold difference to create motion mask
- [ ] Count motion pixels as percentage of frame
- [ ] Update background model slowly

**Deliverable**: Real-time motion percentage value (0-100%)

---

### Step 4.3: Contour Analysis (Optional Enhancement)

- [ ] Find connected regions in motion mask
- [ ] Filter out small regions (noise)
- [ ] Calculate total area of significant motion regions
- [ ] This gives cleaner motion estimate than raw pixel count

**Deliverable**: More accurate motion detection

---

### Step 4.4: Motion to Mood Mapping

- [ ] Create `public/js/mood-analyzer.js`
- [ ] Smooth motion values over time window (5 seconds)
- [ ] Map smoothed motion to mood levels:
  - 0-10% → `chill`
  - 10-30% → `warming_up`
  - 30-60% → `energetic`
  - 60-100% → `peak`
- [ ] Detect trend (rising/falling) for `cooling_down`
- [ ] Send mood updates to server via WebSocket (1/second)

**Deliverable**: Camera motion drives mood state

---

### Step 4.5: Server-Side Mood Processing

- [ ] Create `src/mood/camera-detector.ts`
- [ ] Receive mood updates from browser WebSocket
- [ ] Apply additional smoothing/hysteresis
- [ ] Prevent rapid mood oscillation (require sustained change)
- [ ] Feed processed mood to song selector

**Deliverable**: Stable mood signal from camera input

---

## Phase 5: UI & Polish

### Step 5.1: Now Playing Display

- [ ] Show current track: title, artist, artwork (if available)
- [ ] Show BPM, key, energy level
- [ ] Show playback progress bar
- [ ] Show time remaining

**Deliverable**: Clear view of what's playing

---

### Step 5.2: Mood Visualization

- [ ] Display current mood level (text + icon)
- [ ] Show motion percentage as bar/meter
- [ ] Show smoothed energy value
- [ ] Visual indicator when mood changes

**Deliverable**: Clear view of detected mood

---

### Step 5.3: Up Next Preview

- [ ] Show queued next track info
- [ ] Show why it was selected (energy match)
- [ ] Countdown to transition

**Deliverable**: Know what's coming

---

### Step 5.4: Controls

- [ ] Start/Stop button
- [ ] Skip track button
- [ ] Volume slider (master output)
- [ ] Camera on/off toggle
- [ ] Camera device selector dropdown

**Deliverable**: Manual override capabilities

---

### Step 5.5: Error Handling & Recovery

- [ ] Handle WebSocket disconnection (auto-reconnect, keep playing)
- [ ] Handle audio load failures (skip to next track)
- [ ] Handle camera failures (fall back to random mood)
- [ ] Show error messages in UI
- [ ] Log errors server-side

**Deliverable**: Robust system that doesn't crash

---

### Step 5.6: Configuration File

- [ ] Create `config.json` for runtime settings
- [ ] Configurable: crossfade duration, mood thresholds, smoothing window
- [ ] Load config on startup
- [ ] Document all config options

**Deliverable**: Tunable behavior without code changes

---

## Phase 6: Testing & Documentation

### Step 6.1: Integration Testing

- [ ] Test full flow: start → play → mood change → track change
- [ ] Test 30+ minute continuous operation
- [ ] Test with various library sizes (10, 50, 200 tracks)
- [ ] Test recovery from errors

**Deliverable**: Confidence system works end-to-end

---

### Step 6.2: Performance Testing

- [ ] Verify camera processing at 30fps doesn't lag
- [ ] Verify audio crossfades are glitch-free
- [ ] Monitor memory usage over time (no leaks)
- [ ] Test on target hardware (MacBook)

**Deliverable**: Smooth performance

---

### Step 6.3: Documentation

- [ ] Update README with setup instructions
- [ ] Document library.json format
- [ ] Document config.json options
- [ ] Document WebSocket protocol
- [ ] Add troubleshooting section

**Deliverable**: Someone else can set this up

---

## Milestones Summary

| Milestone | Steps     | Description                                               | Status |
| --------- | --------- | --------------------------------------------------------- | ------ |
| **M0**    | 0.1       | Project setup, library.json in place                      | ✅     |
| **M1**    | 1.1 - 1.5 | Backend foundation, can serve tracks and communicate      | ✅     |
| **M2**    | 2.1 - 2.5 | Browser plays music with crossfades, controlled by server | ✅     |
| **M3**    | 3.1 - 3.3 | Full autonomous DJ with random mood                       | ✅     |
| **M4**    | 4.1 - 4.5 | Camera-based mood detection working                       |        |
| **M5**    | 5.1 - 5.6 | Polished UI and robust error handling                     |        |
| **M6**    | 6.1 - 6.3 | Tested and documented                                     |        |

---

## Current Progress

**Current Step**: Phase 3 Complete ✅

**Next Action**: Begin Phase 4 - Camera-Based Mood Detection

---

## Notes

- Each step should be committed separately for easy rollback
- Test each step before moving to the next
- Steps within a phase can sometimes be parallelized
- Mark steps complete by changing `[ ]` to `[x]`
