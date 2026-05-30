import logging
import os
import threading
from flask import Flask

logger = logging.getLogger("MaO-Bot.keep_alive")

app = Flask(__name__)


@app.route('/')
def home():
    """Health check สำหรับ Render / UptimeRobot ping"""
    return "Bot is alive and monitoring!", 200


@app.route('/health')
def health():
    """✅ Structured health check endpoint — ใช้กับ Docker HEALTHCHECK หรือ monitoring ได้เลย"""
    return {"status": "ok"}, 200


def keep_alive():
    """
    เริ่ม Flask web server ใน daemon thread
    ✅ daemon=True — thread จะตายพร้อม main process อัตโนมัติ
       ไม่มี zombie thread ค้างหลัง bot crash
    ✅ อ่าน PORT จาก environment — Render.com inject PORT เองทุกครั้ง
    """
    port = int(os.environ.get('PORT', 7860))

    def run():
        # ✅ use_reloader=False — ป้องกัน Flask spawn child process ซ้อน
        app.run(host='0.0.0.0', port=port, use_reloader=False)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("Keep-alive server started on port %d", port)