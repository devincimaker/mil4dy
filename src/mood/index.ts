/**
 * Mood Module
 *
 * Exports all mood-related types and classes.
 */

export {
  MoodLevel,
  MoodState,
  MoodDetector,
  MOOD_LEVEL_VALUES,
  MOOD_ENERGY_RANGES,
  energyToMoodLevel,
} from './types.js';

export { BaseMoodDetector } from './detector.js';
export { RandomMoodDetector, RandomDetectorOptions } from './random-detector.js';
export { CameraMoodDetector, CameraDetectorOptions } from './camera-detector.js';

