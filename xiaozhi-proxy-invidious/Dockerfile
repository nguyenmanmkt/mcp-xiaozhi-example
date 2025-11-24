# Sử dụng Python 3.10 bản slim để nhẹ và ổn định
FROM python:3.10-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Cập nhật và cài đặt FFmpeg (BẮT BUỘC để convert nhạc)
# rm -rf để xóa cache giúp giảm dung lượng image
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy file requirements và cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code server vào container
COPY music_server.py .

# Mở port 8000
EXPOSE 5006

# Lệnh chạy server
CMD ["uvicorn", "music_server:app", "--host", "0.0.0.0", "--port", "5006"]
