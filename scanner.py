import io
import re
import asyncio
import logging
import time
from typing import Tuple

import pytesseract
from rapidfuzz import fuzz
import imagehash
from PIL import Image
import cv2
import numpy as np

import config
from blacklist import BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES

logger = logging.getLogger("MaO-Bot.scanner")

pytesseract.pytesseract.tesseract_cmd = getattr(config, 'TESSERACT_CMD', 'tesseract')

# ==========================================
# ✅ ใช้ dict สำหรับ TTL cache: { hash_str: timestamp }
# ==========================================
spam_hash_cache: dict[str, float] = {}

SPAM_REGEX_PATTERNS = [
    r"\+[0-9,]+\s?usdt",
    r"\$[0-9,]+\s?was success",
    r"discord\.gift/[a-zA-Z0-9]+",
    r"withdrawal of \$[0-9,]+",
]

# ✅ Pre-compile regex patterns ครั้งเดียวตอน import
#    แทนการ compile ซ้ำทุกครั้งที่สแกน — ประหยัด CPU
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SPAM_REGEX_PATTERNS]

# ✅ Throttle cache cleanup — รันแค่ทุก 5 นาที แทนทุกครั้งที่มีรูปเข้า
#    ป้องกัน O(n) loop block event loop บน server ที่มี spam cache ใหญ่
_last_cleanup_time: float = 0.0
_CLEANUP_INTERVAL = 300  # วินาที


def _maybe_clean_cache() -> None:
    """ล้าง cache เฉพาะเมื่อถึงรอบ — ไม่ทำทุกครั้งที่สแกน"""
    global _last_cleanup_time
    now = time.monotonic()
    if now - _last_cleanup_time < _CLEANUP_INTERVAL:
        return

    _last_cleanup_time = now
    expiry_seconds = getattr(config, 'IMAGE_CACHE_EXPIRY_MINUTES', 60) * 60
    cutoff = time.time() - expiry_seconds
    expired = [k for k, v in spam_hash_cache.items() if v < cutoff]
    for k in expired:
        del spam_hash_cache[k]

    if expired:
        logger.info("Cache cleanup: removed %d expired entries", len(expired))


def normalize_text(text: str) -> str:
    """Normalize ข้อความสำหรับ fuzzy matching — ใช้ทั้ง image และ text scanner"""
    text = text.lower()
    text = re.sub(r'[^a-z0-9ก-ฮ\.\$\+]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _process_image_sync(image_bytes: bytes) -> Tuple[object | None, str]:
    """
    ✅ รวม CPU-bound image processing ทั้งหมดไว้ใน function เดียว
       เพื่อรันใน thread pool ครั้งเดียว — ป้องกัน event loop ถูก block
    Returns: (processed_img_or_None, img_hash_str)
    """
    # Phase 1: Compute perceptual hash
    # ✅ ใช้ phash แทน average_hash — collision rate ต่ำกว่า แม่นยำกว่าสำหรับ spam detection
    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert('L')
        img_hash = str(imagehash.phash(pil_img))
    except Exception as e:
        logger.warning("_process_image_sync: Failed to compute phash: %s", e)
        img_hash = "unknown"

    # Phase 2: OpenCV preprocessing
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

    # ✅ ตรวจสอบ None ก่อนเข้าถึง .shape
    #    cv2.imdecode คืน None สำหรับ corrupt image, webp บางรูป, HEIC
    if img is None:
        logger.warning("_process_image_sync: cv2 failed to decode image (format unsupported or corrupted)")
        return None, img_hash

    if getattr(config, 'STRICT_REGEX_MODE', True):
        height, width = img.shape
        # ขยายรูปเล็กให้ OCR อ่านได้ดีขึ้น
        if width < 1000:
            img = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        blur = cv2.GaussianBlur(img, (5, 5), 0)
        img = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
            15, 5
        )

    return img, img_hash


