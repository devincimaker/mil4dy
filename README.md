# mil4dy

`mil4dy` turns a folder of MP3 files into one offline DJ mix. It analyzes the
audio itself, caches that analysis, plans a set, and renders beat-length
crossfades with FFmpeg.

## Requirements

- `uv`
- `ffmpeg` and `ffprobe`

## Run it

```bash
uv run mil4dy /path/to/mp3s --minutes 30 --output output/mix.mp3
```

The command creates:

- `output/mix.mp3`: the rendered mix
- `output/mix.json`: the selected tracks, cue points, and transition details
- `.mil4dy/analysis.json`: reusable analysis cache

The MP3 library is read-only. An interrupted or repeated run reuses completed
analysis for files that have not changed.

