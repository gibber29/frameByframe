FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"

COPY alembic.ini ./
COPY backend ./backend
COPY assets ./assets

EXPOSE 8000

CMD ["fastapi", "run", "backend/app/main.py", "--host", "0.0.0.0", "--port", "8000"]
