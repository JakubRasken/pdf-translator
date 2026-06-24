import sys
import os
import fitz  # PyMuPDF
try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def compare_pdfs(pdf_a: str, pdf_b: str, out_dir: str):
    print(f"Comparing {pdf_a} vs {pdf_b}")
    
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    doc_a = fitz.open(pdf_a)
    doc_b = fitz.open(pdf_b)
    
    pages_to_check = min(len(doc_a), len(doc_b))
    
    for page_num in range(pages_to_check):
        page_a = doc_a[page_num]
        page_b = doc_b[page_num]
        
        pix_a = page_a.get_pixmap(dpi=150)
        pix_b = page_b.get_pixmap(dpi=150)
        
        out_a_path = os.path.join(out_dir, f"page_{page_num+1}_a.png")
        out_b_path = os.path.join(out_dir, f"page_{page_num+1}_b.png")
        
        pix_a.save(out_a_path)
        pix_b.save(out_b_path)
        
        if HAS_PIL:
            img_a = Image.open(out_a_path).convert("RGB")
            img_b = Image.open(out_b_path).convert("RGB")
            
            # Compute difference
            diff = ImageChops.difference(img_a, img_b)
            # Create a composite to highlight differences
            # Red will highlight the changes
            diff_mask = diff.convert("L").point(lambda x: 255 if x > 10 else 0)
            red_layer = Image.new("RGB", img_a.size, (255, 0, 0))
            highlighted = Image.composite(red_layer, img_a, diff_mask)
            
            diff_path = os.path.join(out_dir, f"page_{page_num+1}_diff.png")
            highlighted.save(diff_path)
            print(f"Page {page_num+1}: Difference highlighted at {diff_path}")
        else:
            print(f"Page {page_num+1}: Saved images. Install Pillow for difference highlighting.")
            
    doc_a.close()
    doc_b.close()
    print("Comparison complete!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python vision_check.py <original.pdf> <translated.pdf> [output_dir]")
        sys.exit(1)
        
    pdf1 = sys.argv[1]
    pdf2 = sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else "vision_diff"
    
    compare_pdfs(pdf1, pdf2, out)
