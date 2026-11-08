# One image for the API, the polling worker and the scheduled jobs; the command picks the role:
#   python -m scripts.run_api       (default)   python -m scripts.run_worker
#   python -m scripts.init_db       (release)   python -m scripts.enforce_retention (daily)
# Not yet built or deployed from CI. The CPU torch wheel is large; M1.3 (hosted embeddings)
# is what removes torch/transformers from the production image.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_FORMAT=json \
    UNMEET_ENV=production

WORKDIR /app

RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini main.py ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 unmeet && chown -R unmeet /app
USER unmeet

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('API_PORT','8000'), timeout=4)"

CMD ["python", "-m", "scripts.run_api"]
