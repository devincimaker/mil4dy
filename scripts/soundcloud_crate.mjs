#!/usr/bin/env node

/**
 * Build a CSV crate of club-length SoundCloud tracks in one genre whose
 * uploader enabled SoundCloud's native download control.
 *
 * Usage:
 *   node scripts/soundcloud_crate.mjs --genre "tech house" --limit 200
 *   node scripts/soundcloud_crate.mjs --genre "afro house" --limit 100 --pages 12
 *
 * This script catalogs links; it does not download audio.
 */

import { readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const CLUB_TITLE = /\b(?:extended|club|original)[\s_\-]*(?:mix|version|edit)\b|\bextended\b/i;
const SET_TITLE =
  /\b(?:mini[\s-]*mix|mix[\s-]*tape|podcast|radio\s*show|dj\s*set|live\s*set|compilation|playlist|free\s*pack|sample\s*pack|vol\.?\s*\d)\b/i;
const SPAM_TITLE = /\bbackground\b|tag\s*:\s*tag|remove background|tiktok/i;
const HOUSE_FAMILY = /house|techno|electronic|dance|edm|club|remix/i;
const EXCLUDED_GENRE = /battle\s*rap|hip[\s-]*hop|podcast|spoken|audiobook|comedy|country|classical|metal/i;
const COMPETING_HOUSE =
  /\b((?:afro|deep|melodic|organic|progressive|bass|electro|tropical|future|piano|disco|funky|soulful|latin|tribal|jackin|brazilian|french|balearic|slap)\s*house)\b/i;
const PAGE_SIZE = 200;

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

function parseList(value) {
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseArgs(argv) {
  const config = {
    genre: "tech house",
    limit: 200,
    pages: 8,
    maxPerUploader: 5,
    minDurationMs: 3.5 * 60 * 1000,
    maxDurationMs: 12 * 60 * 1000,
    clubOnly: true,
    out: "",
    extraQueries: [],
    excludeDirs: ["music", path.resolve("..", "ai-nightclub", "music")],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = argv[index + 1];
    if (argument === "--genre") config.genre = value, index += 1;
    else if (argument === "--limit") config.limit = Number(value), index += 1;
    else if (argument === "--out") config.out = value, index += 1;
    else if (argument === "--pages") config.pages = Number(value), index += 1;
    else if (argument === "--max-per-uploader") config.maxPerUploader = Number(value), index += 1;
    else if (argument === "--min-minutes") config.minDurationMs = Number(value) * 60 * 1000, index += 1;
    else if (argument === "--max-minutes") config.maxDurationMs = Number(value) * 60 * 1000, index += 1;
    else if (argument === "--club-only") config.clubOnly = true;
    else if (argument === "--any-title") config.clubOnly = false;
    else if (argument === "--query") config.extraQueries.push(value), index += 1;
    else if (argument === "--exclude-dirs") config.excludeDirs = parseList(value), index += 1;
    else if (argument === "--help" || argument === "-h") {
      console.log(
        [
          "node scripts/soundcloud_crate.mjs [options]",
          "",
          "  --genre NAME             Target genre (default: tech house)",
          "  --limit N                Tracks to keep (1-500, default: 200)",
          "  --pages N                Search pages per query (1-25, default: 8)",
          "  --max-per-uploader N     Diversity cap (default: 5)",
          "  --min-minutes N          Minimum duration (default: 3.5)",
          "  --max-minutes N          Maximum duration (default: 12)",
          "  --club-only              Require Extended/Club/Original Mix in the title (default)",
          "  --any-title              Keep any song-length title in the genre",
          "  --out PATH               CSV output path",
          "  --query TEXT             Extra search query (repeatable)",
          "  --exclude-dirs A,B       Libraries whose titles should be skipped",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }

  config.genre = String(config.genre ?? "").trim();
  if (!config.genre) throw new Error("--genre must be a non-empty string");
  if (!Number.isInteger(config.limit) || config.limit < 1 || config.limit > 500) {
    throw new Error("--limit must be an integer from 1 to 500");
  }
  if (!Number.isInteger(config.pages) || config.pages < 1 || config.pages > 25) {
    throw new Error("--pages must be an integer from 1 to 25");
  }
  if (!Number.isInteger(config.maxPerUploader) || config.maxPerUploader < 1) {
    throw new Error("--max-per-uploader must be a positive integer");
  }
  if (!Number.isFinite(config.minDurationMs) || config.minDurationMs < 60_000) {
    throw new Error("--min-minutes must be at least 1");
  }
  if (!Number.isFinite(config.maxDurationMs) || config.maxDurationMs <= config.minDurationMs) {
    throw new Error("--max-minutes must be greater than --min-minutes");
  }
  if (!config.out) {
    config.out = `data/soundcloud_${slugify(config.genre)}_candidates.csv`;
  }
  return config;
}

function queriesForGenre(genre, extraQueries) {
  const compact = genre.replace(/\s+/g, "");
  const queries = [
    `extended mix ${genre}`,
    `${genre} extended mix`,
    `club mix ${genre}`,
    `${genre} club mix`,
    `extended version ${genre}`,
    `${genre} extended version`,
    `original mix ${genre}`,
    `${genre} original mix`,
    `${compact} extended mix`,
    `${genre} free download`,
    `${genre} free dl`,
    `free download ${genre}`,
    `free dl ${genre}`,
    `[FREE DOWNLOAD] ${genre}`,
    `${compact} free download`,
    `${genre} download`,
    `extended mix ${genre} download`,
    `genre:${compact} download`,
    `genre:"${genre}" download`,
    `tag:${compact} download`,
    `tag:"${genre}" download`,
    `genre:${compact} "free download"`,
    `tag:${compact} "free download"`,
  ];
  return [...new Set([...queries, ...extraQueries])];
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: { "User-Agent": "mil4dy-soundcloud-crate/1.0" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
  return response.text();
}

async function discoverClientId() {
  if (process.env.SOUNDCLOUD_CLIENT_ID) return process.env.SOUNDCLOUD_CLIENT_ID;

  const html = await fetchText("https://soundcloud.com/discover");
  const assets = [...new Set(html.match(/https:\/\/a-v2\.sndcdn\.com\/assets\/[^\"']+\.js/g) ?? [])];
  if (assets.length === 0) throw new Error("Could not find SoundCloud application assets");

  for (let index = 0; index < assets.length; index += 8) {
    const scripts = await Promise.allSettled(assets.slice(index, index + 8).map(fetchText));
    for (const result of scripts) {
      if (result.status !== "fulfilled") continue;
      const match = result.value.match(/client_id:\"([A-Za-z0-9_-]{32})\"/);
      if (match) return match[1];
    }
  }
  throw new Error("Could not discover a current public SoundCloud client id");
}

async function fetchSearchPage(query, offset, clientId) {
  const url = new URL("https://api-v2.soundcloud.com/search/tracks");
  url.searchParams.set("q", query);
  url.searchParams.set("limit", String(PAGE_SIZE));
  url.searchParams.set("offset", String(offset));
  url.searchParams.set("client_id", clientId);
  const response = await fetch(url, {
    headers: { "User-Agent": "mil4dy-soundcloud-crate/1.0" },
  });
  if (response.status === 429) {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    return fetchSearchPage(query, offset, clientId);
  }
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${url}`);
  return response.json();
}

async function pool(items, concurrency, task) {
  const results = new Array(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await task(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}

function normalize(value) {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\([^)]*(?:extended|club|original|radio)[^)]*\)/g, "")
    .replace(/\b(?:extended|club|original|radio)\s*(?:mix|version|edit)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function folded(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[-_]+/g, " ");
}

function fieldMatchesGenre(value, genre) {
  const needle = folded(genre).replace(/\s+/g, " ").trim();
  const compact = needle.replace(/\s+/g, "");
  const hay = folded(value);
  return hay.includes(needle) || hay.replace(/\s+/g, "").includes(compact);
}

function matchesTargetGenre(track, genre) {
  if (fieldMatchesGenre(track.title, genre) || fieldMatchesGenre(track.genre, genre)) return true;
  // Tags-only matches are allowed only when the uploader also filed the track
  // as a house-family genre. Operator searches otherwise pull in spam.
  return (
    fieldMatchesGenre(track.tag_list, genre) && HOUSE_FAMILY.test(track.genre ?? "")
  );
}

function hasCompetingGenre(track, genre) {
  // Tags are noisy (tracks often list every house subgenre). Only the title
  // and primary genre field are treated as a conflicting style.
  return [track.title, track.genre].some((field) => {
    const match = String(field ?? "").match(COMPETING_HOUSE);
    if (!match) return false;
    return !matchesTargetGenre({ title: match[1], genre: "", tag_list: "" }, genre);
  });
}

async function existingLibraryKeys(directories) {
  const keys = new Set();
  for (const directory of directories) {
    const resolved = path.resolve(directory);
    try {
      const entries = await readdir(resolved, { recursive: true, withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isFile() || !/\.(?:mp3|m4a|wav|aiff?|flac|ogg)$/i.test(entry.name)) continue;
        keys.add(normalize(entry.name.replace(/\.[^.]+$/, "")));
      }
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  return keys;
}

function isCandidate(track, existing, config) {
  if (track.kind !== "track") return false;
  if (track.downloadable !== true || track.has_downloads_left === false) return false;
  if (track.policy && track.policy !== "ALLOW") return false;
  if (SET_TITLE.test(track.title ?? "") || SPAM_TITLE.test(track.title ?? "")) return false;
  if (config.clubOnly && !CLUB_TITLE.test(track.title ?? "")) return false;
  if (track.duration < config.minDurationMs || track.duration > config.maxDurationMs) return false;
  if (EXCLUDED_GENRE.test(track.genre ?? "")) return false;
  if (!matchesTargetGenre(track, config.genre)) return false;
  if (hasCompetingGenre(track, config.genre)) return false;
  if (existing.has(normalize(track.title ?? ""))) return false;
  return true;
}

function score(track, genre) {
  const title = track.title ?? "";
  const durationMinutes = track.duration / 60_000;
  let value = 0;
  if (/\bextended[\s_\-]*mix\b/i.test(title)) value += 30;
  if (folded(track.genre).includes(folded(genre))) value += 18;
  if (track.user?.verified) value += 10;
  if (durationMinutes >= 5 && durationMinutes <= 8) value += 8;
  value += Math.log10((track.likes_count ?? 0) + 1) * 5;
  value += Math.log10((track.playback_count ?? 0) + 1) * 2;
  value += Math.min(track.download_count ?? 0, 1000) / 250;
  return value;
}

function chooseDiverse(tracks, limit, maxPerUploader, genre) {
  const sorted = [...tracks].sort((left, right) => score(right, genre) - score(left, genre));
  const uploaderCounts = new Map();
  const titleKeys = new Set();
  const chosen = [];
  for (const track of sorted) {
    const uploader = track.user?.id ?? track.user?.username ?? "unknown";
    const count = uploaderCounts.get(uploader) ?? 0;
    if (count >= maxPerUploader) continue;
    const titleKey = normalize(track.title ?? "");
    if (titleKeys.has(titleKey)) continue;
    uploaderCounts.set(uploader, count + 1);
    titleKeys.add(titleKey);
    chosen.push(track);
    if (chosen.length === limit) break;
  }
  return chosen;
}

function csvCell(value) {
  const string = String(value ?? "");
  return /[",\n\r]/.test(string) ? `"${string.replaceAll('"', '""')}"` : string;
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.round(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  return `${minutes}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

function toCsv(tracks, generatedAt) {
  const headers = [
    "rank",
    "title",
    "uploader",
    "genre",
    "duration",
    "soundcloud_url",
    "native_download_enabled",
    "downloads_left",
    "download_count",
    "likes",
    "plays",
    "published_at",
    "license",
    "verified_uploader",
    "soundcloud_track_id",
    "checked_at",
  ];
  const rows = tracks.map((track, index) => [
    index + 1,
    track.title,
    track.user?.username,
    track.genre,
    formatDuration(track.duration),
    track.permalink_url,
    track.downloadable,
    track.has_downloads_left !== false,
    track.download_count,
    track.likes_count,
    track.playback_count,
    track.created_at,
    track.license,
    track.user?.verified ?? false,
    track.id,
    generatedAt,
  ]);
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n") + "\n";
}

function summarizeGenres(tracks) {
  const counts = new Map();
  for (const track of tracks) {
    const genre = (track.genre ?? "").trim() || "(blank)";
    counts.set(genre, (counts.get(genre) ?? 0) + 1);
  }
  return [...counts.entries()].sort((left, right) => right[1] - left[1]);
}

async function main() {
  const config = parseArgs(process.argv.slice(2));
  const queries = queriesForGenre(config.genre, config.extraQueries);
  const clientId = await discoverClientId();
  const existing = await existingLibraryKeys(config.excludeDirs);
  const requests = queries.flatMap((query) =>
    Array.from({ length: config.pages }, (_, page) => ({ query, offset: page * PAGE_SIZE })),
  );

  console.error(`Genre: ${config.genre}`);
  console.error(`Searching ${queries.length} queries × ${config.pages} pages (${requests.length} requests)...`);
  console.error(`Skipping ${existing.size} titles already in local libraries`);

  let completed = 0;
  const pages = await pool(requests, 4, async ({ query, offset }) => {
    const page = await fetchSearchPage(query, offset, clientId);
    completed += 1;
    if (completed === 1 || completed % 20 === 0 || completed === requests.length) {
      console.error(`  fetched ${completed}/${requests.length}`);
    }
    return page;
  });

  const unique = new Map();
  for (const page of pages) {
    for (const track of page.collection ?? []) {
      if (isCandidate(track, existing, config)) unique.set(track.permalink_url, track);
    }
  }

  const tracks = chooseDiverse([...unique.values()], config.limit, config.maxPerUploader, config.genre);
  const generatedAt = new Date().toISOString();
  const output = path.resolve(config.out);
  const jsonOutput = output.replace(/\.csv$/i, ".json");

  await writeFile(output, toCsv(tracks, generatedAt));
  await writeFile(
    jsonOutput,
    JSON.stringify(
      {
        generated_at: generatedAt,
        criteria: {
          genre: config.genre,
          native_download_enabled: true,
          downloads_left: true,
          club_only: config.clubOnly,
          title_pattern: config.clubOnly ? CLUB_TITLE.source : null,
          duration_seconds: [config.minDurationMs / 1000, config.maxDurationMs / 1000],
          max_per_uploader: config.maxPerUploader,
          queries,
        },
        tracks,
      },
      null,
      2,
    ) + "\n",
  );

  console.error(`Qualifying unique tracks: ${unique.size}`);
  console.error(`Wrote ${tracks.length} tracks to ${output}`);
  console.error(`Wrote source metadata to ${jsonOutput}`);
  for (const [genre, count] of summarizeGenres(tracks).slice(0, 12)) {
    console.error(`  ${String(count).padStart(3)}  ${genre}`);
  }

  if (tracks.length < config.limit) {
    console.error(
      `Only ${tracks.length}/${config.limit} natively downloadable tracks matched. That is likely the SoundCloud supply, not a search-depth problem.`,
    );
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error.stack ?? error.message);
  process.exitCode = 1;
});
