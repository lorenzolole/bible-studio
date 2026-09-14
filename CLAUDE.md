# CLAUDE.md — Guía Técnica & Handoff para Bible Studio

Documento técnico de referencia y guía de contexto para asistentes de IA (Claude Code) y desarrolladores que continúen el desarrollo de **Bible Studio**.

---

## 📌 Contexto Rápido & Enlaces Oficiales

- **Nombre del Proyecto**: Bible Studio *(v3.4.0 — renombrado desde TikTok Bible Studio)*.
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
- **Procesamiento de Video & Audio**: FFmpeg 8.0 en la Mac; en Docker el `ffmpeg` de Debian bookworm (5.1). Filtros usados: `movie`, `zoompan`, `alphamerge`, `overlay`, `noise`, `subtitles` (libass), `compand`, `boxblur`.
- **Manipulación Gráfica**: Pillow (máscaras antialiased, generación de overlays de partículas).
- **Frontend**: HTML5 + CSS3 (Apple/Linear dark mode sobrio) + Vanilla JS reactivo.
- **Infraestructura**: Docker multi-stage build (`Dockerfile`), optimizado para Render y Hugging Face Spaces.

---

## 📁 Estructura del Repositorio

- `app.py`: Servidor FastAPI. Endpoints: `/api/books`, `/api/chapter_info`, `/api/chapter_transcription`, `/api/transcribe` + `/api/transcribe_status`, `/api/render` + `/api/render_status`, `/api/presets`, `/api/videos`, `/api/upload_visual`, `/api/upload_music`, `/api/health`. Transcripciones con Whisper y renders corren como jobs en threads (`TRANSCRIBE_JOBS`, `RENDER_JOBS`) que el navegador consulta. `RENDER_LOCK` es el mismo `RLock` que Whisper: un solo trabajo pesado a la vez. Valida rutas de fondos/música (`resolve_media_path`: solo `assets/` y uploads), sanea uploads y limpia temporales (`prune_cache`).
- `transcripts.py`: Transcripciones palabra por palabra por capítulo, alineadas con el texto oficial. `get_clip_phrases()` resuelve los subtítulos de un clip: recorte de la transcripción del capítulo → `SESSION_CLIP_CACHE` → Whisper del clip (alineado) → estimación por texto. Lee `assets/transcripts/` (horneadas) y `cache/transcripts/` (runtime).
- `text_alignment.py`: `align_words_to_text()` conserva los tiempos de Whisper y toma palabras, puntuación y mayúsculas del NIV-UK (difflib; si coincide menos del 60% no toca nada).
- `bake_transcripts.py`: Hornea transcripciones en la Mac (Metal) para commitearlas: `WHISPER_THREADS=8 python3 bake_transcripts.py [LIBRO CAP ...] [--force] [--keep-audio]`. `--realign` alinea con el texto oficial las ya horneadas.
- `downloader.py`: Motor de scraping y descarga de audio de David Suchet y texto bíblico de BibleGateway. Limpieza de encabezados HTML (`<h1-h6>`), notas al pie, spans anidados (small-caps "LORD", palabras de Jesús) y entidades `&nbsp;`.
- `audio_engine.py`: Recorte de audio con `ffmpeg`, compresión vocal broadcast y mezcla con música duckeada.
- `subtitles.py`: Descubrimiento de `whisper-cli`, `transcribe_words()` (WAV 16kHz + JSON completo + timestamps DTW, un Whisper a la vez con `WHISPER_LOCK`), `words_to_phrases()` (agrupa palabras en frases cortando por puntuación) y formateo de subtítulos `.ass`.
- `video_engine.py`: Motor de composición 1080×1920. Todo FFmpeg pasa por `_run_ffmpeg()` (progreso por cuadros vía `-progress`, error con el final de stderr). Reglas de memoria para no pasar los 512 MB: fuentes de video como filtros `movie=` (no `-i`), todo a 30 fps, `THREAD_CAPS` + `-threads 1` por input + `FFMPEG_THREADS` en el encoder, zoom calculado al tamaño final.
- `create_clip.py`: Interfaz de línea de comandos (CLI) para generación por lotes, con subtítulos sincronizados.
- `generate_overlays.py`: Genera las capas de polvo celestial y fuga de luz (`assets/overlays/*.mkv`, FFV1 `yuva420p`; se crean en el build de Docker).
- `static/app.js`: Lógica del cliente, scrubber del timeline, snapping interactivo, e integración de `AbortController` para evitar condiciones de carrera.
- `static/style.css`: Estilos de la aplicación.
- `templates/index.html`: Plantilla principal del estudio web.
- `assets/transcripts/`: Transcripciones horneadas (`{osis}_{cap}.json`, formato `{"version":1,"words":[[palabra, inicio, fin], ...]}`): Nuevo Testamento completo, Génesis, Éxodo, Salmos, Proverbios, Isaías y capítulos populares del resto del AT (incluidos los pasajes virales).
- `assets/`: Biblioteca de música (`music/`), arte sacro (`visuals/`), miniaturas (`thumbnails/`) y overlays (`overlays/`).
- `Dockerfile`: Multi-stage build (compila `whisper.cpp` estático sin dependencias dinámicas, instala FFmpeg y descarga `ggml-base.en.bin`).
- `requirements.txt`: Dependencias Python (`fastapi`, `uvicorn`, `Pillow`, `numpy`, `pydantic`, `python-multipart`).
- `run.sh`: Script de ejecución local en 1 clic.

