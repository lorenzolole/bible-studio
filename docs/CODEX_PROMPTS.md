# Prompts para Codex — assets del Jesus Edit

Pegá cada prompt en Codex por separado, dentro de este repo
(`/Users/lolescaldaferro/Antigravity/TikTokBible`). Están en inglés porque rinden
mejor para generación de imágenes. Codex puede leer el código, así que cada prompt
explica cómo se usa el asset y cómo validarlo.

La app levanta los assets nuevos sola: las figuras desde `assets/figures/` y las obras
desde `assets/visuals/`. Los nombres salen de `catalog.json` y las miniaturas se
generan automáticamente. No hace falta tocar código.

---

## Prompt 1 — Figuras de Jesús en primer plano (PNG con transparencia)

```text
You are working in the Bible Studio repo (FastAPI + FFmpeg app that renders 9:16 TikTok
videos of Bible passages narrated by David Suchet). Read CLAUDE.md, figures.py and
video_engine.py (search for "beat_montage" and "figure_layer") before starting.

GOAL
Create 8 foreground figures of Jesus for the "Jesus Edit" template. In that template,
classical artworks cut fast behind the figure on the music's beats, and the figure stays
in front, anchored to the bottom of the 1080x1920 frame at full width (1080 px).
figures.py adds a warm glow and fades the bottom edge automatically, so deliver the
figure only.

STYLE (match the existing art in assets/visuals/)
- Classical oil painting, Rembrandt-like chiaroscuro, warm golden key light, deep shadows,
  visible brushwork, reverent and dignified. Not photorealistic, not cartoon, not anime.
- Same likeness of Jesus in all 8 figures, matching assets/visuals/tiktok_pfp_jesus.jpg:
  shoulder-length dark brown hair, short beard, calm expression, cream/ivory robe
  (except where noted). A subtle thin golden halo is welcome.
- Look at assets/figures/jesus_claroscuro.png to see the current figure and how the
  cutout is used.

COMPOSITION (important for the video layout)
- Portrait canvas 1200x1500 px, PNG RGBA.
- Waist-up or chest-up, centered horizontally; the body is cut by the BOTTOM edge of the
  canvas (the bottom fade hides the cut). Keep hands and arms inside the canvas.
- Head in the upper 20-45% of the canvas, with 8-12% empty transparent space above the
  head (or halo).
- Fully transparent background (alpha 0) with clean, soft edges; preserve hair strands.
  No backdrop, no floor, no frame, no text, no watermark, no signature.

THE 8 FIGURES (file name -> description -> Spanish display name)
1. jesus_frontal_gaze.png -> frontal bust, looking straight at the viewer, gentle
   authority, soft halo -> "Mirada de frente"
2. jesus_looking_heaven.png -> 3/4 view looking up to heaven, light falling on the face
   from above -> "Mirando al cielo"
3. jesus_praying_hands.png -> eyes closed, hands joined in prayer at chest height ->
   "En oración"
4. jesus_crown_of_thorns.png -> crown of thorns, sorrowful, looking down, red cloak over
   the ivory robe, a few drops of blood on the forehead (restrained, not gory) ->
   "Corona de espinas"
5. jesus_open_arms.png -> waist-up, arms opened wide in welcome (hands inside the canvas;
   use a wider 1500x1500 canvas for this one) -> "Brazos abiertos"
6. jesus_profile_horizon.png -> side profile facing right, looking toward the horizon,
   wind in the hair -> "Perfil al horizonte"
7. jesus_good_shepherd_lamb.png -> waist-up, carrying a white lamb across the shoulders,
   holding its legs -> "Buen Pastor"
8. jesus_risen_blessing.png -> risen Christ in a radiant white robe, right hand raised in
   blessing, faint light rim around the body -> "Resucitado"

HOW TO DELIVER
- Save the PNGs in assets/figures/ with exactly those file names.
- Add each one to assets/figures/catalog.json, keeping the existing entry:
  "jesus_frontal_gaze.png": {"name": "Mirada de frente"}, ...
- If your image generator cannot output transparency, generate the figure on a plain dark
  or neutral background and cut it out with Apple Vision (same as "Copy Subject" in Photos):
  osascript -l JavaScript tools/lift_subject.js input.png assets/figures/<name>.png
  Check the edges afterwards (halo and hair). Only if that fails, fall back to the luminance
  cutout for pure-black backgrounds: python3 figures.py input.png assets/figures/<name>.png

VALIDATE BEFORE FINISHING (run this and fix anything it reports)
python3 - <<'EOF'
import json, os
from PIL import Image
import figures
cat = json.load(open("assets/figures/catalog.json"))
for name in sorted(os.listdir("assets/figures")):
    if not name.endswith(".png"):
        continue
    im = Image.open(os.path.join("assets/figures", name))
    assert im.mode == "RGBA", f"{name}: not RGBA"
    a = im.getchannel("A")
    w, h = im.size
    corners = [a.getpixel(p) for p in [(0, 0), (w - 1, 0), (0, h // 2), (w - 1, h // 2)]]
    bottom_opaque = sum(1 for x in range(w) if a.getpixel((x, h - 1)) > 200) / w
    print(f"{name}: {w}x{h} corners={corners} bottom_opaque={bottom_opaque:.0%} in_catalog={name in cat}")
    assert max(corners) < 10, f"{name}: background is not transparent"
    assert name in cat, f"{name}: missing from catalog.json"
    figures.figure_layer(os.path.join("assets/figures", name), 1080)
print("OK")
EOF

Then start the app (./run.sh), pick "Jesus Edit" in step 03, select each new figure and
check the phone preview: edges must look clean over bright and dark backgrounds.
Do not modify any Python, JS, HTML or CSS file.
```

