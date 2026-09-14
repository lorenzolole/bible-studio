#!/bin/bash
# Bible Studio — local launcher
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

echo "=========================================="
echo "✝ Bible Studio — David Suchet NIV-UK"
echo "=========================================="

# Requirements for transcription and rendering
missing=0
command -v ffmpeg >/dev/null || { echo "✗ Falta ffmpeg: brew install ffmpeg"; missing=1; }
command -v whisper-cli >/dev/null || { echo "✗ Falta whisper-cli: brew install whisper-cpp"; missing=1; }
if [ ! -f models/ggml-base.en.bin ]; then
    echo "✗ Falta el modelo de Whisper. Descargalo con:"
    echo "  curl -L -o models/ggml-base.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
    missing=1
fi
[ "$missing" = 1 ] && exit 1

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
    echo "✗ El puerto $PORT ya está en uso (¿Bible Studio ya está abierto?). Probá con: PORT=8001 ./run.sh"
    exit 1
fi

echo "Iniciando servidor local en http://localhost:$PORT ..."

# Open browser after 1.5 seconds in background
(sleep 1.5 && open "http://localhost:$PORT") &

# Start Uvicorn web server
python3 -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
