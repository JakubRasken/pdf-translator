import fitz
import sys
import os

def find_diagram_regions_test(page, min_curves=4):
    from pdf_processor import find_diagram_regions
    return find_diagram_regions(page, min_curves=min_curves)

def inspect(pdf_path):
    doc = fitz.open(pdf_path)
    page_11 = doc[10] # page 11 physical
    
    print("--- PAGE 11 DRAWINGS ---")
    drawings = page_11.get_drawings()
    print(f"Total drawings: {len(drawings)}")
    curve_count = 0
    line_count = 0
    rect_count = 0
    for d in drawings:
        for item in d["items"]:
            if item[0] == "c": curve_count += 1
            if item[0] == "l": line_count += 1
            if item[0] == "re": rect_count += 1
    print(f"Curves: {curve_count}, Lines: {line_count}, Rects: {rect_count}")

if __name__ == "__main__":
    pdf_path = sys.argv[1]
    inspect(pdf_path)
