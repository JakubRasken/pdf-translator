import json
import time
import logging
import re
from pydantic import BaseModel
from google import genai
from google.genai import types
from deep_translator import GoogleTranslator
from pdf_translator_pipeline.config import GEMINI_API_KEY, DEFAULT_MODEL

# Czech technical translation glossary to correct common machine-translation errors
CZECH_GLOSSARY = {
    # AC Title overrides
    "ROUND FLOW CASSETTE": "KRUHOVÁ KAZETOVÁ JEDNOTKA",
    "COMPACT FOUR-WAY CASSETTE": "KOMPAKTNÍ 4CESTNÁ KAZETOVÁ JEDNOTKA",
    "ONE-WAY CASSETTE": "1CESTNÁ KAZETOVÁ JEDNOTKA",
    "SLIM DUCT": "NÍZKÁ KANÁLOVÁ JEDNOTKA",
    "MEDIUM STATIC PRESSURE DUCT": "KANÁLOVÁ JEDNOTKA SE STŘEDNÍM TLAKEM",
    "HIGH STATIC PRESSURE DUCT": "KANÁLOVÁ JEDNOTKA S VYSOKÝM TLAKEM",
    "BUILIT IN FLOOR STANDING": "ZABUDOVANÁ PARAPETNÍ JEDNOTKA",
    "BUILT IN FLOOR STANDING": "ZABUDOVANÁ PARAPETNÍ JEDNOTKA",
    "FLOOR-CEILING": "PARAPETNÍ/STROPNÍ JEDNOTKA",
    "HIGH WALL": "NÁSTĚNNÁ JEDNOTKA",
    "FRESH AIR DUCT": "KANÁLOVÁ JED. ČERSTVÉHO VZDUCHU",
    "CONSOLE": "PARAPETNÍ JEDNOTKA",
    "ONE": "1CESTNÁ",
    "-WAY CASSETTE": "KAZETOVÁ JEDNOTKA",
    "WAY CASSETTE": "KAZETOVÁ JEDNOTKA",
    
    # Large fails
    "grilování": "mřížka",
    "gril": "mřížka",
    "let běžící vakuové čerpadlo": "nechte běžet vakuové čerpadlo",
    "let běžící": "nechte běžet",
    "let běžet": "nechte běžet",
    "Nadační práce": "Příprava základů",
    "nadační práce": "základové práce",
    "Ruční podání": "Ruční manipulace",
    "ruční podání": "ruční manipulace",
    "Příjezdová kontrola": "Kontrola při převzetí",
    "příjezdová kontrola": "kontrola při převzetí",
    "připojování nálevky": "kalichové připojení",
    "připojení nálevky": "kalichové připojení",
    "měděná trubka z oxidované fosforem": "měděná trubka odkysličená fosforem",
    "měděná trubka z oxidované": "měděná trubka odkysličená",
    "Pokud není opraveno, chladivo se zaměří": "Pokud není potrubí upevněno, pnutí se soustředí",
    "vnitřní stroj": "vnitřní jednotka",
    "vnitřního stroje": "vnitřní jednotky",
    "vnitřním stroji": "vnitřní jednotce",
    "vnitřní stroje": "vnitřní jednotky",
    "vnitřních strojů": "vnitřních jednotek",
    "venkovní stroj": "venkovní jednotka",
    "venkovního stroje": "venkovní jednotky",
    "venkovním stroji": "venkovní jednotce",
    "venkovní stroje": "venkovní jednotky",
    "venkovních strojů": "venkovních jednotek",
    "elektrifikována": "pod napětím",
    "elektrifikován": "pod napětím",
    "elektrifikováno": "pod napětím",
    "Hlučný filer": "Odrušovací filtr",
    "hlučný filer": "odrušovací filtr",
    "HLUČNÝ FILER": "ODRUŠOVACÍ FILTR",
    "Výpočet kapacity díky koeficientu": "Výpočet výkonu na základě koeficientu",
    "kapacita chlazení": "chladicí výkon",
    "kapacita vytápění": "topný výkon",
    "topný výkon bude znám = chladicí výkon": "topný výkon bude vypočten = jmenovitý topný výkon",
    "kapacita vnitřních jednotek": "výkon vnitřních jednotek",
    "jmenovité hodnoty kapacity": "jmenovitého výkonu",
    "Soustředit": "Těžiště",
    "soustředit": "těžiště",
    
    # Diagram greeting translations fixes ("Hi" -> "Ahoj")
    "ahoj rukojeti": "Hi rukojeť",
    "ahoj rukojeť": "Hi rukojeť",
    "ahoj": "Hi",
    
    # Shorter technical phrases to prevent vertical column line-wrapping bugs
    "zkontrolujte vakuum": "kontrola vakua",
    "evakuace začíná": "evakuace start",
    "evakuace končí": "evakuace konec",
    
    # Common terminology fixes
    "vnitřní kapacita": "vnitřní výkon",
    "kapacita venkovní": "výkon venkovní",
    "kapacita vnitřní": "výkon vnitřní",
    "rozměr kapacity": "rozsah výkonu",
    "koeficient modifikace kapacity": "korekční faktor výkonu",
    "jmenovitá kapacita": "jmenovitý výkon",
    "jmenovité kapacity": "jmenovitého výkonu",
    "chladicí kapacita": "chladicí výkon",
    "chladicího výkonu": "chladicího výkonu",
    "topná kapacita": "topný výkon",
    "připojení potrubí": "připojení potrubí",
    "expanzní ventil": "expanzní ventil",
    "expanzního ventilu": "expanzního ventilu",
    "odbočná trubka": "odbočka",
    "odbočné potrubí": "odbočné potrubí",
    "sběrná trubka": "sběrné potrubí",
    "trubka uzavírací": "uzavírací ventil",
    "uzavírací ventil": "uzavírací ventil",
    "doplňování chladiva": "doplňování chladiva",
    "kód poruchy": "chybový kód",
    "kódů poruch": "chybových kódů",
    "odstraňování problémů": "odstraňování poruch",
    "odporu snímačů": "odporu snímačů",
    "leteckého profilu": "aerodynamického tvaru",
    "leteckého spirálového": "aerodynamického spirálového",
    "grilování ventilátoru": "mřížka ventilátoru",
    "směr proudění vzduchu sleduje směr mřížky": "směr proudění vzduchu sleduje směr mřížky",
    "Terminál pevně upevněte a způsobí uvolnění spojení havárie topení": "Svorku pevně upevněte, jinak uvolněné spojení způsobí přehřátí"
}


