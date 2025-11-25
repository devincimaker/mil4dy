# AI DJ - Implementation Plan

This document outlines the step-by-step implementation plan for the AI DJ project. Each step is designed to be atomic and testable.

---

## Phase 0: Project Setup

### Step 0.1: Initialize Project Structure

- [ ] Create folder structure (`src/`, `public/`, `data/`)
- [ ] Initialize `package.json` with TypeScript
- [ ] Configure `tsconfig.json`
- [ ] Set up ESLint and Prettier
- [ ] Add `.gitignore`
- [ ] Create initial `README.md`
- [ ] Place pre-existing `library.json` (from Rekordbox export) in `data/`

**Deliverable**: Empty project that compiles TypeScript, music library ready

---

## Phase 1: Core Backend Foundation

### Step 1.1: Music Library Module

- [ ] Create `src/music/types.ts` with `Track` interface
- [ ] Create `src/music/library.ts` with `MusicLibrary` class
- [ ] Implement `load(path)` to read `library.json`
- [ ] Implement `getAll()`, `getById(id)`, `getByEnergyRange(min, max)`
- [ ] Write unit tests for library queries

**Deliverable**: Can load and query track metadata

---

### Step 1.2: Mood Types & Random Detector

- [ ] Create `src/mood/types.ts` with `MoodState`, `MoodLevel` types
- [ ] Create `src/mood/detector.ts` with abstract `MoodDetector` interface
- [ ] Create `src/mood/random-detector.ts` implementing random mood generation
- [ ] Random detector should drift gradually (not jump wildly)
- [ ] Write unit tests

**Deliverable**: Can generate plausible random mood states

---

### Step 1.3: Song Selector

- [ ] Create `src/selection/selector.ts` with `SongSelector` class
- [ ] Implement mood-to-energy mapping
- [ ] Implement `selectNext(currentTrack, mood)` method
- [ ] Track play history to avoid repeats
- [ ] Prefer similar BPM when possible
- [ ] Write unit tests with mock library

**Deliverable**: Given a mood, returns appropriate next track

---

### Step 1.4: HTTP Server Setup

- [ ] Install `express` and `ws` (WebSocket)
- [ ] Create `src/server/index.ts` as HTTP server entry point
- [ ] Serve static files from `public/`
- [ ] Create `/api/tracks` endpoint to list all tracks
- [ ] Create `/api/tracks/:id/audio` endpoint to stream audio files
- [ ] Set up CORS for local development

**Deliverable**: Server runs, can fetch track list and stream audio via HTTP

---

### Step 1.5: WebSocket Communication

- [ ] Add WebSocket server to existing HTTP server
- [ ] Define message protocol (JSON messages with `type` field)
- [ ] Implement server-side message handlers:
  - `mood_update` (receive from browser)
  - `play_track` (send to browser)
  - `status` (send current state to browser)
- [ ] Create `src/server/connection.ts` to manage client connections

**Deliverable**: Browser can connect via WebSocket, send/receive messages

---

## Phase 2: Browser Audio Playback

### Step 2.1: Basic HTML Shell

- [ ] Create `public/index.html` with minimal structure
- [ ] Create `public/styles.css` with basic styling
- [ ] Create `public/js/main.js` as entry point
- [ ] Add placeholders for: now playing, mood display, camera preview

**Deliverable**: Browser shows basic UI shell

---

### Step 2.2: WebSocket Client

- [ ] Create `public/js/websocket.js` for server communication
- [ ] Implement auto-reconnect on disconnect
- [ ] Implement message send/receive with JSON parsing
- [ ] Dispatch custom events for received messages

**Deliverable**: Browser connects to server, logs messages

---

### Step 2.3: Single-Deck Audio Player

- [ ] Create `public/js/audio-player.js` using Web Audio API
- [ ] Implement `loadTrack(url)` to fetch and decode audio
- [ ] Implement `play()`, `pause()`, `stop()`
- [ ] Implement volume control
- [ ] Track playback position and duration
- [ ] Emit events: `ended`, `timeupdate`
- [ ] Display current track info in UI

**Deliverable**: Can play a single track from server, shows progress

---

### Step 2.4: Two-Deck Crossfade System

- [ ] Create `public/js/mixer.js` with dual-deck architecture
- [ ] Implement deck A and deck B as separate audio players
- [ ] Implement `crossfade(fromDeck, toDeck, duration)` method
- [ ] Use `GainNode` for smooth volume transitions
- [ ] Automatically switch active deck after crossfade completes
- [ ] Calculate when to trigger next track (based on remaining time)

**Deliverable**: Smooth crossfade between two tracks

---

### Step 2.5: Integrate Playback with Server

- [ ] Listen for `play_track` WebSocket messages
- [ ] Queue incoming track on inactive deck
- [ ] Trigger crossfade when current track nears end
- [ ] Send `track_started`, `track_ending` events to server
- [ ] Handle edge cases (track load failure, etc.)

**Deliverable**: Server controls playback, browser executes

---

## Phase 3: DJ Controller (Orchestration)

### Step 3.1: DJ Controller State Machine

- [ ] Create `src/controller/dj-controller.ts`
- [ ] Implement state machine: `IDLE` → `STARTING` → `PLAYING` → `STOPPING`
- [ ] Implement `start()`, `stop()`, `pause()`, `resume()` methods
- [ ] Track current state, current track, next track

**Deliverable**: State machine transitions correctly

---

### Step 3.2: Main Control Loop

- [ ] Subscribe to mood updates from WebSocket
- [ ] Subscribe to track events from browser (`track_ending`, etc.)
- [ ] When track ending: select next track, send to browser
- [ ] When mood changes significantly: log but don't interrupt current track
- [ ] Implement minimum track play time (don't skip too fast)

**Deliverable**: Full automatic flow — mood → selection → playback

---

### Step 3.3: Entry Point & CLI

- [ ] Create `src/index.ts` as main entry point
- [ ] Wire up all modules (library, server, controller)
- [ ] Add CLI arguments: `--port`, `--library`, `--music-dir`
- [ ] Add graceful shutdown handling
- [ ] Create `npm start` script

**Deliverable**: `npm start` runs the full system with random mood

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

| Milestone | Steps     | Description                                               |
| --------- | --------- | --------------------------------------------------------- |
| **M0**    | 0.1       | Project setup, library.json in place                      |
| **M1**    | 1.1 - 1.5 | Backend foundation, can serve tracks and communicate      |
| **M2**    | 2.1 - 2.5 | Browser plays music with crossfades, controlled by server |
| **M3**    | 3.1 - 3.3 | Full autonomous DJ with random mood                       |
| **M4**    | 4.1 - 4.5 | Camera-based mood detection working                       |
| **M5**    | 5.1 - 5.6 | Polished UI and robust error handling                     |
| **M6**    | 6.1 - 6.3 | Tested and documented                                     |

---

## Current Progress

**Current Step**: Not started

**Next Action**: Begin Step 0.1 - Initialize Project Structure

---

## Notes

- Each step should be committed separately for easy rollback
- Test each step before moving to the next
- Steps within a phase can sometimes be parallelized
- Mark steps complete by changing `[ ]` to `[x]`