---

## ⚡ Cambios Recientes Realizados (v3.4.0)

1. **Render en producción arreglado**: FFmpeg llegaba a ~826 MB y el contenedor moría (502). Pico medido ahora: ~300–380 MB. Ver reglas de memoria en `video_engine.py`; no volver a usar entradas `-i` para overlays ni `.mov` ARGB.
2. **Render como job**: `POST /api/render` → `{pending, job_id}`; `GET /api/render_status` → etapa (`queue`, `subtitles`, `audio`, `visual`, `encode`, `thumbnail`), `progress`, `eta_sec`, y al terminar `video_url`/`filename`. El frontend (`waitForRenderJob`) muestra el avance en la tarjeta de render.
3. **Subtítulos alineados con el texto oficial**: las 617 transcripciones tienen `"aligned": true`. Los clips no horneados se alinean en vivo contra el capítulo (`downloader.fetch_passage_text` cachea el texto en memoria).
4. **Botones virales recalibrados** al rango exacto de cada versículo (`data-start`/`data-end` en `templates/index.html`).
5. **Frases del editor**: el navegador solo manda `phrases` al render si fueron transcriptas para el clip actual (`state.phrasesClip`); si no, el servidor las sincroniza.

### v3.3.0

1. **Jobs de transcripción con progreso**: si el clip no sale de una transcripción de capítulo ni del caché de sesión, `/api/transcribe` crea un job en un thread (`TRANSCRIBE_JOBS`) y devuelve `{"pending": true, "job_id", "stage", "progress"}`. El frontend (`waitForTranscribeJob` en `app.js`) consulta `GET /api/transcribe_status?job_id=` y muestra etapa, % y ETA en `#clipProgress`. Los jobs terminados se limpian a los 10 min.
2. **ETA**: `subtitles.estimate_whisper_seconds()` usa una velocidad aprendida (EMA) inicializada con `WHISPER_SEC_PER_AUDIO_SEC` (default 0.5; Docker 3.5) y se combina con el `-pp` de whisper-cli, que avanza por ventanas de 30s.
3. **⚡ en el selector de capítulos**: `/api/books` incluye `instant_chapters` (`transcripts.available_chapters()`).
4. **Horneado ampliado**: `bake_transcripts.py` sin argumentos hornea la lista popular + `FULL_BOOKS` (NT completo, Gen, Exod, Ps, Prov, Isa).

### v3.2.0

1. **Transcripción por capítulo + recorte por clip**: `/api/transcribe` ya no corre Whisper cuando el capítulo tiene transcripción; recorta las palabras del rango (~1 ms). Reemplaza a `assets/preset_transcriptions.json`.
2. **Timestamps DTW**: `whisper-cli -ojf -dtw base.en -nfa`. Los offsets normales de whisper.cpp se corrían hasta 1.7s; con DTW el error medido es ~0.05s. Si el binario rechaza los flags, reintenta sin DTW (`WHISPER_DTW=0` lo desactiva).
3. **Variables de entorno**: `CHAPTER_WHISPER` (default `1`; el `Dockerfile` pone `0` porque en 0.1 vCPU un capítulo entero tarda minutos → en Render los capítulos no horneados usan Whisper solo del clip), `WHISPER_THREADS` (default `2`), `WHISPER_DTW` (default `1`).
4. **Diagnóstico en producción**: `GET /api/health` devuelve ruta de `whisper-cli`, modelo, soporte DTW (`dtw_supported`) y cantidad de transcripciones horneadas. Si un clip no horneado responde `"source":"estimate"`, Whisper falló en el contenedor.
5. **Cola de Whisper**: un solo proceso a la vez; si la misma pestaña (`client_id`) pidió otro clip mientras esperaba, el pedido viejo se descarta (`superseded`).
6. **Bugs corregidos**: render con subtítulos apagados (`timed_phrases` sin definir), comillas rompiendo el editor de frases (escape HTML en `app.js`), versículos truncados por spans anidados en el scraper.

### v3.1.0

1. **Despliegue a Producción en Render**:
   - El proyecto está desplegado y funcionando en `https://bible-studio.onrender.com`.
   - Se configuró el puerto dinámico `PORT` en `Dockerfile` y `app.py`.
2. **Compilación Estática de Whisper**:
   - Se corrigió el error `exit status 127` en Linux compilando `whisper-cli` con `-DBUILD_SHARED_LIBS=OFF`.
   - v3.2.0: también `-DGGML_NATIVE=OFF` + AVX2. Con `NATIVE=ON` el binario usaba instrucciones de la CPU del build y moría con SIGILL (exit -4) en el host de Render. Si vuelve a pasar, `/api/health` → `last_whisper_error`.
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
   - Para capítulos nuevos: hornearlos y después correr `python3 bake_transcripts.py --realign` (el horneado nuevo ya sale alineado; `--realign` es para transcripciones viejas).
2. **Renderizado de Video en la Nube vs Local**:
   - En la Mac un clip de ~10s se renderiza en 5–15s. En Render (0.1 vCPU, libx264 por software) tarda minutos; por eso el render es un job con progreso.
   - Memoria: cualquier cambio en `video_engine.py` hay que medirlo (`/usr/bin/time -l ffmpeg ...` en la Mac o `docker run --memory=512m`). El techo real es ~512 MB **incluyendo** Python.
   - Los videos en `outputs/` se pierden cuando Render reinicia el contenedor: la UI avisa que hay que descargarlos.
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
