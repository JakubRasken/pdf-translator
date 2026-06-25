import fitz
import sys

def inspect(pdf_path):
    doc = fitz.open(pdf_path)
    page_idx = 12  # 13th physical page
    page = doc[page_idx]
    
    print("Testing table strategies on Page 13...")
    
    strategies = [
        {"name": "default", "kwargs": {}},
        {"name": "lines", "kwargs": {"strategy": "lines"}},
        {"name": "lines_strict", "kwargs": {"strategy": "lines_strict"}},
        {"name": "text", "kwargs": {"strategy": "text"}},
        {"name": "lines_tolerant", "kwargs": {"strategy": "lines", "intersection_y_tolerance": 15, "intersection_x_tolerance": 15}},
    ]
    
    for s in strategies:
        try:
            tables = list(page.find_tables(**s["kwargs"]))
            print(f"\n--- Strategy: {s['name']} ---")
            print(f"Found {len(tables)} tables.")
            for i, t in enumerate(tables):
                # Count cells that are primarily on the left side of the table
                left_cells = [c for c in t.cells if c and c[0] < t.bbox[0] + (t.bbox[2]-t.bbox[0])*0.3]
                print(f"  Table {i}: BBox {t.bbox}, Total Cells: {len(t.cells)}, Left-column cells: {len(left_cells)}")
        except Exception as e:
            print(f"Strategy {s['name']} failed: {e}")

if __name__ == "__main__":
    pdf_path = sys.argv[1]
    inspect(pdf_path)
