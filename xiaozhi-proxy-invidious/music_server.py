import subprocess
import logging
import json
import os
from typing import Optional, Generator
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
from dotenv import load_dotenv

# Tải biến môi trường từ file .env (nếu chạy local)
load_dotenv() 

# --- CẤU HÌNH ĐỌC TỪ BIẾN MÔI TRƯỜNG ---
# Lấy giá trị từ biến môi trường, sử dụng giá trị mặc định nếu không tìm thấy
INVIDIOUS_INSTANCE = os.getenv("INVIDIOUS_INSTANCE")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", 16000))
CHANNELS = int(os.getenv("CHANNELS", 1))

# Cấu hình tĩnh
AUDIO_FORMAT = "s16le" # Signed 16-bit Little Endian (Chuẩn PCM thông dụng nhất)

# Thiết lập Log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("XiaozhiServer")

app = FastAPI(title="Xiaozhi Music Server for ESP32")

def get_ffmpeg_command(url: str) -> list:
    """
    Tạo lệnh FFmpeg để stream và convert audio sang PCM raw
    """
    return [
        'ffmpeg',
        '-re',                  # Read input at native frame rate (tùy chọn, bỏ nếu muốn tải nhanh nhất có thể)
        '-i', url,              # Input URL
        '-f', AUDIO_FORMAT,     # Định dạng đầu ra: s16le (raw pcm)
        '-acodec', 'pcm_s16le', # Codec
        '-ar', str(SAMPLE_RATE),# Sample rate (16k)
        '-ac', str(CHANNELS),   # Channels (1 - Mono)
        '-vn',                  # Không video
        '-pipe:1'               # Output ra stdout để Python đọc
    ]

@app.get("/health")
async def health_check():
    """Kiểm tra trạng thái server"""
    return {"status": "ok", "server": "Xiaozhi Music Middleware", "target_invidious": INVIDIOUS_INSTANCE}

@app.get("/search")
async def search_music(q: str = Query(..., description="Tên bài hát")):
    """
    Tìm kiếm bài hát trên Invidious.
    Trả về danh sách bài hát rút gọn cho ESP32 dễ xử lý.
    """
    search_url = f"{INVIDIOUS_INSTANCE}/api/v1/search"
    params = {
        "q": q,
        "type": "video",
        "sort_by": "relevance"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(search_url, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            # Lọc chỉ lấy thông tin cần thiết để tiết kiệm RAM cho ESP32
            results = []
            for item in data[:10]: # Chỉ lấy 10 kết quả đầu
                results.append({
                    "id": item.get("videoId"),
                    "title": item.get("title"),
                    "length": item.get("lengthSeconds"),
                    "author": item.get("author")
                })
            return results
        except Exception as e:
            logger.error(f"Lỗi tìm kiếm: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/info/{video_id}")
async def get_music_info(video_id: str):
    """
    Lấy thông tin chi tiết của video để chọn luồng phát (nếu client muốn tự xử lý URL).
    """
    info_url = f"{INVIDIOUS_INSTANCE}/api/v1/videos/{video_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(info_url, timeout=10.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=404, detail="Không tìm thấy video hoặc lỗi server")

@app.get("/play_pcm/{video_id}")
async def play_pcm(video_id: str):
    """
    ENDPOINT QUAN TRỌNG NHẤT:
    1. Lấy link audio stream từ Invidious.
    2. Dùng FFmpeg convert sang PCM raw.
    3. Stream từng chunk bytes về cho ESP32.
    """
    logger.info(f"Yêu cầu phát nhạc ID: {video_id}")
    
    # Bước 1: Lấy URL stream thực tế (thường là m4a hoặc webm)
    info_url = f"{INVIDIOUS_INSTANCE}/api/v1/videos/{video_id}"
    audio_url = None
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(info_url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            # Tìm adaptive format là audio only để tiết kiệm băng thông
            # Ưu tiên opuc/webm hoặc m4a
            for fmt in data.get("adaptiveFormats", []):
                if "audio" in fmt.get("type", ""):
                    audio_url = fmt.get("url")
                    break
            
            if not audio_url:
                raise HTTPException(status_code=404, detail="Không tìm thấy luồng audio phù hợp")
                
        except Exception as e:
            logger.error(f"Lỗi lấy info video: {e}")
            raise HTTPException(status_code=500, detail="Lỗi khi lấy link nhạc")

    # Bước 2 & 3: Streaming Generator với FFmpeg
    def audio_stream_generator(url: str):
        command = get_ffmpeg_command(url)
        logger.info(f"Bắt đầu FFmpeg: {' '.join(command)}")
        
        # Mở process FFmpeg
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, # Ẩn log rác của ffmpeg
            bufsize=10**6 # Buffer size
        )
        
        chunk_size = 4096 # Kích thước chunk gửi đi (4KB)
        
        try:
            while True:
                data = process.stdout.read(chunk_size)
                if not data:
                    break
                yield data
        except Exception as e:
            logger.error(f"Lỗi stream: {e}")
            process.kill()
        finally:
            if process.poll() is None:
                process.kill()
            logger.info("Kết thúc stream")

    # Trả về StreamingResponse với Content-Type là application/octet-stream
    # ESP32 chỉ cần đọc socket liên tục là có data PCM để đẩy vào I2S
    return StreamingResponse(
        audio_stream_generator(audio_url),
        media_type="application/octet-stream"
    )

if __name__ == "__main__":
    import uvicorn
    # Chạy server tại port 8000, lắng nghe mọi IP
    uvicorn.run(app, host="0.0.0.0", port=5006)
