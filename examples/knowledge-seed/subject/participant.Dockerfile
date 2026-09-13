ARG NODE_BASE
FROM ${NODE_BASE}
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