# Official Czech AC type-name terms (from HR_ENG_Klima katalog 2026 Excel + reviewed tweaks).
# These are applied as a PRE-translation override: a text block whose normalized text
# matches a key is set directly to the Czech value and never sent to the MT engine
# (machine translation mangles these product type names). Factory codes (IMV-..., VMV-...)
# are separate blocks and never match, so they stay intact.
AC_TYPE_OVERRIDES = {
    "ROUND FLOW CASSETTE": "OBOUCESTNÁ KAZETOVÁ JEDNOTKA",
    "COMPACT FOUR-WAY CASSETTE": "KOMPAKTNÍ 4CESTNÁ KAZETOVÁ JEDNOTKA",
    "ONE-WAY CASSETTE": "1CESTNÁ KAZETOVÁ JEDNOTKA",
    "SLIM DUCT": "NÍZKÁ KANÁLOVÁ JEDNOTKA",
    "MEDIUM STATIC PRESSURE DUCT": "KANÁLOVÁ JEDNOTKA SE STŘEDNÍM TLAKEM",
    "HIGH STATIC PRESSURE DUCT": "KANÁLOVÁ JEDNOTKA S VYSOKÝM TLAKEM",
    "BUILIT IN FLOOR STANDING": "ZABUDOVANÁ PARAPETNÍ JEDNOTKA",
    "BUILT IN FLOOR STANDING": "ZABUDOVANÁ PARAPETNÍ JEDNOTKA",
    "FLOOR-CEILING": "PARAPETNÍ / STROPNÍ JEDNOTKA",
    "HIGH WALL": "NÁSTĚNNÁ JEDNOTKA",
    "CONSOLE": "PARAPETNÍ JEDNOTKA",
    "FRESH AIR DUCT": "KANÁLOVÁ JEDNOTKA",
}


def normalize_ac_term(text: str) -> str:
    """Uppercase + collapse all whitespace (so headers split across lines still match)."""
    return " ".join(text.upper().split())


