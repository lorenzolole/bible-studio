import os
import re
import ssl
import html as html_lib
import urllib.request
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("downloader")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "audio")
os.makedirs(CACHE_DIR, exist_ok=True)

# Complete 66 Bible books with OSIS code, English name, Spanish name, and chapter count
BIBLE_BOOKS = [
    {"osis": "Gen", "name_en": "Genesis", "name_es": "Génesis", "testament": "OT", "chapters": 50},
    {"osis": "Exod", "name_en": "Exodus", "name_es": "Éxodo", "testament": "OT", "chapters": 40},
    {"osis": "Lev", "name_en": "Leviticus", "name_es": "Levítico", "testament": "OT", "chapters": 27},
    {"osis": "Num", "name_en": "Numbers", "name_es": "Números", "testament": "OT", "chapters": 36},
    {"osis": "Deut", "name_en": "Deuteronomy", "name_es": "Deuteronomio", "testament": "OT", "chapters": 34},
    {"osis": "Josh", "name_en": "Joshua", "name_es": "Josué", "testament": "OT", "chapters": 24},
    {"osis": "Judg", "name_en": "Judges", "name_es": "Jueces", "testament": "OT", "chapters": 21},
    {"osis": "Ruth", "name_en": "Ruth", "name_es": "Rut", "testament": "OT", "chapters": 4},
    {"osis": "1Sam", "name_en": "1 Samuel", "name_es": "1 Samuel", "testament": "OT", "chapters": 31},
    {"osis": "2Sam", "name_en": "2 Samuel", "name_es": "2 Samuel", "testament": "OT", "chapters": 24},
    {"osis": "1Kgs", "name_en": "1 Kings", "name_es": "1 Reyes", "testament": "OT", "chapters": 22},
    {"osis": "2Kgs", "name_en": "2 Kings", "name_es": "2 Reyes", "testament": "OT", "chapters": 25},
    {"osis": "1Chr", "name_en": "1 Chronicles", "name_es": "1 Crónicas", "testament": "OT", "chapters": 29},
    {"osis": "2Chr", "name_en": "2 Chronicles", "name_es": "2 Crónicas", "testament": "OT", "chapters": 36},
    {"osis": "Ezra", "name_en": "Ezra", "name_es": "Esdras", "testament": "OT", "chapters": 10},
    {"osis": "Neh", "name_en": "Nehemiah", "name_es": "Nehemías", "testament": "OT", "chapters": 13},
    {"osis": "Esth", "name_en": "Esther", "name_es": "Ester", "testament": "OT", "chapters": 10},
    {"osis": "Job", "name_en": "Job", "name_es": "Job", "testament": "OT", "chapters": 42},
    {"osis": "Ps", "name_en": "Psalms", "name_es": "Salmos", "testament": "OT", "chapters": 150},
    {"osis": "Prov", "name_en": "Proverbs", "name_es": "Proverbios", "testament": "OT", "chapters": 31},
    {"osis": "Eccl", "name_en": "Ecclesiastes", "name_es": "Eclesiastés", "testament": "OT", "chapters": 12},
    {"osis": "Song", "name_en": "Song of Solomon", "name_es": "Cantares", "testament": "OT", "chapters": 8},
    {"osis": "Isa", "name_en": "Isaiah", "name_es": "Isaías", "testament": "OT", "chapters": 66},
    {"osis": "Jer", "name_en": "Jeremiah", "name_es": "Jeremías", "testament": "OT", "chapters": 52},
    {"osis": "Lam", "name_en": "Lamentations", "name_es": "Lamentaciones", "testament": "OT", "chapters": 5},
    {"osis": "Ezek", "name_en": "Ezekiel", "name_es": "Ezequiel", "testament": "OT", "chapters": 48},
    {"osis": "Dan", "name_en": "Daniel", "name_es": "Daniel", "testament": "OT", "chapters": 12},
    {"osis": "Hos", "name_en": "Hosea", "name_es": "Oseas", "testament": "OT", "chapters": 14},
    {"osis": "Joel", "name_en": "Joel", "name_es": "Joel", "testament": "OT", "chapters": 3},
    {"osis": "Amos", "name_en": "Amos", "name_es": "Amós", "testament": "OT", "chapters": 9},
    {"osis": "Obad", "name_en": "Obadiah", "name_es": "Abdías", "testament": "OT", "chapters": 1},
    {"osis": "Jonah", "name_en": "Jonah", "name_es": "Jonás", "testament": "OT", "chapters": 4},
    {"osis": "Mic", "name_en": "Micah", "name_es": "Miqueas", "testament": "OT", "chapters": 7},
    {"osis": "Nah", "name_en": "Nahum", "name_es": "Nahúm", "testament": "OT", "chapters": 3},
    {"osis": "Hab", "name_en": "Habakkuk", "name_es": "Habacuc", "testament": "OT", "chapters": 3},
    {"osis": "Zeph", "name_en": "Zephaniah", "name_es": "Sofonías", "testament": "OT", "chapters": 3},
    {"osis": "Hag", "name_en": "Haggai", "name_es": "Hageo", "testament": "OT", "chapters": 2},
    {"osis": "Zech", "name_en": "Zechariah", "name_es": "Zacarías", "testament": "OT", "chapters": 14},
    {"osis": "Mal", "name_en": "Malachi", "name_es": "Malaquías", "testament": "OT", "chapters": 4},
    {"osis": "Matt", "name_en": "Matthew", "name_es": "Mateo", "testament": "NT", "chapters": 28},
    {"osis": "Mark", "name_en": "Mark", "name_es": "Marcos", "testament": "NT", "chapters": 16},
    {"osis": "Luke", "name_en": "Luke", "name_es": "Lucas", "testament": "NT", "chapters": 24},
    {"osis": "John", "name_en": "John", "name_es": "Juan", "testament": "NT", "chapters": 21},
    {"osis": "Acts", "name_en": "Acts", "name_es": "Hechos", "testament": "NT", "chapters": 28},
    {"osis": "Rom", "name_en": "Romans", "name_es": "Romanos", "testament": "NT", "chapters": 16},
    {"osis": "1Cor", "name_en": "1 Corinthians", "name_es": "1 Corintios", "testament": "NT", "chapters": 16},
    {"osis": "2Cor", "name_en": "2 Corinthians", "name_es": "2 Corintios", "testament": "NT", "chapters": 13},
    {"osis": "Gal", "name_en": "Galatians", "name_es": "Gálatas", "testament": "NT", "chapters": 6},
    {"osis": "Eph", "name_en": "Ephesians", "name_es": "Efesios", "testament": "NT", "chapters": 6},
    {"osis": "Phil", "name_en": "Philippians", "name_es": "Filipenses", "testament": "NT", "chapters": 4},
    {"osis": "Col", "name_en": "Colossians", "name_es": "Colosenses", "testament": "NT", "chapters": 4},
    {"osis": "1Thess", "name_en": "1 Thessalonians", "name_es": "1 Tesalonicenses", "testament": "NT", "chapters": 5},
    {"osis": "2Thess", "name_en": "2 Thessalonians", "name_es": "2 Tesalonicenses", "testament": "NT", "chapters": 3},
    {"osis": "1Tim", "name_en": "1 Timothy", "name_es": "1 Timoteo", "testament": "NT", "chapters": 6},
    {"osis": "2Tim", "name_en": "2 Timothy", "name_es": "2 Timoteo", "testament": "NT", "chapters": 4},
    {"osis": "Titus", "name_en": "Titus", "name_es": "Tito", "testament": "NT", "chapters": 3},
    {"osis": "Phlm", "name_en": "Philemon", "name_es": "Filemón", "testament": "NT", "chapters": 1},
    {"osis": "Heb", "name_en": "Hebrews", "name_es": "Hebreos", "testament": "NT", "chapters": 13},
    {"osis": "Jas", "name_en": "James", "name_es": "Santiago", "testament": "NT", "chapters": 5},
    {"osis": "1Pet", "name_en": "1 Peter", "name_es": "1 Pedro", "testament": "NT", "chapters": 5},
    {"osis": "2Pet", "name_en": "2 Peter", "name_es": "2 Pedro", "testament": "NT", "chapters": 3},
    {"osis": "1John", "name_en": "1 John", "name_es": "1 Juan", "testament": "NT", "chapters": 5},
    {"osis": "2John", "name_en": "2 John", "name_es": "2 Juan", "testament": "NT", "chapters": 1},
    {"osis": "3John", "name_en": "3 John", "name_es": "3 Juan", "testament": "NT", "chapters": 1},
    {"osis": "Jude", "name_en": "Jude", "name_es": "Judas", "testament": "NT", "chapters": 1},
    {"osis": "Rev", "name_en": "Revelation", "name_es": "Apocalipsis", "testament": "NT", "chapters": 22},
]

