/**
 * DJ Controller
 *
 * Main orchestrator for the AI DJ system.
 * Manages mood detection, song selection, and playback coordination.
 */

import { MusicLibrary, Track } from '../music/index.js';
import {
  MoodState,
  MoodDetector,
  RandomMoodDetector,
  CameraMoodDetector,
} from '../mood/index.js';
import {
  SongSelector,
  SelectionResult,
  TransitionEvaluator,
  TransitionContext,
  TransitionDecision,
} from '../selection/index.js';
import {
  DJServer,
  ClientConnection,
  ClientMessage,
  ServerMessage,
  PlayTrackMessage,
  StatusMessage,
  PauseMessage,
  ResumeMessage,
  MoodBroadcastMessage,
  EarlyTransitionMessage,
} from '../server/index.js';

export type DJState = 'idle' | 'starting' | 'playing' | 'paused' | 'stopping';

export interface ReactivityOptions {
  /** Enable reactive mode (default: true) */
  enabled?: boolean;
  /** Minimum track play time before early transition (seconds), default 30 */
  minTrackPlayTime?: number;
  /** Cooldown between early transitions (seconds), default 45 */
  cooldownPeriod?: number;
  /** How often to evaluate transitions (ms), default 3000 */
  evaluationInterval?: number;
  /** Score thresholds for decisions */
  thresholds?: {
    letPlay?: number;
    wait?: number;
  };
}

export interface DJControllerOptions {
  /** Path to library.json */
  libraryPath: string;
  /** Path to music files directory */
  musicDir: string;
  /** Server port */
  port?: number;
  /** Path to public directory */
  publicDir?: string;
  /** Minimum track play time in seconds before allowing skip (default: 30) */
  minTrackPlayTime?: number;
  /** Crossfade duration in seconds (default: 8) */
  crossfadeDuration?: number;
  /** Reactivity options for early transitions */
  reactivity?: ReactivityOptions;
}

/**
 * Main DJ controller that orchestrates all components.
 * Coordinates mood detection, song selection, and browser playback.
 */
export class DJController {
  private state: DJState = 'idle';
  private library: MusicLibrary;
  private randomMoodDetector: RandomMoodDetector;
  private cameraMoodDetector: CameraMoodDetector;
  private selector: SongSelector;
  private server: DJServer;
  private transitionEvaluator: TransitionEvaluator;
  private options: Required<DJControllerOptions>;

  private currentTrack: Track | null = null;
  private nextTrack: Track | null = null;
  private startTime: number = 0;
  private currentTrackStartTime: number = 0;

  // Track which mood source is active
  private moodSource: 'camera' | 'random' = 'random';

  // Reactive mode state
  private reactivityEnabled: boolean = true;
  private moodAtTrackStart: MoodState | null = null;
  private lastTransitionTime: number = 0;
  private moodStableSince: number = 0;
  private lastMoodLevel: string = '';
  private evaluationInterval: ReturnType<typeof setInterval> | null = null;
  private waitingForReEvaluation: boolean = false;

