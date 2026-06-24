import os
import re
import logging
import fitz
from pdf_translator_pipeline.config import (
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
    FONT_SCALING_PRECISION_ITERATIONS
)
from pdf_translator_pipeline.translator import (
    GeminiTranslator,
    ac_override_for,
)

logger = logging.getLogger(__name__)


def find_diagram_regions(
    page: fitz.Page,
    cell: float = 12.0,
    min_curves: int = 12,
    min_w: float = 55.0,
    min_h: float = 45.0,
    margin: float = 26.0,
) -> list[fitz.Rect]:
    """Detect chart/schematic/diagram regions on a page so their text can be left stock.

    Charts and schematics are built from hundreds-to-thousands of Bezier curves, while
    tables (which we DO want to translate) are almost pure straight lines. We rasterize
    curve-bearing vector paths onto a coarse grid, find connected components, drop small
    clusters (bullet icons, the logo), and return each remaining cluster's bbox expanded
    by a margin to also capture the axis/labels that sit just outside the plotted area.
    """
    rect = page.rect
    cols = int(rect.width / cell) + 2
    rows = int(rect.height / cell) + 2
    grid = [[0] * cols for _ in range(rows)]

    # cache all drawing rects (used later to grow regions over the chart's grid/frame)
    all_rects = []
    for d in page.get_drawings():
        items = d["items"]
        r = fitz.Rect(d["rect"])
        if r.is_empty:
            continue
        n_curves = sum(1 for it in items if it[0] in ("c", "l", "re"))
        # ignore page-spanning borders/backgrounds when growing regions
        if r.width <= 450 and r.height <= 560:
            all_rects.append(r)
        if n_curves == 0:
            continue
        c0 = max(0, int(r.x0 / cell)); c1 = min(cols - 1, int(r.x1 / cell))
        r0 = max(0, int(r.y0 / cell)); r1 = min(rows - 1, int(r.y1 / cell))
        for ry in range(r0, r1 + 1):
            for cx in range(c0, c1 + 1):
                grid[ry][cx] += n_curves

    visited = [[False] * cols for _ in range(rows)]
    regions: list[fitz.Rect] = []
    for ry in range(rows):
        for cx in range(cols):
            if grid[ry][cx] > 0 and not visited[ry][cx]:
                stack = [(ry, cx)]; visited[ry][cx] = True
                cells = []; total = 0
                while stack:
                    y, x = stack.pop()
                    cells.append((y, x)); total += grid[y][x]
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = y + dy, x + dx
                            if 0 <= ny < rows and 0 <= nx < cols and not visited[ny][nx] and grid[ny][nx] > 0:
                                visited[ny][nx] = True; stack.append((ny, nx))
                if total < min_curves:
                    continue
                xs = [x for _, x in cells]; ys = [y for y, _ in cells]
                raw = fitz.Rect(min(xs) * cell, min(ys) * cell,
                                (max(xs) + 1) * cell, (max(ys) + 1) * cell)
                if raw.width < min_w or raw.height < min_h:
                    continue  # bullet icon / logo / tiny glyph cluster, not a diagram

                # Grow over the chart's grid/frame lines safely.
                # Restrict expansion to relatively small drawing rects to prevent a single
                # page-spanning border from causing the region to engulf the whole page.
                region = fitz.Rect(raw)
                probe = raw + (-10, -10, 10, 10)
                for dr in all_rects:
                    # Only merge small-to-medium structural lines/boxes (e.g., < 250pt)
                    if dr.intersects(probe) and dr.width < 250 and dr.height < 250:
                        region |= dr
                        
                # Use a tighter margin (15.0 instead of 26.0) to avoid capturing nearby standard paragraphs
                tighter_margin = min(margin, 15.0)
                reg = (region + (-tighter_margin, -tighter_margin, tighter_margin, tighter_margin)) & rect
                regions.append(reg)
    return regions


def block_in_diagram(bbox, regions: list[fitz.Rect], frac: float = 0.5) -> bool:
    """True if at least `frac` of the block's area lies inside any diagram region."""
    br = fitz.Rect(bbox)
    if br.is_empty:
        return False
    barea = br.width * br.height
    if barea <= 0:
        return False
    for reg in regions:
        inter = br & reg
        if not inter.is_empty and (inter.width * inter.height) >= frac * barea:
            return True
    return False


