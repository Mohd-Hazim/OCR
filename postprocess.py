# core/postprocess.py - COMPLETE FIXED VERSION
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
# CORE TEXT PROCESSING FUNCTIONS
# ===================================================================

def clean_hindi_text(text: str) -> str:
    """Clean and normalize Hindi/Devanagari text."""
    if not text:
        return ""
    
    # Use IndicNLP normalizer if available
    if _HAS_INDIC and _normalizer:
        try:
            text = _normalizer.normalize(text)
        except Exception as e:
            logger.warning(f"IndicNLP normalization failed: {e}")
    
    # Unicode normalization
    text = unicodedata.normalize('NFC', text)
    
    # Remove zero-width characters
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    
    return text.strip()


def normalize_bullets(text: str) -> str:
    """
    Normalize various bullet point symbols to standard bullets.
    Preserves numbered lists.
    """
    if not text:
        return ""
    
    # Map of bullet variants to standard bullet
    bullet_map = {
        '●': '•',
        '○': '•',
        '◦': '•',
        '∘': '•',
        '∙': '•',
        '·': '•',
        '⦿': '•',
        '⦾': '•',
        '⦁': '•',
        '▪': '•',
        '▫': '•',
        '■': '•',
        '□': '•',
        '◆': '•',
        '◇': '•',
        '►': '•',
        '‣': '•',
        '⁃': '•',
        '⁌': '•',
        '⁍': '•',
    }
    
    # Replace bullet variants
    for old, new in bullet_map.items():
        text = text.replace(old, new)
    
    # Normalize dash-style bullets (but not within words)
    text = re.sub(r'^(\s*)[-–—]\s+', r'\1• ', text, flags=re.MULTILINE)
    
    # Ensure space after bullet
    text = re.sub(r'•([^\s])', r'• \1', text)
    
    return text


# ===================================================================
# LATEX / MATHML CONVERSION
# ===================================================================

def convert_latex_to_mathml(text: str) -> str:
    """
    Convert LaTeX math expressions to MathML.
    Handles both inline ($...$) and display ($$...$$) math.
    """
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
                # Add display attribute for block equations
                if is_display and '<math' in mathml:
                    mathml = mathml.replace('<math>', '<math display="block">')
                return mathml
            except Exception as e:
                logger.warning(f"LaTeX conversion failed for '{latex_expr}': {e}")
        
        # Fallback to unicode representation
        return _latex_to_unicode_fallback(latex_expr, is_display)
    
    # Convert display math ($$...$$)
    text = re.sub(r'\$\$(.+?)\$\$', convert_math, text, flags=re.DOTALL)
    
    # Convert inline math ($...$)
    text = re.sub(r'\$(.+?)\$', convert_math, text)
    
    return text


def _latex_to_unicode_fallback(latex_expr: str, is_display: bool = False) -> str:
    """
    Fallback: Convert common LaTeX symbols to Unicode.
    Used when latex2mathml is not available.
    """
    # Common LaTeX symbol mappings
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
    
    # Handle superscripts and subscripts
    result = _latex_to_unicode_single(result)
    
    # Wrap in styling
    if is_display:
        return f'<div style="text-align: center; font-size: 1.2em; margin: 10px 0;">{result}</div>'
    else:
        return f'<span style="font-style: italic;">{result}</span>'


def _latex_to_unicode_single(text: str) -> str:
    """Convert simple superscripts (^) and subscripts (_) to Unicode."""
    # Superscript mapping
    superscripts = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
        'n': 'ⁿ', 'i': 'ⁱ'
    }
    
    # Subscript mapping
    subscripts = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
        '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎'
    }
    
    # Replace ^{...} with superscripts
    def replace_super(match):
        chars = match.group(1)
        return ''.join(superscripts.get(c, c) for c in chars)
    
    # Replace _{...} with subscripts
    def replace_sub(match):
        chars = match.group(1)
        return ''.join(subscripts.get(c, c) for c in chars)
    
    text = re.sub(r'\^{([^}]+)}', replace_super, text)
    text = re.sub(r'_{([^}]+)}', replace_sub, text)
    
    return text


# ===================================================================
# MATHML DISPLAY ENHANCEMENT
# ===================================================================

