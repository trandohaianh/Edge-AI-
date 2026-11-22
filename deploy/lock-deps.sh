#!/usr/bin/env bash
# Khoá phiên bản phụ thuộc và quét lỗ hổng (docs/SECURITY.md R-4).
#
#   bash deploy/lock-deps.sh          # sinh lại requirements.lock rồi quét
#   bash deploy/lock-deps.sh audit    # chỉ quét requirements.lock hiện có
#
# Chạy trong container python:3.12-slim để tệp khoá khớp đúng môi trường
# Docker (Linux, Python 3.12), dù máy đang dùng là Windows hay macOS.
# Lần sinh đầu tải mọi bản torch để lấy mã băm (vài GB, ~15 phút).
# Trên Windows/Git Bash: đặt MSYS_NO_PATHCONV=1 trước khi chạy.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-lock}"
IMAGE="python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"

docker run --rm -v "$PWD:/repo" -w /repo -e MODE="$MODE" "$IMAGE" bash -euo pipefail -c '
python -m pip install -q --root-user-action=ignore --disable-pip-version-check \
  "pip-tools==7.4.1" "pip-audit==2.7.3"
if [ "$MODE" = lock ]; then
  pip-compile -q --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    --output-file /tmp/lock.txt requirements.txt
  { sed -n "1,6p" requirements.lock; sed -n "/^[a-z]/,\$p" /tmp/lock.txt; } > /tmp/new.lock
  cp /tmp/new.lock requirements.lock
  echo "đã sinh lại requirements.lock"
fi
bash deploy/audit-deps.sh
'
