import re

file_path = r"C:\Users\jakub\Documents\AI\pdf_translator_pipeline\pdf_processor.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Modify check_fits
old_check_fits = '''def check_fits(rect: fitz.Rect, text: str, fontsize: float, fontname: str, fontfile: str = None) -> bool:
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
    
    return rc >= 0'''

new_check_fits = '''def check_fits(rect: fitz.Rect, text: str, fontsize: float, fontname: str, fontfile: str = None, doc_temp=None, page_temp=None) -> bool:
    """
    Checks if the given text fits completely inside the bounding rect
    at the specified font size and font name.
    """
    if rect.width <= 0 or rect.height <= 0:
        return False
        
    created_doc = False
    if doc_temp is None or page_temp is None:
        doc_temp = fitz.open()
        page_temp = doc_temp.new_page(width=rect.x1 + 100, height=rect.y1 + 100)
        created_doc = True
    
    if fontfile:
        try:
            page_temp.insert_font(fontname=fontname, fontfile=fontfile)
        except Exception:
            pass
            
    # insert_textbox returns remaining height (>= 0) if it fits, or negative if it overflows
    rc = page_temp.insert_textbox(rect, text, fontsize=fontsize, fontname=fontname)
    
    if created_doc:
        doc_temp.close()
    
    return rc >= 0'''

content = content.replace(old_check_fits, new_check_fits)

# 2. Modify find_fitting_fontsize signature
old_find_fitting = '''def find_fitting_fontsize(
    rect: fitz.Rect,
    text: str,
    fontname: str,
    initial_size: float,
    fontfile: str = None,
    min_size: float = None,
    max_size: float = MAX_FONT_SIZE,
    is_single_line: bool = False,
    is_table_cell: bool = False
) -> float:'''

new_find_fitting = '''def find_fitting_fontsize(
    rect: fitz.Rect,
    text: str,
    fontname: str,
    initial_size: float,
    fontfile: str = None,
    min_size: float = None,
    max_size: float = MAX_FONT_SIZE,
    is_single_line: bool = False,
    is_table_cell: bool = False,
    doc_temp=None,
    page_temp=None
) -> float:'''

content = content.replace(old_find_fitting, new_find_fitting)

# 3. Modify find_fitting_fontsize call to check_fits
old_check_call1 = '''    if check_fits(rect, text, initial_size, fontname, fontfile):'''
new_check_call1 = '''    if check_fits(rect, text, initial_size, fontname, fontfile, doc_temp, page_temp):'''
content = content.replace(old_check_call1, new_check_call1)

old_check_call2 = '''        if check_fits(rect, text, mid, fontname, fontfile):'''
new_check_call2 = '''        if check_fits(rect, text, mid, fontname, fontfile, doc_temp, page_temp):'''
content = content.replace(old_check_call2, new_check_call2)

# 4. In translate_pdf, create doc_temp around line 698
old_insertion_start = '''        # and removing text (text=0, which is the default).
        page.apply_redactions(images=0, graphics=0, text=0)
        
        # 4. Re-insert the translated text inside the redacted bounding boxes
        registered_fonts = set()'''

new_insertion_start = '''        # and removing text (text=0, which is the default).
        page.apply_redactions(images=0, graphics=0, text=0)
        
        # 4. Re-insert the translated text inside the redacted bounding boxes
        doc_temp = fitz.open()
        page_temp = doc_temp.new_page(width=page.rect.width + 100, height=page.rect.height + 100)
        registered_fonts = set()'''
content = content.replace(old_insertion_start, new_insertion_start)

# 5. Modify call to find_fitting_fontsize
old_find_call = '''            fitting_size = find_fitting_fontsize(
                rect,
                translated_text,
                custom_font_name,
                meta["fontsize"],
                fontfile=font_path,
                is_single_line=is_single_line,
                is_table_cell=is_table_cell
            )'''

new_find_call = '''            fitting_size = find_fitting_fontsize(
                rect,
                translated_text,
                custom_font_name,
                meta["fontsize"],
                fontfile=font_path,
                is_single_line=is_single_line,
                is_table_cell=is_table_cell,
                doc_temp=doc_temp,
                page_temp=page_temp
            )'''
content = content.replace(old_find_call, new_find_call)

# 6. Remove inner doc_temp loop
old_inner_doc = '''            if is_table_cell:
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
                
                if unused_height > 0.0:'''

new_inner_doc = '''            if is_table_cell:
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
                
                if unused_height > 0.0:'''
content = content.replace(old_inner_doc, new_inner_doc)

# 7. Close outer doc_temp at the end of the page loop
old_close = '''            page.insert_textbox(
                rect,
                translated_text,
                fontsize=fitting_size,
                fontname=custom_font_name,
                color=color,
                align=align
            )

    logger.info(f"Saving translated PDF to: {output_path}")'''

new_close = '''            page.insert_textbox(
                rect,
                translated_text,
                fontsize=fitting_size,
                fontname=custom_font_name,
                color=color,
                align=align
            )

        doc_temp.close()

    logger.info(f"Saving translated PDF to: {output_path}")'''
content = content.replace(old_close, new_close)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Modifications done.")
