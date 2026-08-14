import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // WebSocket alerts channel (must precede /api)
      '/api/v1/ws': {
        target: 'ws://127.0.0.1:7000',
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code === 'ECONNREFUSED' || err.code === 'ECONNABORTED') return;
            console.error('[vite] ws proxy error:', err.message);
          });
        },
      },
      // All /api/* calls from the frontend are rewritten to /api/v1/* on the backend.
      '/api': {
        target: 'http://127.0.0.1:7000',
        changeOrigin: true,
        rewrite: (path) => path.startsWith('/api/v1') ? path : path.replace(/^\/api/, '/api/v1'),
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            if (err.code === 'ECONNREFUSED' || err.code === 'ECONNABORTED') {
              if (res && !res.headersSent) {
                res.writeHead(503, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ detail: 'Backend starting up, please wait...' }));
              }
              return;
            }
            console.error('[vite] proxy error:', err.message);
          });
        },
      },
      // MediaMTX HLS video stream proxy
      '/hls': {
        target: 'http://127.0.0.1:8888',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/hls/, ''),
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code === 'ECONNREFUSED' || err.code === 'ECONNABORTED') return;
            console.error('[vite] hls proxy error:', err.message);
          });
        },
      },
      // MediaMTX WebRTC (WHEP) stream proxy
      '/webrtc': {
        target: 'http://127.0.0.1:8889',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/webrtc/, ''),
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code === 'ECONNREFUSED' || err.code === 'ECONNABORTED') return;
            console.error('[vite] webrtc proxy error:', err.message);
          });
        },
      },
    },
  },
})
