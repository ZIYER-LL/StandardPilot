#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[INFO] Created .env from .env.example."
fi

python3 <<'PY'
import os
from pathlib import Path

path = Path('.env')
text = path.read_text(encoding='utf-8')
api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()

if not api_key:
    print('[WARN] ANTHROPIC_API_KEY is not configured as a Codespaces secret.')
else:
    lines = text.splitlines()
    output = []
    replaced = False
    for line in lines:
        if line.startswith('ANTHROPIC_API_KEY='):
            output.append(f'ANTHROPIC_API_KEY={api_key}')
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f'ANTHROPIC_API_KEY={api_key}')
    path.write_text('\n'.join(output) + '\n', encoding='utf-8')
    print('[OK] Applied the Codespaces secret to the ignored .env file.')
PY

docker compose version
docker compose config >/dev/null

echo "[OK] StandardPilot Codespaces environment is ready."
echo "[NEXT] Run: docker compose up -d --build"
