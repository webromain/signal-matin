# Image autonome : Python, Signal Matin et le Chromium qui fabrique les PDF.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp

WORKDIR /app

# Le code reste dans /app (installation editable) : c'est la que le projet
# cherche config.yaml, credentials.json, token.json et le dossier output/.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY web ./web
COPY main.py config.example.yaml ./
RUN pip install -e ".[google]" \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && mkdir -p output && chmod a+rwx output

ENTRYPOINT ["signal-matin"]
CMD ["generate", "--live"]
