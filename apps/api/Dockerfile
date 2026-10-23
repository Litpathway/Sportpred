FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
RUN useradd --create-home --uid 10001 sportpredict
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-deps . && mkdir -p /app/artifacts && chown -R sportpredict:sportpredict /app
ARG INSTALL_SPORTS_SKILLS=false
RUN if [ "$INSTALL_SPORTS_SKILLS" = "true" ]; then pip install --no-cache-dir '.[sports]'; fi
USER sportpredict
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
