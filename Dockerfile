# ==============================================================================
# Stage 1: Build whisper-cli binary (statically linked against whisper & ggml)
# ==============================================================================
FROM python:3.11-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
# GGML_NATIVE=OFF: the build host's CPU (e.g. AVX-512) differs from the runtime host, and a
# -march=native binary dies with SIGILL on the first transcription. Target portable AVX2 instead.
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git && \
    cd whisper.cpp && \
    cmake -B build -DWHISPER_BUILD_EXAMPLES=ON -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON && \
    cmake --build build --config Release -j$(nproc) --target whisper-cli && \
    mkdir -p /dist/bin /dist/lib && \
    cp build/bin/whisper-cli /dist/bin/ && \
    (cp build/bin/*.so* /dist/lib/ 2>/dev/null || true) && \
    (cp build/src/*.so* /dist/lib/ 2>/dev/null || true) && \
    (cp build/ggml/src/*.so* /dist/lib/ 2>/dev/null || true)

# ==============================================================================
# Stage 2: Runtime image (compatible with Render & Hugging Face Spaces)
# ==============================================================================
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    CHAPTER_WHISPER=0 \
    WHISPER_SEC_PER_AUDIO_SEC=5 \
    FFMPEG_THREADS=1 \
    MONTAGE_WORKERS=1

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

# Copy compiled whisper-cli binary and any companion libraries
COPY --from=builder /dist/bin/ /usr/local/bin/
COPY --from=builder /dist/lib/ /usr/local/lib/
RUN ldconfig && \
    chmod +x /usr/local/bin/whisper-cli && \
    whisper-cli --help > /dev/null && \
    echo "✓ whisper-cli verified and fully operational"

# Setup non-root user (required by container best practices: UID 1000)
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
