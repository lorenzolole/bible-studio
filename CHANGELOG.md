# Changelog — Bible Studio

Todos los cambios notables de este proyecto se documentarán en este archivo siguiendo el formato [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

## [3.3.0] - 2026-09-14

### Agregado
- **Progreso real para capítulos no horneados**: `/api/transcribe` responde al instante con un job (`pending`, `job_id`) y el navegador consulta `GET /api/transcribe_status` cada 800 ms. La tarjeta "Texto hablado" muestra etapa (descarga → recorte → cola → Whisper), porcentaje y tiempo estimado.
- El ETA combina el porcentaje de `whisper-cli -pp` con el tiempo transcurrido contra la velocidad aprendida de corridas anteriores (`WHISPER_SEC_PER_AUDIO_SEC`, 3.5 en Docker).
- **Marcador ⚡ en el selector de capítulos** para los que tienen transcripción (`instant_chapters` en `/api/books`).
- **Más capítulos horneados**: Nuevo Testamento completo, Génesis, Éxodo, Salmos, Proverbios e Isaías, además de la lista popular. `bake_transcripts.py` borra los MP3 que descarga (`--keep-audio` para conservarlos).

### Cambiado
- El mismo clip pedido desde dos pestañas reutiliza un único job; un clip ya transcripto en la sesión responde sin job.

---

## [3.2.0] - 2026-09-14

### Agregado
- **Transcripciones por capítulo palabra por palabra (`transcripts.py`)**: cada capítulo se transcribe una vez y cualquier clip se sirve recortando sus palabras; mover el timeline ya no ejecuta Whisper (~1 ms por pedido).
- **~125 capítulos populares horneados en `assets/transcripts/`** con `bake_transcripts.py` (Whisper con Metal en la Mac). Sobreviven a los reinicios de Render y reemplazan a `assets/preset_transcriptions.json`.
- **Timestamps DTW** (`-ojf -dtw base.en -nfa`): error medido ~0.05s contra ~1.7s de los offsets normales de whisper.cpp.
- **Frases cortadas por puntuación** (`words_to_phrases`), sin dejar palabras sueltas como "and" o "the" al final de línea.
- Variables de entorno `CHAPTER_WHISPER`, `WHISPER_DTW` y `WHISPER_THREADS`.
- `GET /api/health`: muestra si el contenedor tiene `whisper-cli`, el modelo, soporte DTW y cuántas transcripciones horneadas carga.
- El reintento sin DTW se decide por la existencia del JSON y no por el exit code (`whisper-cli` sale con 0 ante flags desconocidos).
- **Whisper en Render moría con SIGILL (exit -4)**: `whisper-cli` se compilaba con `GGML_NATIVE=ON` (instrucciones de la CPU del build) y el host de ejecución no las soporta; los clips no horneados caían siempre en la estimación por texto. Ahora se compila con `GGML_NATIVE=OFF` + AVX2.

### Corregido
- Render con subtítulos apagados fallaba (`timed_phrases` sin definir).
- Frases con comillas (ej. Salmo 23) aparecían vacías o cortadas en el editor: escape HTML en `app.js`.
- El scraper truncaba versículos con spans anidados (small-caps "LORD", palabras de Jesús): Génesis 2 devolvía la mitad del texto.
- El servidor quedaba bloqueado mientras corría Whisper o un render (endpoints `async` con subprocess bloqueante): ahora corren en threadpool, con un solo Whisper y un solo render a la vez.
- Al cargar un capítulo corrían dos Whisper en paralelo (clip + capítulo sin límite de hilos); en Docker el de capítulo queda desactivado y los pedidos viejos de la misma pestaña se descartan de la cola.

---

## [3.1.0] - 2026-09-14

### Agregado
- **Despliegue a Producción en la Nube (Render.com Docker Web Service)**:
  - Repositorio oficial publicado en GitHub: `lorenzolole/bible-studio`.
  - Despliegue en vivo en: `https://bible-studio.onrender.com`.
  - `Dockerfile` multi-stage autónomo compatible con Render y Hugging Face Spaces (UID 1000, puerto dinámico `$PORT` / 7860).
  - CI/CD preparado con GitHub Actions (`.github/workflows/sync_to_hf.yml`).
- **Caché Pre-Calibrada de Pasajes Virales (`assets/preset_transcriptions.json`)**:
  - Transcripciones generadas con GPU y precisión de milisegundos para los pasajes clave (`John 3:16`, `Psalm 23:1-3`, `Psalm 91:1-2`, `Philippians 4:13`, `Proverbs 3:5-6`, `Isaiah 41:10`, `Romans 8:28`).
  - Respuesta instantánea (0.05s) en producción sin carga de CPU en el servidor.
- **Caché de Sesión en Memoria**:
  - `SESSION_TRANSCRIPTION_CACHE` almacena en tiempo de ejecución cualquier fragmento transcrito para evitar re-procesamientos.

### Corregido
- **Compilación Estática de `whisper-cli`**:
  - Corrección del error `exit status 127` en Linux mediante compilación con `-DBUILD_SHARED_LIBS=OFF` sobre `python:3.11-slim-bookworm`, incorporando `libwhisper` y `libggml` dentro del binario.
  - Validación en tiempo de build con `whisper-cli --help`.
- **Eliminación de Condiciones de Carrera (*Race Conditions*) en Frontend**:
  - Integración de `AbortController` en `static/app.js`: toda nueva selección o movimiento del slider cancela inmediatamente peticiones anteriores en vuelo.
  - Limpieza visual inmediata del texto viejo al cambiar de libro para evitar la persistencia de subtítulos anteriores.
  - Aumento del debounce a 500ms al arrastrar tiradores del timeline.
- **Limpieza de Entidades HTML en Scraper Bíblico**:
  - Decodificación con `html.unescape` eliminando `&nbsp;`, `\xa0` y entidades crudas en el texto del pasaje.
- **Optimización de Audio para Whisper**:
  - Conversión automática de fragmentos a WAV 16kHz mono (`pcm_s16le`) y ejecución con `-t 2` para evitar colapsar la CPU compartida de la nube.
- **Optimización de Memoria FFmpeg**:
  - Configuración de `-threads 2` y `-preset veryfast` para garantizar que el renderizado de video en 1080×1920 permanezca dentro del límite de 512 MB RAM de contenedores gratuitos.

---

## [3.0.1] - 2026-09-13

### Corregido
- **Erradicación del Tembleque y Jitter en la Animación**:
  - Eliminación de las oscilaciones sinusoidales y saltos discretos de 1 fotograma en `zoompan` que provocaban temblores artificiales en la figura de Jesús.
  - Implementación de un movimiento de acercamiento continuo, majestuoso y ultra-suave ("Butter-smooth Ken Burns slow push-in") con alineación óptica fija en el centro (`iw/2-(iw/zoom/2)`).
- **Normalización Universal de Citas Bíblicas al Idioma Inglés**:
  - El audio narrado es en inglés oficial británico por David Suchet (NIV-UK); ahora todas las citas bíblicas se normalizan automáticamente al inglés (`— JOHN 3:16 —`, `— PSALM 23:1-3 —`, `— PHILIPPIANS 4:13 —`, `— PROVERBS 3:5-6 —`, etc.) mediante `normalize_citation_english()`.
  - Actualización de los 8 pasajes virales de la barra rápida con títulos, citas y versículos clave en inglés oficial.
- **Clarificación de la UI y Ocultación Contextual de Controles**:
  - El selector de "Ritmo de Diapositivas" (`slideshowPacingContainer`) ahora permanece oculto cuando se edita una sola obra de arte y solo se activa cuando se selecciona una colección o presentación de múltiples obras, eliminando la confusión con el movimiento de cámara individual.
  - Renombrado del toggle en el panel de efectos a: `🎥 Movimiento Cinemático Suave (Slow push-in continuo sin temblores)`.

---

## [3.0.0] - 2026-09-13

### Agregado
- **Motor de Video Cinemático Multicapa (Cinematic Atmosphere Engine)**:
  - **Micro-movimiento Orgánico de Cámara ("Camera Drift & Breathing")**: Expresiones sinusoidales armónicas compuestas en `zoompan` para emular una cámara de cine en mano con estabilizador suave, eliminando el zoom lineal estático.
  - **Pulsos Dinámicos de Zoom Reactivos a Whisper AI**: Detección de los tiempos de ataque vocal de David Suchet para inyectar micro-push ins suaves (+2.2%) con decaimiento orgánico (`smooth settle`) que conectan visualmente con las palabras cumbre del versículo.
  - **Atmósfera de Polvo Celestial ("Heavenly Dust Motes")**: Overlay de partículas doradas/etéreas flotando suavemente hacia arriba con centelleo y desenfoque bokeh, superpuestas con canal alfa nativo (`overlay=format=auto`) sin distorsión de color.
  - **Fuga de Luz Cálida Anamórfica ("Warm Divine Light Leak")**: Destello ámbar/dorado de entrada en los primeros 1.5s - 2.0s de video, actuando como gancho instantáneo de retención para el scroll de TikTok.
  - **Grano Fílmico Analógico 35mm**: Texturizado sutil de emulsión de película de cine con `noise=c1s=3:c1f=t+u` y contraste equilibrado.
- **Panel de Control de Atmósfera & Efectos Cinemáticos (Viral FX) en la UI**:
  - Toggles individuales en el Paso 03 del estudio web para encender o apagar a discreción:
    - ✨ *Polvo Celestial* (partículas de luz dorada).
    - 🌅 *Fuga de Luz Cálida* (hook inicial 0-2s).
    - 🎥 *Cámara Viva & Pulsos Whisper* (movimiento reactivo).
    - 🎞️ *Grano Fílmico 35mm* (textura analógica).
- **Generador Autónomo de Overlays (`generate_overlays.py`)**:
  - Script optimizado con Pillow y FFmpeg para pre-renderizar los assets cinemáticos en `assets/overlays/` en menos de 5 segundos.
- **Soporte CLI Enriquecido en `create_clip.py`**:
  - Nuevos flags `--mode` (`pitch_black`, `fullscreen`, `ambient`), `--no-particles`, `--no-leaks`, `--no-motion`, `--no-grain` y generación automática de miniaturas para la biblioteca.

---

## [2.7.0] - 2026-09-13

### Agregado
- **Timeline Interactivo con Doble Tirador (Drag Scrubber)**:
  - Tiradores deslizables con mouse y touch para fijar segundo de inicio (`handleStart`) y fin (`handleEnd`) con tooltips de tiempo en vivo (`mm:ss.s`).
  - Desplazamiento de ventana completa (`timelineActiveRange`): arrastrar el cuerpo central desliza la selección de tiempo a lo largo del capítulo sin alterar su duración.
  - Indicador flotante de tiempo al pasar el cursor sobre la pista (`timelineHoverTime`) y regla graduada de escala temporal.
- **Calibración Quirúrgica de los 8 Pasajes Virales con GPU Whisper**:
  - *Juan 3:16* ajustado a **`120.0s - 133.0s`** (antes apuntaba a `35.0s`, leyendo el diálogo de Nicodemo en el versículo 4).
  - *Salmo 23:1-3* fijado en **`3.0s - 17.0s`**.
  - *Salmo 91:1-2* fijado en **`3.0s - 15.0s`**.
  - *Filipenses 4:13* fijado en **`131.5s - 138.5s`**.
  - *Proverbios 3:5-6* fijado en **`29.5s - 43.0s`**.
  - *Isaías 41:10* fijado en **`99.0s - 114.0s`**.
  - *Romanos 8:28* fijado en **`277.0s - 292.0s`**.
  - *1 Corintios 13:4-7* fijado en **`38.0s - 54.0s`**.
- **Lector de Capítulos con Búsqueda y Salto Directo por Frase (Verse Snapping)**:
  - Nuevo endpoint `GET /api/chapter_transcription` para servir las frases del capítulo con marcas de tiempo.
  - Filtro de búsqueda en tiempo real dentro del cajón de lectura y frases clickeables que ajustan los tiradores del timeline automáticamente.
- **Marca de Agua en Vivo en el Mockup Móvil**: El identificador de canal (`@canal`) se proyecta en tiempo real en la pantalla del smartphone de vista previa.

### Corregido
- **Auto-selección de Música**: Al hacer clic en el botón `▶` para preescuchar cualquier pista, se selecciona automáticamente dicha canción para el video final, eliminando la discrepancia donde quedaba seleccionada la primera pista. Se agregó distintivo visual `Activa ✓` y barra fija de estado.
- **Resolución del Spinner Infinito**: El indicador de carga rotatorio desaparece inmediatamente al completar el renderizado, reemplazado por un checkmark de verificación verde esmeralda y confirmación de éxito.

---

## [2.6.0] - 2026-09-13

### Agregado
- **Enfoque Solemne en Jesucristo & 5 Obras de Arte Sacro en Alta Resolución**:
  - `tiktok_pfp_jesus.jpg`: Retrato en claroscuro de Rembrandt con fondo negro y halo sutil de pan de oro, optimizado como Foto de Perfil (PFP) 1:1 oficial con botón de descarga en la barra superior.
  - `jesus_shepherd_etching.jpg`: Grabado antiguo al aguafuerte / carboncillo del Buen Pastor (estilo `@nehzro`).
  - `jesus_cross_icon.jpg`: Icono bizantino tenebrista de Cristo en la cruz con corona de espinas (estilo `@nanagoes5`).
  - `jesus_walking_waves.jpg`: Óleo dramático y reverente de Jesús rescatando a Pedro sobre las aguas.
  - `jesus_light_world.jpg`: Cristo Luz del Mundo llamando a la puerta con linterna (*estilo Holman Hunt*).
- **Nuevos Modos de Lienzo & Encuadre**:
  - `pitch_black`: Fondo negro absoluto (`#000000`) con obra grabada u óleo centrada en proporción áurea y esquinas redondeadas.
  - `fullscreen`: Obra llenando verticalmente el lienzo 1080×1920 con viñeta sutil de contraste para subtítulos.
  - `ambient`: Fondo enmarcado con desenfoque ambiental desaturado al 85%.
- **Soporte de Códigos USFM**: Mapeo universal de códigos de libros (`JHN`, `PSA`, `PHP`, `PRO`, `ISA`, `ROM`, `1CO`) en `downloader.py`.

### Eliminado
- **Erradicación de Transiciones Artificiales**: Retiro total de transiciones digitales rápidas (`circlecrop`, `radial`, barridos) y desenfoques saturados tipo CapCut, restringiendo las transiciones a disolvencias suaves (`dissolve`) y micro-movimientos solemnes de museo.

---

## [2.5.0] - 2026-09-13

### Agregado
- **Tres Nuevas Pistas Virales de Alta Fidelidad**:
  - *Magic (Slowed + Reverb)* — cloud9ine (*Medasin*).
  - *Gods Creation* — daniel.mp3.
  - *Dimensions* — Arcade Fire & Owen Pallett (*Her Soundtrack*).
- **Barra de Acceso Rápido a Pasajes Virales**: Carrusel horizontal en el Paso 01 con los 8 versículos más reproducidos.
- **Selección Múltiple Libre de Obras**: Interruptor de selección múltiple en la pestaña de obras individuales para armar presentaciones personalizadas con badge de conteo.
- **Marca de Agua / Canal del Creador**: Campo para superponer `@canal` en el video exportado.
- **Opciones de Subtítulos**: Selector de posición (inferior / centro) y transformación a MAYÚSCULAS.
- **Atajo de Teclado**: Barra espaciadora para reproducir/pausar la selección de audio.
- **Corrección de Layout (v2.5.1)**: Resolución del desbordamiento en pantallas medianas mediante `minmax(0, 1fr)` y confinamiento del scroll.

---

## [2.4.0] - 2026-09-13

### Agregado
- **Rediseño Estético Minimalista & Moderno (Menos Vibe-Coded, Cero Clutter)**:
  - Nueva estética neutra y refinada inspirada en la sobriedad tipográfica de Apple.
  - Paleta monocromática con superficies profundas (`#0b0c0e`, `#121418`) y acentos esmeralda/cielo.
  - Tipografía profesional Plus Jakarta Sans combinada con Courier Prime y Playfair Display.
  - Eliminación de bordes brillantes, gradientes estridentes y sobrecarga visual.

---

### Agregado
- **Integración de Música Real (No Sintética)**: Incorporación de 4 pistas reales icónicas, de alto impacto emocional y viral en TikTok:
  - *Jacob and the Stone* — Emile Mosseri (*Minari Soundtrack*, 1:35).
  - *(dream)* — Salvia Palth (1:24).
  - *The Sound of Myself* — Disasterpeace (1:41).
  - *Wilderness* — Soil (7:36).
  - Títulos y créditos legibles en la interfaz de usuario y preescucha instantánea.
- **Nuevas Obras Maestras Bíblicas al Óleo en Alta Resolución (3:4)**:
  - *Moisés en el Monte Sinaí* (`moses_mount_sinai.jpg`): Moisés con las Tablas de la Ley en la cumbre del monte, tormenta y rayos de luz divina estilo claroscuro de Rembrandt.
  - *El Profeta Isaías en el Templo* (`isaiah_prophet_temple.jpg`): Visión celestial de serafines y la gloria de Dios llenando el santuario.
  - *El Paso del Mar Rojo* (`crossing_red_sea.jpg`): La colosal muralla de aguas abiertas iluminadas por la columna de fuego divina.
- **Calibración del Ritmo Visual (Slideshow Pacing)**:
  - Selector en la interfaz: **🎬 Cinemático Reverente (~4.5s)** (predeterminado) vs **⚡ Dinámico / Rítmico (~2.4s)**.
  - Tiempo por obra ampliado de 2.2s a **4.5s** para permitir la contemplación serena de las obras y sincronizarse armónicamente con la voz pausada de David Suchet.
  - Transiciones suavizadas a **0.75s** (`fade`, `dissolve`, `smoothleft`, `fadeblack`) y paneo Ken Burns sincronizado exactamente a la duración de cada diapositiva.
- **Nuevas Colecciones Curadas**:
  - *Profetas, Alianza & Éxodo* (5 obras del Antiguo Testamento).
  - *Vida y Milagros de Jesús* (5 obras del Evangelio).
  - *Paz & Majestad Celestial* (4 obras de contemplación).

### Eliminado
- **Depuración Estética**: Retiro completo de la obra `adoration_shepherds.jpg` (representación de la Virgen María / Natividad) para preservar un enfoque 100% centrado en la narrativa bíblica reverente y pasajes evangélicos.
- **Música Sintética Reemplazada**: Las pistas sintetizadas fueron archivadas, dejando como biblioteca principal las pistas reales de alta fidelidad.

---

## [2.2.0] - 2026-09-13

### Agregado
- **Vista Previa en Vivo del Texto Hablado (Paso 1)**: Tarjeta interactiva `🗣️ Texto Hablado en el Clip (Vista Previa en Vivo)` con conteo dinámico de palabras (`X palabras`) y actualización en tiempo real con debounce al ajustar los puntos de inicio/fin, micro-steppers `[-1s]` / `[+1s]` o píldoras de duración (`15s`, `30s`, `60s`, `Capítulo Completo`).
- **Nuevas Obras Maestras Bíblicas en Alta Resolución**:
  - *Cristo Caminando sobre las Aguas* (óleo dramático en el Mar de Galilea estilo claroscuro de Rembrandt).
  - *La Creación de la Luz* (Génesis con rayo divino celestial estilo Miguel Ángel y Gustave Doré).
  - *El Rey David y el Arpa Sagrada* (templo iluminado con rayos de luz celestial).
  - *Amanecer de la Resurrección* (el Salvador ante el sepulcro vacío al amanecer).
  - Todas integradas con miniaturas optimizadas en `assets/thumbnails/`.
- **Modo Presentación Dinámica Estilo "TikTok Edit"**: Motor de diapositivas (`video_engine.py`) actualizado para ritmos virales: cortes acelerados de 2.0s a 2.4s por toma, transiciones dinámicas ultra rápidas de 0.45s (rotando fluidamente entre `fade`, `smoothleft`, `smoothright`, `fadeblack`, `circlecrop`, `dissolve` y `radial`) y efectos de paneo/zoom Ken Burns alternados.
- **Nuevas Colecciones Temáticas**:
  - *TikTok Edit: Vida y Milagros de Jesús* (5 obras en rotación rápida).
  - *TikTok Edit: Creación & Alabanza* (4 obras celestiales).

### Eliminado
- **Eliminación de Recursos No Bíblicos**: Retirados por completo los bucles e imágenes de gatos (`cozy_cat_grass.jpg`, `loop_cozy_cat.mp4`) para preservar un enfoque 100% bíblico, reverente y de alto impacto estético.

---

## [2.1.0] - 2026-09-13

### Agregado
- **Opción "Sin Música de Fondo" (Voz Pura)**: Tarjeta dedicada `🔇 Sin Música (Solo Voz)` en el paso 4; permite renderizar videos con la narración limpia de David Suchet (ideal para cuentas minimalistas o para usar audios y sonidos virales en tendencia directamente dentro de TikTok).
- **Preescucha Instantánea de Pistas Musicales**: Botón de reproducción rápida (`▶` / `⏸`) en cada tarjeta de música para escuchar la melodía de fondo antes de renderizar.
- **Modo "Sin Subtítulos" / Subtítulos Opcionales**: Interruptor toggle en el encabezado del Paso 2 y opción `🚫 Limpio (Sin Subtítulos)` para exportar videos limpios, listos para las leyendas nativas automáticas de TikTok.
- **Visor Integrado de Texto Bíblico**: Acordeón desplegable `📖 Leer Texto del Capítulo (NIV-UK)` que muestra los versículos completos del capítulo cargado para facilitar la lectura y selección del fragmento de audio.
- **Micro-Controles de Precisión en la Línea de Tiempo**: Botones de ajuste fino `[-1s]` y `[+1s]` para mover los puntos de inicio y fin sin tener que teclear números manualmente.
- **Eliminación Directa de Videos en la Biblioteca**: Endpoint `DELETE /api/videos/{filename}` y botón de papelera (`🗑️`) en cada tarjeta para borrar clips de prueba u obsoletos de forma segura.
- **Estilos de Borde del Marco Visual**: Selector de acabados para el marco central (*Marco Dorado Clásico*, *Minimalista Suave*, *Resplandor Celestial*) reflejados en vivo en el mockup del smartphone.
- **CLI Actualizado**: Soporte de banderas `--no-music` y `--no-subtitles` en `create_clip.py`.

---

## [2.0.0] - 2026-09-13

### Agregado
- **Sincronización Automática con Whisper AI**: Transcripción nativa en menos de 0.5s acelerada por GPU Apple Silicon Metal (`whisper-cli` con modelo `ggml-base.en.bin`), detectando marcas de tiempo exactas para que las palabras aparezcan al ritmo de la voz de David Suchet.
- **Editor Interactivo de Frases**: Lista interactiva en pantalla para revisar y editar cualquier palabra de los subtítulos antes de renderizar.
- **Ajuste Automático de Duración y Timeline Dual**: Píldoras de ajuste en 1 clic (`⚡ Capítulo Completo`, `⏱️ 15s (Gancho)`, `⏱️ 30s`, `⏱️ 60s`) y barra de tiempo interactiva con selector de rango activo.
- **Modo Presentación Dinámica (Slideshow Multi-Foto)**: Soporte para alternar fluidamente entre varias obras de arte mediante transiciones *crossfade* (`xfade`) y paneo lento (*Ken Burns*) a lo largo del video.
- **Colecciones de Arte**: Nuevas colecciones temáticas integradas (*Vida de Cristo*, *Paz y Naturaleza*).
- **Nuevas Obras Clásicas**:
  - *Cristo en Getsemaní* (Heinrich Hofmann).
  - *Tormenta en el Mar de Galilea* (Rembrandt).
  - *Atardecer en la Montaña* (Paisaje sereno con nubes doradas).
- **Documentación**: Creación de `CLAUDE.md` (guía técnica de arquitectura) y `CHANGELOG.md`.

### Corregido
- **Panel Móvil Completamente Fijo (Sticky Preview sin desplazamiento)**: Corregido el desplazamiento indeseado del mockup móvil. Se eliminó el contenedor de scroll interno en `.preview-pane` y se aisló exclusivamente el teléfono en la columna lateral derecha (`top: 80px; align-self: start;`), garantizando que permanezca 100% inmóvil y visible en pantalla mientras se desplazan los controles del editor.
- **Visibilidad y Reubicación de la Biblioteca de Videos**: Se trasladó la "Biblioteca de Videos Generados" a la columna principal directamente debajo del botón de renderizado, resolviendo el problema donde quedaba oculta o cortada por el alto del teléfono.
- **Orden Cronológico y Nombres Identificables en la Biblioteca**:
  - Orden cronológico inverso estricto (`mtime` descendente) para mostrar siempre los videos más recién generados primero.
  - Títulos limpios y legibles para humanos (ej. `Salmos 23`, `Génesis 1`) en lugar de nombres de archivo crípticos.
  - Tarjetas de video enriquecidas con miniatura 9:16, insignia de duración (`15s`, `30s`, `1m 40s`), fecha formateada (`Hoy, 03:44`), peso en MB, botón para reproducir de inmediato dentro del teléfono y botón de descarga directa.
- **Miniaturas Rotas**: Generación de miniaturas `.jpg` optimizadas en `assets/thumbnails/` y `outputs/thumbnails/` para todos los videos e imágenes, eliminando los iconos de imagen rota en bucles `.mp4`.
- **Cierre Completo de Puertos Locales**: Detección y terminación sistemática de servidores de desarrollo huérfanos (puertos 8000, 4181-4189, etc.), asegurando un entorno limpio sin puertos residuales escuchando.

### Mejorado
- **Diseño Creative Suite (Menos "Vibe Coded")**: Rediseño visual integral con estética sobria y profesional inspirada en herramientas como Descript y Linear: paleta grafito oscuro (`#080a0f`), acentos dorados discretos, tipografías refinadas (*Plus Jakarta Sans* y *Cinzel*), y mockup móvil con notch dinámico y halo de luz ambiental.

---

## [1.0.0] - 2026-09-13

### Agregado
- **Extractor de Audio BibleGateway (`downloader.py`)**: Descarga y almacenamiento en caché de la narración de David Suchet para los 66 libros de la Biblia en versión NIV-UK.
- **Motor de Mezcla de Audio (`audio_engine.py`)**: Recorte de fragmentos, realce de voz (filtro pasa-altos + compresión de radiodifusión) y mezcla con música instrumental al 15-18% de volumen con *fade-in* y *fade-out*.
- **Motor de Subtítulos (`subtitles.py`)**: Generación de subtítulos `.ass` a 1080×1920 con 4 estilos predefinidos (Typewriter, SpokenByHim, ClassicSerif, ModernBold).
- **Motor de Video Vertical (`video_engine.py`)**: Composición 9:16 (1080×1920) a 30 FPS con esquinas redondeadas suaves, fondo ambiental desenfocado y viñeta.
- **Biblioteca de Recursos Iniciales**: Bucles de video (*The Good Shepherd*, *Cozy Cat*), obras del Met Museum y 3 pistas de música instrumental de adoración sintetizadas en alta definición.
- **Estudio Web FastAPI (`app.py`)**: Servidor local con interfaz gráfica, reproductor de audio, vista previa en smartphone y galería de videos generados.
- **Herramientas de Ejecución**: Script de inicio rápido `run.sh` y generador por línea de comandos `create_clip.py`.
