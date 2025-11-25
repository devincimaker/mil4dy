/**
 * Transition Evaluator
 *
 * Decides whether to trigger an early track transition based on mood changes.
 * Implements the scoring system from PRD_REACTIVITY.md
 */

import { Track } from '../music/index.js';
import { MoodState } from '../mood/index.js';

/**
 * Configuration for the transition evaluator.
 */
export interface TransitionEvaluatorOptions {
  /** Minimum time a track must play before early transition (seconds), default 30 */
  minTrackPlayTime?: number;
  /** Cooldown between early transitions (seconds), default 45 */
  cooldownPeriod?: number;
  /** How often to evaluate transitions (ms), default 3000 */
  evaluationInterval?: number;
  /** Score thresholds for decisions */
  thresholds?: {
    /** Score below this = let_play, default 30 */
    letPlay?: number;
    /** Score below this = wait, above = transition_now, default 60 */
    wait?: number;
  };
  /** Crossfade duration for "nearly finished" check (seconds), default 8 */
  crossfadeDuration?: number;
}

/**
 * Internal required options with all defaults applied.
 */
interface ResolvedOptions {
  minTrackPlayTime: number;
  cooldownPeriod: number;
  evaluationInterval: number;
  thresholds: {
    letPlay: number;
    wait: number;
  };
  crossfadeDuration: number;
}

/**
 * Context provided to the evaluator for decision making.
 */
export interface TransitionContext {
  /** Currently playing track */
  currentTrack: Track;
  /** Current mood state */
  currentMood: MoodState;
  /** Mood when the current track started playing */
  moodAtTrackStart: MoodState;
  /** How long current track has played (seconds) */
  trackPlayedSeconds: number;
  /** Total duration of current track (seconds) */
  trackDuration: number;
  /** Time since last early transition (seconds) */
  timeSinceLastTransition: number;
  /** How long mood has been stable at current level (seconds) */
  moodStabilitySeconds: number;
}

/**
 * Result of a transition evaluation.
 */
export interface TransitionDecision {
  /** What action to take */
  action: 'transition_now' | 'wait' | 'let_play';
  /** Confidence in this decision (0-1) */
  confidence: number;
  /** Human-readable explanation */
  reason: string;
  /** If 'wait', re-evaluate after this many seconds */
  waitTime?: number;
  /** The urgency score that led to this decision */
  score: number;
}

/**
 * Evaluates whether to trigger an early track transition based on mood changes.
 */
export class TransitionEvaluator {
  private options: ResolvedOptions;

  constructor(options: TransitionEvaluatorOptions = {}) {
    this.options = {
      minTrackPlayTime: options.minTrackPlayTime ?? 30,
      cooldownPeriod: options.cooldownPeriod ?? 45,
      evaluationInterval: options.evaluationInterval ?? 3000,
      thresholds: {
        letPlay: options.thresholds?.letPlay ?? 30,
        wait: options.thresholds?.wait ?? 60,
      },
      crossfadeDuration: options.crossfadeDuration ?? 8,
    };
  }

  /**
   * Evaluate whether to trigger an early transition.
   */
  evaluate(context: TransitionContext): TransitionDecision {
    const {
      currentTrack,
      trackPlayedSeconds,
      trackDuration,
      timeSinceLastTransition,
    } = context;

    const trackRemainingTime = trackDuration - trackPlayedSeconds;

    // ============================================
    // Hard Rules (Non-negotiable)
    // ============================================

    // Rule 1: Minimum play time not reached
    if (trackPlayedSeconds < this.options.minTrackPlayTime) {
      return {
        action: 'let_play',
        confidence: 1,
        reason: `Minimum play time not reached (${trackPlayedSeconds.toFixed(0)}s / ${this.options.minTrackPlayTime}s)`,
        score: 0,
      };
    }

    // Rule 2: Cooldown active
    if (timeSinceLastTransition < this.options.cooldownPeriod) {
      return {
        action: 'let_play',
        confidence: 1,
        reason: `Cooldown active (${timeSinceLastTransition.toFixed(0)}s / ${this.options.cooldownPeriod}s)`,
        score: 0,
      };
    }

    // Rule 3: Track nearly finished anyway
    if (trackRemainingTime < this.options.crossfadeDuration + 5) {
      return {
        action: 'let_play',
        confidence: 1,
        reason: `Track nearly finished (${trackRemainingTime.toFixed(0)}s remaining)`,
        score: 0,
      };
    }

    // Rule 4: Very short track - disable reactive mode
    if (trackDuration < 2 * this.options.minTrackPlayTime) {
      return {
        action: 'let_play',
        confidence: 1,
        reason: `Track too short for reactive mode (${trackDuration.toFixed(0)}s)`,
        score: 0,
      };
    }

    // ============================================
    // Scoring System
    // ============================================

    const score = this.calculateUrgencyScore(context);

    // ============================================
    // Score Interpretation
    // ============================================

    if (score <= this.options.thresholds.letPlay) {
      return {
        action: 'let_play',
        confidence: this.scoreToConfidence(score, 'let_play'),
        reason: this.generateReason(context, score, 'let_play'),
        score,
      };
    }

    if (score <= this.options.thresholds.wait) {
      return {
        action: 'wait',
        confidence: this.scoreToConfidence(score, 'wait'),
        reason: this.generateReason(context, score, 'wait'),
        waitTime: 5, // Re-evaluate in 5 seconds
        score,
      };
    }

    return {
      action: 'transition_now',
      confidence: this.scoreToConfidence(score, 'transition_now'),
      reason: this.generateReason(context, score, 'transition_now'),
      score,
    };
  }

