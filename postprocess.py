# core/postprocess.py - COMPLETE VERSION WITH TRANSPARENT TABLES
import re
import unicodedata
import logging
from html import unescape

logger = logging.getLogger(__name__)

try:
    from indicnlp.normalize.indic_normalize import DevanagariNormalizer
    _HAS_INDIC = True
    _normalizer = DevanagariNormalizer()
except Exception:
    _HAS_INDIC = False
    _normalizer = None

# ===================================================================
# ENHANCED TABLE PROCESSING - TRANSPARENT BACKGROUND
# ===================================================================

def prepare_table_for_word(html: str) -> str:
    """
    Pure Table Grid format - TRANSPARENT background, dark borders.
    NO COLORS - completely transparent for Word.
    """
    if not html or '<table' not in html.lower():
        return html
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    for table in soup.find_all('table'):
        table['border'] = '1'
        table['cellspacing'] = '0'
        table['cellpadding'] = '5'
        
        # TRANSPARENT background, dark borders only
        table['style'] = (
            'border-collapse: collapse; '
            'border: 2px solid #000000; '
            'background-color: transparent; '  # TRANSPARENT
            'font-family: Calibri, Arial, sans-serif; '
            'font-size: 11pt;'
        )
        
        # Style all cells - DARKER borders + TRANSPARENT background
        for cell in table.find_all(['td', 'th']):
            cell['style'] = (
                'border: 1.5px solid #000000; '
                'padding: 5px 8px; '
                'vertical-align: top; '
                'text-align: left; '
                'background-color: transparent; '  # TRANSPARENT
                'color: #000000;'
            )
        
        # Headers - TRANSPARENT background, just bold + borders
        for th in table.find_all('th'):
            th['style'] = (
                'border: 1.5px solid #000000; '
                'padding: 5px 8px; '
                'vertical-align: top; '
                'text-align: left; '
                'background-color: transparent; '  # TRANSPARENT
                'color: #000000; '
                'font-weight: bold;'
            )
    
    return str(soup)


def prepare_content_for_clipboard(html: str) -> str:
    """Pure Table Grid - TRANSPARENT background, dark borders only."""
    if not html:
        return ""
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    # Process all tables with same styling
    for table in soup.find_all('table'):
        table['border'] = '1'
        table['cellspacing'] = '0'
        table['cellpadding'] = '5'
        
        table['style'] = (
            'border-collapse: collapse; '
            'border: 2px solid #000000; '
            'background-color: transparent; '  # TRANSPARENT
            'width: auto; '
            'margin: 10px 0; '
            'font-family: Calibri, Arial, sans-serif; '
            'font-size: 11pt;'
        )
        
        for cell in table.find_all(['td', 'th']):
            cell['style'] = (
                'border: 1.5px solid #000000; '
                'padding: 5px 8px; '
                'vertical-align: top; '
                'text-align: left; '
                'min-width: 50px; '
                'background-color: transparent; '  # TRANSPARENT
                'color: #000000;'
            )
        
        # Headers - transparent background only
        for th in table.find_all('th'):
            th['style'] = (
                'border: 1.5px solid #000000; '
                'padding: 5px 8px; '
                'vertical-align: top; '
                'text-align: left; '
                'min-width: 50px; '
                'background-color: transparent; '  # TRANSPARENT
                'color: #000000; '
                'font-weight: bold;'
            )
    
    # Wrap with Office-compatible HTML - NO background colors
    result = f"""
    <html xmlns:o="urn:schemas-microsoft-com:office:office"
          xmlns:w="urn:schemas-microsoft-com:office:word"
          xmlns="http://www.w3.org/TR/REC-html40">
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Calibri; font-size: 11pt; background-color: transparent; }}
            table {{ border-collapse: collapse; border: 2px solid #000; background: transparent; }}
            td, th {{ border: 1.5px solid #000; padding: 5px 8px; background: transparent; color: #000; }}
        </style>
    </head>
    <body>{str(soup)}</body>
    </html>
    """
    
    return result


