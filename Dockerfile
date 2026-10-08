# Small official Python image. Slim = fewer packages = smaller attack surface.
FROM python:3.12-slim

WORKDIR /app

# Copy dependency metadata + source first, then install the package (and faker for seeding).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . faker      # faker is only needed by scripts/seed_data.py
COPY scripts ./scripts

# Run as a normal user, not root. The app writes logs/ in its working directory.
RUN useradd --create-home appuser && mkdir -p /app/logs && chown appuser /app/logs
USER appuser

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# gunicorn = production WSGI server (Flask's built-in server is for development only).
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8000", "order_assistant.api.app:app"]
