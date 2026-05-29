const fs = require('fs');
const os = require('os');
const path = require('path');

function getRouterPort() {
  // 1. Explicit override via env var
  if (process.env.LOCAL_ROUTER_PORT) {
    const p = parseInt(process.env.LOCAL_ROUTER_PORT, 10);
    if (Number.isInteger(p) && p > 0) return p;
    console.warn(`Invalid LOCAL_ROUTER_PORT=${process.env.LOCAL_ROUTER_PORT}, falling back to tracking dir`);
  }
  // 2. Auto-detect from the most recently started router's tracking file
  const trackingDir = path.join(os.homedir(), '.dispatch', 'routers');
  try {
    const files = fs.readdirSync(trackingDir)
      .filter(f => f.endsWith('.json'))
      .map(f => ({ f, mtime: fs.statSync(path.join(trackingDir, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);
    if (files.length > 0) {
      const data = JSON.parse(fs.readFileSync(path.join(trackingDir, files[0].f), 'utf8'));
      if (Number.isInteger(data.port) && data.port > 0) return data.port;
    }
  } catch (_) {}
  // 3. Fall back to the CLI router's default port
  return 8080;
}

module.exports = getRouterPort;
