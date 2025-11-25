/**
 * AI DJ - Entry Point
 *
 * An autonomous DJ that reads the room and keeps the party going.
 */

import path from 'node:path';
import { DJController } from './controller/index.js';

// Configuration
const config = {
  libraryPath: process.env.LIBRARY_PATH ?? path.join(process.cwd(), 'data', 'library.json'),
  musicDir: process.env.MUSIC_DIR ?? path.join(process.cwd(), 'music'),
  publicDir: process.env.PUBLIC_DIR ?? path.join(process.cwd(), 'public'),
  port: parseInt(process.env.PORT ?? '3000', 10),
};

// Create DJ controller
const dj = new DJController({
  libraryPath: config.libraryPath,
  musicDir: config.musicDir,
  publicDir: config.publicDir,
  port: config.port,
});

// Handle graceful shutdown
const shutdown = async () => {
  console.log('\n🛑 Shutting down...');
  await dj.stop();
  process.exit(0);
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// Start the DJ
console.log('🎧 AI DJ');
console.log('========');
console.log('');

dj.start().catch((error) => {
  console.error('Failed to start AI DJ:', error);
  process.exit(1);
});
