/**
 * Base Mood Detector
 *
 * Abstract base class for mood detectors providing common functionality.
 */

import { MoodDetector, MoodState, MoodLevel } from './types.js';

/**
 * Abstract base class that implements common mood detector functionality.
 */
export abstract class BaseMoodDetector implements MoodDetector {
  protected running: boolean = false;
  protected currentMood: MoodState;
  protected listeners: Set<(mood: MoodState) => void> = new Set();

  constructor() {
    // Initialize with a neutral state
    this.currentMood = {
      level: 'warming_up',
      energy: 0.35,
      trend: 'stable',
      timestamp: Date.now(),
      confidence: 1.0,
    };
  }

  getCurrentMood(): MoodState {
    return { ...this.currentMood };
  }

  abstract start(): void;
  abstract stop(): void;

  isRunning(): boolean {
    return this.running;
  }

  onMoodChange(callback: (mood: MoodState) => void): void {
    this.listeners.add(callback);
  }

  offMoodChange(callback: (mood: MoodState) => void): void {
    this.listeners.delete(callback);
  }

  /**
   * Update the current mood and notify listeners.
   */
  protected updateMood(mood: Partial<MoodState>): void {
    const previousEnergy = this.currentMood.energy;

    this.currentMood = {
      ...this.currentMood,
      ...mood,
      timestamp: Date.now(),
    };

    // Calculate trend based on energy change
    const energyDiff = this.currentMood.energy - previousEnergy;
    if (Math.abs(energyDiff) < 0.02) {
      this.currentMood.trend = 'stable';
    } else if (energyDiff > 0) {
      this.currentMood.trend = 'rising';
    } else {
      this.currentMood.trend = 'falling';
    }

    // Notify listeners
    this.notifyListeners();
  }

  /**
   * Notify all registered listeners of mood change.
   */
  protected notifyListeners(): void {
    const mood = this.getCurrentMood();
    for (const listener of this.listeners) {
      try {
        listener(mood);
      } catch (error) {
        console.error('Error in mood change listener:', error);
      }
    }
  }

  /**
   * Determine mood level from energy with optional previous level for hysteresis.
   */
  protected calculateMoodLevel(energy: number): MoodLevel {
    if (energy <= 0.2) return 'chill';
    if (energy <= 0.4) return 'warming_up';
    if (energy <= 0.65) return 'energetic';
    return 'peak';
  }
}
