/**
 * DJ Mixer - Two-Deck Crossfade System
 *
 * Manages two audio decks with smooth crossfading transitions.
 */

import { AudioPlayer } from './audio-player.js';

export class DJMixer {
  constructor() {
    // Create audio context
    this.audioContext = new (window.AudioContext ||
      window.webkitAudioContext)();

    // Master gain node
    this.masterGain = this.audioContext.createGain();
    this.masterGain.connect(this.audioContext.destination);

    // Create two decks
    this.deckA = new AudioPlayer(this.audioContext, this.masterGain);
    this.deckB = new AudioPlayer(this.audioContext, this.masterGain);

    // Track which deck is active
    this.activeDeck = 'A';
    this.crossfading = false;

    // Configuration
    this.crossfadeDuration = 8; // seconds
    this.triggerTime = 15; // seconds before end to trigger next track

    // Callbacks
    this.onTrackEnding = null;
    this.onTrackStarted = null;
    this.onTrackEnded = null;
    this.onTimeUpdate = null;
    this.onError = null;

    // Queued track
    this.queuedTrack = null;

    // Set up deck callbacks
    this.setupDeckCallbacks();
  }

  /**
   * Set up event handlers for both decks.
   */
  setupDeckCallbacks() {
    // Deck A callbacks
    this.deckA.onTimeUpdate = (info) => {
      if (this.activeDeck === 'A') {
        this.handleTimeUpdate('A', info);
      }
    };

    this.deckA.onEnded = (info) => {
      console.log('[Mixer] Deck A ended');
      if (this.activeDeck === 'A' && !this.crossfading) {
        this.handleTrackEnded('A', info);
      }
    };

    this.deckA.onError = (error) => {
      console.error('[Mixer] Deck A error:', error);
      if (this.onError) this.onError(error);
    };

    // Deck B callbacks
    this.deckB.onTimeUpdate = (info) => {
      if (this.activeDeck === 'B') {
        this.handleTimeUpdate('B', info);
      }
    };

    this.deckB.onEnded = (info) => {
      console.log('[Mixer] Deck B ended');
      if (this.activeDeck === 'B' && !this.crossfading) {
        this.handleTrackEnded('B', info);
      }
    };

    this.deckB.onError = (error) => {
      console.error('[Mixer] Deck B error:', error);
      if (this.onError) this.onError(error);
    };
  }

  /**
   * Handle time updates and check for track ending.
   */
  handleTimeUpdate(deck, info) {
    // Emit time update
    if (this.onTimeUpdate) {
      this.onTimeUpdate({
        deck,
        ...info,
      });
    }

    // Check if we need to trigger next track preparation
    if (
      !this.crossfading &&
      info.remaining <= this.triggerTime &&
      info.remaining > this.triggerTime - 1
    ) {
      console.log(
        `[Mixer] Track ending soon (${info.remaining.toFixed(1)}s remaining)`
      );
      if (this.onTrackEnding) {
        const activeDeckObj = this.getActiveDeck();
        this.onTrackEnding({
          trackId: activeDeckObj.trackId,
          remainingSeconds: info.remaining,
        });
      }
    }

    // Auto-crossfade when track is about to end
    if (
      !this.crossfading &&
      this.queuedTrack &&
      info.remaining <= this.crossfadeDuration
    ) {
      console.log('[Mixer] Auto-starting crossfade to queued track');
      this.startCrossfade();
    }
  }

  /**
   * Handle track ended event.
   */
  handleTrackEnded(deck, info) {
    if (this.onTrackEnded) {
      this.onTrackEnded({ deck, trackId: info.trackId });
    }
  }

  /**
   * Get the active deck object.
   */
  getActiveDeck() {
    return this.activeDeck === 'A' ? this.deckA : this.deckB;
  }

  /**
   * Get the inactive deck object.
   */
  getInactiveDeck() {
    return this.activeDeck === 'A' ? this.deckB : this.deckA;
  }

  /**
   * Load and play a track immediately on the active deck.
   * @param {Object} track - Track object with id and path
   */
  async playImmediate(track) {
    const deck = this.getActiveDeck();
    const url = `/api/tracks/${track.id}/audio`;

    console.log(`[Mixer] Loading "${track.title}" on Deck ${this.activeDeck}`);

    // Stop any current playback
    deck.stop();

    // Load and play
    const loaded = await deck.load(url, track.id);
    if (loaded) {
      deck.setVolume(1);
      deck.play();

      if (this.onTrackStarted) {
        this.onTrackStarted({
          deck: this.activeDeck,
          trackId: track.id,
          track,
        });
      }

      return true;
    }

    return false;
  }

