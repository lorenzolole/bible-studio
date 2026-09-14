# CLAUDE.md — Guía Técnica & Handoff para Bible Studio

Documento técnico de referencia y guía de contexto para asistentes de IA (Claude Code) y desarrolladores que continúen el desarrollo de **Bible Studio**.

---

## 📌 Contexto Rápido & Enlaces Oficiales

- **Nombre del Proyecto**: Bible Studio *(v3.2.0 — renombrado desde TikTok Bible Studio)*.
- **Repositorio Oficial en GitHub**: [https://github.com/lorenzolole/bible-studio](https://github.com/lorenzolole/bible-studio)
  - **Cuenta GitHub Activa**: `lorenzolole`
  - **Rama Principal**: `main`
- **URL en Producción en Vivo**: [https://bible-studio.onrender.com](https://bible-studio.onrender.com)
  - **Plataforma de Despliegue**: Render.com Web Service (Runtime Docker, Plan Gratuito $0/mes, 0.1 vCPU, 512 MB RAM).
  - **Auto-Deploy**: Cualquier `git push origin main` a GitHub dispara automáticamente el build y deploy en Render.
- **Directorio Local**: `/Users/lolescaldaferro/Antigravity/TikTokBible`

---

## 📖 Descripción del Producto

**Bible Studio** es una suite y estudio web automatizado para generar videos verticales solemnes y de alta retención (formato 9:16, 1080×1920) orientados a TikTok, Instagram Reels y YouTube Shorts.

### Componentes Clave:
1. **Audio Sagrado Oficial de David Suchet**:
   - Narración británica oficial de la Biblia NIV-UK extraída dinámicamente de BibleGateway.
   - 66 libros del Antiguo y Nuevo Testamento disponibles en español e inglés.
2. **Música Viral y Contemplativa**:
   - Pistas en `assets/music/`: *Magic (Slowed)* de Cloud9ine, *Gods Creation* de daniel.mp3, *Dimensions* de Arcade Fire, *Jacob and the Stone* de Emile Mosseri, *Dream* de Salvia Palth, *Wilderness* de Soil, *The Sound of Myself* de Disasterpeace.
   - Ducking inteligente de volumen vocal (baja la música al 15% mientras Suchet habla).
3. **Subtítulos Sincronizados con IA (Whisper)**:
   - Sincronización palabra por palabra con `whisper-cli` (whisper.cpp).
   - 4 estilos ASS: `Typewriter` (máquina de escribir dorada), `SpokenByHim` (oro celestial con sombra), `ClassicSerif` (serif clásico), `ModernBold` (grotesco moderno).
4. **Motor Cinemático de Video (v3.0)**:
   - **Ken Burns Continuo**: Acercamiento suave centrado sin saltos ni temblores artificiales.
   - **3 Modos de Encuadre**: `pitch_black` (fondo negro puro #000 con marco áureo redondeado estilo @nehzro), `fullscreen` (pantalla completa con viñeta estilo @nanagoes5), `ambient` (fondo desenfocado).
   - **Efectos Cinemáticos (Viral FX)**: Polvo celestial (partículas de luz), fuga de luz cálida (hook inicial 0-2s), grano fílmico 35mm.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.11/3.13 + FastAPI + Uvicorn + Pydantic.
- **IA / Speech-to-Text**: `whisper-cli` (whisper.cpp v1.9.4) con modelo `ggml-base.en.bin` (en local acelerado por Metal GPU; en Docker compilado estáticamente para CPU).
- **Procesamiento de Video & Audio**: FFmpeg 8.0 (con filtros de escala, ASS subtitles, compand, boxblur, alphamerge).
- **Manipulación Gráfica**: Pillow (máscaras antialiased, generación de overlays de partículas).
- **Frontend**: HTML5 + CSS3 (Apple/Linear dark mode sobrio) + Vanilla JS reactivo.
- **Infraestructura**: Docker multi-stage build (`Dockerfile`), optimizado para Render y Hugging Face Spaces.

---

## 📁 Estructura del Repositorio

- `app.py`: Servidor FastAPI, endpoints REST (`/api/books`, `/api/chapter_info`, `/api/chapter_transcription`, `/api/transcribe`, `/api/render`, `/api/presets`, `/api/videos`). `get_clip_phrases()` resuelve los subtítulos de un clip: transcripción del capítulo → `SESSION_TRANSCRIPTION_CACHE` → Whisper del clip → estimación por texto. Los endpoints pesados son `def` (threadpool) y el render está serializado con `RENDER_LOCK`.
- `transcripts.py`: Transcripciones palabra por palabra por capítulo. Se transcribe el capítulo una vez y cada clip se sirve recortando palabras (0 Whisper al mover el timeline). Lee `assets/transcripts/` (horneadas) y `cache/transcripts/` (runtime).
- `bake_transcripts.py`: Hornea transcripciones de capítulos populares en la Mac (Metal) para commitearlas: `WHISPER_THREADS=8 python3 bake_transcripts.py [LIBRO CAP ...] [--force]`.
- `downloader.py`: Motor de scraping y descarga de audio de David Suchet y texto bíblico de BibleGateway. Limpieza de encabezados HTML (`<h1-h6>`), notas al pie, spans anidados (small-caps "LORD", palabras de Jesús) y entidades `&nbsp;`.
- `audio_engine.py`: Recorte de audio con `ffmpeg`, compresión vocal broadcast y mezcla con música duckeada.
- `subtitles.py`: Descubrimiento de `whisper-cli`, `transcribe_words()` (WAV 16kHz + JSON completo + timestamps DTW, un Whisper a la vez con `WHISPER_LOCK`), `words_to_phrases()` (agrupa palabras en frases cortando por puntuación) y formateo de subtítulos `.ass`.
- `video_engine.py`: Motor de composición de video vertical 1080×1920 con control de hilos (`-threads 2`) y preset (`veryfast`) para no exceder 512 MB RAM.
- `create_clip.py`: Interfaz de línea de comandos (CLI) para generación por lotes.
- `generate_overlays.py`: Generador autónomo de las capas de polvo celestial y fuga de luz.
- `static/app.js`: Lógica del cliente, scrubber del timeline, snapping interactivo, e integración de `AbortController` para evitar condiciones de carrera.
- `static/style.css`: Estilos de la aplicación.
- `templates/index.html`: Plantilla principal del estudio web.
- `assets/transcripts/`: Transcripciones horneadas (`{osis}_{cap}.json`, formato `{"version":1,"words":[[palabra, inicio, fin], ...]}`) de ~125 capítulos populares, incluidos los pasajes virales.
- `assets/`: Biblioteca de música (`music/`), arte sacro (`visuals/`), miniaturas (`thumbnails/`) y overlays (`overlays/`).
- `Dockerfile`: Multi-stage build (compila `whisper.cpp` estático sin dependencias dinámicas, instala FFmpeg y descarga `ggml-base.en.bin`).
- `requirements.txt`: Dependencias Python (`fastapi`, `uvicorn`, `Pillow`, `numpy`, `pydantic`, `python-multipart`).
- `run.sh`: Script de ejecución local en 1 clic.

---

## ⚡ Cambios Recientes Realizados (v3.2.0)

1. **Transcripción por capítulo + recorte por clip**: `/api/transcribe` ya no corre Whisper cuando el capítulo tiene transcripción; recorta las palabras del rango (~1 ms). Reemplaza a `assets/preset_transcriptions.json`.
2. **Timestamps DTW**: `whisper-cli -ojf -dtw base.en -nfa`. Los offsets normales de whisper.cpp se corrían hasta 1.7s; con DTW el error medido es ~0.05s. Si el binario rechaza los flags, reintenta sin DTW (`WHISPER_DTW=0` lo desactiva).
3. **Variables de entorno**: `CHAPTER_WHISPER` (default `1`; el `Dockerfile` pone `0` porque en 0.1 vCPU un capítulo entero tarda minutos → en Render los capítulos no horneados usan Whisper solo del clip), `WHISPER_THREADS` (default `2`), `WHISPER_DTW` (default `1`).
4. **Cola de Whisper**: un solo proceso a la vez; si la misma pestaña (`client_id`) pidió otro clip mientras esperaba, el pedido viejo se descarta (`superseded`).
5. **Bugs corregidos**: render con subtítulos apagados (`timed_phrases` sin definir), comillas rompiendo el editor de frases (escape HTML en `app.js`), versículos truncados por spans anidados en el scraper.

### v3.1.0

1. **Despliegue a Producción en Render**:
   - El proyecto está desplegado y funcionando en `https://bible-studio.onrender.com`.
   - Se configuró el puerto dinámico `PORT` en `Dockerfile` y `app.py`.
2. **Compilación Estática de Whisper**:
   - Se corrigió el error `exit status 127` en Linux compilando `whisper-cli` con `-DBUILD_SHARED_LIBS=OFF`.
3. **Caché Instantánea de Pasajes Virales (0.05s)** *(reemplazada en v3.2.0 por `assets/transcripts/`)*.
4. **Prevención de Condiciones de Carrera (`AbortController`)**:
   - En `static/app.js`, cualquier nuevo clic o movimiento de slider aborta peticiones anteriores en curso, evitando que textos viejos sobrescriban la selección actual.
5. **Limpieza de Títulos y Entidades HTML**:
   - En `downloader.py`, se eliminan etiquetas de encabezado `<h3>` (para que títulos como *"The Word became flesh"* no se metan en el versículo 1 de Juan 1) y se usa `html_lib.unescape` para limpiar `&nbsp;`.
6. **Optimización de Memoria FFmpeg**:
   - Se limitó FFmpeg a `-threads 2` y `-preset veryfast` para evitar que el renderizado de video sea eliminado por falta de memoria (OOM kill) en el contenedor de 512 MB RAM de Render.

---

## 🎯 Puntos de Atención & Próximos Pasos para Claude Code

1. **Capítulos No Horneados en la Nube (CPU Throttling)**:
   - Los capítulos de `assets/transcripts/` responden al instante. Un capítulo no horneado (ej. *Levítico 15*) en Render sigue necesitando Whisper por clip en 0.1 vCPU, y el lector de capítulo no muestra marcas de tiempo.
   - *Para sumar capítulos*: agregarlos a `POPULAR_CHAPTERS` en `bake_transcripts.py` (o pasarlos por argumento), correrlo en la Mac y commitear los JSON.
   - *Pendiente*: indicador de progreso por etapas en la UI, alinear palabras de Whisper con el texto oficial NIV-UK (corrige nombres mal oídos, ej. "Curia Thaba" por "Kiriath Arba"), recalibrar los rangos de los botones virales usando las palabras horneadas (Proverbios 3 e Isaías 41 arrancan con la cola del versículo anterior).
2. **Renderizado de Video en la Nube vs Local**:
   - En la Mac local (Apple M4), FFmpeg renderiza el video en 4 segundos usando aceleración por hardware Metal/VideoToolbox.
   - En Render (0.1 vCPU), el renderizado es por software puro libx264. Asegurarse de mantener los hilos bajos y los presets rápidos.
3. **Comandos para Correr en Local**:
   ```bash
   cd /Users/lolescaldaferro/Antigravity/TikTokBible
   ./run.sh
   ```
4. **Comando para Desplegar a Producción**:
   ```bash
   git add .
   git commit -m "tu mensaje"
   git push origin main
   # Render detecta el push a main y despliega en 2 minutos automáticamente.
   ```
