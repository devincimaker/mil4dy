# AI DJ - Product Requirements Document

## Overview

**AI DJ** is an intelligent music system that automatically selects and mixes songs based on real-time mood detection from a dance floor. It uses computer vision to analyze crowd energy and seamlessly transitions between tracks to maintain the optimal vibe.

### Vision Statement

_An autonomous DJ that reads the room and keeps the party going — no human intervention required._

---

## Goals

### Primary Goals

1. **Automatic song selection** based on detected mood/energy levels
2. **Smooth audio transitions** between tracks (crossfades)
3. **Real-time mood detection** from camera input analyzing dance floor motion
4. **Zero-touch operation** once started — the system runs autonomously

### Non-Goals (Out of Scope for V1)

- Beat-matching or tempo synchronization
- Advanced DJ effects (filters, loops, samples)
- Integration with streaming services
- Multi-room/zone support
- Mobile app

---

## Target Users

**Primary**: The host of a house party who wants great music flow without manually DJing

**Use Case**:

> "I'm hosting a party. I want to set up a laptop with a camera pointed at the dance floor, hit 'start', and have the music automatically match the energy of the room all night."

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser Window                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Camera Feed    │  │  Audio Player   │  │  Status Display │ │
│  │  (MediaDevices) │  │  (Web Audio)    │  │  (optional UI)  │ │
│  └────────┬────────┘  └────────▲────────┘  └─────────────────┘ │
│           │                    │                                 │
│           ▼                    │                                 │
│  ┌─────────────────┐          │                                 │
│  │ Motion Analyzer │          │                                 │
│  │ (Canvas + JS)   │          │                                 │
│  └────────┬────────┘          │                                 │
│           │                    │                                 │
└───────────┼────────────────────┼─────────────────────────────────┘
            │ WebSocket          │ WebSocket
            ▼                    │
┌───────────────────────────────────────────────────────────────────┐
│                      Node.js Backend                               │
│                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │  Mood Engine    │  │  Song Selector  │  │  Mix Planner    │   │
│  │                 │  │                 │  │                 │   │
│  │ - Receives      │  │ - Queries       │  │ - Determines    │   │
│  │   motion data   │  │   library       │  │   crossfade     │   │
│  │ - Smooths       │  │ - Filters by    │  │   timing        │   │
│  │   readings      │  │   energy/mood   │  │ - Sends play    │   │
│  │ - Outputs       │  │ - Avoids        │  │   commands      │   │
│  │   mood state    │  │   repeats       │  │                 │   │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘   │
│           │                    │                    │             │
│           └──────────┬─────────┴────────────────────┘             │
│                      ▼                                            │
│           ┌─────────────────────┐                                 │
│           │   Music Library     │                                 │
│           │   (JSON + Files)    │                                 │
│           └─────────────────────┘                                 │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Why Browser + Node?

| Component       | Runs In | Reason                                        |
| --------------- | ------- | --------------------------------------------- |
| Camera capture  | Browser | Native `getUserMedia` API, no drivers needed  |
| Motion analysis | Browser | Canvas API, runs at 30fps easily              |
| Audio playback  | Browser | Web Audio API is superior for mixing          |
| Song selection  | Node.js | Business logic, library queries               |
| Mood smoothing  | Node.js | Centralized state, prevents erratic switching |
| File serving    | Node.js | Serves audio files to browser                 |

---

## Core Modules

### 1. Mood Detection Module

**Purpose**: Analyze camera feed to determine dance floor energy level

**Input**: Video frames from MacBook camera (or USB camera)

**Output**: Mood state object

```typescript
interface MoodState {
  level: "chill" | "warming_up" | "energetic" | "peak" | "cooling_down";
  energy: number; // 0.0 - 1.0, smoothed
  rawMotion: number; // 0.0 - 1.0, instantaneous
  confidence: number; // 0.0 - 1.0, how reliable is this reading
  timestamp: number;
}
```

**Detection Method**: Background Subtraction + Contour Analysis

1. Maintain a reference "background" frame (updated slowly)
2. Compare each new frame against background
3. Threshold the difference to find moving regions
4. Calculate total motion area as percentage of frame
5. Track motion over time window (e.g., 5 seconds) to smooth spikes

**Mood Mapping**:
| Motion Level | Mood |
|--------------|------|
| 0% - 10% | chill |
| 10% - 30% | warming_up |
| 30% - 60% | energetic |
| 60% - 100% | peak |
| Decreasing trend | cooling_down |

**Configuration**:

- `motionThreshold`: Pixel difference threshold (default: 25)
- `minContourArea`: Ignore small movements (default: 500 px²)
- `smoothingWindow`: Seconds to average over (default: 5)
- `backgroundUpdateRate`: How fast background adapts (default: 0.01)

---

### 2. Music Library Module

**Purpose**: Store and query track metadata

**Input**: JSON file with track information + audio files on disk

