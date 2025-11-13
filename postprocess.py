# core/postprocess.py - ENHANCED MATH SUPPORT (updated)
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

# ... (keep all your existing functions unchanged above: clean_hindi_text,
# normalize_bullets, convert_latex_to_mathml, _latex_to_unicode_fallback, 
# _latex_to_unicode_single, enhance_math_display, prepare_math_for_clipboard,
# process_ocr_text_with_math, render_latex_to_image, convert_mathml_to_omml)
#
# (I assume the previous contents remain exactly as you provided — they are unchanged.)
#
# -------------------------------------------------------------------------
# NEW: Mode-specific processing functions
# -------------------------------------------------------------------------

# Helper: remove emojis and unwanted symbol noise
_EMOJI_PATTERN = re.compile(
    "[" 
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols and pictographs
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "]+", flags=re.UNICODE
)

_SYMBOL_CLEAN_PATTERN = re.compile(r"[■◆►✔✖✦✪✷✸✹✺✻]", flags=re.UNICODE)

def _remove_emojis_and_symbols(text: str) -> str:
    """Remove emoji and certain decorative symbols, keep bullets (•) and essential punctuation."""
    if not text:
        return ""
    # Replace emoji ranges with empty string
    text = _EMOJI_PATTERN.sub("", text)
    # Remove a set of decorative symbols that commonly pollute OCR
    text = _SYMBOL_CLEAN_PATTERN.sub("", text)
    # Trim extra whitespace created by removals
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _normalize_numbered_lists(text: str) -> str:
    """Normalize different numbered list formats into '1.' style."""
    if not text:
        return ""
    # convert "1 )", "1)", "1 -" etc -> "1."
    text = re.sub(r"^(\s*)(\d+)\s*[\.\)\-]\s+", r"\1\2. ", text, flags=re.MULTILINE)
    # ensure space after number + dot
    text = re.sub(r"^(\s*\d+)\.(?!\s)", r"\1. ", text, flags=re.MULTILINE)
    return text


