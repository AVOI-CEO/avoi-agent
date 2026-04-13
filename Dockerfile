FROM debian:13.4

# Disable Python stdout buffering to ensure logs are printed immediately
ENV PYTHONUNBUFFERED=1

# Install system dependencies in one layer, clear APT cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential nodejs npm python3 python3-pip ripgrep ffmpeg gcc python3-dev libffi-dev procps && \
    rm -rf /var/lib/apt/lists/*

COPY . /opt/avoi
WORKDIR /opt/avoi

# Install Python and Node dependencies in one layer, no cache
RUN pip install --no-cache-dir uv --break-system-packages && \
    uv pip install --system --break-system-packages --no-cache -e ".[all]" && \
    npm install --prefer-offline --no-audit && \
    npx playwright install --with-deps chromium --only-shell && \
    cd /opt/avoi/scripts/whatsapp-bridge && \
    npm install --prefer-offline --no-audit && \
    npm cache clean --force

WORKDIR /opt/avoi
RUN chmod +x /opt/avoi/docker/entrypoint.sh

ENV AVOI_HOME=/opt/data
VOLUME [ "/opt/data" ]
ENTRYPOINT [ "/opt/avoi/docker/entrypoint.sh" ]
