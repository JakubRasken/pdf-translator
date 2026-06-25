import fitz

def debug():
    pdf_path = r"C:\Users\jakub\Downloads\VIVAX_prelozit\SERVICE MANUAL\VMV-S121_140_155AREHDA3 -- SM.pdf"
    doc = fitz.open(pdf_path)
    page = doc[12]  # Page 13

    # Draw strict tables in RED
    tables = page.find_tables(strategy="lines_strict")
    for table in tables:
        for cell in table.cells:
            rect = fitz.Rect(cell)
            page.draw_rect(rect, color=(1, 0, 0), width=1.0)
            
    # Draw standard text blocks in BLUE
    blocks = page.get_text("dict")["blocks"]
    for b in blocks:
        if b["type"] == 0:
            page.draw_rect(fitz.Rect(b["bbox"]), color=(0, 0, 1), width=0.5, dashes="[2] 0")
            
    out_path = r"C:\Users\jakub\Downloads\VIVAX_prelozit\SERVICE MANUAL\translated\debug_tables_strict.pdf"
    doc.save(out_path)
    print(f"Saved debug PDF to {out_path}")

if __name__ == "__main__":
    debug()
