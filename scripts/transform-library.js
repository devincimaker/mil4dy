/**
 * Transform music.json into data/library.json format
 * Run with: node scripts/transform-library.js
 */

import { readFileSync, writeFileSync } from 'fs';
import { createHash } from 'crypto';

// Read the source data
const musicData = JSON.parse(readFileSync('./music.json', 'utf-8'));

/**
 * Estimate energy based on BPM and genre
 * This is a rough heuristic - you can manually adjust values later
 */
function estimateEnergy(track) {
  const { bpm, genre } = track;
  const genreLower = (genre || '').toLowerCase();

  // Base energy from BPM (normalized to 0-1 range)
  // Assuming 90 BPM = 0.2, 130 BPM = 0.6, 175 BPM = 1.0
  let energy = Math.min(1, Math.max(0, (bpm - 80) / 100));

  // Genre modifiers
  if (genreLower.includes('chill') || genreLower.includes('ambient')) {
    energy *= 0.6;
  } else if (genreLower.includes('deep')) {
    energy *= 0.8;
  } else if (
    genreLower.includes('techno') ||
    genreLower.includes('trance') ||
    genreLower.includes('psytrance')
  ) {
    energy *= 1.1;
  } else if (
    genreLower.includes('drum') ||
    genreLower.includes('bass') ||
    genreLower.includes('jungle') ||
    genreLower.includes('neurofunk')
  ) {
    energy *= 1.15;
  } else if (genreLower.includes('dubstep')) {
    energy *= 1.1;
  }

  // Clamp to 0-1
  return Math.min(1, Math.max(0, Math.round(energy * 100) / 100));
}

/**
 * Parse duration string "MM:SS" to seconds
 */
function parseDuration(durationStr) {
  const parts = durationStr.split(':');
  if (parts.length === 2) {
    return parseInt(parts[0]) * 60 + parseInt(parts[1]);
  }
  return 0;
}

/**
 * Generate a short unique ID from filename
 */
function generateId(filename) {
  return createHash('md5').update(filename).digest('hex').slice(0, 8);
}

// Transform tracks
const tracks = musicData.map((track) => ({
  id: generateId(track.filename),
  path: `music/${track.filename}`,
  title: track.title,
  artist: track.artist,
  bpm: track.bpm,
  key: track.key,
  energy: estimateEnergy(track),
  duration: parseDuration(track.duration),
  genre: track.genre || null,
}));

// Create library object
const library = {
  version: 1,
  generatedAt: new Date().toISOString(),
  trackCount: tracks.length,
  tracks,
};

// Write output
writeFileSync('./data/library.json', JSON.stringify(library, null, 2));

console.log(`✅ Transformed ${tracks.length} tracks to data/library.json`);
console.log('\nEnergy distribution:');

// Show energy distribution
const energyBuckets = { low: 0, medium: 0, high: 0, peak: 0 };
tracks.forEach((t) => {
  if (t.energy < 0.3) energyBuckets.low++;
  else if (t.energy < 0.5) energyBuckets.medium++;
  else if (t.energy < 0.7) energyBuckets.high++;
  else energyBuckets.peak++;
});

console.log(`  Low (0-0.3):    ${energyBuckets.low} tracks`);
console.log(`  Medium (0.3-0.5): ${energyBuckets.medium} tracks`);
console.log(`  High (0.5-0.7):   ${energyBuckets.high} tracks`);
console.log(`  Peak (0.7-1.0):   ${energyBuckets.peak} tracks`);
