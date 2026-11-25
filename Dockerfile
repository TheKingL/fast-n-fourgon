# syntax=docker/dockerfile:1
# Image du dashboard Streamlit du moteur de consolidation des livraisons (fast-n-fourgon).
#
#   docker build -t fast-n-fourgon .
#   docker run -d -p 8501:8501 -v fast-n-fourgon-historique:/app/data/historique fast-n-fourgon
#   -> http://localhost:8501
#
# Deux étages pour une image légère : les dépendances sont installées dans un venv à part, allégé de ce que
# l'application n'utilise pas, puis seuls ce venv et le code de l'application sont copiés sur la base python slim.

# ---------- Étage 1 : dépendances de l'application (requirements.txt) ----------
FROM python:3.12-slim-trixie AS builder

# Allègement du venv (environ 100 Mo) :
#   - pip et les tests embarqués des librairies (pandas/tests : 43 Mo) ;
#   - pyarrow, imposé par Streamlit : en-têtes C++, Arrow Flight et le système de fichiers S3, chargés seulement par
#     pyarrow.flight et pyarrow.fs.S3FileSystem (l'import final fait échouer le build si cela casse un jour).
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv --without-pip /opt/venv \
    && pip --python /opt/venv/bin/python install --no-cache-dir --disable-pip-version-check \
        --root-user-action=ignore -r /tmp/requirements.txt \
    && find /opt/venv -depth -type d -name tests -exec rm -rf {} + \
    && PYARROW=/opt/venv/lib/python3.12/site-packages/pyarrow \
    && rm -rf "$PYARROW"/include "$PYARROW"/libarrow_flight.so* "$PYARROW"/libarrow_python_flight.so* \
        "$PYARROW"/_flight.cpython-*.so "$PYARROW"/libarrow_s3.so* "$PYARROW"/_s3fs.cpython-*.so \
    && /opt/venv/bin/python -c "import pyarrow, pyarrow.compute, pyarrow.fs, pyarrow.parquet, pandas, plotly, streamlit"

# ---------- Étage 2 : image finale ----------
FROM python:3.12-slim-trixie

LABEL org.opencontainers.image.title="fast-n-fourgon" \
      org.opencontainers.image.description="Dashboard Streamlit du moteur de consolidation des livraisons" \
      org.opencontainers.image.source="https://github.com/TheKingL/fast-n-fourgon"

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Paris \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

# Utilisateur sans droits root (app, uid 1000) : le code lui est en lecture seule, data/ lui appartient (historique,
# sorties du CLI)
RUN useradd --no-log-init --create-home --uid 1000 --user-group app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY main.py ./
COPY backend ./backend
COPY frontend ./frontend
COPY .streamlit ./.streamlit
COPY --chown=app:app data ./data
RUN install -d -o app -g app data/historique

# Historique des runs du dashboard : à monter sur un volume pour le garder d'un conteneur à l'autre
VOLUME ["/app/data/historique"]
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('STREAMLIT_SERVER_PORT', '8501')}/_stcore/health\", timeout=4)"]

USER 1000:1000
CMD ["streamlit", "run", "frontend/app.py"]
