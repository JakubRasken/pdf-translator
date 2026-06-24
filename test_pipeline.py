import os
import sys
import fitz

def create_test_pdf(filepath: str):
    """Generates a structured test PDF mimicking a service manual page."""
    print(f"Generating test PDF at: {filepath}")
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    
    # 1. Add standard text blocks
    page.insert_textbox(
        fitz.Rect(50, 50, 550, 100),
        "SERVICE MANUAL - MODEL 2026-X\nIMPORTANT SAFETY WARNINGS",
        fontsize=16,
        fontname="hebo",
        color=(0, 0.1, 0.4)
    )
    
    page.insert_textbox(
        fitz.Rect(50, 120, 550, 180),
        "Safety instructions must be followed strictly to prevent equipment damage and personal injury. Read all warnings before starting the maintenance procedure.",
        fontsize=11,
        fontname="helv",
        color=(0.1, 0.1, 0.1)
    )
    
    # 2. Add a vector background shape (warning banner)
    # Background fill
    page.draw_rect(
        fitz.Rect(50, 200, 550, 250),
        color=(0.9, 0.2, 0.2),
        fill=(1.0, 0.9, 0.9),
        width=1.5
    )
    # Text on vector shape
    page.insert_textbox(
        fitz.Rect(60, 210, 540, 240),
        "DANGER: HIGH VOLTAGE. DISCONNECT POWER SOURCE BEFORE OPENING COVER.",
        fontsize=10,
        fontname="hebo",
        color=(0.8, 0, 0)
    )
    
    # 3. Add a Table (grid lines + text)
    # Table border and cells
    page.draw_rect(fitz.Rect(50, 300, 350, 420), color=(0.5, 0.5, 0.5), width=1)
    page.draw_line((50, 340), (350, 340), color=(0.5, 0.5, 0.5), width=1)
    page.draw_line((50, 380), (350, 380), color=(0.5, 0.5, 0.5), width=1)
    page.draw_line((200, 300), (200, 420), color=(0.5, 0.5, 0.5), width=1)
    
    # Table Header text
    page.insert_textbox(fitz.Rect(60, 310, 190, 330), "Parameter", fontsize=10, fontname="hebo")
    page.insert_textbox(fitz.Rect(210, 310, 340, 330), "Specification", fontsize=10, fontname="hebo")
    
    # Table Row 1 text
    page.insert_textbox(fitz.Rect(60, 350, 190, 370), "Input Voltage", fontsize=10, fontname="helv")
    page.insert_textbox(fitz.Rect(210, 350, 340, 370), "220V - 240V AC", fontsize=10, fontname="helv")
    
    # Table Row 2 text
    page.insert_textbox(fitz.Rect(60, 390, 190, 410), "Max Current", fontsize=10, fontname="helv")
    page.insert_textbox(fitz.Rect(210, 390, 340, 410), "16 Amperes", fontsize=10, fontname="helv")
    
    # Save the file
    doc.save(filepath)
    doc.close()
    print("Test PDF generated successfully.")

def verify_translated_pdf(input_path: str, output_path: str):
    """Verifies that the translation pipeline ran correctly and matched criteria."""
    print("Verifying translated PDF...")
    
    # Open both PDFs
    in_doc = fitz.open(input_path)
    out_doc = fitz.open(output_path)
    
    in_page = in_doc[0]
    out_page = out_doc[0]
    
    # 1. Compare text contents
    in_text = in_page.get_text("text").replace("\xa0", " ").replace("\xad", "-")
    out_text = out_page.get_text("text").replace("\xa0", " ").replace("\xad", "-")
    
    print("-" * 40)
    print("ORIGINAL TEXT:\n", in_text.strip())
    print("-" * 40)
    print("TRANSLATED TEXT:\n", out_text.strip())
    print("-" * 40)
    
    # 2. Check if table text is translated
    # The table has 'Parameter', 'Specification', 'Input Voltage', '220V - 240V AC'
    table_keywords = ["Parameter", "Specification", "Input Voltage", "220V - 240V AC", "Max Current", "16 Amperes"]
    for kw in table_keywords:
        assert f"[ES] {kw}" in out_text, f"Table keyword '{kw}' was not translated, but table contents must be translated."
        print(f"OK: Table cell text '{kw}' correctly translated.")
        
    # 3. Check if warning text on vector background is translated
    danger_kw = "DANGER: HIGH VOLTAGE."
    assert f"[ES] {danger_kw}" in out_text, f"Translated warning text not found."
    # Ensure it only exists as part of the translated text
    assert out_text.count(danger_kw) == out_text.count(f"[ES] {danger_kw}"), f"Original text '{danger_kw}' was not fully redacted/removed."
    print("OK: Danger banner text was translated correctly and original text was redacted.")
    
    # 4. Check that standard text is translated
    title_kw = "SERVICE MANUAL"
    assert f"[ES] {title_kw}" in out_text, f"Translated title not found."
    assert out_text.count(title_kw) == out_text.count(f"[ES] {title_kw}"), f"Original title '{title_kw}' was not fully redacted/removed."
    print("OK: Standard paragraphs translated successfully and original text was redacted.")
    
    # 5. Check vector drawings
    # Both input and output pages should have the warning rectangle and table grid lines.
    in_drawings = in_page.get_drawings()
    out_drawings = out_page.get_drawings()
    
    # The drawings should be identical
    assert len(in_drawings) == len(out_drawings), f"Drawings count changed! In: {len(in_drawings)}, Out: {len(out_drawings)}"
    print(f"OK: Vector graphics preserved (count: {len(out_drawings)} matches original).")
    
    # 6. Check font sizes for auto-scaling
    # Let's inspect the font size of the first block in the translated output
    out_dict = out_page.get_text("dict")
    for block in out_dict.get("blocks", []):
        if block.get("type") == 0:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    # For the title block: originally 16, now with mock suffix it's much longer.
                    # Let's check if the size was scaled down.
                    if "[ES] SERVICE MANUAL" in span["text"]:
                        original_size = 16.0
                        fitting_size = span["size"]
                        print(f"Title Block Font Size: Original={original_size} -> Translated={fitting_size:.2f}")
                        assert fitting_size < original_size, f"Font size did not scale down! Original: {original_size}, Fitted: {fitting_size}"
                        print("OK: Font scaling algorithm successfully adjusted font size to fit bounds.")
                        break

    in_doc.close()
    out_doc.close()
    print("All verification assertions PASSED!")

if __name__ == "__main__":
    input_file = "test_manual.pdf"
    output_file = "test_manual_translated.pdf"
    
    # Generate test manual
    create_test_pdf(input_file)
    
    # Run pipeline via command line argument parser
    from cli import main as cli_main
    
    # Save original arguments and mock argv
    old_argv = sys.argv
    sys.argv = [
        "cli.py",
        input_file,
        output_file,
        "--target-lang", "es",
        "--mock",
        "--batch-size", "10"
    ]
    
    print("Running CLI translation pipeline...")
    try:
        cli_main()
    except Exception as e:
        print(f"CLI failed to run: {e}")
        sys.exit(1)
    finally:
        sys.argv = old_argv
        
    # Verify results
    try:
        verify_translated_pdf(input_file, output_file)
    except AssertionError as e:
        print(f"Verification FAILED: {e}")
        sys.exit(1)
        
    # Clean up test files
    if os.path.exists(input_file):
        os.remove(input_file)
    if os.path.exists(output_file):
        os.remove(output_file)
        
    print("Pipeline test completed with 100% success!")
