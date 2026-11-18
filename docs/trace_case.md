# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case đã phân tích: `seeded_regression C-002@55`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@55`; tái tạo bằng `python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 55`. |
| Triệu chứng | Lab 8 grader FAIL: status `resolved` thay vì `denied`; ledger ghi 20.000đ/1 refund trong khi nhãn là 0đ/0 refund. Reply tuyên bố đã hoàn 20.000đ. |
| Bước sai đầu tiên | Event 3 `model_override`: `{"delay_days": 5}`. |
| Vì sao là bước đầu tiên | Event 1 chuyển đúng phạm vi principal; event 2 đọc order O-202 từ DB với `delay_days=2`. Chỉ event 3 mới thay fact DB bằng số ngày trong ticket; event 4 tính refund 20.000đ từ fact sai, event 6 báo đã hoàn. |
| Failure mode | FM-03 `ticket_trust`. |
| Đối chứng | `fixed C-002@55` không có `model_override`; quote là 0 (`no_entitlement`), status `denied`, ledger 0đ và grader PASS. |
| Regression test | `test_ticket_override_is_detected_on_regression_and_not_fixed` trong `tests/test_lab9_graders.py`: chạy cả hai shape, xác nhận `DbFactKept` FAIL trên regression và PASS trên fixed. |
| Chưa chắc chắn | Trace chứng minh việc ghi đè và kết quả ở seed này; riêng trace không chứng minh tần suất lỗi trên seed khác. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
