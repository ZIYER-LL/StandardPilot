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
lines = text.splitlines()

zhipu_key = os.environ.get('ZHIPU_API_KEY', '').strip()
anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()

updates = {}
if zhipu_key:
    updates.update({
        'LLM_PROVIDER': 'zhipu',
        'ZHIPU_API_KEY': zhipu_key,
    })
    print('[OK] Applied ZHIPU_API_KEY to the ignored .env file.')
elif anthropic_key:
    updates.update({
        'LLM_PROVIDER': 'anthropic',
        'ANTHROPIC_API_KEY': anthropic_key,
    })
    print('[OK] Applied ANTHROPIC_API_KEY to the ignored .env file.')
else:
    print('[WARN] Neither ZHIPU_API_KEY nor ANTHROPIC_API_KEY is configured as a Codespaces secret.')

if updates:
    output = []
    seen = set()
    for line in lines:
        key = line.split('=', 1)[0] if '=' in line and not line.lstrip().startswith('#') else None
        if key in updates:
            output.append(f'{key}={updates[key]}')
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f'{key}={value}')
    path.write_text('\n'.join(output) + '\n', encoding='utf-8')
PY

docker compose version
docker compose config >/dev/null

echo "[OK] StandardPilot Codespaces environment is ready."
echo "[NEXT] Run: docker compose up -d --build"