  constructor(options: DJControllerOptions) {
    const reactivityOpts = options.reactivity ?? {};

    this.options = {
      libraryPath: options.libraryPath,
      musicDir: options.musicDir,
      port: options.port ?? 3000,
      publicDir: options.publicDir ?? 'public',
      minTrackPlayTime: options.minTrackPlayTime ?? 30,
      crossfadeDuration: options.crossfadeDuration ?? 8,
      reactivity: {
        enabled: reactivityOpts.enabled ?? true,
        minTrackPlayTime: reactivityOpts.minTrackPlayTime ?? 30,
        cooldownPeriod: reactivityOpts.cooldownPeriod ?? 45,
        evaluationInterval: reactivityOpts.evaluationInterval ?? 3000,
        thresholds: {
          letPlay: reactivityOpts.thresholds?.letPlay ?? 30,
          wait: reactivityOpts.thresholds?.wait ?? 60,
        },
      },
    };

    this.reactivityEnabled = this.options.reactivity.enabled ?? true;

    this.library = new MusicLibrary();
    this.randomMoodDetector = new RandomMoodDetector();
    this.cameraMoodDetector = new CameraMoodDetector();
    this.selector = new SongSelector(this.library);

    // Initialize transition evaluator with reactivity options
    this.transitionEvaluator = new TransitionEvaluator({
      minTrackPlayTime: this.options.reactivity.minTrackPlayTime,
      cooldownPeriod: this.options.reactivity.cooldownPeriod,
      evaluationInterval: this.options.reactivity.evaluationInterval,
      thresholds: this.options.reactivity.thresholds,
      crossfadeDuration: this.options.crossfadeDuration,
    });

    // Create server with event handlers
    this.server = new DJServer(
      {
        onMessage: this.handleClientMessage.bind(this),
        onConnect: this.handleClientConnect.bind(this),
        onDisconnect: this.handleClientDisconnect.bind(this),
      },
      {
        port: this.options.port,
        publicDir: this.options.publicDir,
        musicDir: this.options.musicDir,
      }
    );

    // Set up mood change listeners for both detectors
    this.randomMoodDetector.onMoodChange((mood) => {
      if (this.moodSource === 'random') {
        this.handleMoodChange(mood);
      }
    });

    this.cameraMoodDetector.onMoodChange((mood) => {
      if (this.moodSource === 'camera') {
        this.handleMoodChange(mood);
      }
    });

    // Handle camera timeout - fall back to random
    this.cameraMoodDetector.onTimeout = () => {
      if (this.moodSource === 'camera') {
        console.log('📷 Camera inactive, falling back to random mood');
        this.moodSource = 'random';
      }
    };
  }

  /**
   * Initialize and start the DJ system.
   */
  async start(): Promise<void> {
    if (this.state !== 'idle') {
      console.log('DJ is already running');
      return;
    }

    this.state = 'starting';
    this.startTime = Date.now();

    try {
      // Load music library
      await this.library.load(this.options.libraryPath);

      // Set up server handlers
      this.server.setTrackListHandler(() => this.library.getAll());
      this.server.setAudioStreamHandler((trackId) => {
        const track = this.library.getById(trackId);
        if (!track) return null;
        return {
          path: track.path,
          mimeType: 'audio/mpeg',
        };
      });

      // Start server
      await this.server.start();

      // Start random mood detector (camera detector starts when receiving updates)
      this.randomMoodDetector.start();

      // Initialize reactive mode
      if (this.reactivityEnabled) {
        this.startReactiveMode();
      }

      this.state = 'playing';
      console.log('🎧 AI DJ is ready!');
      console.log(`   Library: ${this.library.count()} tracks`);
      console.log(`   Server: http://localhost:${this.server.getPort()}`);
      console.log(
        `   Reactive mode: ${this.reactivityEnabled ? 'enabled' : 'disabled'}`
      );
    } catch (error) {
      this.state = 'idle';
      throw error;
    }
  }

  /**
   * Stop the DJ system.
   */
  async stop(): Promise<void> {
    if (this.state === 'idle') return;

    this.state = 'stopping';

    this.stopReactiveMode();
    this.randomMoodDetector.stop();
    this.cameraMoodDetector.stop();
    await this.server.stop();

    this.state = 'idle';
    this.currentTrack = null;
    this.nextTrack = null;
    console.log('🛑 AI DJ stopped');
  }

  /**
   * Pause playback.
   * Broadcasts pause command to all connected clients.
   */
  pause(): void {
    if (this.state !== 'playing') {
      console.log('Cannot pause: DJ is not playing');
      return;
    }

    this.state = 'paused';
    this.stopReactiveMode();
    this.randomMoodDetector.stop();
    this.cameraMoodDetector.stop();

    const pauseMessage: PauseMessage = { type: 'pause' };
    const clientCount = this.server.broadcast(pauseMessage);

    console.log(`⏸️  Paused (notified ${clientCount} clients)`);
  }

