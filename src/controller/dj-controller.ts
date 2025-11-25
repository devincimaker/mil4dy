/**
 * DJ Controller
 *
 * Main orchestrator for the AI DJ system.
 * Manages mood detection, song selection, and playback coordination.
 */

import { MusicLibrary, Track } from '../music/index.js';
import { MoodState, MoodDetector, RandomMoodDetector } from '../mood/index.js';
import { SongSelector, SelectionResult } from '../selection/index.js';
import {
  DJServer,
  ClientConnection,
  ClientMessage,
  ServerMessage,
  PlayTrackMessage,
  StatusMessage,
  PauseMessage,
  ResumeMessage,
} from '../server/index.js';

export type DJState = 'idle' | 'starting' | 'playing' | 'paused' | 'stopping';

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
}

/**
 * Main DJ controller that orchestrates all components.
 * Coordinates mood detection, song selection, and browser playback.
 */
export class DJController {
  private state: DJState = 'idle';
  private library: MusicLibrary;
  private moodDetector: MoodDetector;
  private selector: SongSelector;
  private server: DJServer;
  private options: Required<DJControllerOptions>;

  private currentTrack: Track | null = null;
  private nextTrack: Track | null = null;
  private startTime: number = 0;
  private currentTrackStartTime: number = 0;

  constructor(options: DJControllerOptions) {
    this.options = {
      libraryPath: options.libraryPath,
      musicDir: options.musicDir,
      port: options.port ?? 3000,
      publicDir: options.publicDir ?? 'public',
      minTrackPlayTime: options.minTrackPlayTime ?? 30,
    };

    this.library = new MusicLibrary();
    this.moodDetector = new RandomMoodDetector();
    this.selector = new SongSelector(this.library);

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

    // Set up mood change listener
    this.moodDetector.onMoodChange(this.handleMoodChange.bind(this));
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

      // Start mood detector
      this.moodDetector.start();

      this.state = 'playing';
      console.log('🎧 AI DJ is ready!');
      console.log(`   Library: ${this.library.count()} tracks`);
      console.log(`   Server: http://localhost:${this.server.getPort()}`);
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

    this.moodDetector.stop();
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
    this.moodDetector.stop();

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
    this.moodDetector.start();

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
   * Get current mood.
   */
  getCurrentMood(): MoodState {
    return this.moodDetector.getCurrentMood();
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
        // Will be used for camera-based mood detection in Phase 4
        console.log(
          `   Mood update: ${message.mood.level} (${message.mood.energy.toFixed(2)})`
        );
        break;

      case 'track_started':
        console.log(`   Track started: ${message.trackId}`);
        this.currentTrackStartTime = Date.now();
        this.selector.recordPlay(message.trackId);
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
    const mood = this.moodDetector.getCurrentMood();
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
    const mood = this.moodDetector.getCurrentMood();
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
   */
  private handleMoodChange(mood: MoodState): void {
    // Log significant mood changes
    console.log(
      `🌡️  Mood: ${mood.level} (${mood.energy.toFixed(2)}) [${mood.trend}]`
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
      currentMood: this.moodDetector.getCurrentMood(),
      uptime: Date.now() - this.startTime,
    };
    connection.send(status);
  }
}
