# PRD: Reactive DJ Mode

## Overview

The AI DJ should intelligently react to mood changes in real-time, not just at track boundaries. When the detected mood shifts significantly, the DJ should decide whether to:

1. **Transition now** - Start crossfading to a better-matched track
2. **Wait and watch** - The mood might settle back
3. **Let it play out** - Current track is close enough, or nearly finished anyway

This makes the DJ feel alive and responsive to the crowd, rather than mechanically playing songs to completion.

---

## Current Behavior (Problem)

```
Timeline:
[====== Track A (4 min, energy 0.3) ======][== Track B ==]
                    ↑
          Mood jumps to 0.8 here
          But we wait 2+ more minutes!
```

- Tracks always play to completion (minus 15s crossfade window)
- Mood changes only affect the NEXT track selection
- `minTrackPlayTime` exists but isn't used meaningfully
- Result: DJ feels slow and unresponsive to crowd energy

---

## Desired Behavior

```
Timeline:
[==== Track A ====][======= Track B (high energy) =======]
                  ↑
        Mood jumps to 0.8, DJ reacts!
        Early transition after 30s minimum
```

- Monitor mood continuously during playback
- When mood shifts significantly, EVALUATE whether to transition early
- Use intelligent decision-making, not just thresholds
- Respect minimum play time to avoid jarring rapid changes

---

## Transition Decision Model

### Inputs

| Input                     | Description                                   | Range   |
| ------------------------- | --------------------------------------------- | ------- |
| `currentTrackEnergy`      | Energy level of playing track                 | 0-1     |
| `currentMoodEnergy`       | Current detected mood energy                  | 0-1     |
| `energyDelta`             | `abs(currentMoodEnergy - currentTrackEnergy)` | 0-1     |
| `moodConfidence`          | How confident we are in the mood reading      | 0-1     |
| `moodTrend`               | Is mood rising, falling, or stable            | enum    |
| `moodStability`           | How long mood has been at current level       | seconds |
| `trackPlayedTime`         | How long current track has played             | seconds |
| `trackRemainingTime`      | Time until track naturally ends               | seconds |
| `timeSinceLastTransition` | Cooldown since last early transition          | seconds |

### Decision Output

```typescript
type TransitionDecision = {
  action: 'transition_now' | 'wait' | 'let_play';
  confidence: number; // 0-1, how confident in this decision
  reason: string; // Human-readable explanation
  waitTime?: number; // If 'wait', re-evaluate after this many seconds
};
```

### Decision Logic

#### 1. Hard Rules (Non-negotiable)

```typescript
// NEVER transition if:
if (trackPlayedTime < minTrackPlayTime)
  return { action: 'let_play', reason: 'Minimum play time not reached' };
if (timeSinceLastTransition < cooldownPeriod)
  return { action: 'let_play', reason: 'Cooldown active' };
if (trackRemainingTime < crossfadeDuration + 5)
  return { action: 'let_play', reason: 'Track nearly finished anyway' };
```

#### 2. Scoring System

Calculate a **transition urgency score** (0-100):

```typescript
let score = 0;

// Energy mismatch (0-40 points)
// Bigger mismatch = more urgent
score += energyDelta * 40;

// Mood confidence (0-20 points)
// Higher confidence = trust the reading more
score += moodConfidence * 20;

// Mood stability bonus (0-15 points)
// Sustained mood change = not just a spike
if (moodStability > 5) score += 10;
if (moodStability > 10) score += 5;

// Track time factor (0-15 points)
// Longer played = less disruptive to switch
const playedRatio = trackPlayedTime / trackDuration;
score += playedRatio * 15;

// Trend alignment (0-10 points)
// If mood is rising and we're playing low energy, more urgent
if (moodTrend === 'rising' && currentTrackEnergy < 0.5) score += 10;
if (moodTrend === 'falling' && currentTrackEnergy > 0.5) score += 10;
```

#### 3. Score Interpretation

| Score  | Action           | Meaning                                               |
| ------ | ---------------- | ----------------------------------------------------- |
| 0-30   | `let_play`       | Current track is fine, or mood isn't different enough |
| 31-60  | `wait`           | Mood is shifting, monitor for 5-10 more seconds       |
| 61-100 | `transition_now` | Clear mismatch, start crossfade immediately           |

