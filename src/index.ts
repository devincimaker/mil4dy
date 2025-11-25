/**
 * AI DJ - Entry Point
 *
 * An autonomous DJ that reads the room and keeps the party going.
 */

import path from 'node:path';
import { DJController } from './controller/index.js';

// ============================================
// CLI Argument Parsing
// ============================================

interface CLIOptions {
  port: number;
  library: string;
  musicDir: string;
  publicDir: string;
  help: boolean;
}

function printHelp(): void {
  console.log(`
🎧 AI DJ - Autonomous DJ that reads the room

Usage: npm start [options]

Options:
  --port <number>      Server port (default: 3000, env: PORT)
  --library <path>     Path to library.json (default: data/library.json, env: LIBRARY_PATH)
  --music-dir <path>   Path to music files directory (default: music, env: MUSIC_DIR)
  --public-dir <path>  Path to public files directory (default: public, env: PUBLIC_DIR)
  --help               Show this help message

Examples:
  npm start
  npm start -- --port 8080
  npm start -- --library ./my-library.json --music-dir ./my-music
  PORT=8080 npm start
`);
}

function parseArgs(args: string[]): CLIOptions {
  const options: CLIOptions = {
    port: parseInt(process.env.PORT ?? '3000', 10),
    library: process.env.LIBRARY_PATH ?? path.join(process.cwd(), 'data', 'library.json'),
    musicDir: process.env.MUSIC_DIR ?? path.join(process.cwd(), 'music'),
    publicDir: process.env.PUBLIC_DIR ?? path.join(process.cwd(), 'public'),
    help: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const nextArg = args[i + 1];

    switch (arg) {
      case '--port':
        if (nextArg) {
          options.port = parseInt(nextArg, 10);
          i++;
        }
        break;
      case '--library':
        if (nextArg) {
          options.library = path.resolve(nextArg);
          i++;
        }
        break;
      case '--music-dir':
        if (nextArg) {
          options.musicDir = path.resolve(nextArg);
          i++;
        }
        break;
      case '--public-dir':
        if (nextArg) {
          options.publicDir = path.resolve(nextArg);
          i++;
        }
        break;
      case '--help':
      case '-h':
        options.help = true;
        break;
    }
  }

  return options;
}

// Parse CLI arguments (skip node and script path)
const options = parseArgs(process.argv.slice(2));

// Show help and exit if requested
if (options.help) {
  printHelp();
  process.exit(0);
}

// ============================================
// DJ Controller Setup
// ============================================

// Create DJ controller
const dj = new DJController({
  libraryPath: options.library,
  musicDir: options.musicDir,
  publicDir: options.publicDir,
  port: options.port,
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
