/**
 * Random Mood Detector
 *
 * Generates plausible random mood states that drift gradually.
 * Useful for testing and as a fallback when camera is unavailable.
 */

import { BaseMoodDetector } from './detector.js';
import { MoodState, MoodLevel, energyToMoodLevel } from './types.js';

export interface RandomDetectorOptions {
  /** How often to update mood (ms), default 2000 */
  updateInterval?: number;
  /** Maximum energy change per update, default 0.08 */
  maxDrift?: number;
  /** Starting energy level, default 0.35 */
  initialEnergy?: number;
  /** Whether to simulate realistic party progression, default true */
  simulateProgression?: boolean;
}

/**
 * Generates random mood states that drift gradually over time.
 * Simulates realistic party energy progression.
 */
export class RandomMoodDetector extends BaseMoodDetector {
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private options: Required<RandomDetectorOptions>;
  private startTime: number = 0;

  constructor(options: RandomDetectorOptions = {}) {
    super();
    this.options = {
      updateInterval: options.updateInterval ?? 2000,
      maxDrift: options.maxDrift ?? 0.08,
      initialEnergy: options.initialEnergy ?? 0.35,
      simulateProgression: options.simulateProgression ?? true,
    };

    // Set initial energy
    this.currentMood.energy = this.options.initialEnergy;
    this.currentMood.level = energyToMoodLevel(this.options.initialEnergy);
  }

  start(): void {
    if (this.running) return;

    this.running = true;
    this.startTime = Date.now();
    console.log('🎲 Random mood detector started');

    // Generate initial mood
    this.generateMood();

    // Start periodic updates
    this.intervalId = setInterval(() => {
      this.generateMood();
    }, this.options.updateInterval);
  }

  stop(): void {
    if (!this.running) return;

    this.running = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    console.log('🎲 Random mood detector stopped');
  }

  /**
   * Generate a new mood value with gradual drift.
   */
  private generateMood(): void {
    const previousEnergy = this.currentMood.energy;
    let targetEnergy: number;

    if (this.options.simulateProgression) {
      // Simulate realistic party progression
      targetEnergy = this.calculateProgressionTarget();
    } else {
      // Pure random drift
      targetEnergy = this.calculateRandomDrift(previousEnergy);
    }

    // Apply drift with smoothing
    const drift = (targetEnergy - previousEnergy) * 0.3;
    const newEnergy = Math.max(0, Math.min(1, previousEnergy + drift));

    // Add small random noise for natural feel
    const noise = (Math.random() - 0.5) * 0.04;
    const finalEnergy = Math.max(0, Math.min(1, newEnergy + noise));

    const previousLevel = this.currentMood.level;
    const newLevel = energyToMoodLevel(finalEnergy, previousLevel);

    this.updateMood({
      energy: finalEnergy,
      level: newLevel,
      confidence: 0.8 + Math.random() * 0.2, // Simulated confidence
    });
  }

  /**
   * Calculate target energy based on simulated party progression.
   * Parties typically: start slow → build up → peak → cool down
   */
  private calculateProgressionTarget(): number {
    const elapsedMinutes = (Date.now() - this.startTime) / 60000;

    // Simulate a ~60 minute party arc compressed into ~10 minute cycles
    const cyclePosition = (elapsedMinutes % 10) / 10;

    // Party energy curve: slow start → peak around 70% → cool down
    let baseTarget: number;
    if (cyclePosition < 0.15) {
      // Warm up phase (first 15%)
      baseTarget = 0.2 + cyclePosition * 2;
    } else if (cyclePosition < 0.7) {
      // Build up and peak (15% - 70%)
      const buildPhase = (cyclePosition - 0.15) / 0.55;
      baseTarget = 0.5 + buildPhase * 0.4;
    } else {
      // Cool down (70% - 100%)
      const coolPhase = (cyclePosition - 0.7) / 0.3;
      baseTarget = 0.9 - coolPhase * 0.5;
    }

    // Add randomness to prevent it feeling too scripted
    return baseTarget + (Math.random() - 0.5) * 0.2;
  }

  /**
   * Calculate pure random drift from current energy.
   */
  private calculateRandomDrift(currentEnergy: number): number {
    const maxDrift = this.options.maxDrift;
    const drift = (Math.random() - 0.5) * 2 * maxDrift;

    // Bias toward center to prevent getting stuck at extremes
    const centerBias = (0.5 - currentEnergy) * 0.1;

    return currentEnergy + drift + centerBias;
  }
}
