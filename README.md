# AI DJ 🎧

An autonomous DJ that reads the room and keeps the party going — no human intervention required.

## Overview

AI DJ uses computer vision to detect dance floor energy and automatically selects and mixes music to match the mood. Point a camera at the dance floor, hit start, and let the AI handle the rest.

## Features

- **Mood Detection**: Analyzes camera feed to gauge dance floor energy
- **Smart Selection**: Picks tracks that match the current vibe
- **Smooth Transitions**: Crossfades between songs automatically
- **Zero Touch**: Runs autonomously once started

## Quick Start

```bash
# Install dependencies
npm install

# Build the project
npm run build

# Start the DJ
npm start
```

Then open `http://localhost:3000` in your browser.

## Project Structure

```
ai-dj/
├── src/
│   ├── index.ts          # Entry point
│   ├── music/            # Track library management
│   ├── mood/             # Mood detection modules
│   ├── selection/        # Song selection logic
│   ├── server/           # HTTP & WebSocket server
│   └── controller/       # DJ orchestration
├── public/               # Browser client (audio, camera, UI)
├── data/
│   └── library.json      # Track metadata
├── music/                # Audio files (not in git)
└── docs/                 # PRD & implementation plan
```

## Configuration

Place your music files in the `music/` directory and ensure `data/library.json` contains metadata for each track.

### Track Metadata Format

```json
{
  "id": "unique-id",
  "path": "music/filename.mp3",
  "title": "Track Title",
  "artist": "Artist Name",
  "bpm": 128,
  "key": "Am",
  "energy": 0.7,
  "duration": 245,
  "genre": "house"
}
```

## Development

```bash
# Run in development mode
npm run dev

# Lint code
npm run lint

# Format code
npm run format
```

## License

MIT

