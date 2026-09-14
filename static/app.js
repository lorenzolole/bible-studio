// TikTok Bible Studio — Creative Suite Controller

let state = {
    books: [],
    selectedBook: null,
    selectedChapter: 1,
    audioDuration: 0,
    selectedVisual: null,
    selectedVisuals: [],
    selectedCollection: null,
    isSlideshowMode: false,
    isMultiSelect: false,
    selectedMusic: null,
    musicVolume: 0.16,
    subtitleStyle: "typewriter",
    subtitlePosition: "bottom",
    textCase: "original",
    enableSubtitles: true,
    frameStyle: "vintage",
    cornerRadius: 42,
    slideshowPacing: "cinematic",
    framingMode: "pitch_black",
    phrases: [],
    passageText: "",
    watermark: ""
};

let musicPreviewAudio = new Audio();
let currentPreviewBtn = null;

// DOM Cache
const bookSelect = document.getElementById("bookSelect");
const chapterSelect = document.getElementById("chapterSelect");
const btnLoadChapter = document.getElementById("btnLoadChapter");
const audioPlayerArea = document.getElementById("audioPlayerArea");
const mainAudio = document.getElementById("mainAudio");
const audioSpeakerTitle = document.getElementById("audioSpeakerTitle");
const currentTimeDisplay = document.getElementById("currentTimeDisplay");
const totalDurationDisplay = document.getElementById("totalDurationDisplay");

const timelineTrack = document.getElementById("timelineTrack");
const timelineActiveRange = document.getElementById("timelineActiveRange");
const timelinePlayhead = document.getElementById("timelinePlayhead");
const handleStart = document.getElementById("handleStart");
const handleEnd = document.getElementById("handleEnd");
const tooltipStart = document.getElementById("tooltipStart");
const tooltipEnd = document.getElementById("tooltipEnd");
const timelineHoverTime = document.getElementById("timelineHoverTime");
const timelineMidTime = document.getElementById("timelineMidTime");
const timelineTotalTime = document.getElementById("timelineTotalTime");

const startSecInput = document.getElementById("startSecInput");
const endSecInput = document.getElementById("endSecInput");
const btnStartMinus = document.getElementById("btnStartMinus");
const btnStartPlus = document.getElementById("btnStartPlus");
const btnEndMinus = document.getElementById("btnEndMinus");
const btnEndPlus = document.getElementById("btnEndPlus");
const btnSetStart = document.getElementById("btnSetStart");
const btnSetEnd = document.getElementById("btnSetEnd");
const btnPlayTrimmed = document.getElementById("btnPlayTrimmed");
const clipDurationBadge = document.getElementById("clipDurationBadge");
const spokenScriptBox = document.getElementById("spokenScriptBox");
const spokenScriptText = document.getElementById("spokenScriptText");
const spokenWordsBadge = document.getElementById("spokenWordsBadge");

const btnTogglePassage = document.getElementById("btnTogglePassage");
const passageContentArea = document.getElementById("passageContentArea");
const passageChevron = document.getElementById("passageChevron");
const passageTextContainer = document.getElementById("passageTextContainer");
const verseSearchInput = document.getElementById("verseSearchInput");
const passagePhrasesInteractive = document.getElementById("passagePhrasesInteractive");

const subtitlesToggle = document.getElementById("subtitlesToggle");
const subtitlesToggleText = document.getElementById("subtitlesToggleText");
const citationInput = document.getElementById("citationInput");
const btnAutoTranscribe = document.getElementById("btnAutoTranscribe");
const transcribeStatus = document.getElementById("transcribeStatus");
const phrasesListContainer = document.getElementById("phrasesListContainer");

const visualsGrid = document.getElementById("visualsGrid");
const collectionsGrid = document.getElementById("collectionsGrid");
const visualUploadInput = document.getElementById("visualUploadInput");
const chkMultiSelectVisuals = document.getElementById("chkMultiSelectVisuals");
const multiSelectCountBadge = document.getElementById("multiSelectCountBadge");
const radiusSlider = document.getElementById("radiusSlider");
const radiusVal = document.getElementById("radiusVal");
const watermarkInput = document.getElementById("watermarkInput");

const musicGrid = document.getElementById("musicGrid");
const musicUploadInput = document.getElementById("musicUploadInput");
const volumeSlider = document.getElementById("volumeSlider");
const volumeVal = document.getElementById("volumeVal");
const activeMusicBar = document.getElementById("activeMusicBar");
const activeMusicName = document.getElementById("activeMusicName");
const activeMusicVolBadge = document.getElementById("activeMusicVolBadge");

const btnRenderVideo = document.getElementById("btnRenderVideo");
const renderStatus = document.getElementById("renderStatus");
const renderStatusText = document.getElementById("renderStatusText");
const renderStatusSub = document.getElementById("renderStatusSub");
const renderSpinner = document.getElementById("renderSpinner");
const renderSuccessIcon = document.getElementById("renderSuccessIcon");

const previewBg = document.getElementById("previewBg");
const previewFgBox = document.getElementById("previewFgBox");
const previewImage = document.getElementById("previewImage");
const previewVideo = document.getElementById("previewVideo");
const previewCaptionText = document.getElementById("previewCaptionText");
const previewCitationText = document.getElementById("previewCitationText");
const previewWatermark = document.getElementById("previewWatermark");
const renderedVideoPlayer = document.getElementById("renderedVideoPlayer");
const downloadArea = document.getElementById("downloadArea");
const btnDownload = document.getElementById("btnDownload");
const historyList = document.getElementById("historyList");

// 1. BOOTSTRAP
async function init() {
    await loadBooks();
    await loadPresets();
    await loadHistory();
    setupEventListeners();

    // Default to Psalms 23 and Pitch Black framing (@nehzro)
    const phoneMockup = document.querySelector(".phone-mockup");
    if (phoneMockup) phoneMockup.classList.add("framing-pitch_black");
    selectBookByName("Salmos");
    chapterSelect.value = "23";
    loadChapterAudio();
}

// 2. BOOKS & CHAPTERS
async function loadBooks() {
    try {
        const res = await fetch("/api/books");
        const data = await res.json();
        state.books = data.books;

        bookSelect.innerHTML = "";
        state.books.forEach(b => {
            const opt = document.createElement("option");
            opt.value = b.osis;
            opt.textContent = `${b.name_es} — ${b.name_en}`;
            bookSelect.appendChild(opt);
        });

        bookSelect.addEventListener("change", () => {
            const book = state.books.find(b => b.osis === bookSelect.value);
            if (book) updateChapterDropdown(book);
        });

        updateChapterDropdown(state.books[0]);
    } catch (e) {
        console.error("Error loading books:", e);
    }
}

function selectBookByName(name) {
    const b = state.books.find(x => x.name_es.toLowerCase() === name.toLowerCase() || x.osis.toLowerCase() === name.toLowerCase());
    if (b) {
        bookSelect.value = b.osis;
        updateChapterDropdown(b);
    }
}