def extract_text_and_tables(html: str) -> dict:
    """Extract and separate text content from tables."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract tables
    tables = []
    for table in soup.find_all('table'):
        tables.append(str(table))
        table.replace_with('[TABLE]')
    
    # Get remaining text
    text = soup.get_text().strip()
    
    return {
        'text': text,
        'tables': tables,
        'has_tables': len(tables) > 0
    }


# ===================================================================
# CORE TEXT PROCESSING FUNCTIONS
# ===================================================================

def clean_hindi_text(text: str) -> str:
    """Clean and normalize Hindi/Devanagari text."""
    if not text:
        return ""
    
    if _HAS_INDIC and _normalizer:
        try:
            text = _normalizer.normalize(text)
        except Exception as e:
            logger.warning(f"IndicNLP normalization failed: {e}")
    
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    
    return text.strip()


def normalize_bullets(text: str) -> str:
    """Normalize various bullet point symbols to standard bullets."""
    if not text:
        return ""
    
    bullet_map = {
        '◉': '•', '○': '•', '◦': '•', '∘': '•', '∙': '•',
        '·': '•', '⦿': '•', '⦾': '•', '⦁': '•', '▪': '•',
        '▫': '•', '■': '•', '□': '•', '◆': '•', '◇': '•',
        '►': '•', '‣': '•', '⁃': '•', '⌂': '•', '⚫': '•',
    }
    
    for old, new in bullet_map.items():
        text = text.replace(old, new)
    
    text = re.sub(r'^(\s*)[-–—]\s+', r'\1• ', text, flags=re.MULTILINE)
    text = re.sub(r'•([^\s])', r'• \1', text)
    
    return text


# ===================================================================
# LATEX / MATHML CONVERSION
# ===================================================================

def convert_latex_to_mathml(text: str) -> str:
    """Convert LaTeX math expressions to MathML."""
    if not text or '$' not in text:
        return text
    
    try:
        from latex2mathml import converter
        _HAS_LATEX2MATHML = True
    except ImportError:
        _HAS_LATEX2MATHML = False
        logger.warning("latex2mathml not available, using unicode fallback")
    
    def convert_math(match):
        latex_expr = match.group(1).strip()
        is_display = match.group(0).startswith('$$')
        
        if _HAS_LATEX2MATHML:
            try:
                mathml = converter.convert(latex_expr)
                if is_display and '<math' in mathml:
                    mathml = mathml.replace('<math>', '<math display="block">')
                return mathml
            except Exception as e:
                logger.warning(f"LaTeX conversion failed for '{latex_expr}': {e}")
        
        return _latex_to_unicode_fallback(latex_expr, is_display)
    
    text = re.sub(r'\$\$(.+?)\$\$', convert_math, text, flags=re.DOTALL)
    text = re.sub(r'\$(.+?)\$', convert_math, text)
    
    return text


def _latex_to_unicode_fallback(latex_expr: str, is_display: bool = False) -> str:
    """Fallback: Convert common LaTeX symbols to Unicode."""
    symbols = {
        r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
        r'\epsilon': 'ε', r'\theta': 'θ', r'\lambda': 'λ', r'\mu': 'μ',
        r'\pi': 'π', r'\sigma': 'σ', r'\phi': 'φ', r'\omega': 'ω',
        r'\sum': '∑', r'\int': '∫', r'\infty': '∞',
        r'\leq': '≤', r'\geq': '≥', r'\neq': '≠',
        r'\approx': '≈', r'\equiv': '≡',
        r'\times': '×', r'\div': '÷', r'\pm': '±',
        r'\sqrt': '√', r'\in': '∈', r'\subset': '⊂',
    }
    
    result = latex_expr
    for latex, unicode_char in symbols.items():
        result = result.replace(latex, unicode_char)
    
    result = _latex_to_unicode_single(result)
    
    if is_display:
        return f'<div style="text-align: center; font-size: 1.2em; margin: 10px 0;">{result}</div>'
    else:
        return f'<span style="font-style: italic;">{result}</span>'


def _latex_to_unicode_single(text: str) -> str:
    """Convert simple superscripts (^) and subscripts (_) to Unicode."""
    superscripts = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
        'n': 'ⁿ', 'i': 'ⁱ'
    }
    
    subscripts = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
        '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎'
    }
    
    def replace_super(match):
        chars = match.group(1)
        return ''.join(superscripts.get(c, c) for c in chars)
    
    def replace_sub(match):
        chars = match.group(1)
        return ''.join(subscripts.get(c, c) for c in chars)
    
    text = re.sub(r'\^{([^}]+)}', replace_super, text)
    text = re.sub(r'_{([^}]+)}', replace_sub, text)
    
    return text


# ===================================================================
# MATH PROCESSING FUNCTIONS
# ===================================================================

def process_ocr_text_with_math(text: str, for_display: bool = True) -> str:
    """
    Process OCR text that may contain mathematical formulas.
    Converts LaTeX to MathML and enhances display.
    """
    if not text:
        return ""
    
    # Convert LaTeX to MathML
    text = convert_latex_to_mathml(text)
    
    # Enhance for display
    if for_display and '<math' in text:
        text = enhance_math_display(text)
    
    return text


def enhance_math_display(html_with_mathml: str) -> str:
    """Add visual styling to MathML for better display."""
    if not html_with_mathml or '<math' not in html_with_mathml:
        return html_with_mathml
    
    # Add styling attributes to math tags
    def style_math(match):
        math_tag = match.group(0)
        if 'xmlns' not in math_tag:
            math_tag = math_tag.replace('<math', '<math xmlns="http://www.w3.org/1998/Math/MathML"')
        if 'style' not in math_tag:
            math_tag = math_tag.replace('<math', '<math style="font-family: Cambria Math, STIXGeneral; font-size: 1.1em;"')
        return math_tag
    
    html_with_mathml = re.sub(r'<math[^>]*>', style_math, html_with_mathml)
    
    return html_with_mathml


def prepare_math_for_clipboard(html: str) -> str:
    """Prepare HTML with MathML for clipboard (Word compatibility)."""
    if not html or '<math' not in html:
        return html
    
    html = re.sub(
        r'<math(?![^>]*xmlns)',
        '<math xmlns="http://www.w3.org/1998/Math/MathML"',
        html
    )
    
    html = html.replace('&lt;math', '<math')
    html = html.replace('&lt;/math&gt;', '</math>')
    html = html.replace('&lt;', '<').replace('&gt;', '>')
    
    return html


def convert_mathml_to_omml(mathml: str) -> str:
    """Convert MathML to Office Math Markup Language (OMML)."""
    if not mathml or '<math' not in mathml:
        return mathml
    
    # Simplified OMML conversion
    omml = mathml.replace(
        'xmlns="http://www.w3.org/1998/Math/MathML"',
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
    )
    
    return omml


def render_latex_to_image(latex_expr: str, output_path: str) -> str:
    """Render LaTeX expression to PNG image."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig = plt.figure(figsize=(4, 1))
        fig.text(0.5, 0.5, f'${latex_expr}$', 
                fontsize=16, ha='center', va='center')
        
        plt.axis('off')
        plt.savefig(output_path, dpi=150, bbox_inches='tight', 
                   pad_inches=0.1, transparent=True)
        plt.close(fig)
        
        logger.info(f"Rendered LaTeX to image: {output_path}")
        return output_path
        
    except Exception as e:
        logger.warning(f"LaTeX image rendering failed: {e}")
        return None


