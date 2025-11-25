/**
 * HTTP & WebSocket Server
 *
 * Main server that serves static files and handles WebSocket connections.
 */

import express, { Express, Request, Response, NextFunction } from 'express';
import { createServer, Server as HttpServer } from 'node:http';
import { WebSocketServer, WebSocket } from 'ws';
import { createReadStream, statSync, existsSync } from 'node:fs';
import path from 'node:path';
import { ConnectionManager, ConnectionEvents, ClientConnection } from './connection.js';
import { ClientMessage, ServerMessage } from './types.js';

export interface ServerOptions {
  /** Port to listen on, default 3000 */
  port?: number;
  /** Path to public directory for static files */
  publicDir?: string;
  /** Path to music directory for audio streaming */
  musicDir?: string;
}

export interface ServerEvents extends ConnectionEvents {
  onMessage: (message: ClientMessage, connection: ClientConnection) => void;
  onConnect: (connection: ClientConnection) => void;
  onDisconnect: (connection: ClientConnection) => void;
}

/**
 * Main server class combining HTTP and WebSocket functionality.
 */
export class DJServer {
  private app: Express;
  private httpServer: HttpServer;
  private wss: WebSocketServer;
  private connectionManager: ConnectionManager;
  private options: Required<ServerOptions>;
  private started: boolean = false;
  private trackListHandler: (() => unknown) | null = null;
  private audioStreamHandler: ((trackId: string) => { path: string; mimeType: string } | null) | null = null;

  constructor(events: ServerEvents, options: ServerOptions = {}) {
    this.options = {
      port: options.port ?? 3000,
      publicDir: options.publicDir ?? path.join(process.cwd(), 'public'),
      musicDir: options.musicDir ?? path.join(process.cwd(), 'music'),
    };

    // Initialize Express app
    this.app = express();
    this.app.use(express.json());

    // Set up CORS for local development
    this.app.use((_req: Request, res: Response, next: NextFunction) => {
      res.header('Access-Control-Allow-Origin', '*');
      res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      res.header('Access-Control-Allow-Headers', 'Content-Type');
      next();
    });

    // Create HTTP server
    this.httpServer = createServer(this.app);

    // Create WebSocket server
    this.wss = new WebSocketServer({ server: this.httpServer });

    // Create connection manager
    this.connectionManager = new ConnectionManager(events);

    // Set up routes
    this.setupRoutes();

    // Set up WebSocket handler
    this.wss.on('connection', (ws: WebSocket) => {
      this.connectionManager.handleConnection(ws);
    });
  }

  /**
   * Set up HTTP routes.
   */
  private setupRoutes(): void {
    // Health check
    this.app.get('/api/health', (_req: Request, res: Response) => {
      res.json({ status: 'ok', uptime: process.uptime() });
    });

    // Track list endpoint
    this.app.get('/api/tracks', (_req: Request, res: Response) => {
      if (this.trackListHandler) {
        try {
          const tracks = this.trackListHandler();
          res.json({ tracks });
        } catch (error) {
          res.status(500).json({ error: 'Failed to fetch tracks' });
        }
      } else {
        res.json({ tracks: [], message: 'Library not loaded yet' });
      }
    });

    // Audio streaming endpoint
    this.app.get('/api/tracks/:id/audio', (req: Request, res: Response) => {
      if (!this.audioStreamHandler) {
        res.status(503).json({ error: 'Audio handler not configured' });
        return;
      }

      const { id } = req.params;
      const result = this.audioStreamHandler(id);

      if (!result) {
        res.status(404).json({ error: 'Track not found' });
        return;
      }

      const { path: filePath, mimeType } = result;
      const fullPath = path.isAbsolute(filePath)
        ? filePath
        : path.join(process.cwd(), filePath);

      if (!existsSync(fullPath)) {
        res.status(404).json({ error: 'Audio file not found' });
        return;
      }

      try {
        const stat = statSync(fullPath);
        const range = req.headers.range;

        if (range) {
          // Handle range requests for seeking
          const parts = range.replace(/bytes=/, '').split('-');
          const start = parseInt(parts[0], 10);
          const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1;
          const chunkSize = end - start + 1;

          res.writeHead(206, {
            'Content-Range': `bytes ${start}-${end}/${stat.size}`,
            'Accept-Ranges': 'bytes',
            'Content-Length': chunkSize,
            'Content-Type': mimeType,
          });

          createReadStream(fullPath, { start, end }).pipe(res);
        } else {
          // Full file request
          res.writeHead(200, {
            'Content-Length': stat.size,
            'Content-Type': mimeType,
            'Accept-Ranges': 'bytes',
          });

          createReadStream(fullPath).pipe(res);
        }
      } catch (error) {
        console.error('Error streaming audio:', error);
        res.status(500).json({ error: 'Failed to stream audio' });
      }
    });

    // Serve static files from public directory
    this.app.use(express.static(this.options.publicDir));

    // SPA fallback - serve index.html for unmatched routes
    this.app.get('*', (req: Request, res: Response) => {
      const indexPath = path.join(this.options.publicDir, 'index.html');
      if (existsSync(indexPath)) {
        res.sendFile(indexPath);
      } else {
        res.status(404).send('Not found');
      }
    });
  }

  /**
   * Set up the tracks list endpoint handler.
   */
  setTrackListHandler(handler: () => unknown): void {
    this.trackListHandler = handler;
  }

  /**
   * Set up the audio streaming endpoint handler.
   */
  setAudioStreamHandler(
    handler: (trackId: string) => { path: string; mimeType: string } | null
  ): void {
    this.audioStreamHandler = handler;
  }

  /**
   * Start the server.
   */
  async start(): Promise<void> {
    if (this.started) return;

    return new Promise((resolve) => {
      this.httpServer.listen(this.options.port, () => {
        this.started = true;
        this.connectionManager.startPingInterval();
        console.log(`🎧 AI DJ Server running on http://localhost:${this.options.port}`);
        resolve();
      });
    });
  }

  /**
   * Stop the server.
   */
  async stop(): Promise<void> {
    if (!this.started) return;

    return new Promise((resolve, reject) => {
      this.connectionManager.closeAll();
      this.wss.close();
      this.httpServer.close((err) => {
        if (err) {
          reject(err);
        } else {
          this.started = false;
          console.log('🛑 Server stopped');
          resolve();
        }
      });
    });
  }

  /**
   * Broadcast a message to all connected clients.
   */
  broadcast(message: ServerMessage): number {
    return this.connectionManager.broadcast(message);
  }

  /**
   * Get the connection manager.
   */
  getConnectionManager(): ConnectionManager {
    return this.connectionManager;
  }

  /**
   * Get the Express app (for additional route configuration).
   */
  getApp(): Express {
    return this.app;
  }

  /**
   * Check if server is running.
   */
  isRunning(): boolean {
    return this.started;
  }

  /**
   * Get the port the server is listening on.
   */
  getPort(): number {
    return this.options.port;
  }
}