# A factory model/part code, e.g. IMV-015CCAREDA, VMV-S121AREHSA1, IMV-022C1AREDA.
_CODE_LINE = re.compile(r"^[A-Z]{2,4}[\-–]?[A-Z0-9./]{3,}\.?$")


def is_factory_code_text(text: str) -> bool:
    """True if the block is (almost) entirely factory model codes, which must stay stock.

    These never need translation; leaving them untouched also keeps them byte-perfect
    and in their original position (no redact/re-insert repositioning).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    code_like = sum(
        1 for ln in lines
        if any(ch.isdigit() for ch in ln) and _CODE_LINE.match(ln.replace(" ", ""))
    )
    return code_like >= max(1, int(0.8 * len(lines)))


def is_vertical_text_block(block: dict) -> bool:
    """True if the block's text is rotated/vertical (writing direction not horizontal).

    Vertical text in these manuals is almost always a chart/diagram axis label; machine
    translation reflows it into garbage, so such blocks are left stock.
    """
    lines = block.get("lines", [])
    if not lines:
        return False
    vert = 0
    for ln in lines:
        dx, dy = ln.get("dir", (1.0, 0.0))
        if abs(dy) > abs(dx):
            vert += 1
    return vert > len(lines) / 2

def srgb_to_rgb(color_int: int) -> tuple[float, float, float]:
    """Converts a PyMuPDF sRGB integer color to an RGB tuple (0.0 to 1.0)."""
    # PyMuPDF represents colors as (r << 16) + (g << 8) + b
    if color_int is None or color_int < 0:
        return (0.0, 0.0, 0.0)  # Default to black
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return (r / 255.0, g / 255.0, b / 255.0)

def get_standard_font(font_name: str) -> str:
    """
    Maps original PDF font names to PyMuPDF's standard built-in fonts
    while preserving bold, italic, serif, sans-serif, and monospaced properties.
    """
    if not font_name:
        return "helv"
        
    font_name_lower = font_name.lower()
    is_bold = "bold" in font_name_lower or "black" in font_name_lower or "demi" in font_name_lower
    is_italic = "italic" in font_name_lower or "oblique" in font_name_lower or "slanted" in font_name_lower
    
    # Monospaced (Courier)
    if "courier" in font_name_lower or "mono" in font_name_lower or "consolas" in font_name_lower or "fixed" in font_name_lower:
        if is_bold and is_italic:
            return "cobi"
        elif is_bold:
            return "cobo"
        elif is_italic:
            return "coit"
        else:
            return "cour"
            
    # Serif (Times Roman)
    elif "times" in font_name_lower or "serif" in font_name_lower or "roman" in font_name_lower or "georgia" in font_name_lower:
        if is_bold and is_italic:
            return "tibi"
        elif is_bold:
            return "tibo"
        elif is_italic:
            return "tiit"
        else:
            return "tiro"
            
    # Sans-Serif / Default (Helvetica)
    else:
        if is_bold and is_italic:
            return "hebi"
        elif is_bold:
            return "hebo"
        elif is_italic:
            return "heit"
        else:
            return "helv"

def get_font_file_path(std_font: str) -> str | None:
    """Maps standard PDF font keys to absolute local Windows TTF file paths to support Czech diacritics."""
    font_map = {
        "helv": r"C:\Windows\Fonts\arial.ttf",
        "hebo": r"C:\Windows\Fonts\arialbd.ttf",
        "heit": r"C:\Windows\Fonts\ariali.ttf",
        "hebi": r"C:\Windows\Fonts\arialbi.ttf",
        
        "cour": r"C:\Windows\Fonts\cour.ttf",
        "cobo": r"C:\Windows\Fonts\courbd.ttf",
        "coit": r"C:\Windows\Fonts\couri.ttf",
        "cobi": r"C:\Windows\Fonts\courbi.ttf",
        
        "tiro": r"C:\Windows\Fonts\times.ttf",
        "tibo": r"C:\Windows\Fonts\timesbd.ttf",
        "tiit": r"C:\Windows\Fonts\timesi.ttf",
        "tibi": r"C:\Windows\Fonts\timesbi.ttf",
    }
    path = font_map.get(std_font)
    if path and os.path.exists(path):
        return path
        
    # Default fallback font supporting Latin extended character maps (Arial)
    default_path = r"C:\Windows\Fonts\arial.ttf"
    if os.path.exists(default_path):
        return default_path
        
    return None

def get_font_name_for_embedding(std_font: str) -> str:
    """Maps standard PDF font keys to custom font identifiers to bypass built-in PDF standard font mapping overrides."""
    mapping = {
        "helv": "Arial",
        "hebo": "Arial-Bold",
        "heit": "Arial-Italic",
        "hebi": "Arial-BoldItalic",
        
        "cour": "CourierNew",
        "cobo": "CourierNew-Bold",
        "coit": "CourierNew-Italic",
        "cobi": "CourierNew-BoldItalic",
        
        "tiro": "TimesNewRoman",
        "tibo": "TimesNewRoman-Bold",
        "tiit": "TimesNewRoman-Italic",
        "tibi": "TimesNewRoman-BoldItalic",
    }
    return mapping.get(std_font, std_font)

def bbox_overlaps(
    bbox1: tuple[float, float, float, float],
    bbox2: tuple[float, float, float, float],
    tolerance: float = 1.0
) -> bool:
    """Checks if two bounding boxes overlap with a tolerance margin to avoid float precision issues."""
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2
    
    # Calculate the overlap in both dimensions
    overlap_x = min(x1_1, x1_2) - max(x0_1, x0_2)
    overlap_y = min(y1_1, y1_2) - max(y0_1, y0_2)
    
    return overlap_x > tolerance and overlap_y > tolerance

def check_fits(rect: fitz.Rect, text: str, fontsize: float, fontname: str, fontfile: str = None) -> bool:
    """
    Checks if the given text fits completely inside the bounding rect
    at the specified font size and font name.
    """
    if rect.width <= 0 or rect.height <= 0:
        return False
        
    doc_temp = fitz.open()
    # Create page slightly larger than the bounding box to avoid canvas bounds errors
    page_temp = doc_temp.new_page(width=rect.x1 + 100, height=rect.y1 + 100)
    
    if fontfile:
        try:
            page_temp.insert_font(fontname=fontname, fontfile=fontfile)
        except Exception:
            pass
            
    # insert_textbox returns remaining height (>= 0) if it fits, or negative if it overflows
    rc = page_temp.insert_textbox(rect, text, fontsize=fontsize, fontname=fontname)
    doc_temp.close()
    
    return rc >= 0

def find_fitting_fontsize(
    rect: fitz.Rect,
    text: str,
    fontname: str,
    initial_size: float,
    fontfile: str = None,
    min_size: float = None,
    max_size: float = MAX_FONT_SIZE,
    is_single_line: bool = False,
    is_table_cell: bool = False
) -> float:
    """
    Finds the largest font size (up to initial_size) that fits the text
    within the bounding rectangle. If is_single_line is True, it ensures
    the text fits on a single line horizontally without wrapping.
    """
    if rect.width <= 0 or rect.height <= 0:
        return MIN_FONT_SIZE

    # Determine default min_size based on initial_size and type to avoid microscopic sizes
    # Allow table cells to scale down further to prevent truncation inside rigid cell boundaries
    if min_size is None:
        if is_table_cell:
            min_size = max(1.0, initial_size * 0.1)
        elif is_single_line:
            min_size = max(6.0, initial_size * 0.7)
        else:
            min_size = max(6.0, initial_size * 0.75)
            
    # Ensure min_size is not larger than initial_size
    min_size = min(min_size, initial_size)

    # Handle single-line constraint to prevent wrapping and overlapping
    if is_single_line:
        try:
            font = fitz.Font(fontname=fontname, fontfile=fontfile)
            width_at_size_1 = font.text_length(text, fontsize=1.0)
            if width_at_size_1 > 0:
                single_line_size = rect.width / width_at_size_1
                # Scale down slightly to avoid boundary wrapping due to float precision
                single_line_size *= 0.97
                fitting_size = min(initial_size, single_line_size)
                
                # Enforce vertical height limit to prevent vertical truncation
                # PyMuPDF insert_textbox requires exactly 1.673 * fontsize height to fit a line
                max_vertical_size = rect.height / 1.72
                fitting_size = min(fitting_size, max_vertical_size)
                
                fitting_size = max(min_size, min(max_size, fitting_size))
                return fitting_size
        except Exception as e:
            logger.error(f"Error calculating single-line font size: {e}")

    # Otherwise, height-based binary search for paragraphs
    if check_fits(rect, text, initial_size, fontname, fontfile):
        return initial_size

    low = min_size
    high = initial_size
    best_size = min_size
    
    for _ in range(FONT_SCALING_PRECISION_ITERATIONS):
        mid = (low + high) / 2.0
        if check_fits(rect, text, mid, fontname, fontfile):
            best_size = mid
            low = mid  # Try larger size
        else:
            high = mid  # Try smaller size
            
    # Apply a 5% safety scale-down to paragraphs to prevent marginal wrapping/overflow
    return max(min_size, best_size * 0.95)

def translate_pdf(
    input_path: str,
    output_path: str,
    translator: GeminiTranslator,
    target_lang: str,
    source_lang: str = "auto",
    batch_size: int = 30
) -> None:
    """Runs the PDF parsing, translation, redaction, and re-insertion pipeline."""
    logger.info(f"Opening input PDF: {input_path}")
    doc = fitz.open(input_path)
    
    blocks_to_translate = []
    block_metadata = {}
    
    # Step 1: Parsing page text blocks and filtering tables/images
    for page_idx, page in enumerate(doc):
        # Detect chart/schematic/diagram regions; text inside these is left stock
        # (never translated or redacted) so diagrams stay exactly as in the original.
        diagram_regions = find_diagram_regions(page)

        # Extract all table bounding boxes and cells
        tables = list(page.find_tables())
        
        # Build cell rect list with metadata
        table_cells = []
        for table_idx, table in enumerate(tables):
            for cell_idx, cell in enumerate(table.cells):
                if cell:
                    table_cells.append({
                        "rect": fitz.Rect(cell),
                        "table_idx": table_idx,
                        "cell_idx": cell_idx,
                        "spans": [] # To hold matched spans
                    })
        
        # Get page text dictionary
        page_dict = page.get_text("dict")

        # 1-pre. Pre-process special blocks BEFORE table detection. Their spans are
        # "consumed" so later passes skip them:
        #   - AC product type-name headers -> emitted as their own block (own bbox,
        #     widened to the column edge) so they aren't merged with factory-code lists
        #     and so the Czech override fits on one line.
        #   - Vertical/rotated text (chart axis labels) -> left stock, never translated.
        consumed_ids = set()
        page_mid = page.rect.width / 2.0
        for block_idx, block in enumerate(page_dict.get("blocks", [])):
            if block.get("type") != 0:
                continue
            block_spans = [s for line in block.get("lines", []) for s in line.get("spans", [])]
            joined = " ".join(
                "".join(s.get("text", "") for s in line.get("spans", []))
                for line in block.get("lines", [])
            ).strip()
            if not joined:
                continue

            if ac_override_for(joined) is not None:
                # this whole block is an AC type-name header
                bb = fitz.Rect(block["bbox"])
                right = (page_mid - 8.0) if bb.x0 < page_mid - 10 else (page.rect.width - 18.0)
                header_bbox = fitz.Rect(bb.x0, bb.y0, max(bb.x1, right), bb.y1)
                dom = max(block_spans, key=lambda s: len(s.get("text", "")), default=None)
                if dom is None:
                    continue
                block_id = f"{page_idx}_acname_{block_idx}"
                blocks_to_translate.append({"id": block_id, "text": joined})
                block_metadata[block_id] = {
                    "page_idx": page_idx,
                    "bbox": tuple(header_bbox),
                    "fontname": dom.get("font", "helv"),
                    "fontsize": dom.get("size", 10.0),
                    "color_int": dom.get("color", 0),
                    "text": joined,
                    "is_single_line": True,
                    "is_table_cell": False,
                }
                for s in block_spans:
                    consumed_ids.add(id(s))
            elif is_vertical_text_block(block):
                # rotated axis label: leave completely stock
                for s in block_spans:
                    consumed_ids.add(id(s))

        # Keep track of matched spans by their object ID to avoid duplicate extraction.
        # Seed with the consumed (AC header + vertical label) spans so later passes skip them.
        matched_span_ids = set(consumed_ids)

        # 1a. Map each span on the page to a table cell if it falls inside
        for block_idx, block in enumerate(page_dict.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for line_idx, line in enumerate(block.get("lines", [])):
                for span_idx, span in enumerate(line.get("spans", [])):
                    if id(span) in consumed_ids:
                        continue  # AC header / vertical-label span, handled separately
                    span_rect = fitz.Rect(span["bbox"])
                    matched_cell = None
                    max_overlap_area = 0.0
                    
                    for cell_info in table_cells:
                        intersection = span_rect & cell_info["rect"]
                        if not intersection.is_empty:
                            area = intersection.width * intersection.height
                            if area > 1.0:  # Require at least 1 square point of overlap
                                if area > max_overlap_area:
                                    max_overlap_area = area
                                    matched_cell = cell_info
                                    
                    if matched_cell:
                        # Store block index and line index to reconstruct lines properly
                        matched_cell["spans"].append((block_idx, line_idx, span))
                        matched_span_ids.add(id(span))
                        
        # 1b. Reconstruct text and metadata for each matched cell
        for cell_info in table_cells:
            if not cell_info["spans"]:
                continue
                
            # To fix PyMuPDF hallucinating massive merged cells across multiple visual columns,
            # we cluster the spans inside the cell based on their horizontal overlap!
            # If two spans are separated by a huge horizontal gap, they fall into separate columns.
            columns = [] # List of [min_x, max_x, spans_list]
            for block_idx, line_idx, span in cell_info["spans"]:
                s_rect = fitz.Rect(span["bbox"])
                matched_col = None
                for col in columns:
                    # Overlap horizontally, or within 10 points
                    if not (s_rect.x1 < col[0] - 10.0 or s_rect.x0 > col[1] + 10.0):
                        matched_col = col
                        break
                if matched_col:
                    matched_col[0] = min(matched_col[0], s_rect.x0)
                    matched_col[1] = max(matched_col[1], s_rect.x1)
                    matched_col[2].append((block_idx, line_idx, span))
                else:
                    columns.append([s_rect.x0, s_rect.x1, [(block_idx, line_idx, span)]])
                    
            # Process each un-merged visual column independently!
            for col_idx, col in enumerate(columns):
                col_spans = col[2]
                
                # Group spans by their original block & line index to preserve reading order
                from collections import defaultdict
                cell_line_groups = defaultdict(list)
                for block_idx, line_idx, span in col_spans:
                    cell_line_groups[(block_idx, line_idx)].append(span)
                    
                # Sort keys to preserve correct top-to-bottom and left-to-right flow
                sorted_keys = sorted(cell_line_groups.keys())
                cell_lines = []
                dominant_span = None
                max_span_len = -1
                
                for key in sorted_keys:
                    line_spans = cell_line_groups[key]
                    line_text = "".join(s.get("text", "") for s in line_spans)
                    if line_text.strip():
                        cell_lines.append(line_text.strip())
                        
                    for s in line_spans:
                        s_text = s.get("text", "")
                        if len(s_text) > max_span_len:
                            dominant_span = s
                            max_span_len = len(s_text)
                            
                cell_text = "\n".join(cell_lines).strip()
                if not cell_text or not dominant_span:
                    continue

                # We intentionally do not check block_in_diagram here because some pages
                # contain valid tables embedded directly inside massive schematic regions.
                # If find_tables() detects it as a table, we trust it and translate it.

                # Factory code lists (IMV-..., VMV-...) need no translation; leave them stock
                if is_factory_code_text(cell_text):
                    continue

                block_id = f"{page_idx}_table_{cell_info['table_idx']}_cell_{cell_info['cell_idx']}_col_{col_idx}"
                blocks_to_translate.append({"id": block_id, "text": cell_text})
                
                first_span_rect = fitz.Rect(col_spans[0][2]["bbox"])
                cell_rect = fitz.Rect(cell_info["rect"])
                
                # Bulletproof lock: Force the cell's left boundary to EXACTLY match the
                # X-coordinate of the original text. This prevents text from shifting left.
                locked_x0 = first_span_rect.x0
                cell_rect.x0 = locked_x0
                        
                block_metadata[block_id] = {
                    "page_idx": page_idx,
                    "bbox": tuple(cell_rect),
                    "fontname": dominant_span.get("font", "helv"),
                    "fontsize": dominant_span.get("size", 10.0),
                    "color_int": dominant_span.get("color", 0),
                    "text": cell_text,
                    "is_single_line": len(cell_lines) == 1,
                    "is_table_cell": True,
                    "align": 0
                }
            
        # 1c. Reconstruct non-table text blocks from unmatched spans
        for block_idx, block in enumerate(page_dict.get("blocks", [])):
            if block.get("type") != 0:
                continue
                
            # Filter lines to only those with unmatched spans
            valid_lines = []
            for line_idx, line in enumerate(block.get("lines", [])):
                line_spans = [s for s in line.get("spans", []) if id(s) not in matched_span_ids]
                if line_spans:
                    valid_lines.append((line_idx, line, line_spans))
                    
            if not valid_lines:
                continue
                
            # Detect if this block is actually a column of separate items (like a BOM)
            # by checking the vertical gaps between lines. Normal paragraphs have tiny gaps.
            is_column_of_data = False
            for i in range(len(valid_lines) - 1):
                y1 = fitz.Rect(valid_lines[i][1]["bbox"]).y1
                y0_next = fitz.Rect(valid_lines[i+1][1]["bbox"]).y0
                if y0_next - y1 > 4.0:
                    is_column_of_data = True
                    break
                    
            # If it's a column of data, treat each line as its own separate block
            # so that it gets translated and drawn at its exact original Y coordinate!
            groups_to_process = []
            if is_column_of_data:
                for line_idx, line, line_spans in valid_lines:
                    groups_to_process.append([(line_idx, line, line_spans)])
            else:
                groups_to_process.append(valid_lines)
                
            for group_idx, group in enumerate(groups_to_process):
                group_lines = []
                dominant_span = None
                max_span_len = -1
                group_bbox = None
                
                for _, line, line_spans in group:
                    line_text = "".join(s.get("text", "") for s in line_spans)
                    if line_text.strip():
                        group_lines.append(line_text.strip())
                        if group_bbox is None:
                            group_bbox = fitz.Rect(line["bbox"])
                        else:
                            group_bbox |= fitz.Rect(line["bbox"])
                        
                    for s in line_spans:
                        s_text = s.get("text", "")
                        if len(s_text) > max_span_len:
                            dominant_span = s
                            max_span_len = len(s_text)
                            
                block_text = "\n".join(group_lines).strip()
                if not block_text or not dominant_span:
                    continue
                    
                # Skip text that sits inside a chart/schematic/diagram region
                if block_in_diagram(group_bbox, diagram_regions) and not ac_override_for(block_text):
                    continue

                # Factory code lists need no translation; leave them stock.
                if is_factory_code_text(block_text):
                    continue

                block_id = f"{page_idx}_block_{block_idx}_g_{group_idx}"
                blocks_to_translate.append({"id": block_id, "text": block_text})
                
                block_metadata[block_id] = {
                    "page_idx": page_idx,
                    "bbox": tuple(group_bbox),
                    "fontname": dominant_span.get("font", "helv"),
                    "fontsize": dominant_span.get("size", 10.0),
                    "color_int": dominant_span.get("color", 0),
                    "text": block_text,
                    "is_single_line": len(group_lines) == 1,
                    "is_table_cell": False
                }
    logger.info(f"Found {len(blocks_to_translate)} text blocks to translate.")

    # Step 2: Translate in batches
    translated_blocks = {}

    # Pre-translation AC type-name override: blocks that are official AC product type
    # names get the exact Czech term and are NOT sent to the MT engine (which mangles
    # them). Only for Czech targets; factory codes never match so they pass through.
    if target_lang.lower() in ["cs", "cz", "czech"]:
        remaining = []
        overridden = 0
        for b in blocks_to_translate:
            cz = ac_override_for(b["text"])
            if cz is not None:
                translated_blocks[b["id"]] = cz
                overridden += 1
            else:
                remaining.append(b)
        if overridden:
            logger.info(f"Applied {overridden} AC type-name overrides (kept stock factory codes).")
        blocks_to_translate = remaining

    for i in range(0, len(blocks_to_translate), batch_size):
        batch = blocks_to_translate[i : i + batch_size]
        logger.info(f"Translating batch {i // batch_size + 1} ({len(batch)} blocks)...")
        translations = translator.translate_batch(batch, target_lang, source_lang)
        translated_blocks.update(translations)
        
        # Sleep briefly between batches if using free Google Translate to avoid rate limiting
        if translator.engine == "google" and i + batch_size < len(blocks_to_translate):
            import time
            time.sleep(2.0)
        
    # Step 3 & 4: Redaction and Re-insertion
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        
        # Get blocks corresponding to the current page
        page_block_ids = [bid for bid in translated_blocks.keys() if block_metadata[bid]["page_idx"] == page_idx]
        
        if not page_block_ids:
            continue
            
        # 3a. Add redaction annotations for all text blocks on this page
        # Note: Do not specify a fill color (leave fill=None) so background is preserved transparently.
        for bid in page_block_ids:
            meta = block_metadata[bid]
            rect = fitz.Rect(meta["bbox"])
            page.add_redact_annot(rect)
            
        # 3b. Apply redactions, preserving images (images=0) and vector graphics/drawings (graphics=0)
        # and removing text (text=0, which is the default).
        page.apply_redactions(images=0, graphics=0, text=0)
        
        # 4. Re-insert the translated text inside the redacted bounding boxes
        registered_fonts = set()
        for bid in page_block_ids:
            meta = block_metadata[bid]
            rect = fitz.Rect(meta["bbox"])
            translated_text = translated_blocks[bid]
            
            # Map font to a standard PDF font
            std_font = get_standard_font(meta["fontname"])
            custom_font_name = get_font_name_for_embedding(std_font)
            
            # Find the local system TTF path for this font to support Czech diacritics
            font_path = get_font_file_path(std_font)
            
            # Register font on the page if not already done
            if font_path and custom_font_name not in registered_fonts:
                try:
                    page.insert_font(fontname=custom_font_name, fontfile=font_path)
                    registered_fonts.add(custom_font_name)
                except Exception as e:
                    logger.error(f"Failed to register font {custom_font_name} ({font_path}) on page {page_idx + 1}: {e}")
            
            is_table_cell = meta.get("is_table_cell", False)
            is_single_line = meta.get("is_single_line", False)
            
            # Adjust bounding box based on block type before size calculation to prevent overlap & wrap
            if is_table_cell:
                # Allow table cells to wrap to prevent extreme font shrinking
                is_single_line = False
                
                # Shrink cell bbox slightly to keep text away from cell borders
                pad_x = min(1.5, rect.width * 0.1)
                # Only apply vertical padding if cell has sufficient height to prevent truncation
                pad_y = min(0.5, rect.height * 0.05) if rect.height >= 12.0 else 0.0
                rect.x0 += pad_x
                rect.y0 += pad_y
                rect.x1 -= pad_x
                rect.y1 -= pad_y
                
                # Removed horizontal expansion to prevent overlapping into adjacent columns
            elif is_single_line:
                # Expand single-line text boxes horizontally to prevent unnecessary wrapping/shrinkage
                rect.x0 -= 1.5
                rect.x1 += 1.5
            else:
                pass

            # Calculate the fitting font size using the font scaling binary search
            fitting_size = find_fitting_fontsize(
                rect,
                translated_text,
                custom_font_name,
                meta["fontsize"],
                fontfile=font_path,
                is_single_line=is_single_line,
                is_table_cell=is_table_cell
            )
            
            # Removed infinite horizontal expansion for single-line blocks to prevent overlapping
            
            # Convert text color
            color = srgb_to_rgb(meta["color_int"])
            align = meta.get("align", 0)
            
            # Vertically center all table cells (single or multi-line) using a dry-run
            if is_table_cell:
                doc_temp = fitz.open()
                page_temp = doc_temp.new_page(width=rect.x1 + 100, height=rect.y1 + 100)
                if font_path and custom_font_name in registered_fonts:
                    try:
                        page_temp.insert_font(fontname=custom_font_name, fontfile=font_path)
                    except Exception:
                        pass
                
                unused_height = page_temp.insert_textbox(
                    rect,
                    translated_text,
                    fontsize=fitting_size,
                    fontname=custom_font_name,
                    align=align
                )
                doc_temp.close()
                
                if unused_height > 0.0:
                    shift = unused_height / 2.0
                    rect.y0 += shift
                    rect.y1 += shift
                    
            # Insert the translated text box
            page.insert_textbox(
                rect,
                translated_text,
                fontsize=fitting_size,
                fontname=custom_font_name,
                color=color,
                align=align
            )
            
    # Save the resulting translated PDF
    logger.info(f"Saving translated PDF to: {output_path}")
    doc.save(output_path)
    doc.close()
    logger.info("Translation complete!")
