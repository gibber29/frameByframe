set -eu

alembic upgrade head
exec fastapi run backend/app/main.py \
  --host 0.0.0.0 \
  --port "${PORT:-10000}"