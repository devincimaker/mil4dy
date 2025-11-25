/**
 * Camera Mood Detector
 *
 * Receives mood updates from browser (camera-based motion detection)
 * and applies server-side smoothing and hysteresis.
 */

import { BaseMoodDetector } from './detector.js';
import { MoodState, MoodLevel, energyToMoodLevel } from './types.js';

export interface CameraDetectorOptions {
  /** Smoothing factor (0-1), higher = more smoothing, default 0.3 */
  smoothingFactor?: number;
  /** Minimum time between mood level changes (ms), default 3000 */
  hysteresisTime?: number;
  /** Minimum energy change to trigger update, default 0.05 */
  minEnergyChange?: number;
  /** Timeout for no updates before falling back (ms), default 10000 */
  timeoutMs?: number;
}

/**
 * Processes mood updates from browser camera.
 * Applies additional smoothing and prevents rapid oscillation.
 */
export class CameraMoodDetector extends BaseMoodDetector {
  private options: Required<CameraDetectorOptions>;
  private lastLevelChangeTime: number = 0;
  private lastUpdateTime: number = 0;
  private timeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private smoothedEnergy: number = 0;

  // Callback when camera times out (no updates received)
  public onTimeout: (() => void) | null = null;

  constructor(options: CameraDetectorOptions = {}) {
    super();
    this.options = {
      smoothingFactor: options.smoothingFactor ?? 0.3,
      hysteresisTime: options.hysteresisTime ?? 3000,
      minEnergyChange: options.minEnergyChange ?? 0.05,
      timeoutMs: options.timeoutMs ?? 10000,
    };
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.lastUpdateTime = Date.now();
    this.startTimeoutTimer();
    console.log('📷 Camera mood detector started');
  }

  stop(): void {
    if (!this.running) return;
    this.running = false;
    this.stopTimeoutTimer();
    console.log('📷 Camera mood detector stopped');
  }

  /**
   * Process a mood update from the browser.
   * @param browserMood - Mood data from browser camera analysis
   */
  processBrowserUpdate(browserMood: {
    level: MoodLevel;
    energy: number;
    trend: 'rising' | 'falling' | 'stable';
    confidence: number;
  }): void {
    if (!this.running) return;

    this.lastUpdateTime = Date.now();
    this.resetTimeoutTimer();

    // Apply exponential smoothing to energy
    const alpha = this.options.smoothingFactor;
    this.smoothedEnergy =
      alpha * browserMood.energy + (1 - alpha) * this.smoothedEnergy;

    // Check if energy changed enough to warrant an update
    const energyDelta = Math.abs(this.smoothedEnergy - this.currentMood.energy);
    if (energyDelta < this.options.minEnergyChange) {
      return; // Skip minor fluctuations
    }

    // Determine new mood level with hysteresis
    const now = Date.now();
    const timeSinceLastChange = now - this.lastLevelChangeTime;
    const previousLevel = this.currentMood.level;

    // Convert smoothed energy to mood level
    let newLevel = energyToMoodLevel(this.smoothedEnergy, previousLevel);

    // Apply hysteresis - only allow level change if enough time has passed
    if (newLevel !== previousLevel) {
      if (timeSinceLastChange < this.options.hysteresisTime) {
        // Not enough time passed, keep previous level
        newLevel = previousLevel;
      } else {
        // Allow the change
        this.lastLevelChangeTime = now;
      }
    }

    // Update mood state
    this.updateMood({
      energy: this.smoothedEnergy,
      level: newLevel,
      trend: browserMood.trend,
      confidence: browserMood.confidence,
    });
  }

  /**
   * Start the timeout timer.
   */
  private startTimeoutTimer(): void {
    this.stopTimeoutTimer();
    this.timeoutTimer = setTimeout(() => {
      this.handleTimeout();
    }, this.options.timeoutMs);
  }

  /**
   * Reset the timeout timer.
   */
  private resetTimeoutTimer(): void {
    if (this.running) {
      this.startTimeoutTimer();
    }
  }

  /**
   * Stop the timeout timer.
   */
  private stopTimeoutTimer(): void {
    if (this.timeoutTimer) {
      clearTimeout(this.timeoutTimer);
      this.timeoutTimer = null;
    }
  }

  /**
   * Handle timeout (no camera updates received).
   */
  private handleTimeout(): void {
    console.log('📷 Camera mood detector timed out (no updates received)');
    if (this.onTimeout) {
      this.onTimeout();
    }
  }

  /**
   * Get time since last update in milliseconds.
   */
  getTimeSinceLastUpdate(): number {
    return Date.now() - this.lastUpdateTime;
  }

  /**
   * Check if camera is actively sending updates.
   */
  isReceivingUpdates(): boolean {
    return this.getTimeSinceLastUpdate() < this.options.timeoutMs;
  }
}

