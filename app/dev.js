const { spawn } = require('child_process');
const path = require('path');

const projectRoot = path.resolve(__dirname, '..');

console.log('[dev] Starting Copartner server...');
console.log('[dev] Project root:', projectRoot);

// Start Python server
const server = spawn('python', ['core/copartner_server.py'], {
  cwd: projectRoot,
  stdio: 'inherit',
  shell: true
});

// Give the server a moment to boot before starting Tauri
setTimeout(() => {
  console.log('[dev] Starting Tauri dev...');
  
  const tauri = spawn('npx', ['tauri', 'dev'], {
    cwd: __dirname,
    stdio: 'inherit',
    shell: true
  });

  // Forward cleanup
  tauri.on('close', (code) => {
    console.log(`[dev] Tauri exited with code ${code}`);
    server.kill();
    process.exit(code || 0);
  });

  tauri.on('error', (err) => {
    console.error('[dev] Tauri failed to start:', err.message);
    server.kill();
    process.exit(1);
  });
}, 3000);

// Cleanup on Ctrl+C
process.on('SIGINT', () => {
  console.log('\n[dev] Shutting down...');
  server.kill();
  process.exit(0);
});

process.on('SIGTERM', () => {
  server.kill();
  process.exit(0);
});

server.on('error', (err) => {
  console.error('[dev] Server failed to start:', err.message);
  process.exit(1);
});
