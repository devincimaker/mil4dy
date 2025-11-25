/**
 * Mood Types
 *
 * Type definitions for mood detection and state management.
 */

/**
 * Discrete mood levels representing dance floor energy.
 */
export type MoodLevel =
  | 'chill' // Low energy, ambient, warm-up
  | 'warming_up' // Building energy, getting started
  | 'energetic' // Good energy, main floor vibes
  | 'peak' // Maximum energy, peak hour
  | 'cooling_down'; // Energy decreasing, wind down

/**
 * Numerical representation of mood levels for calculations.
 */
export const MOOD_LEVEL_VALUES: Record<MoodLevel, number> = {
  chill: 0.15,
  warming_up: 0.35,
  energetic: 0.6,
  peak: 0.85,
  cooling_down: 0.4,
};

/**
 * Energy ranges for each mood level.
 */
export const MOOD_ENERGY_RANGES: Record<
  MoodLevel,
  { min: number; max: number }
> = {
  chill: { min: 0, max: 0.25 },
  warming_up: { min: 0.2, max: 0.45 },
  energetic: { min: 0.4, max: 0.7 },
  peak: { min: 0.65, max: 1.0 },
  cooling_down: { min: 0.25, max: 0.5 },
};

/**
 * Full mood state including level, numerical value, and trend.
 */
export interface MoodState {
  /** Current discrete mood level */
  level: MoodLevel;
  /** Numerical energy value (0-1) */
  energy: number;
  /** Whether energy is rising, falling, or stable */
  trend: 'rising' | 'falling' | 'stable';
  /** Timestamp of this mood reading */
  timestamp: number;
  /** Confidence in this reading (0-1), useful for camera detection */
  confidence: number;
}

/**
 * Interface for all mood detectors to implement.
 */
export interface MoodDetector {
  /** Get the current mood state */
  getCurrentMood(): MoodState;

  /** Start the detector (e.g., start camera, start random timer) */
  start(): void;

  /** Stop the detector */
  stop(): void;

  /** Check if detector is running */
  isRunning(): boolean;

  /** Subscribe to mood updates */
  onMoodChange(callback: (mood: MoodState) => void): void;

  /** Unsubscribe from mood updates */
  offMoodChange(callback: (mood: MoodState) => void): void;
}

/**
 * Convert a numerical energy value to a mood level.
 * @param energy - Energy value from 0 to 1
 * @param previousLevel - Previous mood level (used for hysteresis)
 */
export function energyToMoodLevel(
  energy: number,
  previousLevel?: MoodLevel
): MoodLevel {
  // Add hysteresis to prevent rapid oscillation
  const hysteresis = previousLevel ? 0.05 : 0;

  if (energy <= 0.2 - hysteresis) return 'chill';
  if (energy <= 0.4 - hysteresis) return 'warming_up';
  if (energy <= 0.65 - hysteresis) return 'energetic';
  if (energy > 0.65 + hysteresis) return 'peak';

  // If within hysteresis range, keep previous level
  return previousLevel || 'energetic';
}