# Scraped passage text by (osis, chapter or verse reference); the text never changes
_PASSAGE_CACHE = {}

USFM_ALIASES = {
    "jhn": "John", "psa": "Ps", "php": "Phil", "pro": "Prov",
    "isa": "Isa", "rom": "Rom", "1co": "1Cor", "2co": "2Cor",
    "gen": "Gen", "exo": "Exod", "mat": "Matt", "mrk": "Mark",
    "luk": "Luke", "act": "Acts", "rev": "Rev", "heb": "Heb",
    "jas": "Jas", "1pe": "1Pet", "2pe": "2Pet", "1jn": "1John"
}

def resolve_book(query: str):
    """Resolve user input to a book dictionary, supporting OSIS, Spanish, English, and USFM codes."""
    if not query:
        return None
    q = query.strip().lower()
    if q in USFM_ALIASES:
        q = USFM_ALIASES[q].lower()
    q_norm = q.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    
    for b in BIBLE_BOOKS:
        b_en = b["name_en"].lower()
        b_es = b["name_es"].lower()
        b_es_norm = b_es.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        b_osis = b["osis"].lower()
        
        if q in (b_osis, b_en, b_es, b_es_norm):
            return b
        if q_norm in (b_osis, b_en, b_es, b_es_norm):
            return b

    for b in BIBLE_BOOKS:
        b_en = b["name_en"].lower()
        b_es = b["name_es"].lower()
        b_es_norm = b_es.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        if q in b_en or q in b_es or q_norm in b_es_norm:
            return b

    return None