function updateChapterDropdown(book) {
    state.selectedBook = book;
    chapterSelect.innerHTML = "";
    for (let i = 1; i <= book.chapters; i++) {
        const opt = document.createElement("option");
        opt.value = i;
        opt.textContent = `Capítulo ${i}`;
        chapterSelect.appendChild(opt);
    }
}

// 3. AUDIO LOADING & AUTO DURATION
let currentChapterPhrases = [];

async function loadChapterAudio(customStart = null, customEnd = null, customCitation = null) {
    const bookOsis = bookSelect.value;
    const chapter = parseInt(chapterSelect.value);

    btnLoadChapter.disabled = true;
    btnLoadChapter.innerHTML = "Descargando...";

    // Clear stale phrases immediately
    state.phrases = [];
    renderPhrasesList();
    if (spokenScriptText) {
        spokenScriptText.innerHTML = `<span class="loading-pulse">🪄 Cargando audio y sincronizando pasaje...</span>`;
    }

    try {
        const res = await fetch(`/api/chapter_info?book=${bookOsis}&chapter=${chapter}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.detail || "Error loading audio");

        mainAudio.src = data.audio_url;
        state.audioDuration = data.duration;
        audioPlayerArea.classList.remove("hidden");
        audioSpeakerTitle.textContent = `${data.book.name_es} ${chapter} — David Suchet (NIV-UK)`;
        
        if (customCitation && typeof customCitation === "string") {
            citationInput.value = customCitation;
            previewCitationText.textContent = `— ${customCitation.toUpperCase()} —`;
        } else {
            citationInput.value = `${data.book.name_en.toUpperCase()} ${chapter}`;
            previewCitationText.textContent = `— ${citationInput.value} —`;
        }

        // Populate passage reader drawer
        state.passageText = (data.passage && data.passage.text) ? data.passage.text : "";
        if (passageTextContainer) {
            passageTextContainer.textContent = state.passageText || "Texto bíblico no disponible para este capítulo.";
        }
        if (passageAccordionTitle) {
            passageAccordionTitle.textContent = `Leer Texto: ${data.book.name_es} ${chapter} (NIV-UK)`;
        }

        // Scale indicators
        if (timelineMidTime) timelineMidTime.textContent = formatSec(data.duration / 2);
        if (timelineTotalTime) timelineTotalTime.textContent = formatSec(data.duration);

        // Auto-set duration: Custom viral bounds or default 15s
        const hasCustom = (typeof customStart === "number" || (typeof customStart === "string" && !isNaN(parseFloat(customStart))));
        if (hasCustom && customEnd !== null && !isNaN(parseFloat(customEnd))) {
            startSecInput.value = parseFloat(customStart).toFixed(1);
            endSecInput.value = Math.min(parseFloat(customEnd), data.duration).toFixed(1);
        } else {
            startSecInput.value = (0.0).toFixed(1);
            endSecInput.value = Math.min(15.0, data.duration).toFixed(1);
        }
        updateActiveRangeVisual();
        updateDurationBadge();

        // Auto-transcribe the selected segment
        autoTranscribeCurrentSegment();

        // Load interactive chapter transcription for instant phrase snapping
        loadChapterTranscript(bookOsis, chapter);

    } catch (e) {
        alert("Error cargando capítulo: " + e.message);
    } finally {
        btnLoadChapter.disabled = false;
        btnLoadChapter.innerHTML = "Cargar Audio";
    }
}

async function loadChapterTranscript(bookOsis, chapter) {
    if (!passagePhrasesInteractive) return;
    passagePhrasesInteractive.innerHTML = `<div class="p-2 text-muted text-xs">Cargando transcripción con marcas de tiempo...</div>`;
    try {
        const res = await fetch(`/api/chapter_transcription?book=${bookOsis}&chapter=${chapter}`);
        const data = await res.json();
        if (data.success && data.phrases && data.phrases.length > 0) {
            currentChapterPhrases = data.phrases;
            renderInteractivePhrases(currentChapterPhrases);
        } else {
            passagePhrasesInteractive.innerHTML = `<div class="p-2 text-muted text-xs">Marcas de tiempo no disponibles para este capítulo.</div>`;
        }
    } catch (e) {
        console.warn("Could not load chapter transcription:", e);
    }
}

function renderInteractivePhrases(phrases) {
    if (!passagePhrasesInteractive) return;
    passagePhrasesInteractive.innerHTML = "";
    if (!phrases || phrases.length === 0) {
        passagePhrasesInteractive.innerHTML = `<div class="p-2 text-muted text-xs">No se encontraron frases.</div>`;
        return;
    }
    phrases.forEach(p => {
        const row = document.createElement("div");
        row.className = "passage-phrase-row";
        row.innerHTML = `
            <span>${escapeHtml(p.text)}</span>
            <span class="passage-phrase-time">${formatSec(p.start)} - ${formatSec(p.end)}</span>
        `;
        row.onclick = () => {
            document.querySelectorAll(".passage-phrase-row").forEach(r => r.classList.remove("active"));
            row.classList.add("active");
            startSecInput.value = p.start.toFixed(1);
            endSecInput.value = p.end.toFixed(1);
            updateActiveRangeVisual();
            updateDurationBadge();
            mainAudio.currentTime = p.start;
            scheduleSegmentTranscribe(0);
        };
        passagePhrasesInteractive.appendChild(row);
    });
}

// 4. SUBTITLES & AI WHISPER TRANSCRIPTION
let transcribeDebounceTimer = null;
let transcribeAbortController = null;

// Identifies this tab so the server can skip queued Whisper work for clips we already moved away from
const CLIENT_ID = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function escapeHtml(text) {
    return String(text ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function scheduleSegmentTranscribe(delay = 500) {
    if (transcribeDebounceTimer) clearTimeout(transcribeDebounceTimer);
    if (spokenScriptText) {
        spokenScriptText.innerHTML = `<span class="loading-pulse">🪄 Sincronizando palabras con David Suchet...</span>`;
    }
    if (delay === 0) {
        autoTranscribeCurrentSegment();
    } else {
        transcribeDebounceTimer = setTimeout(() => {
            autoTranscribeCurrentSegment();
        }, delay);
    }
}

function updateSpokenScriptPreview() {
    if (!spokenScriptText) return;

    if (!state.phrases || state.phrases.length === 0) {
        spokenScriptText.innerHTML = `<span class="text-muted">No se detectaron palabras en este fragmento.</span>`;
        if (spokenWordsBadge) spokenWordsBadge.textContent = "0 palabras";
        return;
    }

    const fullText = state.phrases.map(p => p.text ? p.text.trim() : "").filter(Boolean).join(" ");
    const words = fullText.length > 0 ? fullText.split(/\s+/).filter(Boolean).length : 0;

    spokenScriptText.textContent = `“${fullText}”`;
    if (spokenWordsBadge) {
        spokenWordsBadge.textContent = `${words} palabra${words === 1 ? '' : 's'}`;
    }
}

async function autoTranscribeCurrentSegment() {
    const start = parseFloat(startSecInput.value) || 0;
    const end = parseFloat(endSecInput.value) || 15;

    // Abort any ongoing in-flight request to avoid race conditions and stale text overwrites
    if (transcribeAbortController) {
        transcribeAbortController.abort();
    }
    transcribeAbortController = new AbortController();
    const currentSignal = transcribeAbortController.signal;

    transcribeStatus.textContent = "Sincronizando con Whisper AI...";
    if (spokenScriptText) {
        spokenScriptText.innerHTML = `<span class="loading-pulse">🪄 Sincronizando palabras con David Suchet...</span>`;
    }
    btnAutoTranscribe.disabled = true;

    try {
        const res = await fetch("/api/transcribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: currentSignal,
            body: JSON.stringify({
                book: bookSelect.value,
                chapter: parseInt(chapterSelect.value),
                start_sec: start,
                end_sec: end,
                client_id: CLIENT_ID
            })
        });

        const data = await res.json();
        if (data.superseded) return; // A newer clip request from this tab replaced it
        if (!data.success) throw new Error("Error en transcripción");

        state.phrases = data.phrases || [];
        renderPhrasesList();
        updateSpokenScriptPreview();
        transcribeStatus.textContent = `${state.phrases.length} frases sincronizadas${data.source === "chapter" ? " · instantáneo" : ""}`;
        
        if (state.phrases.length > 0) {
            previewCaptionText.textContent = state.phrases[0].text;
        }

    } catch (e) {
        if (e.name === "AbortError") {
            // Superseded by newer request, cleanly ignore
            return;
        }
        console.error("Transcription error:", e);
        transcribeStatus.textContent = "Error de sincronización";
        updateSpokenScriptPreview();
    } finally {
        btnAutoTranscribe.disabled = false;
    }
}

function renderPhrasesList() {
    if (!state.phrases || state.phrases.length === 0) {
        phrasesListContainer.innerHTML = `<p class="empty-phrases-notice">No se detectaron frases.</p>`;
        return;
    }

    phrasesListContainer.innerHTML = "";
    state.phrases.forEach((p, idx) => {
        const row = document.createElement("div");
        row.className = "phrase-row-item";
        row.innerHTML = `
            <span class="phrase-timestamp">${p.start.toFixed(1)}s - ${p.end.toFixed(1)}s</span>
            <input type="text" class="phrase-text-input" value="${escapeHtml(p.text)}">
        `;
        const input = row.querySelector(".phrase-text-input");
        input.addEventListener("input", (e) => {
            state.phrases[idx].text = e.target.value;
            if (idx === 0) previewCaptionText.textContent = e.target.value;
            updateSpokenScriptPreview();
        });
        phrasesListContainer.appendChild(row);
    });
}

// 5. PRESETS (VISUALS & MUSIC)
async function loadPresets() {
    try {
        const res = await fetch("/api/presets");
        const data = await res.json();

        // Visuals
        visualsGrid.innerHTML = "";
        data.visuals.forEach((v, idx) => {
            const card = document.createElement("div");
            card.className = `visual-item-card ${idx === 0 ? "selected" : ""}`;
            card.dataset.id = v.id;
            card.innerHTML = `
                <img src="${v.thumb}" class="visual-thumb" alt="${v.name}" loading="lazy">
                <div class="visual-meta">${v.name}</div>
            `;
            card.onclick = () => selectVisual(v, card);
            visualsGrid.appendChild(card);

            if (idx === 0) selectVisual(v, card);
        });

        // Collections (Slideshows)
        collectionsGrid.innerHTML = "";
        data.collections.forEach((c, idx) => {
            const card = document.createElement("div");
            card.className = "collection-card";
            card.innerHTML = `
                <div class="collection-title">${c.name}</div>
                <div class="collection-desc">${c.description}</div>
            `;
            card.onclick = () => selectCollection(c, card);
            collectionsGrid.appendChild(card);
        });

        // Music
        musicGrid.innerHTML = "";
        
        // 1. "Sin Música" option card (First choice)
        const noMusicCard = document.createElement("div");
        noMusicCard.className = "music-item-card no-music";
        noMusicCard.innerHTML = `
            <div class="music-card-main">
                <span class="music-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"></line><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4h5v4"></path></svg>
                </span>
                <span class="music-name">Sin Música (Solo Voz)</span>
            </div>
        `;
        noMusicCard.onclick = () => selectNoMusic(noMusicCard);
        musicGrid.appendChild(noMusicCard);

        // 2. Preset music tracks with preview button
        data.music.forEach((m, idx) => {
            const card = document.createElement("div");
            card.className = "music-item-card";
            card.innerHTML = `
                <div class="music-card-main">
                    <span class="music-icon">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
                    </span>
                    <span class="music-name">${m.name}</span>
                    <span class="music-check-indicator">Activa ✓</span>
                </div>
                <button type="button" class="btn-music-preview" title="Preescuchar pista">
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                </button>
            `;
            
            const previewBtn = card.querySelector(".btn-music-preview");
            previewBtn.onclick = (e) => {
                e.stopPropagation();
                toggleMusicPreview(m, previewBtn, card);
            };

            card.onclick = () => selectMusic(m, card);
            musicGrid.appendChild(card);

            // Default: select the first ambient track
            if (idx === 0) {
                selectMusic(m, card);
            }
        });

    } catch (e) {
        console.error("Error loading presets:", e);
    }
}

function selectNoMusic(cardElement) {
    state.selectedMusic = null;
    stopMusicPreview();

    document.querySelectorAll(".music-item-card").forEach(c => c.classList.remove("selected"));
    if (cardElement) cardElement.classList.add("selected");

    if (volumeSlider) volumeSlider.disabled = true;
    if (volumeVal) volumeVal.textContent = "Silenciado";

    if (activeMusicName) activeMusicName.textContent = "Sin Música (Solo Voz Suchet)";
    if (activeMusicVolBadge) activeMusicVolBadge.textContent = "Silenciado";
}

function selectMusic(m, cardElement) {
    state.selectedMusic = m;
    document.querySelectorAll(".music-item-card").forEach(c => c.classList.remove("selected"));
    if (cardElement) cardElement.classList.add("selected");

    if (volumeSlider) volumeSlider.disabled = false;
    if (volumeVal) volumeVal.textContent = `${Math.round(state.musicVolume * 100)}%`;

    if (activeMusicName) activeMusicName.textContent = m.name;
    if (activeMusicVolBadge) activeMusicVolBadge.textContent = `${Math.round(state.musicVolume * 100)}%`;
}

function toggleMusicPreview(m, btnElement, cardElement = null) {
    // Automatically select the track being previewed
    if (cardElement) {
        selectMusic(m, cardElement);
    }

    if (currentPreviewBtn === btnElement) {
        stopMusicPreview();
    } else {
        stopMusicPreview();
        musicPreviewAudio.src = m.url;
        musicPreviewAudio.volume = Math.max(0.1, state.musicVolume);
        musicPreviewAudio.play().catch(() => {});
        btnElement.innerHTML = `<svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="4" width="4" height="16"></rect><rect x="15" y="4" width="4" height="16"></rect></svg>`;
        btnElement.classList.add("playing");
        currentPreviewBtn = btnElement;

        musicPreviewAudio.onended = () => {
            stopMusicPreview();
        };
    }
}

function stopMusicPreview() {
    if (musicPreviewAudio) {
        musicPreviewAudio.pause();
        musicPreviewAudio.currentTime = 0;
    }
    if (currentPreviewBtn) {
        currentPreviewBtn.innerHTML = `<svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
        currentPreviewBtn.classList.remove("playing");
        currentPreviewBtn = null;
    }
}

function selectVisual(v, cardElement) {
    if (state.isMultiSelect) {
        state.selectedCollection = null;
        document.querySelectorAll(".collection-card").forEach(c => c.classList.remove("selected"));

        const idx = state.selectedVisuals.findIndex(item => item.id === v.id);
        if (idx >= 0) {
            state.selectedVisuals.splice(idx, 1);
            if (cardElement) cardElement.classList.remove("multi-selected", "selected");
        } else {
            state.selectedVisuals.push(v);
            if (cardElement) cardElement.classList.add("multi-selected", "selected");
        }

        updateMultiSelectUI();

        if (state.selectedVisuals.length > 0) {
            state.isSlideshowMode = state.selectedVisuals.length > 1;
            const last = state.selectedVisuals[state.selectedVisuals.length - 1];
            state.selectedVisual = last;
            previewBg.style.backgroundImage = `url('${last.thumb || last.url}')`;
            previewImage.src = last.url;
            previewImage.classList.remove("hidden");
            previewVideo.classList.add("hidden");
            applyFrameStyleToMockup();
        }
        return;
    }

    state.isSlideshowMode = false;
    state.selectedVisual = v;
    state.selectedVisuals = [v];
    state.selectedCollection = null;

    document.querySelectorAll(".visual-item-card").forEach(c => c.classList.remove("selected", "multi-selected"));
    document.querySelectorAll(".collection-card").forEach(c => c.classList.remove("selected"));
    if (cardElement) cardElement.classList.add("selected");

    previewBg.style.backgroundImage = `url('${v.thumb || v.url}')`;
    applyFrameStyleToMockup();

    if (v.type === "video") {
        previewImage.classList.add("hidden");
        previewVideo.classList.remove("hidden");
        previewVideo.src = v.url;
        previewVideo.play().catch(() => {});
    } else {
        previewVideo.classList.add("hidden");
        previewImage.classList.remove("hidden");
        previewImage.src = v.url;
    }
    updatePacingVisibility();
}

function updatePacingVisibility() {
    const pacingBox = document.getElementById("slideshowPacingContainer");
    if (!pacingBox) return;
    const isMulti = state.isSlideshowMode || (state.isMultiSelect && state.selectedVisuals && state.selectedVisuals.length > 1);
    if (isMulti) {
        pacingBox.classList.remove("hidden");
    } else {
        pacingBox.classList.add("hidden");
    }
}

function updateMultiSelectUI() {
    if (!multiSelectCountBadge) return;
    const count = state.selectedVisuals ? state.selectedVisuals.length : 0;
    if (count > 0 && state.isMultiSelect) {
        multiSelectCountBadge.textContent = `${count} ${count === 1 ? 'obra' : 'obras'}`;
        multiSelectCountBadge.classList.remove("hidden");
    } else {
        multiSelectCountBadge.classList.add("hidden");
    }
    updatePacingVisibility();
}

function selectCollection(c, cardElement) {
    state.isSlideshowMode = true;
    state.selectedCollection = c;
    state.selectedVisual = null;
    state.selectedVisuals = [];
    if (chkMultiSelectVisuals) chkMultiSelectVisuals.checked = false;
    state.isMultiSelect = false;
    updateMultiSelectUI();

    document.querySelectorAll(".visual-item-card").forEach(x => x.classList.remove("selected", "multi-selected"));
    document.querySelectorAll(".collection-card").forEach(x => x.classList.remove("selected"));
    if (cardElement) cardElement.classList.add("selected");

    previewBg.style.backgroundImage = `url('${c.thumb}')`;
    applyFrameStyleToMockup();

    previewVideo.classList.add("hidden");
    previewImage.classList.remove("hidden");
    previewImage.src = c.thumb;
}

function applyFrameStyleToMockup() {
    if (previewFgBox) {
        previewFgBox.className = `phone-media-frame frame-${state.frameStyle || "vintage"}`;
    }
}

let stopAtEndHandler = null;

function toggleTrimmedPlayback() {
    if (!mainAudio.src) return;
    const start = parseFloat(startSecInput.value) || 0;
    const end = parseFloat(endSecInput.value) || 15;

    if (!mainAudio.paused) {
        mainAudio.pause();
    } else {
        if (stopAtEndHandler) {
            mainAudio.removeEventListener("timeupdate", stopAtEndHandler);
            stopAtEndHandler = null;
        }

        if (mainAudio.currentTime < start || mainAudio.currentTime >= end) {
            mainAudio.currentTime = start;
        }
        mainAudio.play().catch(() => {});

        stopAtEndHandler = () => {
            if (mainAudio.currentTime >= end) {
                mainAudio.pause();
                mainAudio.removeEventListener("timeupdate", stopAtEndHandler);
                stopAtEndHandler = null;
            }
        };
        mainAudio.addEventListener("timeupdate", stopAtEndHandler);
    }
}

// INTERACTIVE DUAL-HANDLE DRAG SCRUBBER
function setupTimelineDraggers() {
    if (!timelineTrack || !timelineActiveRange) return;

    let activeDrag = null; // 'start', 'end', 'range'
    let dragStartX = 0;
    let initialStart = 0;
    let initialEnd = 0;
    let initialDuration = 0;

    function getSecFromClientX(clientX) {
        if (!state.audioDuration) return 0;
        const rect = timelineTrack.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        return ratio * state.audioDuration;
    }

    // 1. Handle Start (Drag to change start time)
    if (handleStart) {
        const onStartDrag = (clientX) => {
            activeDrag = 'start';
            handleStart.classList.add("is-dragging");
            timelineActiveRange.classList.add("is-dragging");
            document.body.style.cursor = "ew-resize";
        };

        handleStart.addEventListener("mousedown", (e) => {
            e.stopPropagation();
            e.preventDefault();
            onStartDrag(e.clientX);
        });

        handleStart.addEventListener("touchstart", (e) => {
            e.stopPropagation();
            if (e.touches.length > 0) onStartDrag(e.touches[0].clientX);
        }, { passive: false });
    }

    // 2. Handle End (Drag to change end time)
    if (handleEnd) {
        const onEndDrag = (clientX) => {
            activeDrag = 'end';
            handleEnd.classList.add("is-dragging");
            timelineActiveRange.classList.add("is-dragging");
            document.body.style.cursor = "ew-resize";
        };

        handleEnd.addEventListener("mousedown", (e) => {
            e.stopPropagation();
            e.preventDefault();
            onEndDrag(e.clientX);
        });

        handleEnd.addEventListener("touchstart", (e) => {
            e.stopPropagation();
            if (e.touches.length > 0) onEndDrag(e.touches[0].clientX);
        }, { passive: false });
    }

    // 3. Drag Selection Window (Slide entire range across the chapter)
    timelineActiveRange.addEventListener("mousedown", (e) => {
        if (e.target === handleStart || e.target === handleEnd || (handleStart && handleStart.contains(e.target)) || (handleEnd && handleEnd.contains(e.target))) return;
        e.stopPropagation();
        e.preventDefault();
        activeDrag = 'range';
        dragStartX = e.clientX;
        initialStart = parseFloat(startSecInput.value) || 0;
        initialEnd = parseFloat(endSecInput.value) || 15;
        initialDuration = Math.max(1, initialEnd - initialStart);
        timelineActiveRange.classList.add("is-dragging");
        document.body.style.cursor = "grabbing";
    });

    timelineActiveRange.addEventListener("touchstart", (e) => {
        if (e.touches.length === 0) return;
        const target = e.target;
        if (target === handleStart || target === handleEnd || (handleStart && handleStart.contains(target)) || (handleEnd && handleEnd.contains(target))) return;
        e.stopPropagation();
        activeDrag = 'range';
        dragStartX = e.touches[0].clientX;
        initialStart = parseFloat(startSecInput.value) || 0;
        initialEnd = parseFloat(endSecInput.value) || 15;
        initialDuration = Math.max(1, initialEnd - initialStart);
        timelineActiveRange.classList.add("is-dragging");
    }, { passive: false });

    // Global Move & Up Listeners
    const onPointerMove = (clientX) => {
        if (!activeDrag || !state.audioDuration) return;

        const currentEnd = parseFloat(endSecInput.value) || 15;
        const currentStart = parseFloat(startSecInput.value) || 0;

        if (activeDrag === 'start') {
            const sec = getSecFromClientX(clientX);
            const clamped = Math.max(0, Math.min(currentEnd - 0.5, sec));
            startSecInput.value = clamped.toFixed(1);
            if (tooltipStart) tooltipStart.textContent = formatSec(clamped);
            updateActiveRangeVisual();
            updateDurationBadge();
            mainAudio.currentTime = clamped;
        } else if (activeDrag === 'end') {
            const sec = getSecFromClientX(clientX);
            const clamped = Math.max(currentStart + 0.5, Math.min(state.audioDuration, sec));
            endSecInput.value = clamped.toFixed(1);
            if (tooltipEnd) tooltipEnd.textContent = formatSec(clamped);
            updateActiveRangeVisual();
            updateDurationBadge();
        } else if (activeDrag === 'range') {
            const rect = timelineTrack.getBoundingClientRect();
            const deltaSec = ((clientX - dragStartX) / rect.width) * state.audioDuration;
            let newStart = initialStart + deltaSec;
            newStart = Math.max(0, Math.min(state.audioDuration - initialDuration, newStart));
            let newEnd = newStart + initialDuration;

            startSecInput.value = newStart.toFixed(1);
            endSecInput.value = newEnd.toFixed(1);
            if (tooltipStart) tooltipStart.textContent = formatSec(newStart);
            if (tooltipEnd) tooltipEnd.textContent = formatSec(newEnd);
            updateActiveRangeVisual();
            updateDurationBadge();
            mainAudio.currentTime = newStart;
        }
    };

    const onPointerUp = () => {
        if (!activeDrag) return;
        activeDrag = null;
        if (handleStart) handleStart.classList.remove("is-dragging");
        if (handleEnd) handleEnd.classList.remove("is-dragging");
        timelineActiveRange.classList.remove("is-dragging");
        document.body.style.cursor = "";

        // Synchronize live whisper transcript for current fragment
        scheduleSegmentTranscribe(200);
    };

    window.addEventListener("mousemove", (e) => {
        if (activeDrag) {
            e.preventDefault();
            onPointerMove(e.clientX);
        }
    });

    window.addEventListener("mouseup", onPointerUp);

    window.addEventListener("touchmove", (e) => {
        if (activeDrag && e.touches.length > 0) {
            e.preventDefault();
            onPointerMove(e.touches[0].clientX);
        }
    }, { passive: false });

    window.addEventListener("touchend", onPointerUp);

    // Track Hover Time Indicator
    if (timelineHoverTime) {
        timelineTrack.addEventListener("mousemove", (e) => {
            if (!state.audioDuration || activeDrag) {
                timelineHoverTime.classList.add("hidden");
                return;
            }
            const rect = timelineTrack.getBoundingClientRect();
            const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
            const sec = (x / rect.width) * state.audioDuration;
            timelineHoverTime.style.left = `${x}px`;
            timelineHoverTime.textContent = formatSec(sec);
            timelineHoverTime.classList.remove("hidden");
        });

        timelineTrack.addEventListener("mouseleave", () => {
            timelineHoverTime.classList.add("hidden");
        });
    }

    // Click on timelineTrack to jump / seek (only if not dragging)
    timelineTrack.addEventListener("click", (e) => {
        if (activeDrag || !state.audioDuration) return;
        if (e.target === handleStart || e.target === handleEnd || (handleStart && handleStart.contains(e.target)) || (handleEnd && handleEnd.contains(e.target))) return;
        const rect = timelineTrack.getBoundingClientRect();
        const posRatio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        const clickSec = posRatio * state.audioDuration;
        mainAudio.currentTime = clickSec;
    });
}

// 6. EVENT LISTENERS & DUAL TIMELINE
function setupEventListeners() {
    setupTimelineDraggers();

    btnLoadChapter.addEventListener("click", loadChapterAudio);
    btnAutoTranscribe.addEventListener("click", autoTranscribeCurrentSegment);

    // Quick Viral Passages Buttons
    document.querySelectorAll(".passage-pill").forEach(pill => {
        pill.addEventListener("click", async () => {
            document.querySelectorAll(".passage-pill").forEach(p => p.classList.remove("active"));
            pill.classList.add("active");

            const bookOsis = pill.dataset.book;
            const chapter = parseInt(pill.dataset.chapter);
            const start = parseFloat(pill.dataset.start) || 0.0;
            const end = parseFloat(pill.dataset.end) || 15.0;
            const citation = pill.dataset.citation;

            // Set book & chapter dropdowns
            const bookObj = (state.books || []).find(b => b.osis === bookOsis);
            if (bookObj) {
                bookSelect.value = bookObj.osis;
                updateChapterDropdown(bookObj);
            } else {
                bookSelect.value = bookOsis;
            }
            chapterSelect.value = chapter;

            // Trigger chapter loading with custom verse range & citation
            await loadChapterAudio(start, end, citation);
        });
    });

    // Audio Playback Events
    mainAudio.addEventListener("timeupdate", () => {
        if (!state.audioDuration) return;
        const cur = mainAudio.currentTime;
        currentTimeDisplay.textContent = formatSec(cur);
        totalDurationDisplay.textContent = formatSec(state.audioDuration);

        const ratio = cur / state.audioDuration;
        timelinePlayhead.style.left = `${ratio * 100}%`;

        // Synchronize preview captions in real time
        updateActiveCaption(cur);
    });

    // Duration Preset Pills
    document.querySelectorAll(".pill-btn").forEach(pill => {
        pill.addEventListener("click", () => {
            document.querySelectorAll(".pill-btn").forEach(p => p.classList.remove("active"));
            pill.classList.add("active");

            const durType = pill.dataset.dur;
            startSecInput.value = (0.0).toFixed(1);
            if (durType === "full") {
                endSecInput.value = state.audioDuration.toFixed(1);
            } else {
                const targetDur = parseFloat(durType);
                endSecInput.value = Math.min(state.audioDuration, targetDur).toFixed(1);
            }
            updateActiveRangeVisual();
            updateDurationBadge();
            scheduleSegmentTranscribe(0);
        });
    });

    // Manual Precision Trimming
    btnSetStart.addEventListener("click", () => {
        startSecInput.value = mainAudio.currentTime.toFixed(1);
        updateActiveRangeVisual();
        updateDurationBadge();
        scheduleSegmentTranscribe(0);
    });

    btnSetEnd.addEventListener("click", () => {
        endSecInput.value = mainAudio.currentTime.toFixed(1);
        updateActiveRangeVisual();
        updateDurationBadge();
        scheduleSegmentTranscribe(0);
    });

    startSecInput.addEventListener("change", () => {
        updateActiveRangeVisual();
        updateDurationBadge();
        scheduleSegmentTranscribe(150);
    });

    endSecInput.addEventListener("change", () => {
        updateActiveRangeVisual();
        updateDurationBadge();
        scheduleSegmentTranscribe(150);
    });

    // Preescuchar Selección
    btnPlayTrimmed.addEventListener("click", toggleTrimmedPlayback);

    // Micro Steppers for Start/End
    if (btnStartMinus) {
        btnStartMinus.addEventListener("click", () => {
            let val = Math.max(0, (parseFloat(startSecInput.value) || 0) - 1.0);
            startSecInput.value = val.toFixed(1);
            updateActiveRangeVisual();
            updateDurationBadge();
            scheduleSegmentTranscribe(300);
        });
    }
    if (btnStartPlus) {
        btnStartPlus.addEventListener("click", () => {
            let maxStart = Math.max(0, (parseFloat(endSecInput.value) || 15) - 0.5);
            let val = Math.min(maxStart, (parseFloat(startSecInput.value) || 0) + 1.0);
            startSecInput.value = val.toFixed(1);
            updateActiveRangeVisual();
            updateDurationBadge();
            scheduleSegmentTranscribe(300);
        });
    }
    if (btnEndMinus) {
        btnEndMinus.addEventListener("click", () => {
            let minEnd = (parseFloat(startSecInput.value) || 0) + 0.5;
            let val = Math.max(minEnd, (parseFloat(endSecInput.value) || 15) - 1.0);
            endSecInput.value = val.toFixed(1);
            updateActiveRangeVisual();
            updateDurationBadge();
            scheduleSegmentTranscribe(300);
        });
    }
    if (btnEndPlus) {
        btnEndPlus.addEventListener("click", () => {
            let maxEnd = state.audioDuration || 9999;
            let val = Math.min(maxEnd, (parseFloat(endSecInput.value) || 15) + 1.0);
            endSecInput.value = val.toFixed(1);
            updateActiveRangeVisual();
            updateDurationBadge();
            scheduleSegmentTranscribe(300);
        });
    }

    // Passage Accordion Drawer
    if (btnTogglePassage && passageContentArea) {
        btnTogglePassage.addEventListener("click", () => {
            passageContentArea.classList.toggle("hidden");
            if (passageChevron) passageChevron.classList.toggle("open");
        });
    }

    // Subtitles Toggle
    if (subtitlesToggle) {
        subtitlesToggle.addEventListener("change", (e) => {
            state.enableSubtitles = e.target.checked;
            if (subtitlesToggleText) {
                subtitlesToggleText.textContent = state.enableSubtitles ? "Activados" : "Desactivados";
            }
            if (!state.enableSubtitles || state.subtitleStyle === "none") {
                previewCaptionText.classList.add("hidden");
            } else {
                previewCaptionText.classList.remove("hidden");
            }
        });
    }

    // Citation change
    citationInput.addEventListener("input", () => {
        previewCitationText.textContent = `— ${citationInput.value.toUpperCase()} —`;
    });

    // Subtitle Style Options
    document.querySelectorAll(".style-option").forEach(opt => {
        opt.addEventListener("click", () => {
            document.querySelectorAll(".style-option").forEach(x => x.classList.remove("selected"));
            opt.classList.add("selected");
            state.subtitleStyle = opt.dataset.style;

            if (state.subtitleStyle === "none" || !state.enableSubtitles) {
                previewCaptionText.classList.add("hidden");
            } else {
                previewCaptionText.classList.remove("hidden");
                previewCaptionText.className = "caption-bubble";
                if (state.subtitleStyle === "typewriter") previewCaptionText.classList.add("font-typewriter");
                if (state.subtitleStyle === "spokenbyhim") previewCaptionText.classList.add("font-spoken");
                if (state.subtitleStyle === "classicserif") previewCaptionText.classList.add("font-serif");
                if (state.subtitleStyle === "modern_bold") previewCaptionText.classList.add("font-modern");
            }
        });
    });

    // Frame Style Selector Buttons
    document.querySelectorAll(".frame-style-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".frame-style-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.frameStyle = btn.dataset.frame || "vintage";
            applyFrameStyleToMockup();
        });
    });

    // Framing Modes Selector Buttons
    document.querySelectorAll(".framing-mode-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".framing-mode-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.framingMode = btn.dataset.framing || "pitch_black";

            // Update Phone Mockup Preview in Real-time
            const mockup = document.querySelector(".phone-mockup");
            const radiusBox = document.getElementById("radiusSliderBox");
            if (mockup) {
                mockup.classList.remove("framing-pitch_black", "framing-fullscreen", "framing-ambient");
                mockup.classList.add(`framing-${state.framingMode}`);
            }
            if (radiusBox) {
                radiusBox.style.display = state.framingMode === "fullscreen" ? "none" : "block";
            }
        });
    });

    // Slideshow Pacing Selector Buttons
    document.querySelectorAll(".pacing-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".pacing-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.slideshowPacing = btn.dataset.pacing || "cinematic";
        });
    });

    // Subtitle Position Segmented Control
    document.querySelectorAll("[data-sub-pos]").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("[data-sub-pos]").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.subtitlePosition = btn.dataset.subPos || "bottom";
            const layer = document.querySelector(".phone-captions-layer");
            if (layer) {
                layer.style.bottom = state.subtitlePosition === "center" ? "120px" : "32px";
            }
        });
    });

    // Subtitle Text Case Segmented Control
    document.querySelectorAll("[data-text-case]").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("[data-text-case]").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.textCase = btn.dataset.textCase || "original";
            if (state.textCase === "uppercase") {
                previewCaptionText.style.textTransform = "uppercase";
            } else {
                previewCaptionText.style.textTransform = "none";
            }
        });
    });

    // Multi-Select Visuals Checkbox
    if (chkMultiSelectVisuals) {
        chkMultiSelectVisuals.addEventListener("change", (e) => {
            state.isMultiSelect = e.target.checked;
            if (!state.isMultiSelect) {
                document.querySelectorAll(".visual-item-card").forEach(c => c.classList.remove("multi-selected"));
                if (state.selectedVisual) {
                    state.selectedVisuals = [state.selectedVisual];
                    const activeCard = Array.from(document.querySelectorAll(".visual-item-card")).find(c => c.dataset.id === state.selectedVisual.id);
                    if (activeCard) activeCard.classList.add("selected");
                }
            } else {
                if (state.selectedVisual) {
                    state.selectedVisuals = [state.selectedVisual];
                    const activeCard = Array.from(document.querySelectorAll(".visual-item-card")).find(c => c.dataset.id === state.selectedVisual.id);
                    if (activeCard) activeCard.classList.add("multi-selected", "selected");
                } else {
                    state.selectedVisuals = [];
                }
            }
            updateMultiSelectUI();
        });
    }

    // Keyboard spacebar shortcut to play/pause audio preview
    window.addEventListener("keydown", (e) => {
        if (e.code === "Space") {
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
            if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) {
                return;
            }
            e.preventDefault();
            toggleTrimmedPlayback();
        }
    });

    // Tabs Bar (Single Loop vs Slideshow)
    document.querySelectorAll(".tab-btn").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach(t => t.classList.remove("active"));
            tab.classList.add("active");

            const mode = tab.dataset.tab;
            if (mode === "single") {
                document.getElementById("tabSingleVisuals").classList.add("active");
                document.getElementById("tabSlideshowVisuals").classList.remove("active");
                state.isSlideshowMode = state.isMultiSelect && state.selectedVisuals.length > 1;
            } else {
                document.getElementById("tabSingleVisuals").classList.remove("active");
                document.getElementById("tabSlideshowVisuals").classList.add("active");
                state.isSlideshowMode = true;
                // Auto-select first collection if none selected
                const firstCol = document.querySelector(".collection-card");
                if (firstCol && !state.selectedCollection) firstCol.click();
            }
            updatePacingVisibility();
        });
    });

    // Sliders
    radiusSlider.addEventListener("input", () => {
        state.cornerRadius = parseInt(radiusSlider.value);
        radiusVal.textContent = `${state.cornerRadius}px`;
        previewFgBox.style.borderRadius = `${state.cornerRadius * 0.42}px`;
    });

    volumeSlider.addEventListener("input", () => {
        state.musicVolume = parseFloat(volumeSlider.value) / 100.0;
        volumeVal.textContent = `${volumeSlider.value}%`;
        if (activeMusicVolBadge && state.selectedMusic) {
            activeMusicVolBadge.textContent = `${volumeSlider.value}%`;
        }
    });

    // Watermark / Creator Handle Live Preview
    if (watermarkInput) {
        watermarkInput.addEventListener("input", () => {
            const wm = watermarkInput.value.trim();
            if (previewWatermark) {
                if (wm) {
                    previewWatermark.textContent = wm;
                    previewWatermark.classList.remove("hidden");
                } else {
                    previewWatermark.classList.add("hidden");
                }
            }
        });
    }

    // Verse Search Filter in Passage Drawer
    if (verseSearchInput) {
        verseSearchInput.addEventListener("input", (e) => {
            const q = e.target.value.toLowerCase().trim();
            if (!q) {
                renderInteractivePhrases(currentChapterPhrases);
            } else {
                const filtered = currentChapterPhrases.filter(p => p.text.toLowerCase().includes(q));
                renderInteractivePhrases(filtered);
            }
        });
    }

    // Playback state synchronization for preview button
    mainAudio.addEventListener("play", () => {
        if (btnPlayTrimmed) {
            btnPlayTrimmed.textContent = "⏸ Pausar selección";
            btnPlayTrimmed.classList.add("playing");
        }
    });
    mainAudio.addEventListener("pause", () => {
        if (btnPlayTrimmed) {
            btnPlayTrimmed.textContent = "▶ Preescuchar selección";
            btnPlayTrimmed.classList.remove("playing");
        }
    });

    // File Uploads
    visualUploadInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/upload_visual", { method: "POST", body: formData });
            const data = await res.json();
            if (data.success) {
                const newVis = {
                    id: data.name,
                    name: data.name.split(".")[0],
                    path: data.path,
                    url: data.url,
                    thumb: data.thumb,
                    type: file.type.includes("video") ? "video" : (file.type.includes("gif") ? "gif" : "image")
                };
                selectVisual(newVis, null);
            }
        } catch (err) {
            alert("Error subiendo visual: " + err.message);
        }
    });

    musicUploadInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/api/upload_music", { method: "POST", body: formData });
            const data = await res.json();
            if (data.success) {
                const newMusic = {
                    id: data.name,
                    name: data.name.split(".")[0],
                    path: data.path,
                    url: data.url
                };
                selectMusic(newMusic, null);
            }
        } catch (err) {
            alert("Error subiendo música: " + err.message);
        }
    });

    // Render Button
    btnRenderVideo.addEventListener("click", handleRenderVideo);
}

