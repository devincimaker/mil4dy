/**
 * Server Types
 *
 * Type definitions for WebSocket messages and server communication.
 */

import { Track } from '../music/index.js';
import { MoodState } from '../mood/index.js';

/**
 * Base message structure - all messages have a type field.
 */
export interface BaseMessage {
  type: string;
}

// ============================================
// Messages FROM Browser TO Server
// ============================================

/**
 * Mood update from browser (camera-based detection).
 */
export interface MoodUpdateMessage extends BaseMessage {
  type: 'mood_update';
  mood: MoodState;
}

/**
 * Track started playing in browser.
 */
export interface TrackStartedMessage extends BaseMessage {
  type: 'track_started';
  trackId: string;
  timestamp: number;
}

/**
 * Track is ending soon (time to prepare next track).
 */
export interface TrackEndingMessage extends BaseMessage {
  type: 'track_ending';
  trackId: string;
  remainingSeconds: number;
}

/**
 * Track finished playing.
 */
export interface TrackEndedMessage extends BaseMessage {
  type: 'track_ended';
  trackId: string;
}

/**
 * Client requesting current status.
 */
export interface StatusRequestMessage extends BaseMessage {
  type: 'status_request';
}

/**
 * Client ready to receive commands.
 */
export interface ClientReadyMessage extends BaseMessage {
  type: 'client_ready';
}

// ============================================
// Messages FROM Server TO Browser
// ============================================

/**
 * Command to play a track.
 */
export interface PlayTrackMessage extends BaseMessage {
  type: 'play_track';
  track: Track;
  reason: string;
  queuePosition: 'immediate' | 'next';
}

/**
 * Current status update.
 */
export interface StatusMessage extends BaseMessage {
  type: 'status';
  state: 'idle' | 'playing' | 'paused';
  currentTrack: Track | null;
  nextTrack: Track | null;
  currentMood: MoodState;
  uptime: number;
}

/**
 * Command to pause playback.
 */
export interface PauseMessage extends BaseMessage {
  type: 'pause';
}

/**
 * Command to resume playback.
 */
export interface ResumeMessage extends BaseMessage {
  type: 'resume';
}

/**
 * Command to stop playback.
 */
export interface StopMessage extends BaseMessage {
  type: 'stop';
}

/**
 * Error message.
 */
export interface ErrorMessage extends BaseMessage {
  type: 'error';
  error: string;
  details?: string;
}

/**
 * Mood broadcast to all clients.
 */
export interface MoodBroadcastMessage extends BaseMessage {
  type: 'mood_broadcast';
  mood: MoodState;
  source: 'camera' | 'random';
}

/**
 * Command for early transition (reactive mode).
 */
export interface EarlyTransitionMessage extends BaseMessage {
  type: 'early_transition';
  track: Track;
  reason: string;
  score: number;
}

// ============================================
// Union Types
// ============================================

/**
 * All possible messages from browser to server.
 */
export type ClientMessage =
  | MoodUpdateMessage
  | TrackStartedMessage
  | TrackEndingMessage
  | TrackEndedMessage
  | StatusRequestMessage
  | ClientReadyMessage;

/**
 * All possible messages from server to browser.
 */
export type ServerMessage =
  | PlayTrackMessage
  | StatusMessage
  | PauseMessage
  | ResumeMessage
  | StopMessage
  | ErrorMessage
  | MoodBroadcastMessage
  | EarlyTransitionMessage;

/**
 * Type guard for client messages.
 */
export function isClientMessage(msg: unknown): msg is ClientMessage {
  return (
    typeof msg === 'object' &&
    msg !== null &&
    'type' in msg &&
    typeof (msg as BaseMessage).type === 'string'
  );
}

/**
 * Parse a JSON string into a client message.
 */
export function parseClientMessage(json: string): ClientMessage | null {
  try {
    const parsed = JSON.parse(json);
    if (isClientMessage(parsed)) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}
