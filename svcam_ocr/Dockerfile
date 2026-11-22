# Basis: offizielles Python-Image (Debian). Die Home-Assistant-Basisimages mit Python
# sind Alpine (musl), dafür gibt es keine ONNX-Runtime-Pakete.
# Seit Supervisor 2026.04 wird BUILD_FROM nicht mehr übergeben, daher fester Name.
FROM docker.io/library/python:3.12-slim-bookworm

# Werden vom Supervisor bzw. von der GitHub-Automatik übergeben
ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=dev

LABEL io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.name="SvCam OCR" \
      io.hass.description="Lokale Texterkennung für Kamerabilder" \
      org.opencontainers.image.source="https://github.com/CarWoWeb/ha-svcam-ocr" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Modelle beim Bauen laden, damit die App später ohne Internet startet
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"

COPY app/ /app/

CMD ["python", "/app/server.py"]
