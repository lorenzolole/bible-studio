# AGENTS.md — Bible Studio

Instrucciones para agentes (Codex y otros). La documentación técnica completa está en
`CLAUDE.md` y el historial en `CHANGELOG.md`: leelos antes de cambiar nada.

## Reglas rápidas
- Idioma con el usuario (Lole): español rioplatense, directo y conciso.
- Uso principal: local (`./run.sh`, puerto 8000). Render (plan gratuito, 512 MB) es secundario,
  pero el código tiene que seguir entrando en 512 MB.
- Cambios en `video_engine.py`: medir memoria antes de commitear (`/usr/bin/time -l ffmpeg ...`).
  Fuentes de video siempre como filtros `movie=`, nunca como entradas `-i` (ver comentarios en el archivo).
- No recalcular transcripciones: `assets/transcripts/` (617 capítulos) ya está alineado con el texto NIV-UK.
- Assets nuevos sin tocar código: figuras en `assets/figures/` + `catalog.json`, obras en
  `assets/visuals/` + `catalog.json`. Prompts de generación: `docs/CODEX_PROMPTS.md`.
- Verificar antes de terminar: `python3 -m py_compile *.py` y `node --check static/app.js`.
- Deploy: `git push origin main` dispara Render. Confirmar con Lole antes de pushear.
