import io
import re
import asyncio
from PIL import Image
import pytesseract
from rapidfuzz import fuzz
import imagehash

import config
from blacklist import BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES

pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
spam_hash_cache = set()

def normalize_text(text):
    text = text.lower()
    return re.sub(r'[^a-z0-9ก-ฮ]', '', text)

def process_image(img):
    width, height = img.size
    box = (0, height // 2, width, height) 
    cropped_img = img.crop(box)
    cropped_img.thumbnail((600, 600))
    return cropped_img

async def analyze_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('L')
    
    img_hash = str(imagehash.average_hash(img))
    if config.IMAGE_CACHE_ENABLED and img_hash in spam_hash_cache:
        return True, "เจอสแปมรูปเดิมที่เคยโดนแบน (ระบบจำภาพ)"

    opt_img = process_image(img)
    raw_text = await asyncio.to_thread(pytesseract.image_to_string, opt_img, lang='eng')
    norm_text = normalize_text(raw_text)
    
    is_spam = False
    reason = ""
    all_blacklists = BLACK_LISTED_DOMAINS + BLACK_LISTED_SPAM_PHRASES
    
    for phrase in all_blacklists:
        if phrase in norm_text:
            is_spam, reason = True, f"เจอคำต้องห้าม: '{phrase}'"
            break
        
        similarity = fuzz.partial_ratio(phrase, norm_text)
        if similarity >= config.FUZZY_THRESHOLD:
            is_spam, reason = True, f"เจอคำคล้าย: '{phrase}' ({similarity}%)"
            break

    if is_spam and config.IMAGE_CACHE_ENABLED:
        spam_hash_cache.add(img_hash)
        
    return is_spam, reason