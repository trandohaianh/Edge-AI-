"""Kiểm thử đầu-cuối trên trình duyệt thật: tự động hoá kịch bản E-1..E-10
của docs/TEST_PLAN.md mục 3, cộng luồng nhập mã truy cập (trước đây chỉ kiểm
qua API). Người trực thao tác thế nào thì bài kiểm thử bấm đúng như vậy.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[3]

DANG_CHAY = "● đang chạy"


def _open(page, server, scenario="clear"):
    server.post(f"/api/scenario/{scenario}")
    page.goto(server.url + "/")
    expect(page.locator("#live")).to_have_text(DANG_CHAY)
    expect(page.locator("#trk tr[data-tid]").first).to_be_visible()


def test_e1_mo_trang_thay_dang_chay_vet_bam_va_ban_do(page, server):
    _open(page, server)
    expect(page.locator("#scn")).not_to_have_text("—")
    expect(page.locator("#scen button")).to_have_count(7)
    # Bản đồ có vẽ: canvas không còn trống.
    drawn = page.evaluate(
        "() => { const c=document.getElementById('map');"
        " const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;"
        " for (let i=3;i<d.length;i+=4) if (d[i]) return true; return false; }"
    )
    assert drawn
    assert page.js_errors == []


def test_e2_e5_xac_nhan_ghi_vao_nhat_ky_va_lenh_kiem_tra_doc_duoc(page, server):
    before = len(server.audit_lines())
    _open(page, server)
    tid = int(page.locator("#trk tr.sel").get_attribute("data-tid"))
    page.click("#bok")
    expect(page.locator("#actmsg")).to_have_text("Đã ghi quyết định vào nhật ký.")
    row = page.locator(f'#trk tr[data-tid="{tid}"]')
    expect(row).to_contain_text("ĐÃ XÁC NHẬN")
    expect(page.locator("#bok")).to_be_disabled()
    expect(page.locator("#audit")).to_contain_text("XÁC NHẬN")

    lines = server.audit_lines()
    assert len(lines) == before + 1
    assert lines[-1]["action"] == "xac_nhan" and lines[-1]["tid"] == tid
    # E-5: lệnh kiểm tra chuỗi băm của kỹ thuật viên đọc được nhật ký vừa ghi,
    # kể cả khi đầu ra bị chuyển hướng (lỗi L-1).
    r = subprocess.run(
        [sys.executable, "-m", "edge_ai.api.audit_log", str(server.log)],
        cwd=ROOT / "backend",
        capture_output=True,
        timeout=60,
    )
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0, out + r.stderr.decode("utf-8", "replace")
    assert f"{before + 1} dòng hợp lệ" in out


def test_e3_e4_nhieu_muc_tieu_chi_bo_qua_dung_vet_duoc_chon(page, server):
    _open(page, server)
    page.get_by_role("button", name="Nhiều mục tiêu").click()
    expect(page.locator("#actmsg")).to_have_text("Đã chuyển kịch bản: Nhiều mục tiêu")
    # Chờ hệ thống xác nhận đủ các drone: mỗi drone một hàng "CHỜ QUYẾT ĐỊNH".
    page.wait_for_function(
        "() => document.querySelectorAll('#trk .tag.warn').length >= 2", timeout=60_000
    )
    waiting = page.locator("#trk tr:has(.tag.warn)")
    tid = int(waiting.nth(1).get_attribute("data-tid"))
    page.locator(f'#trk tr[data-tid="{tid}"]').click()
    expect(page.locator(f'#trk tr[data-tid="{tid}"]')).to_have_class("sel")
    page.click("#bno")
    expect(page.locator("#actmsg")).to_have_text("Đã ghi quyết định vào nhật ký.")
    expect(page.locator(f'#trk tr[data-tid="{tid}"]')).to_contain_text("ĐÃ BỎ QUA")
    # Chỉ đúng một vết bị bỏ qua; các drone khác vẫn chờ người quyết.
    expect(page.locator("#trk .tag.no")).to_have_count(1)
    assert page.locator("#trk .tag.warn").count() >= 1
    last = server.audit_lines()[-1]
    assert last["action"] == "bo_qua" and last["tid"] == tid


def test_e6_e8_mat_ket_noi_thi_khoa_nut_roi_tu_hoi_phuc(page, own_server):
    _open(page, own_server)
    own_server.stop()
    # E-6: số liệu cũ bị làm mờ, băng đỏ, nút quyết định bị khoá.
    expect(page.locator("#live")).to_have_text("● mất kết nối máy chủ")
    expect(page.locator("body")).to_have_class("stale")
    expect(page.locator("#banner")).to_contain_text("Mất kết nối máy chủ")
    expect(page.locator("#bok")).to_be_disabled()
    expect(page.locator("#bno")).to_be_disabled()
    # E-7: lệnh gửi khi mất kết nối báo tiếng Việt, nói rõ là chưa ghi gì.
    page.get_by_role("button", name="Trời quang").click()
    expect(page.locator("#actmsg")).to_contain_text("mất kết nối máy chủ — chưa có gì được ghi")
    expect(page.locator("#actmsg")).to_have_class("msg err")
    # E-8: máy chủ lên lại thì trang tự trở về bình thường, không cần tải lại.
    own_server.start()
    expect(page.locator("#live")).to_have_text(DANG_CHAY, timeout=30_000)
    expect(page.locator("body")).not_to_have_class("stale")
    expect(page.locator("#banner")).to_be_hidden()
    expect(page.locator("#bok")).to_be_enabled()


def test_ma_truy_cap_sai_bi_tu_choi_dung_thi_ghi_duoc(page, token_server):
    answers = ["ma-sai", "ma-e2e-dung"]
    asked: list[str] = []

    def on_dialog(d):
        asked.append(d.message)
        d.accept(answers.pop(0))

    page.on("dialog", on_dialog)
    token_server.post("/api/scenario/clear", token="ma-e2e-dung")
    page.goto(token_server.url + "/")
    expect(page.locator("#live")).to_have_text(DANG_CHAY)

    page.click("#bok")
    expect(page.locator("#actmsg")).to_contain_text("sai mã truy cập")
    assert token_server.audit_lines() == []

    page.click("#bok")
    expect(page.locator("#actmsg")).to_have_text("Đã ghi quyết định vào nhật ký.")
    assert len(asked) == 2 and "mã truy cập" in asked[0]
    assert len(token_server.audit_lines()) == 1
    # Mã chỉ nằm trong sessionStorage của tab, không bao giờ lên URL.
    assert "ma-e2e-dung" not in page.url
    assert page.evaluate("sessionStorage.getItem('edge_token')") == "ma-e2e-dung"
    # Lần bấm sau không hỏi lại mã.
    page.get_by_role("button", name="Trời quang").click()
    expect(page.locator("#actmsg")).to_have_text("Đã chuyển kịch bản: Trời quang")
    assert len(asked) == 2


def test_csp_chan_script_chen_vao_trang(page, server):
    _open(page, server)
    ran = page.evaluate(
        "() => { const s=document.createElement('script');"
        " s.textContent='window.__chen=1'; document.head.appendChild(s);"
        " return window.__chen === 1; }"
    )
    assert ran is False
