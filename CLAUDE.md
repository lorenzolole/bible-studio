# CLAUDE.md — Guía del Proyecto TikTok Bible Studio

Documento técnico de referencia y guía de desarrollo para asistentes de IA y desarrolladores que trabajen en el repositorio **TikTokBible**.

---

## 📖 Descripción del Proyecto

**TikTok Bible Studio** (v3.0.0) es una suite de creación automatizada de videos verticales (9:16, 1080×1920) optimizados para TikTok, Instagram Reels y YouTube Shorts. Combina:
1. **Audio oficial de David Suchet** (NIV-UK de BibleGateway) con compresión y realce vocal.
2. **Música real viral y contemplativa** (Emile Mosseri, Salvia Palth, Disasterpeace, Soil, Daniel.mp3, Cloud9ine, Her Soundtrack) con ducking y mezcla automática.
3. **Motor de Video Cinemático Multicapa (v3.0)**:
   - **Micro-movimiento Orgánico de Cámara**: respiración y deriva sinusoidal armónica de cámara en mano (evitando el zoom plano robótico).
   - **Pulsos Dinámicos Sincronizados con Whisper**: micro-zooms suaves (+2.2%) que acompañan el clímax vocal de David Suchet.
   - **Atmósfera de Polvo Celestial**: partículas luminosas doradas y etéreas flotando continuamente con desenfoque bokeh.
   - **Fuga de Luz Cálida Anamórfica**: destello ámbar/dorado inicial (0-2s) que funciona como gancho de retención de scroll en TikTok.
   - **Grano Fílmico Analógico 35mm**: emulsión de celuloide solemne que unifica los tonos del arte sacro.
   - 3 modos de lienzo: `pitch_black` (@nehzro), `fullscreen` (@nanagoes5) y `ambient`.
4. **Subtítulos sincronizados con IA**: Integración nativa con `whisper-cli` (Whisper en Apple Silicon GPU Metal) para temporización precisa palabra por palabra en 4 estilos ASS (`Typewriter`, `SpokenByHim`, `ClassicSerif`, `ModernBold`).
5. **Estudio Web Minimalista & Preciso**:
   - Panel de control de **Atmósfera & Efectos Cinemáticos (Viral FX)** con toggles independientes.
   - Timeline con doble tirador arrastrable (`handleStart`, `handleEnd`), desplazamiento continuo de ventana y regla de tiempo.
   - 8 Pasajes virales calibrados al segundo exacto (Juan 3:16 en 120s–133s).
   - Cajón de texto bíblico con búsqueda y salto directo por versículo (`/api/chapter_transcription`).
   - Mockup móvil sticky con proyección en tiempo real de marca de agua (`@canal`) y reproductor instantáneo.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.13 + FastAPI + Uvicorn + Pydantic
- **Procesamiento Multimedia**: FFmpeg 8.0 (con aceleración `videotoolbox` y filtros `subtitles`, `boxblur`, `alphamerge`, `xfade`, `aecho`, viñeta)
- **Manipulación de Imágenes**: Pillow (generación de máscaras antialiased de esquinas redondeadas)
- **Transcripción de Voz / IA**: `whisper-cli` (whisper.cpp v1.9.4) con modelo `ggml-base.en.bin` en GPU Apple Silicon Metal
- **Frontend**: HTML5 + CSS3 (estética minimalista suiza/Apple dark-mode) + Vanilla JS

---

## 🚀 Comandos Principales

### Iniciar Servidor Web
```bash
# Script de inicio rápido (abre el navegador automáticamente en macOS)
./run.sh

# O manualmente con Uvicorn:
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Generador CLI (Línea de Comandos)
```bash
# Ejemplo: Salmos 23 de 3s a 17s con subtítulos estilo máquina de escribir
python3 create_clip.py --book "Salmos" --chapter 23 --start 3 --end 17 --citation "PSALM 23:1-3" --style typewriter