def get_audio_stream_url(osis: str, chapter: int) -> str:
    """Scrape the direct MP3 stream URL from BibleGateway David Suchet NIVUK audio player."""
    page_url = f"https://www.biblegateway.com/audio/suchet/nivuk/{osis}.{chapter}"
    req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        html = resp.read().decode("utf-8")
        
    m = re.search(r'src=[\"\'](https://stream\.biblegateway\.com/[^\"\']+\.mp3)[\"\']', html)
    if m:
        return m.group(1)
        
    m2 = re.search(r'(https://stream\.biblegateway\.com/bibles/[^\"\']+\.mp3)', html)
    if m2:
        return m2.group(1)
        
    raise ValueError(f"Could not find audio stream for {osis}.{chapter} on BibleGateway")

def download_audio_chapter(book_str: str, chapter: int) -> dict:
    """
    Download or retrieve cached MP3 of David Suchet for book and chapter.
    Returns dict with local_path, osis, chapter, book_info, duration_seconds.
    """
    book = resolve_book(book_str)
    if not book:
        raise ValueError(f"Unknown book: '{book_str}'")
        
    osis = book["osis"]
    cached_file = os.path.join(CACHE_DIR, f"{osis}_{chapter}.mp3")
    
    if os.path.exists(cached_file) and os.path.getsize(cached_file) > 10000:
        logger.info(f"Using cached audio for {osis} {chapter}: {cached_file}")
    else:
        stream_url = get_audio_stream_url(osis, chapter)
        logger.info(f"Downloading David Suchet audio: {stream_url} -> {cached_file}")
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(stream_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp, open(cached_file, "wb") as out_f:
            while chunk := resp.read(64 * 1024):
                out_f.write(chunk)
                
    return {
        "local_path": cached_file,
        "osis": osis,
        "chapter": chapter,
        "book": book,
        "file_size": os.path.getsize(cached_file)
    }

def fetch_passage_text(book_str: str, chapter: int) -> dict:
    """
    Fetch the text of the passage from BibleGateway NIVUK.
    """
    book = resolve_book(book_str)
    if not book:
        return {"error": "Book not found"}
    osis = book["osis"]
    cache_key = (osis, str(chapter))
    if cache_key in _PASSAGE_CACHE:
        return dict(_PASSAGE_CACHE[cache_key])
    url = f"https://www.biblegateway.com/passage/?search={osis}+{chapter}&version=NIVUK"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            raw_html = resp.read().decode("utf-8")
        
        # BibleGateway mixes quote styles (class='footnote' vs class="versenum")
        clean_html = re.sub(r"<sup[^>]*class=['\"](?:footnote|crossreference|versenum)['\"][^>]*>.*?</sup>", '', raw_html, flags=re.DOTALL)
        clean_html = re.sub(r"<span[^>]*class=['\"]chapternum['\"][^>]*>.*?</span>", '', clean_html, flags=re.DOTALL)
        clean_html = re.sub(r'<h[1-6][^>]*>.*?</h[1-6]>', '', clean_html, flags=re.DOTALL)

        # Unwrap spans nested inside verse text (small-caps "Lord", red-letter "woj"), innermost first;
        # otherwise the verse regex below stops at the first inner </span> and truncates the verse
        inner_span = re.compile(r'<span(?![^>]*class="text )[^>]*>((?:(?!<span).)*?)</span>', flags=re.DOTALL)
        while True:
            unwrapped = inner_span.sub(r'\1', clean_html)
            if unwrapped == clean_html:
                break
            clean_html = unwrapped

        spans = re.findall(r'<span[^>]*class="text [^"]*"[^>]*>(.*?)</span>', clean_html, flags=re.DOTALL)
        texts = []
        for s in spans:
            t = re.sub(r'<[^>]+>', '', s).strip()
            if t:
                t = html_lib.unescape(t).replace('\xa0', ' ').replace('&nbsp;', ' ')
                t = re.sub(r'\s+', ' ', t).strip()
                if t:
                    texts.append(t)
        full_text = " ".join(texts)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        result = {
            "reference": f"{book['name_en']} {chapter}",
            "reference_es": f"{book['name_es']} {chapter}",
            "text": full_text
        }
        if full_text:
            _PASSAGE_CACHE[cache_key] = result
        return dict(result)
    except Exception as e:
        logger.error(f"Error fetching passage text: {e}")
        return {"reference": f"{book['name_en']} {chapter}", "text": ""}

def normalize_citation_english(citation_str: str) -> str:
    """Normalize any Bible citation into clean, uppercase English format (e.g., 'Salmo 23:1-3' -> 'PSALM 23:1-3')."""
    if not citation_str:
        return ""
    cit = citation_str.strip()
    m = re.match(r"^([0-9]?\s*[A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s*(.*)$", cit)
    if m:
        book_raw = m.group(1).strip()
        ref_raw = m.group(2).strip()
        book = resolve_book(book_raw)
        if book:
            eng_name = book["name_en"]
            if eng_name.lower() == "psalms":
                eng_name = "Psalm"
            return f"{eng_name.upper()} {ref_raw}".strip()
    return cit.upper()

if __name__ == "__main__":
    import sys
    test_book = sys.argv[1] if len(sys.argv) > 1 else "Salmos"
    test_ch = int(sys.argv[2]) if len(sys.argv) > 2 else 23
    print(f"Testing {test_book} {test_ch}...")
    res = download_audio_chapter(test_book, test_ch)
    print("Audio downloaded:", res)
    text_info = fetch_passage_text(test_book, test_ch)
    print("Text snippet:", text_info["text"][:120], "...")
