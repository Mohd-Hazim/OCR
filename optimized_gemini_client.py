# core/optimized_gemini_client_v2.py - ENHANCED RATE LIMITING
"""
Optimized Gemini API client with smart rate limiting.

New Features:
✅ Intelligent key scheduling based on availability
✅ More keys = proportionally less wait time
✅ Automatic penalty system for rate-limited keys
✅ Self-healing (penalties decay on success)
✅ Thread-safe operation
"""

import io
import base64
import logging
import time
from PIL import Image
import google.generativeai as genai
from bs4 import BeautifulSoup
from utils.config import load_config

# Import the new smart rate limiter
from core.rate_limit_enhanced import get_limiter, SmartRateLimiter

logger = logging.getLogger(__name__)

# =====================================================================
# SMART KEY MANAGEMENT
# =====================================================================

def get_next_api_key() -> str:
    """
    Get next API key using smart rate limiting.
    
    Features:
    - Automatically waits if all keys are on cooldown
    - Selects least-penalized key
    - More keys = less wait time per key
    
    Returns:
        API key string
    """
    cfg = load_config()
    all_keys = cfg.get("gemini_api_keys", [])

    # 1) No keys at all
    if not all_keys:
        logger.error("❗ No Gemini API keys found in config.")
        return "NO_KEYS"

    # 2) Check if all keys are fully exhausted for the day
    limiter = get_limiter()
    if limiter.all_keys_daily_exhausted(all_keys):
        logger.error("⛔ All API keys appear exhausted for the day.")
        return "ALL_KEYS_EXHAUSTED"
    
    # Get rate limiter instance
    limiter = get_limiter()
    
    try:
        # Select best key (automatically waits if needed)
        key, wait_time = limiter.select_best_key(all_keys, max_wait=30.0)
        
        if wait_time > 0.1:
            logger.info(f"⏱️ Waited {wait_time:.2f}s for available key")
        
        # Mark as used (updates timestamp)
        limiter.mark_used(key)
        
        logger.debug(f"🔑 Using key: {key[:8]}...")
        return key
        
    except Exception as e:
        logger.error(f"Key selection failed: {e}")
        # Fallback to first key
        return all_keys[0] if all_keys else None


# =====================================================================
# OPTIMIZED IMAGE ENCODING
# =====================================================================

_image_cache = {}

def optimize_image_for_api(pil_image: Image.Image, max_size: int = 1024) -> str:
    """Optimize and encode image with caching."""
    cache_key = f"{pil_image.size}_{pil_image.mode}"
    
    if cache_key in _image_cache:
        logger.debug("📦 Using cached image encoding")
        return _image_cache[cache_key]
    
    # Resize if needed
    w, h = pil_image.size
    if max(w, h) > max_size:
        scale = max_size / max(w, h)
        pil_image = pil_image.resize(
            (int(w * scale), int(h * scale)),
            Image.LANCZOS
        )
    
    # Convert to RGB
    if pil_image.mode not in ("RGB", "L"):
        pil_image = pil_image.convert("RGB")
    
    # Encode to JPEG with optimization
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=85, optimize=True)
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    
    # Cache result
    _image_cache[cache_key] = img_b64
    
    # Limit cache size
    if len(_image_cache) > 10:
        _image_cache.pop(next(iter(_image_cache)))
    
    return img_b64


# =====================================================================
# FAST TABLE NORMALIZATION
# =====================================================================

def normalize_merged_cells_fast(html: str) -> str:
    """Fast table normalization without heavy processing."""
    if not html or "<table" not in html.lower():
        return html
    
    if "rowspan" not in html.lower() and "colspan" not in html.lower():
        return html
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        
        for table in tables:
            rows = table.find_all("tr")
            max_cols = max(
                len(row.find_all(["td", "th"])) for row in rows
            ) if rows else 0
            
            new_table = soup.new_tag("table")
            for row in rows:
                tr = soup.new_tag("tr")
                cells = row.find_all(["td", "th"])
                
                for cell in cells:
                    td = soup.new_tag("td")
                    td.string = cell.get_text(strip=True)
                    tr.append(td)
                
                # Pad to max columns
                while len(tr.find_all(["td", "th"])) < max_cols:
                    tr.append(soup.new_tag("td"))
                
                new_table.append(tr)
            
            table.replace_with(new_table)
        
        return str(soup)
    
    except Exception as e:
        logger.warning(f"Table normalization failed: {e}")
        return html


# =====================================================================
# PROMPTS
# =====================================================================

TEXT_PROMPT = """Extract all text exactly as shown. Include:
- Hindi + English
- Math formulas ($...$)
- Bullets
Output text only."""

TABLE_PROMPT = """Extract table as HTML.
Rules:
1. Use rowspan/colspan for merged cells
2. Plain HTML only (<table><tr><td>)
3. No styling or markdown
Output must start with <table>"""


# =====================================================================
# ASYNC TEXT EXTRACTION
# =====================================================================

