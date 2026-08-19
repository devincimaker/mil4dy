---
name: sicktaste-promo-downloader
description: Download Sick Taste files through the site's official listener UI (Start download → email → optional SoundCloud follow → Download). Catalog Top 100 / Fresh / Featured checkpoint into a unique inbox. Use when the user asks to download Sick Taste tracks, a Sick Taste crate, or runs /sicktaste-promo-downloader.
---

# Sick Taste promo downloader

Download files the uploader is offering through Sick Taste's official page. 

## Browser

Use Playwright MCP with the persistent Chrome profile (the default). That profile already holds the Sick Taste artist session and SoundCloud OAuth from earlier runs. Do not switch to a fresh isolated profile mid-crate.

If a page shows **This is an exclusive download** and asks to log in, tell the user to sign in via the in-page modal (not `wp-login.php`) and wait. Exclusive originals are allowed once signed in.

## Establish scope

1. Default chart: `https://sicktaste.com/top-100/`. Also accept Fresh, Featured, or a list of `/d/{id}/` URLs the user names.
2. Extract each row's rank, visible title, channel, and `https://sicktaste.com/d/{id}/` link (class `wmp-chart-get`).
3. Apply [references/original-promo-filter.md](references/original-promo-filter.md) before opening download pages. Record every skip in the manifest with the filter reason.
4. Create inbox `<project>/music/inbox/sicktaste_<YYYY-MM-DD>`. If that folder already belongs to another run, add a numeric suffix. Never overwrite or empty an existing directory.
5. Keep a checkpoint manifest beside the inbox (`<inbox>.manifest.jsonl`). Also update `music/SICKTASTE_.md` after every completed song: flip `todo` → `done` and write the served filename. On resume, trust only rows whose final file still exists.
6. Default listener email: `devinci.maker@gmail.com`. Override if the user gives another address. Do not invent an email.

Fred Dope – Feel The Rhythm (`/d/38ynbe/`) was already completed into `music/inbox/sicktaste_2026-08-18/`. Treat that path as occupied; reuse the same day's inbox only when appending, never replace files.

## Download one track

Process tracks **one at a time**. SoundCloud OAuth opens a popup; parallel tabs collide.

Follow [references/official-ui.md](references/official-ui.md). In short:

1. Open `/d/{id}/` (full page, not the chart drawer).
2. If the gate is exclusive and logged out, stop and ask the user to sign in.
3. Click **Start download** if that step is showing.
4. If **Your email address** / **Get the track** appears, fill the configured email and submit.
5. If **Connect SoundCloud** appears and is not `is-done`, click it, switch to the SoundCloud authorize tab, click **Allow**, and wait for that tab to close.
6. Register a download listener, then click the visible **Download** link (exact name). Wait until the file finishes. Do not move `.crdownload` files.
7. Move only that new audio file into the inbox with a collision-safe name (`stem (1).ext`).
8. Append a manifest row: rank, title, `/d/` URL, filter result, served filename, final path, bytes, timestamp, skip/fail reason.

If the page unlocks but never shows **Download** after email + SoundCloud, screenshot, mark `no-official-download`, and continue.

## Pause and finish

On pause: finish the current track, flush the manifest, start no new `/d/` pages.

When done, report completed / skipped / failed counts, skip reasons, inbox path, file count, total size, and extensions. Leave the user's other browser tabs alone.