# Ejemplo: Juan 3 con modo pitch_black y música cloud9ine
python3 create_clip.py --book "Juan" --chapter 3 --start 120.0 --end 133.0 --citation "JOHN 3:16" --style spokenbyhim --mode pitch_black
```

### Cerrar Puertos / Matar Servidor
```bash
kill -9 $(lsof -ti:8000) 2>/dev/null || true
```

---

## 📁 Arquitectura del Código

- `app.py`: Servidor FastAPI, endpoints REST (`/api/books`, `/api/chapter_info`, `/api/chapter_transcription`, `/api/transcribe`, `/api/presets`, `/api/render`, `GET/DELETE /api/videos`).
- `downloader.py`: Scraper y descargador de BibleGateway para audio MP3 de David Suchet y texto de versículos. Manejo de nombres en español/inglés y códigos USFM (`JHN`, `PSA`, `PHP`, etc.).
- `audio_engine.py`: Recorte con `ffprobe`/`ffmpeg`, realce vocal (highpass 75Hz + compresor broadcast), y mezcla con música duckeada al 15-18%.
- `subtitles.py`: Transcripción nativa con `whisper-cli` (Metal GPU) y formateador `.ass` 1080x1920 con estilos customizados.
- `video_engine.py`: Motor de composición FFmpeg con 3 modos de encuadre (`pitch_black`, `fullscreen`, `ambient`), máscaras redondeadas antialiased, viñetas, marca de agua y quemado de subtítulos.
- `create_clip.py`: Interfaz CLI con argparse.
- `templates/index.html`: UI del estudio web minimalista con timeline dual, cajón de lectura y vista previa de smartphone.
- `static/style.css`: Sistema de diseño moderno, limpio y sin clutter (Apple/Linear dark aesthetic).
- `static/app.js`: Lógica reactiva en cliente: scrubber drag & drop, snapping por frase, selector de música con preescucha y confirmación.
- `assets/`:
  - `visuals/`: Grabados tenebristas al aguafuerte, óleos de Jesucristo y miniaturas en `assets/thumbnails/`.
  - `music/`: Pistas virales reales (`cloud9ine_magic.mp3`, `daniel_gods_creation.mp3`, `arcadefire_dimensions.mp3`, `emile_mosseri_jacob.mp3`, `salvia_palth_dream.mp3`, etc.).
- `models/`: Modelo Whisper `ggml-base.en.bin`.
- `cache/`: Audios en caché, archivos temporales y máscaras PNG.
- `outputs/`: Videos finales generados (`.mp4`, 1080x1920).

---

## ⚠️ Reglas y Buenas Prácticas de Desarrollo

1. **Evitar Bloqueos de SSL**: BibleGateway y otros servidores pueden requerir deshabilitar la verificación estricta de certificados SSL en scripts de scraping Python (`ssl.create_default_context()` con `check_hostname=False` y `verify_mode=ssl.CERT_NONE`).
2. **Escapado de Rutas en Filtros FFmpeg**: Al pasar rutas de subtítulos a `subtitles=...` en FFmpeg, escapar siempre dos puntos `:` y barras invertidas `\` (`subtitle_ass.replace("\\", "/").replace(":", "\\:")`).
3. **Dimensiones Pares para Códecs H.264**: Todo tamaño calculado para video o máscaras debe redondearse a números pares (`w - w % 2`), de lo contrario `libx264` lanzará un error de formato de píxeles `yuv420p`.
4. **Miniaturas Web**: Nunca renderizar archivos `.mp4` dentro de etiquetas `<img>` HTML; utilizar siempre las miniaturas JPG generadas en `assets/thumbnails/`.
5. **Panel Móvil Fijo (Sticky Preview)**: El contenedor `.preview-pane` en la columna derecha debe mantener `position: sticky; top: 80px; align-self: start;` y contener exclusivamente la tarjeta del mockup móvil (sin scroll interno ni elementos secundarios debajo) para garantizar que el smartphone permanezca 100% inmóvil al desplazarse por el editor.
6. **Biblioteca de Videos en Columna Principal**: La galería de videos generados reside en la columna principal izquierda (debajo del dock de renderizado) con visualización en cuadrícula (`.history-gallery-grid`), orden cronológico inverso (`mtime` descendente), miniaturas 9:16 y títulos identificables legibles.
7. **Arte Sacro y Enfoque Bíblico Estricto**: Utilizar exclusivamente arte sacro reverente (escenas del Antiguo y Nuevo Testamento, profetas, creación, milagros de Jesús) sin figuras o representaciones no deseadas (como santos o vírgenes ajenos a los pasajes evangélicos puros).
8. **Ritmo Cinemático en Presentaciones**: Mantener ~4.5s por diapositiva con fundidos suaves (0.75s) como valor predeterminado para permitir la lectura y contemplación al ritmo de la narración de David Suchet.
9. **Limpieza de Puertos Locales**: Al pausar o finalizar sesiones, asegurar que no queden procesos `uvicorn` o servidores `http.server` corriendo en segundo plano escuchando en puertos locales.