def _run_ocr_and_detect(processed_img) -> Tuple[bool, str]:
    """
    ✅ OCR + spam detection ใน thread pool
    Returns: (is_spam, reason)
    """
    raw_text = pytesseract.image_to_string(processed_img, lang='eng')
    norm_text = normalize_text(raw_text)

    # ตรวจ regex patterns (pre-compiled)
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(raw_text):
            return True, f"ตรวจพบแพทเทิร์นสแปม: '{pattern.pattern}'"

    # ตรวจ blacklist: exact match + fuzzy match
    all_blacklists = BLACK_LISTED_DOMAINS + BLACK_LISTED_SPAM_PHRASES
    fuzzy_threshold = getattr(config, 'FUZZY_THRESHOLD', 85)

    for phrase in all_blacklists:
        norm_phrase = normalize_text(phrase)

        # Exact match ก่อน — เร็วกว่า fuzzy
        if norm_phrase in norm_text:
            return True, f"เจอคำตรงตัว: '{phrase}'"

        # Fuzzy match เฉพาะ phrase ที่ยาวพอ (> 5 ตัวอักษร)
        if len(norm_phrase) > 5:
            score = fuzz.partial_ratio(norm_phrase, norm_text)
            if score >= fuzzy_threshold:
                return True, f"เจอคำคล้าย: '{phrase}' ({int(score)}%)"

    return False, ""


async def analyze_image(image_bytes: bytes) -> Tuple[bool, str, str]:
    """
    วิเคราะห์รูปภาพว่าเป็นสแปมไหม
    Returns: (is_spam, reason, img_hash)
    """
    _maybe_clean_cache()

    # ✅ รัน image processing ทั้งหมดใน thread pool — ไม่ block event loop
    processed_img, img_hash = await asyncio.to_thread(_process_image_sync, image_bytes)

    # Cache hit: ตรวจหลัง compute hash
    if getattr(config, 'IMAGE_CACHE_ENABLED', True) and img_hash in spam_hash_cache:
        spam_hash_cache[img_hash] = time.time()  # ✅ Refresh TTL
        return True, "จำภาพนี้ได้ (ระบบ Cache)", img_hash

    # ✅ รูป decode ไม่ได้ → ไม่ถือว่า spam แต่ log ให้รู้
    if processed_img is None:
        return False, "", img_hash

    # ✅ รัน OCR + detection ใน thread pool ด้วย — ไม่ block event loop
    is_spam, reason = await asyncio.to_thread(_run_ocr_and_detect, processed_img)

    if is_spam and getattr(config, 'IMAGE_CACHE_ENABLED', True):
        spam_hash_cache[img_hash] = time.time()
        logger.info("Spam cached: hash=%s reason=%s", img_hash, reason)

    return is_spam, reason, img_hash


def analyze_text(text: str) -> Tuple[bool, str]:
    """
    ✅ ปรับให้ใช้ normalize_text + pre-compiled regex + fuzzy match
       เหมือนกับ analyze_image — consistency และจับ obfuscated spam ได้ดีขึ้น
    """
    norm_text = normalize_text(text)
    fuzzy_threshold = getattr(config, 'FUZZY_THRESHOLD', 85)

    # Regex patterns
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return True, f"จับแพทเทิร์นสแปมได้: '{pattern.pattern}'"

    # Blacklist: exact + fuzzy
    for domain in BLACK_LISTED_DOMAINS:
        norm_domain = normalize_text(domain)
        if norm_domain in norm_text:
            return True, f"เจอลิงก์อันตราย: '{domain}'"
        if len(norm_domain) > 5:
            score = fuzz.partial_ratio(norm_domain, norm_text)
            if score >= fuzzy_threshold:
                return True, f"เจอลิงก์คล้าย: '{domain}' ({int(score)}%)"

    for phrase in BLACK_LISTED_SPAM_PHRASES:
        norm_phrase = normalize_text(phrase)
        if norm_phrase in norm_text:
            return True, f"เจอประโยคสแปม: '{phrase}'"
        if len(norm_phrase) > 5:
            score = fuzz.partial_ratio(norm_phrase, norm_text)
            if score >= fuzzy_threshold:
                return True, f"เจอคำคล้าย (fuzzy): '{phrase}' ({int(score)}%)"

    return False, ""