---

## Implementation Plan

### Phase 1: Transition Evaluator ✅ IMPLEMENTED

Create `src/selection/transition-evaluator.ts`:

```typescript
interface TransitionContext {
  currentTrack: Track;
  currentMood: MoodState;
  trackPlayedSeconds: number;
  trackDuration: number;
  timeSinceLastTransition: number;
  moodStabilitySeconds: number;
}

class TransitionEvaluator {
  evaluate(context: TransitionContext): TransitionDecision;
  private calculateUrgencyScore(context: TransitionContext): number;
}
```

### Phase 2: DJ Controller Integration ✅ IMPLEMENTED

Update `DJController` to:

1. **Track mood stability** - How long has mood been at current level?
2. **Periodic evaluation** - Every 2-3 seconds, run transition evaluator
3. **Act on decisions** - If `transition_now`, trigger early crossfade
4. **Track cooldowns** - Prevent rapid-fire transitions

```typescript
// In DJController
private lastTransitionTime: number = 0;
private moodStableSince: number = 0;
private evaluationInterval: NodeJS.Timeout | null = null;

private startReactiveMode(): void {
  this.evaluationInterval = setInterval(() => {
    this.evaluateTransition();
  }, 3000); // Check every 3 seconds
}

private evaluateTransition(): void {
  const decision = this.transitionEvaluator.evaluate({
    currentTrack: this.currentTrack,
    currentMood: this.getCurrentMood(),
    trackPlayedSeconds: this.getTrackPlayedTime(),
    trackDuration: this.currentTrack.duration,
    timeSinceLastTransition: Date.now() - this.lastTransitionTime,
    moodStabilitySeconds: this.getMoodStability(),
  });

  if (decision.action === 'transition_now') {
    this.triggerEarlyTransition(decision.reason);
  }
}
```

### Phase 3: Browser Communication ✅ IMPLEMENTED

New message types:

```typescript
// Server → Browser
interface EarlyTransitionMessage {
  type: 'early_transition';
  track: Track;
  reason: string;
}

// Browser handles this by immediately queuing
// the track and starting crossfade
```

### Phase 4: Configuration ✅ IMPLEMENTED

Add to `config.json`:

```json
{
  "reactivity": {
    "enabled": true,
    "minTrackPlayTime": 30,
    "cooldownPeriod": 45,
    "evaluationInterval": 3000,
    "thresholds": {
      "letPlay": 30,
      "wait": 60,
      "transitionNow": 61
    }
  }
}
```

---

## UI Updates

### Activity Log

```
🌡️ Mood shift detected: chill → peak (Δ0.6)
🤔 Evaluating transition... (score: 72)
⚡ Early transition triggered: "Energy mismatch with rising crowd"
⏭️ Crossfading to: "High Energy Track" by Artist
```

### Mood Card Enhancement

Show when DJ is "considering" a transition:

- Pulsing indicator when score > 30
- "Monitoring mood shift..." status text

---

## Edge Cases

### Rapid Oscillation

**Problem**: Mood bouncing between levels causing chaos
**Solution**: `moodStability` requirement - mood must be sustained 5+ seconds

### Low Confidence Camera

**Problem**: Poor lighting = unreliable mood detection
**Solution**: Weight confidence heavily in score; low confidence = prefer `let_play`

### Very Short Tracks

**Problem**: Track is only 90 seconds, minPlayTime is 30s
**Solution**: If track duration < 2 \* minPlayTime, disable reactive mode for that track

### Back-to-Back Early Transitions

**Problem**: Two early transitions in a row feels chaotic
**Solution**: `cooldownPeriod` of 45-60 seconds between early transitions

---

## Success Metrics

1. **Responsiveness**: Average time between mood shift and track energy alignment
2. **Stability**: Early transitions per hour (target: 2-6, not too many)
3. **Smoothness**: No transitions before 30 seconds
4. **User satisfaction**: Does it feel like a real DJ reading the room?

---

## Future Enhancements

1. **Learning**: Track which early transitions "worked" (crowd stayed energized)
2. **Genre awareness**: Some genres tolerate early cuts better than others
3. **Beat matching**: Only transition at phrase boundaries (every 16/32 bars)
4. **Predictive**: Anticipate mood changes based on time of night / historical patterns