# Normalized lookup for fast exact matching of whole text blocks.
AC_TYPE_OVERRIDES_NORM = {normalize_ac_term(k): v for k, v in AC_TYPE_OVERRIDES.items()}


def ac_override_for(text: str) -> str | None:
    """Return the official Czech term if the whole block is an AC type name, else None."""
    return AC_TYPE_OVERRIDES_NORM.get(normalize_ac_term(text))


def apply_czech_glossary(text: str) -> str:
    # Sort keys by length in descending order to avoid partial matches first
    sorted_keys = sorted(CZECH_GLOSSARY.keys(), key=len, reverse=True)
    for key in sorted_keys:
        val = CZECH_GLOSSARY[key]
        # Case-insensitive replacement
        pattern = re.compile(re.escape(key), re.IGNORECASE)
        def repl(match):
            matched_text = match.group(0)
            if matched_text.isupper():
                return val.upper()
            elif matched_text[0].isupper() if matched_text else False:
                return val[0].upper() + val[1:] if len(val) > 1 else val.upper()
            return val
        text = pattern.sub(repl, text)
    return text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TranslationItem(BaseModel):
    id: str
    translated_text: str

class TranslationResponse(BaseModel):
    translations: list[TranslationItem]

class GeminiTranslator:
    def __init__(self, api_key: str = None, model: str = DEFAULT_MODEL, engine: str = "gemini", mock: bool = False):
        self.mock = mock
        self.model = model
        self.api_key = api_key or GEMINI_API_KEY
        self.engine = engine
        
        # If mock flag is explicitly set, use mock engine
        if self.mock:
            self.engine = "mock"
            
        if self.engine == "gemini" and not self.api_key:
            logger.warning("GEMINI_API_KEY environment variable not found. Falling back to free Google Translate engine.")
            self.engine = "google"
            
        if self.engine == "gemini":
            try:
                # Initialize Google GenAI client
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"GeminiTranslator initialized successfully with model: {self.model}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client: {e}. Falling back to free Google Translate engine.")
                self.engine = "google"
                
        if self.engine == "google":
            logger.info("Using free Google Translate engine (no API key required).")
        elif self.engine == "mock":
            logger.info("Using mock translator engine.")

    def translate_batch(self, blocks: list[dict], target_lang: str, source_lang: str = "auto") -> dict[str, str]:
        """
        Translates a list of text blocks.
        Each block should be a dictionary: {"id": str, "text": str}
        """
        if not blocks:
            return {}
            
        results = {}
        if self.engine == "mock":
            results = self._mock_translate(blocks, target_lang)
        elif self.engine == "google":
            results = self._google_translate(blocks, target_lang, source_lang)
        else:
            # self.engine == "gemini"
            try:
                results = self._gemini_translate(blocks, target_lang, source_lang)
            except Exception as e:
                logger.error(f"Gemini translation failed: {e}. Falling back to free Google Translate for this batch.")
                results = self._google_translate(blocks, target_lang, source_lang)
                
        # Post-process with Czech glossary if target language is Czech
        if target_lang.lower() in ["cs", "cz", "czech"]:
            for bid, text in results.items():
                results[bid] = apply_czech_glossary(text)
                
        return results

    def _mock_translate(self, blocks: list[dict], target_lang: str) -> dict[str, str]:
        results = {}
        for block in blocks:
            text = block["text"]
            # To test font scaling, mock translation adds language prefix and a expansion suffix
            suffix = " [MOCK_TRANS_LONG_TEXT_FOR_SCALING]"
            results[block["id"]] = f"[{target_lang.upper()}] {text}{suffix}"
        return results

    def _google_translate(self, blocks: list[dict], target_lang: str, source_lang: str) -> dict[str, str]:
        """Translates text blocks using the free Google Translate API via deep-translator."""
        results = {}
        src = source_lang if source_lang != "auto" else "auto"
        
        # We group blocks into sub-batches to keep the total character length of each request under 4200.
        # This complies with Google Translate's free web query character limit (5000 chars).
        delimiter = "\n#===#\n"
        sub_batches = []
        current_sub_batch = []
        current_char_count = 0
        
        for b in blocks:
            text_len = len(b["text"])
            # If a single block is huge, put it in its own batch
            if text_len + len(delimiter) > 4000:
                if current_sub_batch:
                    sub_batches.append(current_sub_batch)
                    current_sub_batch = []
                    current_char_count = 0
                sub_batches.append([b])
            else:
                if current_char_count + text_len + len(delimiter) > 4200:
                    sub_batches.append(current_sub_batch)
                    current_sub_batch = [b]
                    current_char_count = text_len
                else:
                    current_sub_batch.append(b)
                    current_char_count += text_len + len(delimiter)
                    
        if current_sub_batch:
            sub_batches.append(current_sub_batch)
            
        # Translate each sub-batch using the joined delimiter approach
        for s_idx, s_batch in enumerate(sub_batches):
            texts_to_translate = [b["text"] for b in s_batch]
            merged_text = delimiter.join(texts_to_translate)
            
            try:
                translator = GoogleTranslator(source=src, target=target_lang)
                translated_result = translator.translate(merged_text)
                
                pattern = re.compile(r"\s*#===#\s*")
                translated_texts = pattern.split(translated_result)
                
                if len(translated_texts) == len(s_batch):
                    for b, trans_text in zip(s_batch, translated_texts):
                        results[b["id"]] = trans_text.strip() if trans_text else b["text"]
                    # Add a very small sleep between sub-batch requests to be polite
                    time.sleep(0.3)
                    continue
                else:
                    logger.warning(
                        f"Delimiter mismatch in sub-batch {s_idx + 1}: expected {len(s_batch)}, got {len(translated_texts)}. "
                        "Falling back to sequential translation for this sub-batch."
                    )
            except Exception as e:
                logger.error(f"Google Translate sub-batch {s_idx + 1} failed: {e}. Falling back to sequential.")
                
            # Fallback for this sub-batch: sequential translation
            try:
                translator = GoogleTranslator(source=src, target=target_lang)
                for b in s_batch:
                    trans_text = translator.translate(b["text"])
                    results[b["id"]] = trans_text if trans_text else b["text"]
                    time.sleep(0.3)
                # No return here, let it complete the remaining sub-batches
            except Exception as e:
                logger.error(f"Google Translate sequential sub-batch fallback failed: {e}. Using mock.")
                # If even this fails, write mock translations
                for b in s_batch:
                    results[b["id"]] = f"[{target_lang.upper()}] {b['text']}"
                    
        return results

    def _gemini_translate(self, blocks: list[dict], target_lang: str, source_lang: str) -> dict[str, str]:
        source_desc = f"from {source_lang}" if source_lang != "auto" else "automatically detected language"
        system_instruction = (
            "You are a professional technical translator specializing in service manuals.\n"
            f"Translate the provided text blocks precisely {source_desc} to the target language: '{target_lang}'.\n"
            "Maintain the tone, technical terms, and paragraph structures (like newlines or bullet points) of the original text.\n"
            "Return the translations in JSON format matching the specified schema."
        )
        
        # Prepare input data as JSON string for reliability
        input_data = json.dumps([{"id": b["id"], "text": b["text"]} for b in blocks], ensure_ascii=False)
        
        prompt = (
            f"Translate the following text blocks to target language: '{target_lang}'.\n"
            "Do not translate code snippets, mathematical formulas, or parts that should remain untranslated (like brand names or model codes) unless appropriate.\n"
            f"Input blocks:\n{input_data}"
        )
        
        max_retries = 5
        base_delay = 15.0
        response = None
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=TranslationResponse,
                        temperature=0.1,  # Low temperature for precise translation
                    )
                )
                break
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < max_retries - 1:
                        sleep_time = base_delay * (attempt + 1)
                        logger.warning(
                            f"Gemini API rate limit (429) hit. Waiting {sleep_time:.1f} seconds "
                            f"(Attempt {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(sleep_time)
                        continue
                raise e
        
        try:
            response_data = json.loads(response.text)
            results = {}
            for item in response_data.get("translations", []):
                results[item["id"]] = item["translated_text"]
                
            # Verify and fill missing values (safety check)
            for b in blocks:
                if b["id"] not in results:
                    logger.warning(f"Block ID {b['id']} missing in translation output. Falling back to original.")
                    results[b["id"]] = b["text"]
            return results
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}. Raw response text: {response.text}")
            raise e
