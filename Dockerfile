# Image autonome : Python, Signal Matin et le Chromium qui fabrique les PDF.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/tmp

WORKDIR /app

# Dependances et Chromium d'abord, avec un paquet vide : cette couche lourde reste
# en cache tant que pyproject.toml ne change pas, et modifier le code ne la refait pas.
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p src/signal_matin/assets output \
    && touch src/signal_matin/__init__.py \
       src/signal_matin/assets/signal_matin.css \
       src/signal_matin/assets/signal_matin_pagination.js \
    && pip install -e ".[google]" \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && chmod a+rwx output

# Le code reste dans /app (installation editable) : c'est la que le projet
# cherche config.yaml, credentials.json, token.json et le dossier output/.
COPY src ./src
COPY web ./web
COPY main.py config.example.yaml ./

ENTRYPOINT ["signal-matin"]
CMD ["generate", "--live"]