def _normalize_indentation(text: str) -> str:
    """Make indentation consistent using 2-space per level for display/plain text outputs."""
    if not text:
        return ""
    lines = text.splitlines()
    norm_lines = []
    for ln in lines:
        # convert tabs to spaces
        ln = ln.replace("\t", "    ")
        # collapse runs of 4 spaces into 2 (for gentler indentation)
        ln = re.sub(r"^(?: {4})+", lambda m: "  " * (len(m.group(0)) // 4), ln)
        # Remove stray leading/trailing spaces (but preserve indentation)
        leading = re.match(r"^(\s*)", ln).group(1)
        content = ln[len(leading):].rstrip()
        norm_lines.append(leading + content)
    return "\n".join(norm_lines)


def _cleanup_paragraph_spacing(text: str) -> str:
    """Ensure single blank line between paragraphs, and trim edges."""
    if not text:
        return ""
    # Normalize CRLF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove excessive blank lines (keep max one)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim whitespace
    text = text.strip()
    return text


def _smart_linebreaks_text(text: str) -> str:
    """
    Improve line-breaks: keep lines that are continuous (not sentence breaks),
    insert breaks before bullets/numbers/headers.
    This is intentionally conservative (prefers not to merge separate lines).
    """
    if not text:
        return ""
    # If text looks like HTML or table, return as-is (text-mode expects plain text)
    if any(tag in text.lower() for tag in ["<table", "<tr", "<td", "<ul", "<ol", "<li>", "<math"]):
        return text

    # Normalize spaces
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.rstrip() for ln in text.split("\n")]

    out_lines = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            out_lines.append("")
            continue

        # If current line ends with a sentence end marker, keep break
        if re.search(r"[.!?:;\u0964]\s*$", s):
            out_lines.append(s)
            continue

        # If next line starts with lowercase, it's probably a continuation -> merge
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if nxt and nxt and nxt[0].islower() and not re.match(r"^[\-\*\u2022\u25CF\u25CB\u25E6\u2023\u25AA\u25AB]", nxt):
            # merge current and next if the current line doesn't end with punctuation
            if out_lines and out_lines[-1] and not out_lines[-1].endswith((" ", "-", "—")):
                out_lines.append(s + " ")
            else:
                out_lines.append(s + " ")
        else:
            out_lines.append(s)

    # Join where we can: merge lines that were intentionally concatenated
    merged = []
    buffer = ""
    for line in out_lines:
        if line.endswith(" "):
            buffer += line
        else:
            if buffer:
                buffer += line
                merged.append(buffer.strip())
                buffer = ""
            else:
                merged.append(line)
    if buffer:
        merged.append(buffer.strip())

    return ("\n\n".join(merged)).strip()


def _strip_html_styles(html: str) -> str:
    """Remove inline style attributes and color attributes to produce a clean grid-like table."""
    if not html:
        return ""
    # Remove style="..." entirely
    html = re.sub(r'\sstyle="[^"]*"', "", html, flags=re.IGNORECASE)
    # Remove bgcolor / color attributes
    html = re.sub(r'\s(?:bgcolor|color|width|height)="[^"]*"', "", html, flags=re.IGNORECASE)
    # Remove class attributes that might carry styling
    html = re.sub(r'\sclass="[^"]*"', "", html, flags=re.IGNORECASE)
    # Remove inline CSS comments
    html = re.sub(r'/\*.*?\*/', '', html, flags=re.DOTALL)
    return html


def _normalize_bullets_in_html(html: str) -> str:
    """Replace various bullet characters inside HTML text nodes with single '•'."""
    if not html:
        return ""
    # Normalize common bullet chars
    html = re.sub(r'[●○◦∘∙·⦿⦾⦁\-\*]+', '•', html)
    # Ensure bullet followed by space
    html = re.sub(r'(•)([^\s<])', r'\1 \2', html)
    return html


def clean_text_mode_output(text: str) -> str:
    """
    Text mode pipeline:
    - Bullet normalisation
    - Emoji/symbol removal
    - Smart line breaks
    - Paragraph spacing cleanup
    - Numbered list normalisation
    - Indentation normalisation
    - If input contains tables, flatten to text
    """
    if not text:
        return ""

    # If HTML table is present, flatten: remove tags and keep cell text separated by tabs/newlines
    if "<table" in text.lower():
        # remove styles first
        flat = re.sub(r'<\/?(table|tbody|thead|tfoot|tr|th|td)[^>]*>', lambda m: "\n" if m.group(0).lower().startswith("</") else "\t", text, flags=re.IGNORECASE)
        # fallback: strip tags
        flat = re.sub(r'<[^>]+>', '', flat)
        flat = unescape(flat)
        # collapse whitespace
        flat = re.sub(r'[ \t]{2,}', ' ', flat)
        flat = re.sub(r'\n{3,}', '\n\n', flat)
        text = flat.strip()

    # Normalize bullets first (keeps list structure)
    text = normalize_bullets(text)

    # Remove emojis/decorative symbols (but preserve bullets)
    text = _remove_emojis_and_symbols(text)

    # Normalize numbered lists
    text = _normalize_numbered_lists(text)

    # Smart line breaks
    text = _smart_linebreaks_text(text)

    # Indentation normalization
    text = _normalize_indentation(text)

    # Cleanup paragraph spacing
    text = _cleanup_paragraph_spacing(text)

    return text.strip()


def clean_table_mode_output(html_or_text: str) -> str:
    """
    Table mode pipeline:
    - Accepts HTML or text that contains a table.
    - Removes inline styles/colors and extraneous attributes.
    - Ensures 'table grid' design (simple borders) by removing inline CSS.
    - Normalizes bullets and numbered lists inside cells.
    - Removes emojis/symbols inside cells.
    Returns: cleaned HTML (table-only) - if no table detected, returns input (cleaned) as plain text.
    """
    if not html_or_text:
        return ""

    # If input isn't HTML, attempt to treat as TSV-like or simple rows -> convert to simple table HTML
    if "<table" not in html_or_text.lower():
        # try to heuristically convert pipe/tab separated to HTML table
        lines = [ln for ln in html_or_text.splitlines() if ln.strip()]
        if not lines:
            return ""

        # If looks like rows with tabs or pipes, convert to table
        if any(("|" in ln) or ("\t" in ln) for ln in lines):
            rows = []
            for ln in lines:
                cells = [c.strip() for c in re.split(r'\t|\s*\|\s*', ln) if c is not None]
                rows.append(cells)
            # Build simple HTML table
            html = ["<table>"]
            for r in rows:
                html.append("<tr>")
                for c in r:
                    # normalize bullets/numbers inside cell
                    c = normalize_bullets(c)
                    c = _remove_emojis_and_symbols(c)
                    c = _normalize_numbered_lists(c)
                    c = c.replace("<", "&lt;").replace(">", "&gt;")
                    html.append(f"<td>{c}</td>")
                html.append("</tr>")
            html.append("</table>")
            result = "\n".join(html)
            return _strip_html_styles(result)

        # If not convertible, fallback: return cleaned plain text
        cleaned = _remove_emojis_and_symbols(html_or_text)
        cleaned = normalize_bullets(cleaned)
        cleaned = _normalize_numbered_lists(cleaned)
        cleaned = _cleanup_paragraph_spacing(cleaned)
        return cleaned

    # At this point we have HTML table content
    html = html_or_text

    # Remove inline styles and attributes
    html = _strip_html_styles(html)

    # Remove color attributes / font tags
    html = re.sub(r'<font[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'</font>', '', html, flags=re.IGNORECASE)

    # Normalize bullets inside tags (cells and list items)
    html = _normalize_bullets_in_html(html)

    # Normalize numbered lists inside table cells: convert "1)", "1 -" etc to "1."
    def _norm_nums_in_cell(match):
        inner = match.group(1)
        inner = _normalize_numbered_lists(inner)
        inner = _remove_emojis_and_symbols(inner)
        return f"<td>{inner}</td>"

    html = re.sub(r'<td[^>]*>(.*?)</td>', lambda m: f"<td>{_remove_emojis_and_symbols(_normalize_numbered_lists(re.sub(r'<[^>]+>', '', m.group(1)).strip()))}</td>", html, flags=re.IGNORECASE|re.DOTALL)

    # Force simple grid style via attributes (styling for display is handled by popup._apply_content_styling)
    # Ensure table tags are well-formed (collapse multiple spaces)
    html = re.sub(r'\s+', ' ', html)

    # Finally, return cleaned HTML table
    return html.strip()


def clean_math_mode_output(text: str, for_display: bool = True) -> str:
    """
    Math mode pipeline:
    - Convert LaTeX ($...$, $$...$$) to MathML (using convert_latex_to_mathml)
    - Use unicode fallback where needed
    - Enhance MathML display for app
    - Return HTML-ready string with MathML
    """
    if not text:
        return ""

    # Convert LaTeX to MathML (uses latex2mathml if available)
    converted = convert_latex_to_mathml(text)

    # Remove trailing/leading whitespace
    converted = converted.strip()

    # Add visual enhancements for display if requested
    if for_display and "<math" in converted:
        converted = enhance_math_display(converted)

    return converted


# Exported convenience alias names (backward compatibility)
__all__ = [
    # existing exports if any...
    "clean_text_mode_output",
    "clean_table_mode_output",
    "clean_math_mode_output",
    # keep the original helpers too
    "process_ocr_text_with_math",
    "prepare_math_for_clipboard",
]