**Track Schema**:

```typescript
interface Track {
  id: string; // Unique identifier
  path: string; // Relative path to audio file
  title: string;
  artist: string;

  // Musical properties
  bpm: number; // Beats per minute
  key: string; // Musical key (e.g., "Am", "C", "F#m")
  energy: number; // 0.0 - 1.0, how energetic/intense

  // Timing
  duration: number; // Total length in seconds

  // Optional metadata
  genre?: string;
  tags?: string[]; // e.g., ["vocal", "build", "drop"]
}
```

**Library File** (`data/library.json`):

```json
{
  "version": 1,
  "tracks": [
    {
      "id": "001",
      "path": "tracks/artist-song.mp3",
      "title": "Song Name",
      "artist": "Artist Name",
      "bpm": 128,
      "key": "Am",
      "energy": 0.7,
      "duration": 245
    }
  ]
}
```

**Query Methods**:

- `getByEnergyRange(min, max)` — Find tracks within energy range
- `getAll()` — Return all tracks
- `getById(id)` — Fetch specific track
- `getRandom(excludeIds)` — Random track, excluding recently played

---

### 3. Song Selector Module

**Purpose**: Choose the next track based on current mood

**Input**:

- Current mood state
- Currently playing track (if any)
- Play history

**Output**: Next track to play

**Selection Algorithm**:

1. Map mood level to target energy range:

   - `chill` → 0.0 - 0.3
   - `warming_up` → 0.2 - 0.5
   - `energetic` → 0.4 - 0.7
   - `peak` → 0.6 - 1.0
   - `cooling_down` → 0.3 - 0.6

2. Query library for tracks in energy range

3. Filter out recently played (last N tracks)

4. Prefer tracks with similar BPM to current (±10%) for smoother transitions

5. Select randomly from top candidates (weighted toward better energy match)

**Configuration**:

- `historySize`: How many tracks to remember (default: 10)
- `bpmTolerance`: Acceptable BPM difference (default: 0.1 = 10%)
- `energyPadding`: Expand energy range if few matches (default: 0.1)

---

### 4. Audio Player Module

**Purpose**: Play audio files with crossfade transitions

**Implementation**: Web Audio API in browser

**Features**:

- Load and decode audio files
- Two-deck system (A/B) for crossfading
- Smooth volume transitions
- Track progress monitoring
- Trigger next track before current ends

**Crossfade Behavior**:

```
Track A:  ████████████████████▓▓▓░░░
Track B:                    ░░░▓▓▓████████████████████
                               ↑
                          Crossfade zone
                          (default: 10 seconds)
```

**Events Emitted**:

- `trackStarted` — New track began playing
- `trackEnding` — Track approaching end (trigger next selection)
- `trackEnded` — Track finished
- `crossfadeStarted` — Beginning transition
- `crossfadeCompleted` — Transition finished

**Configuration**:

- `crossfadeDuration`: Overlap time in seconds (default: 10)
- `triggerBeforeEnd`: When to request next track (default: 30 seconds)

---

### 5. DJ Controller Module

**Purpose**: Orchestrate all modules, main control loop

**Responsibilities**:

- Initialize all modules
- Subscribe to mood updates
- Trigger song selection at appropriate times
- Handle edge cases (empty library, no camera, etc.)
- Manage system state

**State Machine**:

```
[IDLE] → start() → [STARTING] → first track loaded → [PLAYING]
                                                          ↓
                        [PAUSED] ← pause() ←──────────────┘
                            ↓
                        resume() → [PLAYING]

[PLAYING] → stop() → [STOPPING] → audio faded → [IDLE]
```

**Main Loop** (simplified):

```
1. Receive mood update from browser
2. If track ending soon:
   a. Get current mood
   b. Select next track
   c. Schedule crossfade
3. Update internal state
4. Broadcast status to browser
```

---

## User Interface

### Minimal Status Display (Browser)

Since this is headless-first, the UI is optional but useful for monitoring:

```
┌─────────────────────────────────────────────────────┐
│  AI DJ                                    [■ Live]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  🎵 Now Playing                                     │
│  ─────────────────                                  │
│  Artist Name - Track Title                          │
│  BPM: 128 | Key: Am | Energy: ███████░░░ 72%       │
│                                                     │
│  ⏱ 2:34 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5:12   │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  📊 Mood Detection                                  │
│  ─────────────────                                  │
│  Status: ENERGETIC                                  │
│  Motion: ██████████████░░░░░░ 68%                  │
│                                                     │
│  [Camera Preview]                                   │
│  ┌─────────────────────┐                           │
│  │                     │                           │
│  │    (live feed)      │                           │
│  │                     │                           │
│  └─────────────────────┘                           │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ⏭ Up Next                                         │
│  Another Artist - Another Track (Energy: 75%)       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Controls

- **Start/Stop**: Begin or end the DJ session
- **Skip**: Force skip to next track
- **Camera Select**: Choose input device (if multiple)

---

## Technical Requirements

### Runtime

- **Node.js**: v18+ (LTS)
- **Browser**: Chrome/Edge (for Web Audio API + getUserMedia)
- **OS**: macOS (initially), cross-platform later

### Dependencies (Tentative)

**Backend (Node.js)**:

- `express` or `fastify` — HTTP server
- `ws` — WebSocket communication
- `typescript` — Type safety

**Frontend (Browser)**:

- Vanilla JS/TS or lightweight framework
- Web Audio API (native)
- Canvas API (native)

### Audio Formats Supported

- MP3 (primary)
- WAV
- FLAC (if browser supports)
- M4A/AAC

### Performance Targets

- Camera processing: 30 fps
- Mood update frequency: 1 Hz (once per second)
- Audio latency: < 100ms
- Crossfade smoothness: No audible glitches

---

## Development Phases

### Phase 1: Foundation (MVP)

- [ ] Project setup (Node + TypeScript + browser client)
- [ ] Music library loader (read JSON, serve files)
- [ ] Basic audio player (single track playback)
- [ ] Random mood detector (no camera yet)
- [ ] Song selector (basic energy matching)
- [ ] DJ controller loop
- **Deliverable**: System plays music, switches tracks based on random mood

### Phase 2: Audio Mixing

- [ ] Two-deck audio player
- [ ] Crossfade implementation
- [ ] Track timing / end detection
- [ ] Smooth transitions
- **Deliverable**: Seamless crossfades between tracks

### Phase 3: Vision

- [ ] Camera capture in browser
- [ ] Background subtraction algorithm
- [ ] Contour analysis for motion
- [ ] Motion → mood mapping
- [ ] Mood smoothing (prevent erratic changes)
- **Deliverable**: Real camera input drives song selection

### Phase 4: Polish

- [ ] Status UI in browser
- [ ] Error handling / recovery
- [ ] Configuration file support
- [ ] Logging / debugging tools
- **Deliverable**: Reliable system ready for house party use

### Future Phases (Post-V1)

- Beat detection and tempo matching
- Key-based harmonic mixing
- Multiple camera support
- Audio analysis (auto-generate energy values)
- External controller support (MIDI)
- Spotify/streaming integration

---

## Success Criteria

### Functional

1. ✅ System runs unattended for 4+ hours without crashing
2. ✅ Song selection responds to mood changes within 1-2 tracks
3. ✅ Crossfades are smooth with no audio gaps or clicks
4. ✅ Camera correctly detects high vs low motion

### User Experience

1. ✅ Setup takes < 5 minutes (start server, open browser, grant camera)
2. ✅ No manual intervention needed during party
3. ✅ Music energy roughly matches dance floor energy

---

## Open Questions

1. **Library management**: Should there be a UI to add/edit tracks, or is JSON editing sufficient?

2. **Fallback behavior**: What happens if camera is blocked/fails? Continue with last known mood? Random?

3. **Calibration**: Should there be a "calibration" phase where the system learns what "no movement" looks like for the specific venue?

4. **Audio output**: Direct browser output, or should we support external audio interfaces?

---

## Appendix

### A. Mood Level Definitions

| Level        | Description                            | Typical BPM Range | Energy Range |
| ------------ | -------------------------------------- | ----------------- | ------------ |
| Chill        | Low activity, people chatting, ambient | 80-110            | 0.0-0.3      |
| Warming Up   | Some movement, getting started         | 100-120           | 0.2-0.5      |
| Energetic    | Active dancing, good energy            | 115-130           | 0.4-0.7      |
| Peak         | Maximum energy, everyone dancing       | 125-140           | 0.6-1.0      |
| Cooling Down | Energy decreasing, winding down        | 110-125           | 0.3-0.6      |

### B. Example Track Metadata

```json
{
  "id": "demo-001",
  "path": "tracks/demo-track.mp3",
  "title": "Midnight Drive",
  "artist": "Synthwave Artist",
  "bpm": 118,
  "key": "Fm",
  "energy": 0.6,
  "duration": 312,
  "genre": "synthwave",
  "tags": ["driving", "nocturnal", "retro"]
}
```

### C. Background Subtraction Pseudocode

```
initialize:
  background = null
  alpha = 0.01  // background learning rate

for each frame:
  grayscale = convertToGray(frame)

  if background is null:
    background = grayscale
    continue

  // Calculate difference from background
  diff = absoluteDifference(grayscale, background)

  // Threshold to binary
  mask = threshold(diff, 25)

  // Find contours (connected regions)
  contours = findContours(mask)

  // Calculate total motion area
  motionArea = sum(contourArea(c) for c in contours if contourArea(c) > minArea)
  motionPercent = motionArea / totalFrameArea

  // Update background slowly
  background = background * (1 - alpha) + grayscale * alpha

  return motionPercent
```
