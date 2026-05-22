#!/usr/bin/env bash
set -euo pipefail

# JJYB_AI智剪服务启动脚本
cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi

export APP_HOST="${APP_HOST:-0.0.0.0}"
export APP_PORT="${APP_PORT:-5000}"

echo "========================================"
echo "  Starting JJYB_AI智剪 Flask Server..."
echo "========================================"
echo
echo "[Start] Server starting..."
echo "[URL]   http://127.0.0.1:${APP_PORT}"
echo "[Stop]  Press Ctrl+C to stop"
echo

exec "$PYTHON_BIN" -u -c "import frontend.app as app_module; app_module.socketio.run(app_module.app, host=app_module.APP_HOST, port=app_module.APP_PORT, debug=app_module.APP_DEBUG, use_reloader=False, allow_unsafe_werkzeug=True)"