  /**
   * Resume playback.
   * Broadcasts resume command to all connected clients.
   */
  resume(): void {
    if (this.state !== 'paused') {
      console.log('Cannot resume: DJ is not paused');
      return;
    }

    this.state = 'playing';
    // Restart the appropriate mood detector
    if (this.moodSource === 'camera') {
      this.cameraMoodDetector.start();
    } else {
      this.randomMoodDetector.start();
    }

    // Restart reactive mode
    if (this.reactivityEnabled) {
      this.startReactiveMode();
    }

    const resumeMessage: ResumeMessage = { type: 'resume' };
    const clientCount = this.server.broadcast(resumeMessage);

    console.log(`▶️  Resumed (notified ${clientCount} clients)`);
  }

  /**
   * Get current state.
   */
  getState(): DJState {
    return this.state;
  }

  /**
   * Get current mood from the active detector.
   */
  getCurrentMood(): MoodState {
    if (this.moodSource === 'camera') {
      return this.cameraMoodDetector.getCurrentMood();
    }
    return this.randomMoodDetector.getCurrentMood();
  }

  /**
   * Get current mood source.
   */
  getMoodSource(): 'camera' | 'random' {
    return this.moodSource;
  }

  /**
   * Handle incoming client WebSocket messages.
   */
  private handleClientMessage(
    message: ClientMessage,
    connection: ClientConnection
  ): void {
    console.log(`📨 Message from ${connection.id}: ${message.type}`);

    switch (message.type) {
      case 'client_ready':
        this.handleClientReady(connection);
        break;

      case 'status_request':
        this.sendStatus(connection);
        break;

      case 'mood_update':
        this.handleCameraMoodUpdate(message.mood);
        break;

      case 'track_started':
        console.log(`   Track started: ${message.trackId}`);
        this.handleTrackStarted(message.trackId);
        break;

      case 'track_ending':
        console.log(
          `   Track ending: ${message.trackId}, ${message.remainingSeconds}s remaining`
        );
        this.handleTrackEnding(connection, message.trackId);
        break;

      case 'track_ended':
        console.log(`   Track ended: ${message.trackId}`);
        break;
    }
  }

  /**
   * Handle new client connection.
   */
  private handleClientConnect(connection: ClientConnection): void {
    console.log(`👋 New client: ${connection.id}`);
    // Send current status to new client
    this.sendStatus(connection);
  }

  /**
   * Handle client disconnection.
   */
  private handleClientDisconnect(connection: ClientConnection): void {
    console.log(`👋 Client left: ${connection.id}`);
  }

  /**
   * Handle client ready message.
   */
  private handleClientReady(connection: ClientConnection): void {
    // Select and send first track
    const mood = this.getCurrentMood();
    const selection = this.selector.selectNext(mood);

    this.currentTrack = selection.track;
    this.currentTrackStartTime = Date.now();

    const playMessage: PlayTrackMessage = {
      type: 'play_track',
      track: selection.track,
      reason: selection.reason,
      queuePosition: 'immediate',
    };

    connection.send(playMessage);
    console.log(
      `🎵 Playing: "${selection.track.title}" by ${selection.track.artist}`
    );
    console.log(`   Reason: ${selection.reason}`);
  }

  /**
   * Handle track ending event with minimum play time check.
   */
  private handleTrackEnding(
    connection: ClientConnection,
    trackId: string
  ): void {
    const playedSeconds = (Date.now() - this.currentTrackStartTime) / 1000;
    const minTime = this.options.minTrackPlayTime;

    if (playedSeconds < minTime) {
      console.log(
        `   ⚠️ Track only played ${playedSeconds.toFixed(0)}s (min: ${minTime}s), but allowing natural transition`
      );
    }

    this.prepareNextTrack(connection);
  }

  /**
   * Prepare and queue the next track.
   */
  private prepareNextTrack(connection: ClientConnection): void {
    const mood = this.getCurrentMood();
    const selection = this.selector.selectNext(
      mood,
      this.currentTrack ?? undefined
    );

    this.nextTrack = selection.track;

    const playMessage: PlayTrackMessage = {
      type: 'play_track',
      track: selection.track,
      reason: selection.reason,
      queuePosition: 'next',
    };

    connection.send(playMessage);
    console.log(
      `⏭️  Next up: "${selection.track.title}" by ${selection.track.artist}`
    );
    console.log(`   Reason: ${selection.reason}`);
  }

