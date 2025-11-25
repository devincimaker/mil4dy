/**
 * Song Selector
 *
 * Selects the next track based on current mood and playback history.
 */

import { Track, MusicLibrary } from '../music/index.js';
import { MoodState, MOOD_ENERGY_RANGES } from '../mood/index.js';

export interface SelectorOptions {
  /** Number of recent tracks to avoid repeating, default 10 */
  historySize?: number;
  /** BPM tolerance for matching (±%), default 0.15 (15%) */
  bpmTolerance?: number;
  /** Energy tolerance for matching (±), default 0.15 */
  energyTolerance?: number;
  /** Prefer similar BPM to current track, default true */
  preferSimilarBpm?: boolean;
}

export interface SelectionResult {
  track: Track;
  reason: string;
  score: number;
}

/**
 * Selects appropriate tracks based on mood state.
 */
export class SongSelector {
  private library: MusicLibrary;
  private playHistory: string[] = [];
  private options: Required<SelectorOptions>;

  constructor(library: MusicLibrary, options: SelectorOptions = {}) {
    this.library = library;
    this.options = {
      historySize: options.historySize ?? 10,
      bpmTolerance: options.bpmTolerance ?? 0.15,
      energyTolerance: options.energyTolerance ?? 0.15,
      preferSimilarBpm: options.preferSimilarBpm ?? true,
    };
  }

  /**
   * Select the next track based on mood and optional current track.
   * @param mood - Current mood state
   * @param currentTrack - Currently playing track (optional)
   */
  selectNext(mood: MoodState, currentTrack?: Track): SelectionResult {
    const candidates = this.getCandidates(mood, currentTrack);

    if (candidates.length === 0) {
      // Fallback: expand search if no candidates found
      const fallbackCandidates = this.getFallbackCandidates(mood);
      if (fallbackCandidates.length === 0) {
        // Ultimate fallback: random track not in history
        const allTracks = this.library.getAll();
        const available = allTracks.filter(
          (t) => !this.playHistory.includes(t.id)
        );
        const track =
          available.length > 0
            ? available[Math.floor(Math.random() * available.length)]
            : allTracks[Math.floor(Math.random() * allTracks.length)];
        return { track, reason: 'fallback (no matching tracks)', score: 0 };
      }
      return this.selectBestCandidate(fallbackCandidates, mood, currentTrack);
    }

    return this.selectBestCandidate(candidates, mood, currentTrack);
  }

  /**
   * Get candidate tracks matching the mood.
   */
  private getCandidates(mood: MoodState, currentTrack?: Track): Track[] {
    const energyRange = this.getTargetEnergyRange(mood);
    let candidates = this.library.getByEnergyRange(energyRange);

    // Filter out recently played tracks
    candidates = candidates.filter((t) => !this.playHistory.includes(t.id));

    // If we have a current track and want similar BPM, filter by BPM range
    if (currentTrack && this.options.preferSimilarBpm) {
      const bpmRange = this.getBpmRange(currentTrack.bpm);
      const bpmFiltered = candidates.filter(
        (t) => t.bpm >= bpmRange.min && t.bpm <= bpmRange.max
      );
      // Only use BPM filter if it leaves us with options
      if (bpmFiltered.length >= 3) {
        candidates = bpmFiltered;
      }
    }

    return candidates;
  }

  /**
   * Get fallback candidates with relaxed criteria.
   */
  private getFallbackCandidates(mood: MoodState): Track[] {
    // Expand energy range significantly
    const targetEnergy = mood.energy;
    const expandedRange = {
      min: Math.max(0, targetEnergy - 0.3),
      max: Math.min(1, targetEnergy + 0.3),
    };

    let candidates = this.library.getByEnergyRange(expandedRange);

    // Still filter out recent history, but reduce the window
    const reducedHistory = this.playHistory.slice(0, 5);
    candidates = candidates.filter((t) => !reducedHistory.includes(t.id));

    return candidates;
  }

  /**
   * Select the best candidate from a list based on scoring.
   */
  private selectBestCandidate(
    candidates: Track[],
    mood: MoodState,
    currentTrack?: Track
  ): SelectionResult {
    // Score each candidate
    const scored = candidates.map((track) => ({
      track,
      score: this.scoreTrack(track, mood, currentTrack),
    }));

    // Sort by score (highest first)
    scored.sort((a, b) => b.score - a.score);

    // Add some randomness - pick from top candidates
    const topCount = Math.min(5, Math.ceil(scored.length * 0.3));
    const topCandidates = scored.slice(0, topCount);
    const selected =
      topCandidates[Math.floor(Math.random() * topCandidates.length)];

    // Generate reason
    const reason = this.generateReason(selected.track, mood, currentTrack);

    return { track: selected.track, reason, score: selected.score };
  }

