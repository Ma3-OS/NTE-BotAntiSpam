# ==========================================
# ✅ ใช้ python:3.11-slim เพื่อความเบาและเสถียร
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# ==========================================
# ✅ Copy requirements ก่อน source code
# ==========================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy source code
COPY . .

# ==========================================
# ✅ ใช้ non-root user — Security best practice
# ==========================================
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# ✅ Health check สำหรับ Docker/Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-7860}/health || exit 1

CMD ["python", "-u", "main.py"]