def enhance_math_display(html_with_mathml: str) -> str:
    """
    Add visual styling to MathML for better display.
    """
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
    """
    Prepare HTML with MathML for clipboard (Word compatibility).
    Ensures proper XML namespaces and encoding.
    """
    if not html or '<math' not in html:
        return html
    
    # Ensure MathML namespace
    html = re.sub(
        r'<math(?![^>]*xmlns)',
        '<math xmlns="http://www.w3.org/1998/Math/MathML"',
        html
    )
    
    # Unescape any escaped MathML tags
    html = html.replace('&lt;math', '<math')
    html = html.replace('&lt;/math&gt;', '</math>')
    html = html.replace('&lt;', '<').replace('&gt;', '>')
    
    return html


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


# ===================================================================
# MATHML TO OMML CONVERSION (for Word)
# ===================================================================

def convert_mathml_to_omml(mathml: str) -> str:
    """
    Convert MathML to Office Math Markup Language (OMML).
    Simplified conversion for basic compatibility.
    """
    if not mathml or '<math' not in mathml:
        return mathml
    
    # This is a placeholder - full OMML conversion requires XSLT
    # For now, we'll just ensure proper namespace
    omml = mathml.replace(
        'xmlns="http://www.w3.org/1998/Math/MathML"',
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
    )
    
    return omml


# ===================================================================
# LATEX TO IMAGE RENDERING
# ===================================================================

