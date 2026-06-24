import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Translation settings
DEFAULT_SOURCE_LANG = "auto"
DEFAULT_TARGET_LANG = "es"  # Spanish default

# Layout parameters
MIN_FONT_SIZE = 1.0
MAX_FONT_SIZE = 40.0
FONT_SCALING_PRECISION_ITERATIONS = 8
