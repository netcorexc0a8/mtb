FROM python:3.12-slim

ARG VERSION=0.0.0-dev
LABEL org.opencontainers.image.title="mtb" \
      org.opencontainers.image.description="MikroTik RouterOS config & certificate backup" \
      org.opencontainers.image.source="https://github.com/netcorexc0a8/mtb" \
      org.opencontainers.image.version="${VERSION}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /data /backups && chmod 777 /data /backups

WORKDIR /opt/mtb
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mtb ./mtb
RUN echo "__version__ = \"${VERSION}\"" > mtb/_version.py \
 && printf '#!/bin/sh\nexec python -m mtb "$@"\n' > /usr/local/bin/mtb \
 && chmod +x /usr/local/bin/mtb

# HOME в /tmp: контейнер может работать под произвольным uid (PUID)
ENV PYTHONUNBUFFERED=1 HOME=/tmp \
    DATA_DIR=/data BACKUP_DIR=/backups WEB_LISTEN=0.0.0.0:8080

EXPOSE 8080

HEALTHCHECK --interval=5m --timeout=10s --start-period=30s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=5)" || exit 1

ENTRYPOINT ["mtb"]
CMD ["serve"]