  /**
   * Handle mood changes from detector.
   * Broadcasts mood to all connected clients and tracks mood stability.
   */
  private handleMoodChange(mood: MoodState): void {
    // Track mood stability for reactive mode
    if (mood.level !== this.lastMoodLevel) {
      this.moodStableSince = Date.now();
      this.lastMoodLevel = mood.level;
    }

    // Log significant mood changes
    console.log(
      `🌡️  Mood: ${mood.level} (${mood.energy.toFixed(2)}) [${mood.trend}] (${this.moodSource})`
    );

    // Broadcast mood to all clients
    const moodBroadcast: MoodBroadcastMessage = {
      type: 'mood_broadcast',
      mood,
      source: this.moodSource,
    };
    this.server.broadcast(moodBroadcast);
  }

  /**
   * Handle camera mood update from browser.
   */
  private handleCameraMoodUpdate(browserMood: {
    level: string;
    energy: number;
    trend: 'rising' | 'falling' | 'stable';
    confidence: number;
  }): void {
    // Switch to camera mode if not already
    if (this.moodSource !== 'camera') {
      console.log('📷 Switching to camera-based mood detection');
      this.moodSource = 'camera';
      this.randomMoodDetector.stop();
      this.cameraMoodDetector.start();
    }

    // Process the update through camera detector
    this.cameraMoodDetector.processBrowserUpdate({
      level: browserMood.level as MoodState['level'],
      energy: browserMood.energy,
      trend: browserMood.trend,
      confidence: browserMood.confidence,
    });

    console.log(
      `   📷 Camera mood: ${browserMood.level} (${browserMood.energy.toFixed(2)})`
    );
  }

  /**
   * Send current status to a connection.
   */
  private sendStatus(connection: ClientConnection): void {
    const status: StatusMessage = {
      type: 'status',
      state:
        this.state === 'playing'
          ? 'playing'
          : this.state === 'paused'
            ? 'paused'
            : 'idle',
      currentTrack: this.currentTrack,
      nextTrack: this.nextTrack,
      currentMood: this.getCurrentMood(),
      uptime: Date.now() - this.startTime,
    };
    connection.send(status);
  }

  // ============================================
  // Reactive Mode Methods
  // ============================================

  /**
   * Handle track started event - capture mood at track start.
   */
  private handleTrackStarted(trackId: string): void {
    this.currentTrackStartTime = Date.now();
    this.moodAtTrackStart = { ...this.getCurrentMood() };
    this.lastMoodLevel = this.moodAtTrackStart.level;
    this.moodStableSince = Date.now();
    this.selector.recordPlay(trackId);

    // Update current track reference
    const track = this.library.getById(trackId);
    if (track) {
      this.currentTrack = track;
    }

    console.log(
      `   📍 Mood at track start: ${this.moodAtTrackStart.level} (${this.moodAtTrackStart.energy.toFixed(2)})`
    );
  }

  /**
   * Start reactive mode - begins periodic transition evaluation.
   */
  private startReactiveMode(): void {
    if (this.evaluationInterval) {
      return; // Already running
    }

    const interval = this.options.reactivity.evaluationInterval;
    console.log(`⚡ Reactive mode started (evaluating every ${interval}ms)`);

    this.evaluationInterval = setInterval(() => {
      this.evaluateTransition();
    }, interval);
  }

  /**
   * Stop reactive mode.
   */
  private stopReactiveMode(): void {
    if (this.evaluationInterval) {
      clearInterval(this.evaluationInterval);
      this.evaluationInterval = null;
      console.log('⚡ Reactive mode stopped');
    }
  }

