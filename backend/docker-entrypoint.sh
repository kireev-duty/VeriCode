#!/bin/sh
set -e

# Wait for the database, apply migrations, optionally load demo data, then start the given command.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  python - <<'EOF'
import time
from sqlalchemy import create_engine, text
from app.core.config import settings
for attempt in range(60):
    try:
        with create_engine(settings.database_url).connect() as c:
            c.execute(text("select 1"))
        break
    except Exception as exc:  # noqa: BLE001
        print(f"waiting for database ({exc.__class__.__name__})", flush=True)
        time.sleep(2)
else:
    raise SystemExit("database is not available")
EOF
  alembic upgrade head
  if [ "${SEED_DEMO:-false}" = "true" ]; then
    python -m app.seed.run --candidates "${SEED_CANDIDATES:-500}"
  fi
fi

exec "$@"
