#!/usr/bin/env bash
# Quét lỗ hổng đã biết trong requirements.lock (dùng cả trong CI).
# Cần: pip install "pip-audit==2.7.3"
#
# torch bản CPU mang nhãn "+cpu" (vd. 2.15.0+cpu), cơ sở dữ liệu lỗ hổng chỉ
# biết bản "2.15.0". Bỏ nhãn trước khi quét để torch KHÔNG bị bỏ qua; mã băm
# không cần cho bước này nên bỏ luôn.
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
grep -E '^[A-Za-z0-9_.-]+==' requirements.lock | sed -E 's/ *\\$//; s/\+[a-z0-9]+$//' > "$tmp"
echo "quét $(wc -l < "$tmp") gói trong requirements.lock"
pip-audit --no-deps --disable-pip --strict -r "$tmp"
