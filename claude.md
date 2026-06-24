# PDF Translation Pipeline - Context & Guidelines

## 🎯 Goal
The objective is to translate a highly technical AC Service Manual (e.g., Vivax) from English to Czech while **perfectly preserving** the original PDF layout, tables, formatting, and schematics.

## 🚫 What NOT To Do (User Preferences & Constraints)
*   **Do NOT edit or translate diagrams/schematics/flowcharts.** The text inside them often breaks or overlaps. They must be kept completely stock (in English).
*   **Do NOT break tables.**
*   **Do NOT overlap text.** Use proper bounding boxes and text wrapping (`insert_textbox` instead of `insert_text`).
*   **Do NOT join paragraph lines with spaces (`" ".join`).** While it seems like a good idea to fix split sentences for the translation API, it completely destroys the PyMuPDF text block rendering layout and ruins tables/diagrams. Stick to `"\n".join` for block extraction.
*   **Do NOT use automatic AC terminology.** Always map specific AC model types (e.g., "COMPACT FOUR-WAY CASSETTE") to the exact official Czech translations from the provided Excel file.

## ⚙️ How It Works (The Pipeline)
1.  **Text Extraction (`pdf_processor.py`):** Uses PyMuPDF (`fitz`) to extract text blocks (`type == 0`). It captures the bounding box (`bbox`), font size, color, and text content.
2.  **Translation (`translator.py`):** Sends the extracted blocks to an API (Google Translate or Gemini) in batches to get the Czech text.
3.  **Redaction & Insertion:** The original text bounding box is redacted. The new translated text is inserted back into the exact same bounding box using a binary-search algorithm (`find_fitting_fontsize`) to dynamically scale the font so it fits without overflowing.
4.  **Post-Processing Scripts (`scratch/`):** 
    *   `fix_ac_excel.py`: A manual script used to strictly overwrite AC names on the specification pages using `insert_textbox` to enforce correct wrapping.
    *   `run_overlay.py`: A script designed to restore original diagrams.

## ⚠️ Known Issues (What DOES NOT Work)
*   **Fixing "Split Sentences":** Because PDFs use absolute positioning, paragraphs are often extracted as hard-broken lines. Re-joining them with spaces breaks the bounding box mapping, causing massive layout corruption. We have to live with split sentences or fix them manually.
*   **Diagram Overlay Collateral Damage:** 
    *   *The Problem:* To avoid translating diagram labels, we run a script (`run_overlay2.py`) that finds areas with many vector drawings, creates a bounding box around them, and pastes the original English diagram on top of the translated PDF. 
    *   *Why it fails:* If a page contains **both** a large diagram **and** a block of standard text, the diagram bounding box expansion sometimes engulfs the entire page. When the stock diagram is overlaid, it overwrites the newly translated Czech text block with the old English text. 
    *   *Future Fix Needed:* The overlay bounding box logic needs to be much tighter, or text blocks outside the explicit diagram area must be explicitly protected.
