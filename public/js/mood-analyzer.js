/**
 * Mood Analyzer
 *
 * Converts motion detection data into mood states.
 * Smooths values over time and maps to mood levels.
 */

export class MoodAnalyzer {
  constructor(options = {}) {
    // Smoothing parameters
    this.smoothingWindow = options.smoothingWindow ?? 5000; // ms
    this.updateInterval = options.updateInterval ?? 1000; // Send updates every 1 second

    // Motion history for smoothing
    this.motionHistory = [];

    // Mood thresholds (motion percentage → mood)
    this.thresholds = {
      chill: 10, // 0-10% motion
      warming_up: 30, // 10-30% motion
      energetic: 60, // 30-60% motion
      peak: 100, // 60-100% motion
    };

    // Current state
    this.currentMood = {
      level: 'chill',
      energy: 0,
      trend: 'stable',
      confidence: 0.5,
      motionRaw: 0,
      motionSmoothed: 0,
    };

    // Previous values for trend detection
    this.previousEnergy = 0;
    this.trendHistory = [];

    // Callbacks
    this.onMoodUpdate = null;

    // Update timer
    this.updateTimer = null;
    this.lastUpdateTime = 0;
  }

  /**
   * Start the mood analyzer.
   */
  start() {
    this.lastUpdateTime = Date.now();

    // Set up periodic update emission
    this.updateTimer = setInterval(() => {
      this.emitUpdate();
    }, this.updateInterval);

    console.log('[MoodAnalyzer] Started');
  }

  /**
   * Stop the mood analyzer.
   */
  stop() {
    if (this.updateTimer) {
      clearInterval(this.updateTimer);
      this.updateTimer = null;
    }
    console.log('[MoodAnalyzer] Stopped');
  }

  /**
   * Process a motion detection result.
   * @param {Object} motion - Motion data from detector
   * @param {number} motion.percentage - Motion percentage 0-100
   */
  processMotion(motion) {
    const now = Date.now();

    // Add to history
    this.motionHistory.push({
      value: motion.percentage,
      timestamp: now,
    });

    // Remove old entries outside smoothing window
    const cutoff = now - this.smoothingWindow;
    this.motionHistory = this.motionHistory.filter((m) => m.timestamp > cutoff);

    // Calculate smoothed motion
    const smoothedMotion = this.calculateSmoothedMotion();

    // Map to energy (0-1)
    const energy = this.motionToEnergy(smoothedMotion);

    // Detect trend
    const trend = this.detectTrend(energy);

    // Map energy to mood level
    const level = this.energyToLevel(energy, trend);

    // Update current mood
    this.currentMood = {
      level,
      energy,
      trend,
      confidence: this.calculateConfidence(),
      motionRaw: motion.percentage,
      motionSmoothed: smoothedMotion,
    };
  }

  /**
   * Calculate smoothed motion using weighted average.
   * More recent values have higher weight.
   */
  calculateSmoothedMotion() {
    if (this.motionHistory.length === 0) return 0;

    const now = Date.now();
    let weightedSum = 0;
    let weightSum = 0;

    for (const entry of this.motionHistory) {
      // Weight by recency (newer = higher weight)
      const age = now - entry.timestamp;
      const weight = 1 - age / this.smoothingWindow;

      weightedSum += entry.value * weight;
      weightSum += weight;
    }

    return weightSum > 0 ? weightedSum / weightSum : 0;
  }

  /**
   * Map motion percentage (0-100) to energy (0-1).
   * Uses a slight curve to make mid-range more responsive.
   */
  motionToEnergy(motionPercentage) {
    // Normalize to 0-1
    const normalized = motionPercentage / 100;

    // Apply slight curve for better responsiveness
    // This makes mid-range values more prominent
    const curved = Math.pow(normalized, 0.8);

    return Math.min(1, Math.max(0, curved));
  }

  /**
   * Detect energy trend (rising, falling, stable).
   */
  detectTrend(currentEnergy) {
    // Add to trend history
    this.trendHistory.push(currentEnergy);

    // Keep last 5 values
    if (this.trendHistory.length > 5) {
      this.trendHistory.shift();
    }

    if (this.trendHistory.length < 3) {
      return 'stable';
    }

    // Calculate average of first half vs second half
    const mid = Math.floor(this.trendHistory.length / 2);
    const firstHalf =
      this.trendHistory.slice(0, mid).reduce((a, b) => a + b, 0) / mid;
    const secondHalf =
      this.trendHistory.slice(mid).reduce((a, b) => a + b, 0) /
      (this.trendHistory.length - mid);

    const diff = secondHalf - firstHalf;

    if (diff > 0.05) return 'rising';
    if (diff < -0.05) return 'falling';
    return 'stable';
  }

  /**
   * Map energy to mood level with hysteresis.
   */
  energyToLevel(energy, trend) {
    const currentLevel = this.currentMood.level;

    // Thresholds with hysteresis (slightly different for up vs down)
    const hysteresis = 0.03;

    if (energy < 0.1 - (currentLevel === 'chill' ? 0 : hysteresis)) {
      return 'chill';
    } else if (energy < 0.3 - (currentLevel === 'warming_up' ? 0 : hysteresis)) {
      return 'warming_up';
    } else if (energy < 0.6 - (currentLevel === 'energetic' ? 0 : hysteresis)) {
      return 'energetic';
    } else if (energy < 0.85) {
      return 'peak';
    } else if (trend === 'falling' && energy >= 0.85) {
      return 'cooling_down';
    }

    return 'peak';
  }

  /**
   * Calculate confidence based on data quality.
   */
  calculateConfidence() {
    // Base confidence on amount of data
    const dataPoints = this.motionHistory.length;
    const maxPoints = this.smoothingWindow / 100; // ~50 points at 10fps

    const dataConfidence = Math.min(1, dataPoints / maxPoints);

    // Higher confidence when motion is consistent
    if (this.motionHistory.length < 2) return 0.5;

    const values = this.motionHistory.map((m) => m.value);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance =
      values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
    const stdDev = Math.sqrt(variance);

    // Lower variance = higher confidence
    const consistencyConfidence = Math.max(0.3, 1 - stdDev / 50);

    return dataConfidence * consistencyConfidence;
  }

  /**
   * Emit mood update to callback.
   */
  emitUpdate() {
    if (this.onMoodUpdate) {
      this.onMoodUpdate(this.getMood());
    }
  }

  /**
   * Get current mood state.
   */
  getMood() {
    return { ...this.currentMood };
  }

  /**
   * Get mood in format suitable for WebSocket transmission.
   */
  getMoodForServer() {
    return {
      level: this.currentMood.level,
      energy: this.currentMood.energy,
      trend: this.currentMood.trend,
      confidence: this.currentMood.confidence,
    };
  }

  /**
   * Reset the analyzer state.
   */
  reset() {
    this.motionHistory = [];
    this.trendHistory = [];
    this.previousEnergy = 0;
    this.currentMood = {
      level: 'chill',
      energy: 0,
      trend: 'stable',
      confidence: 0.5,
      motionRaw: 0,
      motionSmoothed: 0,
    };
    console.log('[MoodAnalyzer] Reset');
  }

  /**
   * Adjust motion thresholds.
   */
  setThresholds(thresholds) {
    this.thresholds = { ...this.thresholds, ...thresholds };
    console.log('[MoodAnalyzer] Thresholds updated:', this.thresholds);
  }
}

