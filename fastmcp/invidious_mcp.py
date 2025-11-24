from mcp.server.fastmcp import FastMCP
import requests
import os

# === Cấu hình ĐÃ SỬA ===
# Đã sửa port mặc định từ 5006 thành 8000 (theo docker-compose.yml)
PROXY_BASE = os.getenv("INVIDIOUS_PROXY", "http://localhost:5006")

mcp = FastMCP("Invidious Music Player (via Proxy)")

# ==========================
# 🔍 Tìm kiếm video
# (Endpoint: /search?q={query})
# ==========================
@mcp.tool()
def search_video(query: str) -> dict:
    """Tìm kiếm video nhạc qua Invidious Proxy."""
    try:
        r = requests.get(f"{PROXY_BASE}/search", params={"q": query}, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if isinstance(data, list):
            results = [
                {
                    "title": v.get("title"),
                    "author": v.get("author"),
                    "videoId": v.get("id"), # Sửa: Server trả về key là "id"
                    # Lưu ý: Server hiện tại không trả về thumbnail, đã bỏ field này.
                    "length": v.get("length"), # Sửa: Server trả về key là "length"
                    # Sửa: Endpoint info phải là /info/{id}
                    "info_url": f"{PROXY_BASE}/info/{v.get('id')}"
                }
                for v in data
            ]
            return {"success": True, "results": results[:10]}
        else:
            # Xử lý trường hợp server trả về lỗi 500 với cấu trúc JSON khác
            return {"success": False, "message": "Kết quả tìm kiếm không hợp lệ hoặc lỗi server nội bộ."}
    except Exception as e:
        return {"success": False, "message": f"Lỗi tìm kiếm: {e}"}


# ==========================
# 🎧 Lấy thông tin chi tiết
# (Endpoint: /info/{videoId})
# ==========================
@mcp.tool()
def get_video_info(videoId: str) -> dict:
    """Lấy thông tin chi tiết video từ proxy."""
    # Sửa: Sử dụng endpoint /info/{videoId}
    try:
        r = requests.get(f"{PROXY_BASE}/info/{videoId}", timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # Lưu ý: Endpoint /info trả về JSON thô của Invidious, phức tạp hơn.
        return {
            "success": True,
            "title": data.get("title"),
            "author": data.get("author"),
            "duration_seconds": data.get("lengthSeconds"),
            # Link PCM Stream thực tế cho ESP32
            "pcm_stream_url": f"{PROXY_BASE}/play_pcm/{videoId}"
        }
    except Exception as e:
        return {"success": False, "message": f"Lỗi lấy video info: {e}"}


# ==========================
# 🔊 Lấy link stream PCM (ESP32)
# (Endpoint: /play_pcm/{videoId})
# ==========================
@mcp.tool()
def get_pcm_stream_url(videoId: str) -> dict:
    """Lấy trực tiếp link stream PCM 16kHz cho ESP32 phát nhạc."""
    # Server FastAPI sẽ phản hồi với Content-Type: application/octet-stream
    # MCP tool chỉ cần trả về URL để client (ESP32) tự kết nối và đọc stream
    
    # Sửa: Sử dụng endpoint /play_pcm/{videoId}
    pcm_url = f"{PROXY_BASE}/play_pcm/{videoId}"
    
    # Kiểm tra server có sẵn không bằng cách gọi health check
    try:
        r = requests.get(pcm_url, stream=True, timeout=5)
        # Chỉ kiểm tra status code, không đọc toàn bộ nội dung (vì là stream lớn)
        r.raise_for_status() 
        r.close()
        
        return {
            "success": True,
            "message": "Sẵn sàng stream PCM.",
            "pcm_stream_url": pcm_url
        }
    except Exception as e:
        return {"success": False, "message": f"Lỗi: Không thể kết nối hoặc server lỗi khi khởi tạo stream. {e}"}


# ==========================
# 🩺 Kiểm tra tình trạng proxy
# (Endpoint: /health)
# ==========================
@mcp.tool()
def health_check() -> dict:
    """Kiểm tra tình trạng hoạt động của Invidious Proxy."""
    try:
        r = requests.get(f"{PROXY_BASE}/health", timeout=5)
        r.raise_for_status()
        data = r.json()
        return {"success": True, "proxy_status": data}
    except Exception as e:
        return {"success": False, "message": f"Lỗi khi kiểm tra: {e}"}


# === Khởi chạy server MCP ===
if __name__ == "__main__":
    mcp.run(transport="stdio")
