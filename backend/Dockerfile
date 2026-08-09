FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
EXPOSE 8000
# Migrations run before the app starts, every container start -- a no-op
# when already at head. Without this, alembic/ existed in the repo but was
# never actually copied into the image (or run anywhere), so schema changes
# landed in code but never reached deployed databases -- see
# docs/DESIGN_NOTES.md D-11.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
