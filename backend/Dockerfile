FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
# Not run by the container itself -- copied so `docker compose exec api
# python -m scripts.promote_admin <email>` works against the deployed
# database without a separate local checkout (D-15, issue #42).
COPY scripts ./scripts
EXPOSE 8000
# Migrations run before the app starts, every container start -- a no-op
# when already at head. Without this, alembic/ existed in the repo but was
# never actually copied into the image (or run anywhere), so schema changes
# landed in code but never reached deployed databases -- see
# docs/DESIGN_NOTES.md D-11.
# app.core.migrate wraps `alembic upgrade head` and self-heals the specific
# case D-11 required a manual fix for (tables exist, no alembic_version row,
# columns exactly match current models) instead of crash-looping forever.
CMD ["sh", "-c", "python -m app.core.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
