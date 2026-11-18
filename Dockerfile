# Ảnh chạy dashboard + vòng xử lý trên CPU (x86_64 hoặc arm64).
# Trên Jetson nên thay ảnh gốc bằng l4t-pytorch của NVIDIA tương ứng JetPack
# để có torch dùng GPU — xem reports/01_Danh_gia_va_phat_trien.md.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    EDGE_AUDIT_LOG=/var/lib/edge/audit.jsonl

WORKDIR /app
COPY requirements.txt .
# torch bản CPU từ kho chính thức của PyTorch: nhẹ hơn nhiều so với bản CUDA.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.2" \
 && pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY static/ static/
COPY data/*.pt data/*.json data/

RUN useradd --system --uid 10001 edge \
 && mkdir -p /var/lib/edge && chown edge /var/lib/edge
USER edge

EXPOSE 8099
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8099/api/health',timeout=2).status==200 else 1)"

WORKDIR /app/src
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8099"]