def render_latex_to_image(latex_expr: str, output_path: str) -> str:
    """
    Render LaTeX expression to PNG image.
    Returns the path to the generated image, or None on failure.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib import mathtext
        
        # Create figure
        fig = plt.figure(figsize=(4, 1))
        fig.text(0.5, 0.5, f'${latex_expr}$', 
                fontsize=16, ha='center', va='center')
        
        # Save to file
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
# EMOJI AND SYMBOL CLEANUP
# ===================================================================

_EMOJI_PATTERN = re.compile(
    "[" 
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # extended-A
    "]+", flags=re.UNICODE
)

_SYMBOL_CLEAN_PATTERN = re.compile(r"[■◆►✔✖✦✪✷✸✹✺✻]", flags=re.UNICODE)


def _remove_emojis_and_symbols(text: str) -> str:
    """Remove emojis and decorative symbols, keep bullets and punctuation."""
    if not text:
        return ""
    
    text = _EMOJI_PATTERN.sub("", text)
    text = _SYMBOL_CLEAN_PATTERN.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    
    return text.strip()


# ===================================================================
# LIST NORMALIZATION
# ===================================================================

def _normalize_numbered_lists(text: str) -> str:
    """Normalize different numbered list formats into '1.' style."""
    if not text:
        return ""
    
    # Convert "1)", "1 -", etc. to "1."
    text = re.sub(r"^(\s*)(\d+)\s*[\.\)\-]\s+", r"\1\2. ", text, flags=re.MULTILINE)
    
    # Ensure space after number
    text = re.sub(r"^(\s*\d+)\.(?!\s)", r"\1. ", text, flags=re.MULTILINE)
    
    return text


def _normalize_indentation(text: str) -> str:
    """Make indentation consistent using 2-space per level."""
    if not text:
        return ""
    
    lines = text.splitlines()
    norm_lines = []
    
    for ln in lines:
        # Convert tabs to spaces
        ln = ln.replace("\t", "    ")
        
        # Collapse 4-space indents to 2-space
        ln = re.sub(r"^(?: {4})+", lambda m: "  " * (len(m.group(0)) // 4), ln)
        
        # Preserve indentation but trim trailing spaces
        leading = re.match(r"^(\s*)", ln).group(1)
        content = ln[len(leading):].rstrip()
        norm_lines.append(leading + content)
    
    return "\n".join(norm_lines)


def _cleanup_paragraph_spacing(text: str) -> str:
    """Ensure single blank line between paragraphs."""
    if not text:
        return ""
    
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()


# ===================================================================
# HTML TABLE PROCESSING
# ===================================================================

def _strip_html_styles(html: str) -> str:
    """Remove inline styles and color attributes from HTML."""
    if not html:
        return ""
    
    # Remove style attributes
    html = re.sub(r'\sstyle="[^"]*"', "", html, flags=re.IGNORECASE)
    
    # Remove color/size attributes
    html = re.sub(r'\s(?:bgcolor|color|width|height)="[^"]*"', "", html, flags=re.IGNORECASE)
    
    # Remove class attributes
    html = re.sub(r'\sclass="[^"]*"', "", html, flags=re.IGNORECASE)
    
    return html


def _normalize_bullets_in_html(html: str) -> str:
    """Replace various bullet characters in HTML with standard bullet."""
    if not html:
        return ""
    
    html = re.sub(r'[●○◦∘∙·⦿⦾⦁\-\*]+', '•', html)
    html = re.sub(r'(•)([^\s<])', r'\1 \2', html)
    
    return html


# ===================================================================
# MODE-SPECIFIC PROCESSING PIPELINES
# ===================================================================

def clean_text_mode_output(text: str) -> str:
    """
    Text mode pipeline:
    - Bullet normalization
    - Emoji/symbol removal
    - Numbered list normalization
    - Indentation normalization
    - Paragraph spacing cleanup
    """
    if not text:
        return ""
    
    # Handle HTML tables - flatten to text
    if "<table" in text.lower():
        flat = re.sub(r'<\/?(table|tbody|thead|tfoot|tr|th|td)[^>]*>', 
                     lambda m: "\n" if m.group(0).lower().startswith("</") else "\t", 
                     text, flags=re.IGNORECASE)
        flat = re.sub(r'<[^>]+>', '', flat)
        flat = unescape(flat)
        flat = re.sub(r'[ \t]{2,}', ' ', flat)
        flat = re.sub(r'\n{3,}', '\n\n', flat)
        text = flat.strip()
    
    # Apply transformations
    text = normalize_bullets(text)
    text = _remove_emojis_and_symbols(text)
    text = _normalize_numbered_lists(text)
    text = _normalize_indentation(text)
    text = _cleanup_paragraph_spacing(text)
    
    return text.strip()


def clean_table_mode_output(html_or_text: str) -> str:
    """
    Table mode pipeline:
    - Remove inline styles
    - Normalize bullets and lists inside cells
    - Remove emojis/symbols
    Returns: cleaned HTML table
    """
    if not html_or_text:
        return ""
    
    # If no table detected, return cleaned text
    if "<table" not in html_or_text.lower():
        # Try to convert pipe/tab separated to table
        lines = [ln for ln in html_or_text.splitlines() if ln.strip()]
        if not lines:
            return ""
        
        # Check for pipe or tab separators
        if any(("|" in ln) or ("\t" in ln) for ln in lines):
            rows = []
            for ln in lines:
                cells = [c.strip() for c in re.split(r'\t|\s*\|\s*', ln)]
                rows.append(cells)
            
            # Build HTML table
            html = ["<table>"]
            for r in rows:
                html.append("<tr>")
                for c in r:
                    c = normalize_bullets(c)
                    c = _remove_emojis_and_symbols(c)
                    c = _normalize_numbered_lists(c)
                    c = c.replace("<", "&lt;").replace(">", "&gt;")
                    html.append(f"<td>{c}</td>")
                html.append("</tr>")
            html.append("</table>")
            result = "\n".join(html)
            return _strip_html_styles(result)
        
        # Fallback: return cleaned plain text
        return clean_text_mode_output(html_or_text)
    
    # Process HTML table
    html = html_or_text
    html = _strip_html_styles(html)
    html = _normalize_bullets_in_html(html)
    
    # Clean cell contents
    def clean_cell(match):
        inner = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        inner = _normalize_numbered_lists(inner)
        inner = _remove_emojis_and_symbols(inner)
        return f"<td>{inner}</td>"
    
    html = re.sub(r'<td[^>]*>(.*?)</td>', clean_cell, html, flags=re.IGNORECASE | re.DOTALL)
    
    # Collapse whitespace
    html = re.sub(r'\s+', ' ', html)
    
    return html.strip()


def clean_math_mode_output(text: str, for_display: bool = True) -> str:
    """
    Math mode pipeline:
    - Convert LaTeX to MathML
    - Enhance display styling
    Returns: HTML with MathML
    """
    if not text:
        return ""
    
    # Convert LaTeX to MathML
    converted = convert_latex_to_mathml(text)
    
    # Add display enhancements
    if for_display and '<math' in converted:
        converted = enhance_math_display(converted)
    
    return converted.strip()


# ===================================================================
# EXPORTS
# ===================================================================

__all__ = [
    'clean_hindi_text',
    'normalize_bullets',
    'convert_latex_to_mathml',
    'enhance_math_display',
    'prepare_math_for_clipboard',
    'process_ocr_text_with_math',
    'render_latex_to_image',
    'convert_mathml_to_omml',
    'clean_text_mode_output',
    'clean_table_mode_output',
    'clean_math_mode_output',
]