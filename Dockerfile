# ==========================================
# ✅ ใช้ python:3.11-slim แทน 3.10
#    3.11 เร็วกว่า 3.10 ประมาณ 10-25% (better specializing adaptive interpreter)
# ==========================================
FROM python:3.11-slim

# ==========================================
# ✅ ติดตั้ง system dependencies
#    --no-install-recommends ป้องกัน apt ดึงของแถมที่ไม่ต้องการ
# ==========================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tha \
    libgl1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ==========================================
# ✅ Copy requirements ก่อน source code
#    Docker จะ cache layer นี้ไว้ — pip install จะ rebuild เฉพาะเมื่อ requirements.txt เปลี่ยน
#    ถ้าแก้แค่ bot.py, layer นี้จะถูก cache → build เร็วขึ้นมาก
# ==========================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy source code หลังติดตั้ง dependencies
COPY . .

# ==========================================
# ✅ ใช้ non-root user — Security best practice
#    ป้องกัน process ใน container มีสิทธิ์ root
# ==========================================
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# ✅ Health check สำหรับ Docker/Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-7860}/health || exit 1

CMD ["python", "-u", "bot.py"]
