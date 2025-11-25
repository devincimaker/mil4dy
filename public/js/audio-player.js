/**
 * Audio Player - Single Deck
 *
 * Uses Web Audio API for precise control over playback.
 * Supports loading, playing, pausing, and volume control.
 */

export class AudioPlayer {
  constructor(audioContext, destinationNode) {
    this.audioContext = audioContext;
    this.destinationNode = destinationNode || audioContext.destination;

    // Audio nodes
    this.sourceNode = null;
    this.gainNode = audioContext.createGain();
    this.gainNode.connect(this.destinationNode);

    // State
    this.buffer = null;
    this.isPlaying = false;
    this.isPaused = false;
    this.startTime = 0;
    this.pauseTime = 0;
    this.duration = 0;
    this.volume = 1;

    // Track info
    this.trackId = null;
    this.trackUrl = null;

    // Callbacks
    this.onEnded = null;
    this.onTimeUpdate = null;
    this.onLoaded = null;
    this.onError = null;

    // Time update interval
    this.timeUpdateInterval = null;
  }

  /**
   * Load a track from URL.
   * @param {string} url - URL to the audio file
   * @param {string} trackId - Track identifier
   */
  async load(url, trackId) {
    try {
      this.trackUrl = url;
      this.trackId = trackId;

      // Fetch the audio file
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch audio: ${response.status}`);
      }

      const arrayBuffer = await response.arrayBuffer();

      // Decode the audio data
      this.buffer = await this.audioContext.decodeAudioData(arrayBuffer);
      this.duration = this.buffer.duration;

      console.log(`[Deck] Loaded: ${trackId} (${this.duration.toFixed(1)}s)`);

      if (this.onLoaded) {
        this.onLoaded({ trackId, duration: this.duration });
      }

      return true;
    } catch (error) {
      console.error(`[Deck] Load error:`, error);
      if (this.onError) {
        this.onError(error);
      }
      return false;
    }
  }

  /**
   * Start playback.
   * @param {number} offset - Start position in seconds (default: 0)
   */
  play(offset = 0) {
    if (!this.buffer) {
      console.warn('[Deck] No buffer loaded');
      return false;
    }

    // Resume audio context if suspended (browser autoplay policy)
    if (this.audioContext.state === 'suspended') {
      this.audioContext.resume();
    }

    // Stop any existing playback
    this.stopSource();

    // Create new source node
    this.sourceNode = this.audioContext.createBufferSource();
    this.sourceNode.buffer = this.buffer;
    this.sourceNode.connect(this.gainNode);

    // Handle track end
    this.sourceNode.onended = () => {
      if (this.isPlaying && !this.isPaused) {
        this.isPlaying = false;
        this.stopTimeUpdates();
        if (this.onEnded) {
          this.onEnded({ trackId: this.trackId });
        }
      }
    };

    // Calculate start position
    const startOffset = this.isPaused ? this.pauseTime : offset;

    // Start playback
    this.sourceNode.start(0, startOffset);
    this.startTime = this.audioContext.currentTime - startOffset;
    this.isPlaying = true;
    this.isPaused = false;

    // Start time updates
    this.startTimeUpdates();

    console.log(`[Deck] Playing from ${startOffset.toFixed(1)}s`);
    return true;
  }

  /**
   * Pause playback.
   */
  pause() {
    if (!this.isPlaying || this.isPaused) return;

    this.pauseTime = this.getCurrentTime();
    this.stopSource();
    this.isPaused = true;
    this.isPlaying = false;
    this.stopTimeUpdates();

    console.log(`[Deck] Paused at ${this.pauseTime.toFixed(1)}s`);
  }

  /**
   * Resume playback after pause.
   */
  resume() {
    if (!this.isPaused) return;
    this.play(this.pauseTime);
  }

  /**
   * Stop playback completely.
   */
  stop() {
    this.stopSource();
    this.isPlaying = false;
    this.isPaused = false;
    this.pauseTime = 0;
    this.stopTimeUpdates();

    console.log('[Deck] Stopped');
  }

  /**
   * Stop the source node safely.
   */
  stopSource() {
    if (this.sourceNode) {
      try {
        this.sourceNode.onended = null;
        this.sourceNode.stop();
        this.sourceNode.disconnect();
      } catch (e) {
        // Ignore errors from already stopped sources
      }
      this.sourceNode = null;
    }
  }

  /**
   * Get current playback time in seconds.
   */
  getCurrentTime() {
    if (this.isPaused) {
      return this.pauseTime;
    }
    if (!this.isPlaying) {
      return 0;
    }
    return this.audioContext.currentTime - this.startTime;
  }

  /**
   * Get remaining time in seconds.
   */
  getRemainingTime() {
    return Math.max(0, this.duration - this.getCurrentTime());
  }

  /**
   * Get playback progress (0-1).
   */
  getProgress() {
    if (this.duration === 0) return 0;
    return this.getCurrentTime() / this.duration;
  }

  /**
   * Set volume (0-1).
   */
  setVolume(volume) {
    this.volume = Math.max(0, Math.min(1, volume));
    this.gainNode.gain.setValueAtTime(
      this.volume,
      this.audioContext.currentTime
    );
  }

  /**
   * Smoothly fade volume over time.
   * @param {number} targetVolume - Target volume (0-1)
   * @param {number} duration - Fade duration in seconds
   */
  fadeVolume(targetVolume, duration) {
    const target = Math.max(0, Math.min(1, targetVolume));
    this.gainNode.gain.linearRampToValueAtTime(
      target,
      this.audioContext.currentTime + duration
    );
    this.volume = target;
  }

  /**
   * Get the gain node for external routing.
   */
  getGainNode() {
    return this.gainNode;
  }

  /**
   * Check if track is loaded and ready.
   */
  isReady() {
    return this.buffer !== null;
  }

  /**
   * Start emitting time updates.
   */
  startTimeUpdates() {
    this.stopTimeUpdates();
    this.timeUpdateInterval = setInterval(() => {
      if (this.onTimeUpdate && this.isPlaying) {
        this.onTimeUpdate({
          currentTime: this.getCurrentTime(),
          duration: this.duration,
          remaining: this.getRemainingTime(),
          progress: this.getProgress(),
        });
      }
    }, 250); // Update 4 times per second
  }

  /**
   * Stop time updates.
   */
  stopTimeUpdates() {
    if (this.timeUpdateInterval) {
      clearInterval(this.timeUpdateInterval);
      this.timeUpdateInterval = null;
    }
  }

  /**
   * Clean up resources.
   */
  dispose() {
    this.stop();
    this.gainNode.disconnect();
    this.buffer = null;
  }
}