function updateActiveCaption(currentAudioSec) {
    if (!state.phrases || state.phrases.length === 0) return;
    const active = state.phrases.find(p => currentAudioSec >= p.start && currentAudioSec <= p.end);
    if (active) {
        previewCaptionText.textContent = active.text;
    }
}

function updateActiveRangeVisual() {
    if (!state.audioDuration) return;
    const start = parseFloat(startSecInput.value) || 0;
    const end = parseFloat(endSecInput.value) || 15;

    const leftPercent = (start / state.audioDuration) * 100;
    const widthPercent = Math.max(0.2, ((end - start) / state.audioDuration) * 100);

    timelineActiveRange.style.left = `${leftPercent}%`;
    timelineActiveRange.style.width = `${widthPercent}%`;

    if (tooltipStart) tooltipStart.textContent = formatSec(start);
    if (tooltipEnd) tooltipEnd.textContent = formatSec(end);
}

function updateDurationBadge() {
    const start = parseFloat(startSecInput.value) || 0;
    const end = parseFloat(endSecInput.value) || 0;
    const dur = Math.max(0, end - start);
    clipDurationBadge.textContent = `${dur.toFixed(1)}s`;
}

function formatSec(sec) {
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1);
    return `${m.toString().padStart(2, '0')}:${s.padStart(4, '0')}`;
}