  /**
   * Score a track based on how well it fits the mood and current context.
   */
  private scoreTrack(
    track: Track,
    mood: MoodState,
    currentTrack?: Track
  ): number {
    let score = 0;

    // Energy match (0-40 points)
    const energyDiff = Math.abs(track.energy - mood.energy);
    score += Math.max(0, 40 - energyDiff * 100);

    // BPM compatibility (0-30 points)
    if (currentTrack) {
      const bpmRatio = track.bpm / currentTrack.bpm;
      // Perfect match, double, or half time are good
      const bpmDistances = [
        Math.abs(bpmRatio - 1),
        Math.abs(bpmRatio - 2),
        Math.abs(bpmRatio - 0.5),
      ];
      const bestBpmMatch = Math.min(...bpmDistances);
      score += Math.max(0, 30 - bestBpmMatch * 100);
    } else {
      // No current track, give moderate BPM score
      score += 15;
    }

    // Key compatibility (0-20 points) - simplified
    if (currentTrack) {
      const keyScore = this.getKeyCompatibility(track.key, currentTrack.key);
      score += keyScore * 20;
    } else {
      score += 10;
    }

    // Trend matching (0-10 points)
    if (mood.trend === 'rising' && track.energy > mood.energy) {
      score += 10;
    } else if (mood.trend === 'falling' && track.energy < mood.energy) {
      score += 10;
    } else if (mood.trend === 'stable') {
      score += 5;
    }

    return score;
  }

  /**
   * Get target energy range based on mood.
   */
  private getTargetEnergyRange(mood: MoodState): { min: number; max: number } {
    const baseRange = MOOD_ENERGY_RANGES[mood.level];
    const tolerance = this.options.energyTolerance;

    // Center around the actual energy value while respecting mood range
    const center = mood.energy;
    return {
      min: Math.max(baseRange.min, center - tolerance),
      max: Math.min(baseRange.max, center + tolerance),
    };
  }

  /**
   * Get BPM range based on tolerance.
   */
  private getBpmRange(bpm: number): { min: number; max: number } {
    const tolerance = this.options.bpmTolerance;
    return {
      min: bpm * (1 - tolerance),
      max: bpm * (1 + tolerance),
    };
  }

  /**
   * Simple key compatibility check.
   * Returns 0-1 score for compatibility.
   */
  private getKeyCompatibility(key1: string, key2: string): number {
    if (key1 === key2) return 1;

    // Extract root and mode
    const parse = (key: string) => {
      const isMinor = key.includes('m');
      const root = key.replace('m', '');
      return { root, isMinor };
    };

    const k1 = parse(key1);
    const k2 = parse(key2);

    // Same root = good
    if (k1.root === k2.root) return 0.8;

    // Relative major/minor
    // (simplified - would need full circle of fifths for accuracy)
    if (k1.isMinor !== k2.isMinor) return 0.6;

    // Different keys
    return 0.3;
  }

  /**
   * Generate human-readable reason for selection.
   */
  private generateReason(
    track: Track,
    mood: MoodState,
    currentTrack?: Track
  ): string {
    const parts: string[] = [];

    // Energy match
    const energyDiff = Math.abs(track.energy - mood.energy);
    if (energyDiff < 0.1) {
      parts.push('perfect energy match');
    } else if (energyDiff < 0.2) {
      parts.push('good energy match');
    }

    // BPM info
    if (currentTrack) {
      const bpmRatio = track.bpm / currentTrack.bpm;
      if (Math.abs(bpmRatio - 1) < 0.05) {
        parts.push('matching BPM');
      } else if (
        Math.abs(bpmRatio - 2) < 0.1 ||
        Math.abs(bpmRatio - 0.5) < 0.1
      ) {
        parts.push('compatible tempo');
      }
    }

    // Mood level
    parts.push(`${mood.level} mood`);

    return parts.join(', ');
  }

  /**
   * Record a track as played.
   */
  recordPlay(trackId: string): void {
    this.playHistory.unshift(trackId);
    // Keep history within size limit
    if (this.playHistory.length > this.options.historySize) {
      this.playHistory.pop();
    }
  }

  /**
   * Clear play history.
   */
  clearHistory(): void {
    this.playHistory = [];
  }

  /**
   * Get the current play history.
   */
  getHistory(): string[] {
    return [...this.playHistory];
  }
}
