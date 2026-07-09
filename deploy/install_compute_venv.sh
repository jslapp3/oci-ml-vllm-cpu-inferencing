#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo deploy/install_compute_venv.sh" >&2
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/oci-vllm-ml-inference}"
APP_USER="${APP_USER:-oci-forecast}"
ENV_DIR="${ENV_DIR:-/etc/oci-forecast}"
ENV_FILE="${ENV_FILE:-${ENV_DIR}/forecast.env}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Could not find python3.11 or python3. Install Python 3.11 for best Chronos/Torch compatibility." >&2
  exit 1
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$APP_DIR" --shell /sbin/nologin "$APP_USER"
fi

if [[ "$APP_DIR" == "/" || "$APP_DIR" == "/opt" || "$APP_DIR" == "/opt/" ]]; then
  echo "Refusing unsafe APP_DIR: $APP_DIR" >&2
  exit 1
fi

systemctl stop forecast-orchestrator.service chronos-ml.service >/dev/null 2>&1 || true

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "$ENV_DIR"

echo "Copying application files to ${APP_DIR}"
tar \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='.venv-*' \
  --exclude='deploy/*.env' \
  -C "$SOURCE_DIR" \
  -cf - . | tar -C "$APP_DIR" -xf -

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$APP_DIR/deploy/compute.env.example" "$ENV_FILE"
  echo "Created ${ENV_FILE}; edit it before enabling real Chronos or ADB credentials."
else
  echo "${ENV_FILE} already exists; leaving it unchanged."
fi

echo "Creating ML virtual environment"
rm -rf "$APP_DIR/.venv-ml"
"$PYTHON_BIN" -m venv "$APP_DIR/.venv-ml"
"$APP_DIR/.venv-ml/bin/python" -m pip install --upgrade pip wheel
"$APP_DIR/.venv-ml/bin/pip" install -r "$APP_DIR/requirements-ml.txt"

echo "Creating orchestrator virtual environment"
rm -rf "$APP_DIR/.venv-orchestrator"
"$PYTHON_BIN" -m venv "$APP_DIR/.venv-orchestrator"
"$APP_DIR/.venv-orchestrator/bin/python" -m pip install --upgrade pip wheel
"$APP_DIR/.venv-orchestrator/bin/pip" install -r "$APP_DIR/requirements-orchestrator.txt"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

install -m 0644 "$APP_DIR/deploy/systemd/chronos-ml.service" /etc/systemd/system/chronos-ml.service
install -m 0644 "$APP_DIR/deploy/systemd/forecast-orchestrator.service" /etc/systemd/system/forecast-orchestrator.service

systemctl daemon-reload
systemctl enable chronos-ml.service forecast-orchestrator.service

cat <<EOF

Installed OCI forecast services.

Next:
  sudo vi ${ENV_FILE}
  sudo systemctl start chronos-ml.service
  sudo systemctl start forecast-orchestrator.service
  sudo systemctl status chronos-ml.service
  sudo systemctl status forecast-orchestrator.service

Smoke test:
  curl http://127.0.0.1:8080/health
EOF
