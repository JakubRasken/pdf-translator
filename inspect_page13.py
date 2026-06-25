import fitz
import sys

def inspect(pdf_path):
    doc = fitz.open(pdf_path)
    page_idx = 12  # 13th page of the file
    page = doc[page_idx]
    
    print(f"--- PAGE INDEX {page_idx} (Physical Page {page_idx+1}) ---")
    
    # 1. Check Tables
    tables = list(page.find_tables())
    print(f"Default find_tables: {len(tables)} tables")
    
    tables_lines = list(page.find_tables(strategy="lines"))
    print(f"strategy='lines': {len(tables_lines)} tables")
    
    tables_text = list(page.find_tables(strategy="text"))
    print(f"strategy='text': {len(tables_text)} tables")

    # 2. Check Drawings
    drawings = page.get_drawings()
    curve_count = line_count = rect_count = 0
    for d in drawings:
        for item in d["items"]:
            if item[0] == "c": curve_count += 1
            if item[0] == "l": line_count += 1
            if item[0] == "re": rect_count += 1
    print(f"Drawings: {len(drawings)} (c:{curve_count}, l:{line_count}, re:{rect_count})")
    
    # 3. Check Diagram Regions
    from pdf_processor import find_diagram_regions
    regions = find_diagram_regions(page)
    print(f"Diagram Regions detected: {len(regions)}")
    for r in regions:
        print(f"  {r}")
        
    # 4. Save visual
    for r in regions:
        page.draw_rect(r, color=(0,0,1), width=2)
    for t in tables_text:
        page.draw_rect(t.bbox, color=(1,0,0), width=1)
    doc.save("scratch/inspect_page_13.pdf")
    print("Saved scratch/inspect_page_13.pdf")

if __name__ == "__main__":
    pdf_path = sys.argv[1]
    inspect(pdf_path)
