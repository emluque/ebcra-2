# The base image is pinned to an exact version so a rebuild never silently
# reuses a stale locally-cached tag. Bump it deliberately, then rebuild with
# `docker compose build --pull ebcra-web`.
FROM python:3.12.15-slim-trixie

WORKDIR /ebcra-2-web

# All dependencies ship as pure-Python wheels, so no compiler is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY / .

USER app

EXPOSE 8000

CMD ["gunicorn", "ebcra.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]

#CMD ["sleep", "infinity"]