  /**
   * Calculate the urgency score (0-100).
   */
  private calculateUrgencyScore(context: TransitionContext): number {
    const {
      currentTrack,
      currentMood,
      moodAtTrackStart,
      trackPlayedSeconds,
      trackDuration,
      moodStabilitySeconds,
    } = context;

    let score = 0;

    // ============================================
    // Energy mismatch (0-40 points)
    // Bigger mismatch = more urgent
    // ============================================
    const currentTrackEnergy = currentTrack.energy;
    const currentMoodEnergy = currentMood.energy;
    const energyDelta = Math.abs(currentMoodEnergy - currentTrackEnergy);

    score += energyDelta * 40;

    // ============================================
    // Mood confidence (0-20 points)
    // Higher confidence = trust the reading more
    // ============================================
    score += currentMood.confidence * 20;

    // ============================================
    // Mood stability bonus (0-15 points)
    // Sustained mood change = not just a spike
    // ============================================
    if (moodStabilitySeconds > 5) score += 10;
    if (moodStabilitySeconds > 10) score += 5;

    // ============================================
    // Track time factor (0-15 points)
    // Longer played = less disruptive to switch
    // ============================================
    const playedRatio = trackPlayedSeconds / trackDuration;
    score += playedRatio * 15;

    // ============================================
    // Trend alignment (0-10 points)
    // If mood is rising and we're playing low energy, more urgent
    // ============================================
    if (currentMood.trend === 'rising' && currentTrackEnergy < 0.5) {
      score += 10;
    } else if (currentMood.trend === 'falling' && currentTrackEnergy > 0.5) {
      score += 10;
    }

    // ============================================
    // Direction bonus (0-10 points)
    // Reward larger shifts from track start mood
    // ============================================
    const moodShiftFromStart = Math.abs(
      currentMoodEnergy - moodAtTrackStart.energy
    );
    score += moodShiftFromStart * 10;

    return Math.min(100, Math.max(0, score));
  }

  /**
   * Convert score to confidence level.
   */
  private scoreToConfidence(
    score: number,
    action: TransitionDecision['action']
  ): number {
    const { letPlay, wait } = this.options.thresholds;

    switch (action) {
      case 'let_play':
        // High confidence when score is very low
        return Math.max(0.5, 1 - score / letPlay);

      case 'wait':
        // Medium confidence in the middle range
        const waitRange = wait - letPlay;
        const positionInRange = (score - letPlay) / waitRange;
        return 0.4 + positionInRange * 0.3;

      case 'transition_now':
        // Higher score = higher confidence
        return Math.min(1, 0.7 + (score - wait) / 100);
    }
  }

  /**
   * Generate a human-readable reason for the decision.
   */
  private generateReason(
    context: TransitionContext,
    score: number,
    action: TransitionDecision['action']
  ): string {
    const {
      currentTrack,
      currentMood,
      moodAtTrackStart,
      moodStabilitySeconds,
    } = context;

    const energyDelta = Math.abs(currentMood.energy - currentTrack.energy);
    const moodShift = currentMood.energy - moodAtTrackStart.energy;

    const parts: string[] = [];

    // Energy mismatch description
    if (energyDelta > 0.4) {
      parts.push(`large energy mismatch (Δ${energyDelta.toFixed(2)})`);
    } else if (energyDelta > 0.25) {
      parts.push(`moderate energy mismatch (Δ${energyDelta.toFixed(2)})`);
    } else if (energyDelta < 0.15) {
      parts.push('track energy matches mood');
    }

    // Mood trend
    if (currentMood.trend === 'rising' && moodShift > 0.2) {
      parts.push('crowd energy rising');
    } else if (currentMood.trend === 'falling' && moodShift < -0.2) {
      parts.push('crowd energy dropping');
    }

    // Stability
    if (moodStabilitySeconds > 10) {
      parts.push(`mood stable ${moodStabilitySeconds.toFixed(0)}s`);
    }

    // Confidence note
    if (currentMood.confidence < 0.5) {
      parts.push('low confidence');
    }

    // Action-specific suffix
    switch (action) {
      case 'transition_now':
        return parts.length > 0
          ? `${parts.join(', ')} - triggering early transition`
          : 'Triggering early transition';

      case 'wait':
        return parts.length > 0
          ? `${parts.join(', ')} - monitoring`
          : 'Monitoring mood shift';

      case 'let_play':
        return parts.length > 0
          ? `${parts.join(', ')} - continuing current track`
          : 'Current track is appropriate';
    }
  }

  /**
   * Get the evaluation interval.
   */
  getEvaluationInterval(): number {
    return this.options.evaluationInterval;
  }

  /**
   * Get the minimum track play time.
   */
  getMinTrackPlayTime(): number {
    return this.options.minTrackPlayTime;
  }

  /**
   * Get the cooldown period.
   */
  getCooldownPeriod(): number {
    return this.options.cooldownPeriod;
  }
}