  /**
   * Queue a track on the inactive deck for crossfade.
   * @param {Object} track - Track object with id and path
   */
  async queueNext(track) {
    const deck = this.getInactiveDeck();
    const url = `/api/tracks/${track.id}/audio`;
    const inactiveDeckName = this.activeDeck === 'A' ? 'B' : 'A';

    console.log(`[Mixer] Queuing "${track.title}" on Deck ${inactiveDeckName}`);

    // Load the track
    const loaded = await deck.load(url, track.id);
    if (loaded) {
      deck.setVolume(0); // Start silent
      this.queuedTrack = track;
      return true;
    }

    return false;
  }

  /**
   * Start crossfade from active deck to inactive deck.
   */
  startCrossfade() {
    if (this.crossfading) {
      console.log('[Mixer] Already crossfading');
      return;
    }

    const fromDeck = this.getActiveDeck();
    const toDeck = this.getInactiveDeck();

    if (!toDeck.isReady()) {
      console.warn('[Mixer] Next deck not ready for crossfade');
      return;
    }

    this.crossfading = true;
    const targetDeck = this.activeDeck === 'A' ? 'B' : 'A';

    console.log(
      `[Mixer] Starting crossfade: ${this.activeDeck} → ${targetDeck}`
    );

    // Start the incoming track
    toDeck.play();

    // Notify track started
    if (this.onTrackStarted && this.queuedTrack) {
      this.onTrackStarted({
        deck: targetDeck,
        trackId: toDeck.trackId,
        track: this.queuedTrack,
      });
    }

    // Perform crossfade
    fromDeck.fadeVolume(0, this.crossfadeDuration);
    toDeck.fadeVolume(1, this.crossfadeDuration);

    // Switch active deck after crossfade completes
    setTimeout(() => {
      fromDeck.stop();
      this.activeDeck = targetDeck;
      this.crossfading = false;
      this.queuedTrack = null;
      console.log(`[Mixer] Crossfade complete, Deck ${targetDeck} now active`);
    }, this.crossfadeDuration * 1000);
  }

  /**
   * Skip to the next track immediately (hard cut).
   */
  async skipToNext() {
    if (!this.queuedTrack) {
      console.warn('[Mixer] No track queued to skip to');
      return false;
    }

    const fromDeck = this.getActiveDeck();
    const toDeck = this.getInactiveDeck();
    const targetDeck = this.activeDeck === 'A' ? 'B' : 'A';

    // Stop current track
    fromDeck.stop();

    // Start next track at full volume
    toDeck.setVolume(1);
    toDeck.play();

    // Notify track started
    if (this.onTrackStarted) {
      this.onTrackStarted({
        deck: targetDeck,
        trackId: toDeck.trackId,
        track: this.queuedTrack,
      });
    }

    // Switch active deck
    this.activeDeck = targetDeck;
    this.queuedTrack = null;
    this.crossfading = false;

    return true;
  }

  /**
   * Pause playback.
   */
  pause() {
    this.getActiveDeck().pause();
  }

  /**
   * Resume playback.
   */
  resume() {
    // Resume audio context if needed (browser autoplay policy)
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume();
    }
    this.getActiveDeck().resume();
  }

  /**
   * Stop all playback.
   */
  stop() {
    this.deckA.stop();
    this.deckB.stop();
    this.crossfading = false;
    this.queuedTrack = null;
  }

  /**
   * Set master volume (0-1).
   */
  setMasterVolume(volume) {
    this.masterGain.gain.setValueAtTime(
      Math.max(0, Math.min(1, volume)),
      this.audioContext.currentTime
    );
  }

  /**
   * Set crossfade duration in seconds.
   */
  setCrossfadeDuration(seconds) {
    this.crossfadeDuration = Math.max(1, Math.min(30, seconds));
  }

  /**
   * Set trigger time (seconds before end to request next track).
   */
  setTriggerTime(seconds) {
    this.triggerTime = Math.max(5, Math.min(60, seconds));
  }

  /**
   * Get current playback state.
   */
  getState() {
    const activeDeck = this.getActiveDeck();
    return {
      activeDeck: this.activeDeck,
      isPlaying: activeDeck.isPlaying,
      isPaused: activeDeck.isPaused,
      currentTime: activeDeck.getCurrentTime(),
      duration: activeDeck.duration,
      remaining: activeDeck.getRemainingTime(),
      progress: activeDeck.getProgress(),
      trackId: activeDeck.trackId,
      crossfading: this.crossfading,
      hasQueuedTrack: this.queuedTrack !== null,
    };
  }

  /**
   * Resume audio context (call after user interaction).
   */
  async unlock() {
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume();
      console.log('[Mixer] Audio context unlocked');
    }
  }

  /**
   * Clean up resources.
   */
  dispose() {
    this.stop();
    this.deckA.dispose();
    this.deckB.dispose();
    this.audioContext.close();
  }
}