# ===================================================================
# MODE-SPECIFIC PROCESSING PIPELINES
# ===================================================================

def clean_text_mode_output(text: str) -> str:
    """Text mode pipeline."""
    if not text:
        return ""
    
    if "<table" in text.lower():
        flat = re.sub(r'<\/?(table|tbody|thead|tfoot|tr|th|td)[^>]*>', 
                     lambda m: "\n" if m.group(0).lower().startswith("</") else "\t", 
                     text, flags=re.IGNORECASE)
        flat = re.sub(r'<[^>]+>', '', flat)
        flat = unescape(flat)
        flat = re.sub(r'[ \t]{2,}', ' ', flat)
        flat = re.sub(r'\n{3,}', '\n\n', flat)
        text = flat.strip()
    
    text = normalize_bullets(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()

# ===================================================================
# TABLE STRUCTURE FIXER (NEW)
# ===================================================================

def enforce_table_integrity(html: str) -> str:
    """
    Ensures all table rows have equal number of columns.
    Prevents broken tables.
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return html

    rows = table.find_all("tr")
    max_cols = 0

    # Count max columns
    for tr in rows:
        cols = len(tr.find_all(["td", "th"]))
        if cols > max_cols:
            max_cols = cols

    # Add missing cells
    for tr in rows:
        cells = tr.find_all(["td", "th"])
        missing = max_cols - len(cells)
        for _ in range(missing):
            tr.append(soup.new_tag("td"))

    return str(table)

def clean_table_mode_output(html_or_text: str) -> str:
    """Table mode pipeline - preserves table structure with transparent background."""
    if not html_or_text:
        return ""
    
    if "<table" not in html_or_text.lower():
        return html_or_text

    # 1) Fix broken tables (IMPORTANT)
    html_or_text = enforce_table_integrity(html_or_text)

    # 2) Style for Word
    return prepare_table_for_word(html_or_text)



def clean_math_mode_output(text: str, for_display: bool = True) -> str:
    """Math mode pipeline."""
    if not text:
        return ""
    
    converted = convert_latex_to_mathml(text)
    
    if for_display and '<math' in converted:
        converted = re.sub(
            r'<math[^>]*>',
            lambda m: m.group(0).replace('<math', '<math xmlns="http://www.w3.org/1998/Math/MathML"'),
            converted
        )
    
    return converted.strip()


# ===================================================================
# EXPORTS
# ===================================================================

__all__ = [
    'clean_hindi_text',
    'normalize_bullets',
    'convert_latex_to_mathml',
    'prepare_math_for_clipboard',
    'prepare_table_for_word',
    'prepare_content_for_clipboard',
    'extract_text_and_tables',
    'process_ocr_text_with_math',
    'enhance_math_display',
    'convert_mathml_to_omml',
    'render_latex_to_image',
    'clean_text_mode_output',
    'clean_table_mode_output',
    'clean_math_mode_output',
]