---

## Prompt 2 — Obras de fondo para el montaje (9:16)

```text
You are working in the Bible Studio repo (FastAPI + FFmpeg app that renders 9:16 TikTok
videos of Bible passages). Read CLAUDE.md, then app.py (function get_presets) and
video_engine.py (search for "_montage_segment") before starting.

GOAL
Create 16 new background artworks for the "Jesus Edit" template. In that template these
images cut fast on the music's beats (a 12% punch-in zoom each, sometimes a white flash)
BEHIND a foreground figure of Jesus that covers roughly the lower 55% of the frame.
They are also usable on their own in the other templates.

STYLE (match the existing art in assets/visuals/, look at several of them first)
- Epic classical oil painting: dramatic chiaroscuro, golden divine light, deep blues and
  warm ambers, visible brushwork, reverent. Think Rembrandt, Gustave Doré, John Martin.
- High contrast with ONE clear focal point in the center or upper half of the image
  (the lower half will be covered by the figure).
- Jesus must NOT be the main subject (the figure in front is Jesus). Tiny distant
  silhouettes are fine.
- No text, letters, watermarks, signatures or painted frames.

FORMAT
- Exactly 1080x1920 px (9:16 portrait), JPG quality 90, sRGB.
  Generate larger if needed and downscale/crop to exactly 1080x1920.

THE 16 ARTWORKS (file name -> description -> Spanish display name)
1.  golgotha_three_crosses.jpg -> three crosses silhouetted on Golgotha hill against a
    blood-orange storm sky -> "Gólgota al atardecer"
2.  empty_tomb_dawn.jpg -> the empty tomb, stone rolled away, rays of dawn pouring out ->
    "Tumba vacía al amanecer"
3.  galilee_storm_lightning.jpg -> huge waves on the Sea of Galilee, a small fishing boat,
    lightning splitting the sky -> "Tormenta en Galilea"
4.  jerusalem_night_lamps.jpg -> ancient Jerusalem at night, oil lamps glowing, temple on
    the hill under the stars -> "Jerusalén de noche"
5.  heaven_light_clouds.jpg -> heavenly light breaking through towering clouds, god rays
    -> "Luz del cielo"
6.  angels_descending_gold.jpg -> angels descending a golden staircase of light (Jacob's
    ladder) -> "Escalera de Jacob"
7.  burning_bush_sinai.jpg -> the burning bush on a dark mountainside, flames that do not
    consume -> "Zarza ardiente"
8.  noah_ark_rainbow.jpg -> Noah's ark on a dark sea after the storm, a rainbow over it ->
    "Arca de Noé"
9.  gethsemane_olive_moon.jpg -> ancient twisted olive trees of Gethsemane under moonlight,
    no people in focus -> "Olivos de Getsemaní"
10. last_supper_candles.jpg -> the Last Supper table seen close: bread, cup of wine,
    candles, hands only, warm light -> "La Última Cena"
11. star_bethlehem_hills.jpg -> the star of Bethlehem shining over dark hills and a tiny
    village -> "Estrella de Belén"
12. dove_jordan_river.jpg -> a white dove descending in a column of light over the Jordan
    river -> "Paloma sobre el Jordán"
13. sinai_tablets_glow.jpg -> the stone tablets of the Law glowing on top of Mount Sinai
    amid lightning -> "Tablas en el Sinaí"
14. elijah_chariot_fire.jpg -> Elijah's chariot of fire rising into a whirlwind in the sky
    -> "Carro de fuego"
15. lion_and_lamb.jpg -> a lion and a lamb resting together in a golden meadow at sunrise
    -> "El león y el cordero"
16. scroll_candlelight.jpg -> an ancient scroll of Scripture open by candlelight, dark
    still life -> "Pergamino a la luz de la vela"

HOW TO DELIVER
- Save the images in assets/visuals/ with exactly those file names. The app picks up new
  files automatically and generates thumbnails.
- Create or extend assets/visuals/catalog.json with one entry per file:
  "golgotha_three_crosses.jpg": {"name": "Gólgota al atardecer", "category": "Montaje"}, ...
- In app.py, inside get_presets(), add ONE collection to the `collections` list, following
  the format of the existing entries exactly:
  id "col_jesus_edit_montage", name "Jesus Edit: Gloria y Tormenta", a one-line Spanish
  description, "paths" = the 16 new images as "assets/visuals/<file>", and
  "thumb" = "/thumbnails/golgotha_three_crosses.jpg".
  This is the only code change allowed.

VALIDATE BEFORE FINISHING
python3 - <<'EOF'
import json, os
from PIL import Image
cat = json.load(open("assets/visuals/catalog.json"))
for name, meta in cat.items():
    path = os.path.join("assets/visuals", name)
    im = Image.open(path)
    print(name, im.size, im.mode, meta)
    assert im.size == (1080, 1920), f"{name}: must be 1080x1920"
    assert im.mode == "RGB", f"{name}: must be RGB JPG"
print("OK", len(cat), "artworks")
EOF
python3 -m py_compile app.py

Then start the app (./run.sh), choose "Jesus Edit", open "Colecciones Temáticas", select
the new collection and watch the phone preview. Every image must read clearly in a
0.5-second cut and leave its focal point visible above the figure.
```
