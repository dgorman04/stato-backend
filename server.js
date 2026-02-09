require('dotenv').config();
const WebSocket = require('ws');
const { createClient } = require('redis');

const WS_PORT = process.env.WS_PORT || 3001;
const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';

// WebSocket server
const wss = new WebSocket.Server({ port: WS_PORT }, () => {
  console.log(`WebSocket running on ws://0.0.0.0:${WS_PORT}`);
});

wss.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\nPort ${WS_PORT} is already in use.`);
    console.error('Either close the other process using it, or set WS_PORT to a different port (e.g. in .env: WS_PORT=3002).');
    console.error('On Windows, find the process: netstat -ano | findstr :' + WS_PORT);
    process.exit(1);
  }
  throw err;
});

function heartbeat() { this.isAlive = true; }

wss.on('connection', (ws) => {
  ws.isAlive = true;
  ws.on('pong', heartbeat);
  console.log('Client connected');

  ws.on('close', () => console.log('Client disconnected'));
});

setInterval(() => {
  wss.clients.forEach((ws) => {
    if (!ws.isAlive) return ws.terminate();
    ws.isAlive = false;
    ws.ping();
  });
}, 30000);

// Redis subscriber
(async () => {
  const sub = createClient({
    url: REDIS_URL,
    legacyMode: true, // important for older Redis
  });

  sub.on('error', (err) => console.error('Redis error', err));

  await sub.connect();

  // Subscribe to both events and chat channels
  sub.subscribe('events', (msg) => {
    console.log('Redis → WS (events):', msg);

    wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(msg);
      }
    });
  });

  sub.subscribe('chat', (msg) => {
    console.log('Redis → WS (chat):', msg);

    wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(msg);
      }
    });
  });

  console.log('Subscribed to Redis channels: events, chat');
})();
