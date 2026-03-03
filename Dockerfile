# SIP Engine — CPU-only Docker image
# Build: docker build -t sip-engine .
# Run:   docker run -v $(pwd)/secopDatabases:/app/secopDatabases -v $(pwd)/artifacts:/app/artifacts sip-engine run-pipeline --quick

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files for installation
COPY pyproject.toml ./
COPY src/ ./src/

# Install the package with all dependencies
RUN pip install --no-cache-dir ".[dev]"

# Stage 2: Runtime (smaller image)
FROM python:3.12-slim

WORKDIR /app

# Install curl for data downloads (primary download method)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY src/ ./src/
COPY pyproject.toml ./

# Create directories for data and artifacts
RUN mkdir -p secopDatabases artifacts Data/Propia/PACO

# Create non-root user
RUN useradd -m -u 1000 sip && chown -R sip:sip /app
USER sip

# Default: show help
ENTRYPOINT ["python", "-m", "sip_engine"]
CMD ["--help"]
