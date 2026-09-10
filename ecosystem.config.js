// PM2 process definitions.
//
// Paths are resolved from this file's location so the config works on any
// machine; it previously hardcoded /home/newjoinee/... and /home/your-user/...
// and pointed the backend at a "myvenv" interpreter that is not in the repo.
const path = require('path');

const ROOT = __dirname;
const LOG_DIR = path.join(ROOT, 'logs');
// Override with BACKEND_PYTHON if the virtualenv lives elsewhere.
const PYTHON = process.env.BACKEND_PYTHON || path.join(ROOT, 'backend', '.venv', 'bin', 'python');

module.exports = {
  apps: [
    {
      name: 'voice-agent-frontend',
      cwd: path.join(ROOT, 'AI-Voice-Agent-App'),
      script: 'npx',
      args: 'serve -s dist -l 5173',
      env: {
        NODE_ENV: 'production',
        PORT: 5173,
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: path.join(LOG_DIR, 'frontend-error.log'),
      out_file: path.join(LOG_DIR, 'frontend-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
    },
    {
      name: 'voice-agent-backend',
      cwd: path.join(ROOT, 'backend'),
      script: PYTHON,
      // Deliberately a single worker. Live call state - the per-session
      // handler tasks, the ConnectionManager's sockets and AI audio buffers,
      // and the in-memory session logs - is held in module-level process
      // memory. With --workers 4 a reconnect can land on a worker that knows
      // nothing about the session, the "session_already_active" guard stops
      // working, and the saved recording loses whichever half of the call was
      // handled elsewhere. Scale out with more machines behind a
      // sticky-session load balancer, not with more workers.
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 1',
      env: {
        PYTHONPATH: path.join(ROOT, 'backend'),
        ENVIRONMENT: 'production',
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      error_file: path.join(LOG_DIR, 'backend-error.log'),
      out_file: path.join(LOG_DIR, 'backend-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
    },
  ],
};
