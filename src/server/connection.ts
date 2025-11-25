/**
 * WebSocket Connection Manager
 *
 * Manages client connections and message routing.
 */

import { WebSocket } from 'ws';
import {
  ClientMessage,
  ServerMessage,
  parseClientMessage,
} from './types.js';

export interface ConnectionEvents {
  onMessage: (message: ClientMessage, connection: ClientConnection) => void;
  onConnect: (connection: ClientConnection) => void;
  onDisconnect: (connection: ClientConnection) => void;
}

/**
 * Represents a single client connection.
 */
export class ClientConnection {
  readonly id: string;
  readonly connectedAt: number;
  private ws: WebSocket;
  private alive: boolean = true;

  constructor(ws: WebSocket, id: string) {
    this.ws = ws;
    this.id = id;
    this.connectedAt = Date.now();
  }

  /**
   * Send a message to this client.
   */
  send(message: ServerMessage): boolean {
    if (this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    try {
      this.ws.send(JSON.stringify(message));
      return true;
    } catch (error) {
      console.error(`Failed to send message to client ${this.id}:`, error);
      return false;
    }
  }

  /**
   * Close this connection.
   */
  close(): void {
    this.ws.close();
  }

  /**
   * Check if connection is still open.
   */
  isOpen(): boolean {
    return this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * Mark connection as alive (for ping/pong).
   */
  markAlive(): void {
    this.alive = true;
  }

  /**
   * Check and reset alive status.
   */
  checkAlive(): boolean {
    if (!this.alive) {
      return false;
    }
    this.alive = false;
    this.ws.ping();
    return true;
  }
}

/**
 * Manages all WebSocket client connections.
 */
export class ConnectionManager {
  private connections: Map<string, ClientConnection> = new Map();
  private events: ConnectionEvents;
  private nextId: number = 1;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(events: ConnectionEvents) {
    this.events = events;
  }

  /**
   * Handle a new WebSocket connection.
   */
  handleConnection(ws: WebSocket): ClientConnection {
    const id = `client-${this.nextId++}`;
    const connection = new ClientConnection(ws, id);
    this.connections.set(id, connection);

    console.log(`🔌 Client connected: ${id}`);

    // Set up message handler
    ws.on('message', (data) => {
      try {
        const message = parseClientMessage(data.toString());
        if (message) {
          this.events.onMessage(message, connection);
        } else {
          console.warn(`Invalid message from ${id}:`, data.toString());
        }
      } catch (error) {
        console.error(`Error processing message from ${id}:`, error);
      }
    });

    // Set up close handler
    ws.on('close', () => {
      console.log(`🔌 Client disconnected: ${id}`);
      this.connections.delete(id);
      this.events.onDisconnect(connection);
    });

    // Set up error handler
    ws.on('error', (error) => {
      console.error(`WebSocket error for ${id}:`, error);
    });

    // Set up pong handler
    ws.on('pong', () => {
      connection.markAlive();
    });

    // Notify of new connection
    this.events.onConnect(connection);

    return connection;
  }

  /**
   * Broadcast a message to all connected clients.
   */
  broadcast(message: ServerMessage): number {
    let sent = 0;
    for (const connection of this.connections.values()) {
      if (connection.send(message)) {
        sent++;
      }
    }
    return sent;
  }

  /**
   * Get a connection by ID.
   */
  get(id: string): ClientConnection | undefined {
    return this.connections.get(id);
  }

  /**
   * Get all active connections.
   */
  getAll(): ClientConnection[] {
    return Array.from(this.connections.values());
  }

  /**
   * Get the number of active connections.
   */
  count(): number {
    return this.connections.size;
  }

  /**
   * Start periodic ping to detect dead connections.
   */
  startPingInterval(intervalMs: number = 30000): void {
    this.pingInterval = setInterval(() => {
      for (const [id, connection] of this.connections) {
        if (!connection.checkAlive()) {
          console.log(`🔌 Client ${id} timed out, closing connection`);
          connection.close();
          this.connections.delete(id);
        }
      }
    }, intervalMs);
  }

  /**
   * Stop ping interval.
   */
  stopPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  /**
   * Close all connections and clean up.
   */
  closeAll(): void {
    this.stopPingInterval();
    for (const connection of this.connections.values()) {
      connection.close();
    }
    this.connections.clear();
  }
}

