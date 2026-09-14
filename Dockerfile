# ==============================================================================
# Stage 1: Build whisper-cli binary
# ==============================================================================
FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git && \
    cd whisper.cpp && \
    cmake -B build -DWHISPER_BUILD_EXAMPLES=ON && \
    cmake --build build --config Release -j$(nproc) --target whisper-cli && \
    mkdir -p /dist/bin && \
    cp build/bin/whisper-cli /dist/bin/

# ==============================================================================
# Stage 2: Runtime image (compatible with Hugging Face Spaces Docker SDK)
# ==============================================================================
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Install runtime system packages (FFmpeg, fonts, certs, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-freefont-ttf \
    fonts-liberation \
    fonts-dejavu-core \
    fontconfig \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled whisper-cli binary
COPY --from=builder /dist/bin/whisper-cli /usr/local/bin/whisper-cli
RUN chmod +x /usr/local/bin/whisper-cli

# Setup non-root user (required by Hugging Face Spaces: UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install Python dependencies
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application source and assets
COPY --chown=user:user . .

# Ensure required directories exist, generate cinematic overlays and download Whisper model
RUN mkdir -p models cache/audio cache/uploads outputs/thumbnails assets/overlays && \
    python3 generate_overlays.py && \
    curl -L -f https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin -o models/ggml-base.en.bin

EXPOSE 7860

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
