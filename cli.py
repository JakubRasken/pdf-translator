import argparse
import os
import sys
import logging
from pdf_translator_pipeline.config import (
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    DEFAULT_MODEL,
    GEMINI_API_KEY
)
from pdf_translator_pipeline.translator import GeminiTranslator
from pdf_translator_pipeline.pdf_processor import translate_pdf

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    setup_logging()
    logger = logging.getLogger("pdf_translator_cli")

    parser = argparse.ArgumentParser(
        description="Python-based PDF translation pipeline preserving layout geometry."
    )
    parser.add_argument(
        "input_pdf",
        type=str,
        help="Path to the source PDF file to translate."
    )
    parser.add_argument(
        "output_pdf",
        type=str,
        nargs="?",
        default=None,
        help="Path where the translated PDF will be saved. Defaults to '[input_name]_translated.pdf'."
    )
    parser.add_argument(
        "--target-lang", "-t",
        type=str,
        default=DEFAULT_TARGET_LANG,
        help=f"Target language code (e.g. 'es' for Spanish, 'fr' for French). Default: '{DEFAULT_TARGET_LANG}'."
    )
    parser.add_argument(
        "--source-lang", "-s",
        type=str,
        default=DEFAULT_SOURCE_LANG,
        help=f"Source language code or 'auto' to auto-detect. Default: '{DEFAULT_SOURCE_LANG}'."
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Gemini model to use. Default: '{DEFAULT_MODEL}'."
    )
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        default=None,
        help="Gemini API Key. Can also be set via the GEMINI_API_KEY environment variable."
    )
    parser.add_argument(
        "--engine", "-e",
        type=str,
        choices=["gemini", "google", "mock"],
        default="gemini",
        help="Translation engine to use. Default: 'gemini'."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force use of local mock translator (no API key required, useful for layout/scaling testing)."
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=30,
        help="Number of text blocks to translate per API request. Default: 30."
    )

    args = parser.parse_args()

    # Validate input file existence
    if not os.path.isfile(args.input_pdf):
        logger.error(f"Input file not found: {args.input_pdf}")
        sys.exit(1)

    # Resolve output path if not specified
    if args.output_pdf is None:
        base, ext = os.path.splitext(args.input_pdf)
        args.output_pdf = f"{base}_translated{ext}"

    # Determine key and engine
    api_key = args.api_key or GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
    engine = args.engine
    
    if args.mock:
        engine = "mock"
    elif engine == "gemini" and not api_key:
        logger.warning("No API key found in environment or arguments. Defaulting to free Google Translate engine.")
        engine = "google"

    logger.info("=" * 60)
    logger.info("PDF Translation Pipeline")
    logger.info(f"Input file:   {args.input_pdf}")
    logger.info(f"Output file:  {args.output_pdf}")
    logger.info(f"Target Lang:  {args.target_lang}")
    logger.info(f"Source Lang:  {args.source_lang}")
    logger.info(f"Engine:       {engine.upper()}")
    if engine == "gemini":
        logger.info(f"Model:        {args.model}")
    logger.info("=" * 60)

    try:
        translator = GeminiTranslator(api_key=api_key, model=args.model, engine=engine, mock=args.mock)
        translate_pdf(
            input_path=args.input_pdf,
            output_path=args.output_pdf,
            translator=translator,
            target_lang=args.target_lang,
            source_lang=args.source_lang,
            batch_size=args.batch_size
        )
        logger.info(f"Success! Translated PDF saved to: {args.output_pdf}")
    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
