# Ảnh chạy dashboard + vòng xử lý trên CPU (x86_64 hoặc arm64).
# Build từ GỐC repo:   docker build -f deploy/Dockerfile -t edge-ai .
# Trên Jetson: thay ảnh gốc bằng l4t-pytorch của NVIDIA đúng bản JetPack để
# torch dùng được GPU (xem reports/02, mục 7).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EDGE_AUDIT_LOG=/var/lib/edge/audit.jsonl \
    EDGE_STATIC_DIR=/app/frontend \
    EDGE_DATA_DIR=/app/data

WORKDIR /app

# Tầng phụ thuộc tách riêng để đổi mã không phải cài lại torch.
COPY requirements.txt .
# torch bản CPU từ kho chính thức của PyTorch: nhẹ hơn nhiều so với bản CUDA.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.2" \
 && pip install --no-cache-dir -r requirements.txt

COPY backend/edge_ai/ backend/edge_ai/
COPY frontend/ frontend/
COPY data/models/ data/models/
COPY data/results/ data/results/

RUN useradd --system --uid 10001 --no-create-home edge \
 && mkdir -p /var/lib/edge \
 && chown edge /var/lib/edge
USER edge

EXPOSE 8099
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8099/api/health',timeout=2).status==200 else 1)"

# --proxy-headers + forwarded-allow-ips: tin header X-Forwarded-* từ Caddy
# trong mạng nội bộ của compose để log ghi đúng IP người dùng và https.
CMD ["python", "-m", "uvicorn", "edge_ai.api.server:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8099", "--proxy-headers", "--forwarded-allow-ips", "*"]