  /**
   * Evaluate whether to trigger an early transition.
   */
  private evaluateTransition(): void {
    // Skip if not in playing state or no current track
    if (
      this.state !== 'playing' ||
      !this.currentTrack ||
      !this.moodAtTrackStart
    ) {
      return;
    }

    const currentMood = this.getCurrentMood();
    const trackPlayedSeconds = (Date.now() - this.currentTrackStartTime) / 1000;
    const timeSinceLastTransition =
      (Date.now() - this.lastTransitionTime) / 1000;
    const moodStabilitySeconds = (Date.now() - this.moodStableSince) / 1000;

    const context: TransitionContext = {
      currentTrack: this.currentTrack,
      currentMood,
      moodAtTrackStart: this.moodAtTrackStart,
      trackPlayedSeconds,
      trackDuration: this.currentTrack.duration,
      timeSinceLastTransition,
      moodStabilitySeconds,
    };

    const decision = this.transitionEvaluator.evaluate(context);

    // Log evaluation for debugging (only if interesting)
    if (decision.score > 20) {
      console.log(
        `🤔 Evaluating: score=${decision.score.toFixed(0)}, action=${decision.action}`
      );
      console.log(`   ${decision.reason}`);
    }

    // Act on the decision
    switch (decision.action) {
      case 'transition_now':
        this.triggerEarlyTransition(decision);
        break;

      case 'wait':
        // Schedule a re-evaluation if we're waiting
        if (!this.waitingForReEvaluation && decision.waitTime) {
          this.waitingForReEvaluation = true;
          console.log(
            `⏳ Waiting ${decision.waitTime}s before re-evaluating...`
          );
          setTimeout(() => {
            this.waitingForReEvaluation = false;
          }, decision.waitTime * 1000);
        }
        break;

      case 'let_play':
        // Do nothing, let the track continue
        break;
    }
  }

  /**
   * Trigger an early transition to a new track.
   */
  private triggerEarlyTransition(decision: TransitionDecision): void {
    if (!this.currentTrack) return;

    console.log('⚡ EARLY TRANSITION TRIGGERED');
    console.log(`   Score: ${decision.score.toFixed(0)}`);
    console.log(`   Reason: ${decision.reason}`);

    // Record the transition time for cooldown
    this.lastTransitionTime = Date.now();

    // Select a new track based on current mood
    const mood = this.getCurrentMood();
    const selection = this.selector.selectNext(mood, this.currentTrack);

    console.log(
      `   New track: "${selection.track.title}" by ${selection.track.artist}`
    );

    // Broadcast early transition to all clients
    const earlyTransitionMessage: EarlyTransitionMessage = {
      type: 'early_transition',
      track: selection.track,
      reason: decision.reason,
      score: decision.score,
    };

    const clientCount = this.server.broadcast(earlyTransitionMessage);
    console.log(`   Notified ${clientCount} client(s)`);

    // Update next track reference
    this.nextTrack = selection.track;
  }

  /**
   * Enable or disable reactive mode at runtime.
   */
  setReactivityEnabled(enabled: boolean): void {
    this.reactivityEnabled = enabled;

    if (enabled && this.state === 'playing' && !this.evaluationInterval) {
      this.startReactiveMode();
    } else if (!enabled && this.evaluationInterval) {
      this.stopReactiveMode();
    }

    console.log(`⚡ Reactive mode ${enabled ? 'enabled' : 'disabled'}`);
  }

  /**
   * Check if reactive mode is enabled.
   */
  isReactivityEnabled(): boolean {
    return this.reactivityEnabled;
  }

  /**
   * Get current reactive mode stats for debugging.
   */
  getReactiveStats(): {
    enabled: boolean;
    moodAtTrackStart: MoodState | null;
    trackPlayedSeconds: number;
    timeSinceLastTransition: number;
    moodStabilitySeconds: number;
  } {
    return {
      enabled: this.reactivityEnabled,
      moodAtTrackStart: this.moodAtTrackStart,
      trackPlayedSeconds: (Date.now() - this.currentTrackStartTime) / 1000,
      timeSinceLastTransition: (Date.now() - this.lastTransitionTime) / 1000,
      moodStabilitySeconds: (Date.now() - this.moodStableSince) / 1000,
    };
  }
}
