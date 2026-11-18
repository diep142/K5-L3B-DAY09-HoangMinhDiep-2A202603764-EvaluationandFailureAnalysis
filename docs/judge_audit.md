# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | có | dùng có điều kiện |
| helpful | 100 | 0.375 | 1.000 | 0.300 | không | loại |

Nguồn: replay công khai `data/eval/judge_tone_public.csv` và `data/eval/judge_helpful_public.csv`; positive class là `FAIL`. Rogan–Gladen hiệu chỉnh fail rate của `tone_ok` từ 0.280 lên 0.300; `helpful` từ 0.090 lên 0.300. `helpful` có confusion matrix TP=9, FP=0, FN=21, TN=70: judge không dự báo nhầm FAIL nhưng bỏ sót 70% lỗi, nên recall=0.300 và κ=0.375 không đạt sàn. Không dùng judge này làm gate. `tone_ok` đạt các sàn trên tập này, nhưng chỉ nên là tín hiệu phụ do dữ liệu calibration/replay công khai chưa phải tập held-out.

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | HL-015 | PASS | FAIL | Người | Reply báo 55.000đ nhưng ledger 40.000đ; rubric phải kiểm chứng số tiền với ledger, không chỉ độ trôi chảy. |
| 2 | HL-016 | PASS | FAIL | Người | Reply báo 55.000đ nhưng ledger 35.000đ; thêm đối chiếu mọi số tiền được nêu với kết quả có thẩm quyền. |
| 3 | HL-020 | PASS | FAIL | Người | Reply báo 90.000đ nhưng ledger 120.000đ; sai tiền phải là lỗi factual blocking. |
| 4 | HL-047 | PASS | FAIL | Người | “Ok bạn…” sai xưng hô/giọng điệu; rubric cần đánh giá sự phù hợp với khách, không chỉ liên quan câu hỏi. |
| 5 | HL-053 | PASS | FAIL | Người | Reply báo 110.000đ nhưng ledger 90.000đ; lời xin lỗi dài không bù được thông tin giao dịch sai. |
| 6 | HL-087 | PASS | FAIL | Người | Reply báo 60.000đ nhưng ledger 90.000đ; củng cố quy tắc kiểm tra con số định lượng. |
| 7 | H-081 (tone) | FAIL | PASS | Judge | Người gán nhãn đọc nhầm ticket; sửa nhãn sau khi đối chiếu fact, không sửa rubric để hợp thức hóa nhãn sai. |
| 8 | H-042 (tone) | FAIL | PASS | Người | Câu ngắn vẫn đủ thông tin; bỏ tiêu chí xin lỗi bắt buộc nếu không có căn cứ nghiệp vụ. |

## Kết luận
- Loại `helpful`: TP=9, FP=0, FN=21, TN=70; recall 0.300 và κ=0.375 dưới sàn, nên judge bỏ sót quá nhiều câu trả lời lỗi để làm gate.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
- `helpful` bị loại làm gate; trước khi hiệu chuẩn lại, cần rubric hữu ích có tiêu chí quan sát được (liên quan yêu cầu, đúng tiền/trạng thái, không hứa sai) và mẫu nhãn độc lập.