// 7. RENDER VIDEO HANDLER
async function handleRenderVideo() {
    const start = parseFloat(startSecInput.value) || 0;
    const end = parseFloat(endSecInput.value) || 0;

    if (end <= start) {
        alert("El tiempo de fin debe ser mayor al de inicio.");
        return;
    }

    let visualPayload;
    if (state.isMultiSelect && state.selectedVisuals && state.selectedVisuals.length > 0) {
        visualPayload = state.selectedVisuals.map(v => v.path);
    } else if (state.isSlideshowMode && state.selectedCollection) {
        visualPayload = state.selectedCollection.paths;
    } else if (state.selectedVisual) {
        visualPayload = state.selectedVisual.path;
    } else {
        alert("Por favor selecciona un fondo visual o colección.");
        return;
    }

    btnRenderVideo.disabled = true;
    renderStatus.classList.remove("hidden");
    renderStatus.classList.remove("is-success");
    if (renderSpinner) renderSpinner.classList.remove("hidden");
    if (renderSuccessIcon) renderSuccessIcon.classList.add("hidden");
    renderStatusText.textContent = "Mezclando audio de David Suchet y renderizando video 9:16...";
    if (renderStatusSub) renderStatusSub.textContent = "Renderizado con FFmpeg en alta resolución";

    const payload = {
        book: bookSelect.value,
        chapter: parseInt(chapterSelect.value),
        start_sec: start,
        end_sec: end,
        citation: citationInput.value.trim() || `${bookSelect.value} ${chapterSelect.value}`,
        visual_paths: visualPayload,
        music_path: state.selectedMusic ? state.selectedMusic.path : "",
        music_volume: state.musicVolume,
        subtitle_style: state.subtitleStyle,
        subtitle_position: state.subtitlePosition || "bottom",
        text_case: state.textCase || "original",
        watermark: watermarkInput ? watermarkInput.value.trim() : "",
        enable_subtitles: state.enableSubtitles && state.subtitleStyle !== "none",
        corner_radius: state.cornerRadius,
        slideshow_pacing: state.slideshowPacing || "cinematic",
        framing_mode: state.framingMode || "pitch_black",
        enable_particles: document.getElementById("chkParticles") ? document.getElementById("chkParticles").checked : true,
        enable_light_leak: document.getElementById("chkLightLeak") ? document.getElementById("chkLightLeak").checked : true,
        enable_dynamic_motion: document.getElementById("chkDynamicMotion") ? document.getElementById("chkDynamicMotion").checked : true,
        enable_film_grain: document.getElementById("chkFilmGrain") ? document.getElementById("chkFilmGrain").checked : true,
        phrases: state.phrases
    };

    try {
        const res = await fetch("/api/render", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (!data.success) throw new Error(data.detail || "Error en el renderizado");

        // Load finished video directly in phone stage
        renderedVideoPlayer.src = data.video_url;
        renderedVideoPlayer.classList.remove("hidden");
        renderedVideoPlayer.play();

        downloadArea.classList.remove("hidden");
        btnDownload.href = data.video_url;
        btnDownload.download = data.filename;

        renderStatus.classList.add("is-success");
        if (renderSpinner) renderSpinner.classList.add("hidden");
        if (renderSuccessIcon) renderSuccessIcon.classList.remove("hidden");
        renderStatusText.textContent = "¡Video generado con éxito!";
        if (renderStatusSub) renderStatusSub.textContent = "Listo para publicar en TikTok • Previsualizando en el teléfono";
        await loadHistory();
    } catch (e) {
        alert("Error renderizando video: " + e.message);
        renderStatus.classList.add("hidden");
    } finally {
        btnRenderVideo.disabled = false;
    }
}

// 8. HISTORY GALLERY
async function loadHistory() {
    try {
        const res = await fetch("/api/videos");
        const data = await res.json();

        if (!data.videos || data.videos.length === 0) {
            historyList.innerHTML = `<p class="empty-history-text">Tus videos aparecerán aquí una vez generados.</p>`;
            return;
        }

        historyList.innerHTML = "";
        data.videos.forEach(v => {
            const card = document.createElement("div");
            card.className = "history-card-item";
            
            const thumbSrc = v.thumb_url || "/assets/visuals/jesus_good_shepherd.jpg";
            const durTag = v.duration ? `<span class="history-dur-badge">${v.duration}</span>` : "";

            card.innerHTML = `
                <div class="history-thumb-box" onclick="playInMockup('${v.url}', '${v.filename}')" title="Clic para reproducir en el teléfono">
                    <img src="${thumbSrc}" alt="${v.title}" class="history-thumb-img" onerror="this.src='/assets/visuals/jesus_good_shepherd.jpg'">
                    ${durTag}
                    <div class="history-play-overlay">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                    </div>
                </div>
                <div class="history-info-box">
                    <div>
                        <span class="history-tag-badge">9:16 VERTICAL</span>
                        <h4 class="history-title" title="${v.title}">${v.title}</h4>
                        <div class="history-filename-sub">${v.filename}</div>
                        <div class="history-meta-row">
                            <span>${v.created_at}</span>
                            <span class="history-meta-dot"></span>
                            <span>${v.size_mb} MB</span>
                        </div>
                    </div>
                    <div class="history-actions-row">
                        <button class="btn-card-play" onclick="playInMockup('${v.url}', '${v.filename}')">
                            Reproducir
                        </button>
                        <a href="${v.url}" download="${v.filename}" class="btn-card-download" title="Descargar archivo MP4">
                            Descargar
                        </a>
                        <button class="btn-card-delete" onclick="handleDeleteVideo('${v.filename}')" title="Eliminar este video">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                    </div>
                </div>
            `;
            historyList.appendChild(card);
        });
    } catch (e) {
        console.error("Error loading history:", e);
    }
}

async function handleDeleteVideo(filename) {
    if (!confirm(`¿Estás seguro de que deseas eliminar este video?\n(${filename})`)) return;
    try {
        const res = await fetch(`/api/videos/${encodeURIComponent(filename)}`, { method: "DELETE" });
        const data = await res.json();
        if (data.success) {
            await loadHistory();
        } else {
            alert("Error al eliminar: " + (data.detail || "Error desconocido"));
        }
    } catch (err) {
        alert("Error al eliminar video: " + err.message);
    }
}

function playInMockup(url, filename) {
    renderedVideoPlayer.src = url;
    renderedVideoPlayer.classList.remove("hidden");
    renderedVideoPlayer.play();
    downloadArea.classList.remove("hidden");
    btnDownload.href = url;
    if (filename) btnDownload.download = filename;

    // Smoothly scroll phone into view if needed
    const phoneStage = document.querySelector(".phone-stage-card");
    if (phoneStage) {
        phoneStage.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
}

window.addEventListener("DOMContentLoaded", init);