async def _extract_text_async(pil_image: Image.Image) -> str:
    """Async text extraction with rate limiting."""
    try:
        # Get key with smart rate limiting
        key = get_next_api_key()
        if not key:
            return ""
        
        genai.configure(api_key=key)
        
        # Optimize image
        img_b64 = optimize_image_for_api(pil_image, max_size=1536)
        
        # Use flash-lite for speed
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        
        # Make API call
        import asyncio
        response = await asyncio.to_thread(
            model.generate_content,
            [
                {"text": TEXT_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
            ]
        )
        
        # Mark success
        limiter = get_limiter()
        limiter.mark_success(key)
        
        return getattr(response, "text", "").strip()
    
    except Exception as e:
        logger.exception(f"Text extraction failed: {e}")
        
        # Check if rate limit error
        if "429" in str(e) or "quota" in str(e).lower():
            limiter = get_limiter()
            limiter.mark_failure(key, is_rate_limit=True)
        
        return ""


def extract_text_async(pil_image: Image.Image, api_key: str = None) -> str:
    """Sync wrapper for async text extraction."""
    import asyncio
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(_extract_text_async(pil_image))
        return result
    finally:
        loop.close()


# =====================================================================
# TABLE EXTRACTION WITH ENHANCED RATE LIMITING
# =====================================================================

def extract_complete_content(
    pil_image: Image.Image,
    api_key: str = None,  # Ignored - uses smart rate limiter
    prompt: str = None,
    max_retries: int = 3
) -> str:
    """
    Table extraction with smart rate limiting.
    
    Features:
    - Automatic retry with backoff
    - Smart key selection
    - Penalty system for rate-limited keys
    """
    used_prompt = prompt if prompt else TABLE_PROMPT
    img_b64 = optimize_image_for_api(pil_image, max_size=2048)
    
    limiter = get_limiter()
    
    for attempt in range(1, max_retries + 1):
        # Get best available key (waits if needed)
        key = get_next_api_key()
        if not key:
            logger.error("No API keys available")
            return ""
        
        try:
            logger.info(
                f"🔄 Table extraction attempt {attempt}/{max_retries} "
                f"with key {key[:8]}..."
            )
            
            # Configure API
            genai.configure(api_key=key)
            
            # Use Pro model for tables
            model = genai.GenerativeModel(
                "gemini-2.5-pro",
                generation_config={"temperature": 0.0}
            )
            
            # Make API call
            resp = model.generate_content([
                {"text": used_prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
            ])
            
            # Mark success
            limiter.mark_success(key)
            
            # Process response
            text = getattr(resp, "text", "").strip()
            
            # Clean markdown fences
            if text.startswith("```html"):
                text = text[7:].strip()
            if text.startswith("```"):
                text = text[3:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
            
            # Normalize tables
            if "<table" in text.lower():
                text = normalize_merged_cells_fast(text)
            
            logger.info(f"✅ Table extracted ({len(text)} chars)")
            return text
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # HARD limit: this key is exhausted for the day
            if "quota" in error_msg or "daily" in error_msg or "exceeded" in error_msg:
                logger.error(f"⛔ Daily quota exhausted for key {key[:8]}")
                limiter.mark_failure(key, is_rate_limit=True)
                return "KEY_DAILY_EXHAUSTED"

            # Check if rate limit error
            is_rate_limit = any(
                indicator in error_msg
                for indicator in ["429", "quota", "rate", "limit"]
            )
            
            if is_rate_limit:
                logger.warning(
                    f"⚠️ Attempt {attempt}: Rate limited on key {key[:8]}..."
                )
                limiter.mark_failure(key, is_rate_limit=True)
                
                # Exponential backoff (only if not last attempt)
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 8)
                    logger.info(f"⏳ Backing off {wait_time}s before retry...")
                    time.sleep(wait_time)
            else:
                # Non-rate-limit error
                logger.error(f"❌ Attempt {attempt}: {e}")
                limiter.mark_failure(key, is_rate_limit=False)
                
                # Don't retry on non-rate-limit errors
                break
    
    logger.error("Table extraction failed after all retries")
    return ""


# =====================================================================
# CACHE MANAGEMENT
# =====================================================================

def clear_cache():
    """Clear image cache."""
    global _image_cache
    _image_cache.clear()
    logger.info("🧹 Cleared image cache")


def get_rate_limiter_status() -> dict:
    """Get current rate limiter status."""
    limiter = get_limiter()
    return limiter.get_status()


def reset_rate_limiter():
    """Reset rate limiter (clear all penalties)."""
    limiter = get_limiter()
    limiter.reset_all()
    logger.info("🔄 Rate limiter reset")


# =====================================================================
# CONFIGURATION
# =====================================================================

def configure_rate_limit(rpm_per_key: int = 15):
    """
    Configure rate limiting.
    
    Args:
        rpm_per_key: Requests per minute per API key
    """
    from core.rate_limit_enhanced import configure_limiter
    configure_limiter(rpm_per_key)
    logger.info(f"⚙️ Rate limit configured: {rpm_per_key} RPM per key")


# =====================================================================
# LEGACY COMPATIBILITY
# =====================================================================

def extract_table_text(pil_image: Image.Image, api_key: str = None):
    """Legacy alias for extract_complete_content."""
    return extract_complete_content(pil_image, api_key)