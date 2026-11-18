# Báo cáo Day 09 - Phạm Công Bằng, 2A202603134

## 1. Kết luận trước
Pipeline đưa ra kết luận Hold.
Lô dữ liệu thô ban đầu có 224 ảnh. Khâu tiếp nhận lọc bỏ 21 ảnh gồm 8 ảnh trùng lặp từng byte, 3 ảnh trùng lặp phash, 5 ảnh trùng tập test, 3 ảnh kích thước quá nhỏ, 2 ảnh hỏng dữ liệu. Số ảnh hợp lệ đưa vào pipeline là 203 ảnh và được lưu ra thư mục dữ liệu sạch.
Lý do nhận kết luận Hold: Khâu sửa tự động và hàng đợi duyệt đã xử lý hết toàn bộ lỗi bắt buộc. Tuy nhiên số ảnh dính cảnh báo còn lại là 44 trên tổng số 203 ảnh, tương đương 21.67%, vượt ngưỡng trần 10% quy định. Hàng đợi có 130 ảnh nhưng ngân sách chỉ cho phép duyệt 80 ảnh, còn lại 50 ảnh chưa được xử lý nên cổng quyết định không cho phép Release.

## 2. Lỗi và phân việc
Tổng hợp các vấn đề ghi nhận từ danh sách lỗi đợt một gồm 57 lỗi bắt buộc và 171 cảnh báo trên 224 ảnh:

| Mã lỗi | Số lượng | Phân việc | Lý do xử lý |
|---|---:|---|---|
| dup_image_exact | 8 ảnh | Máy | Trùng từng byte theo mã băm md5, máy xóa an toàn |
| dup_image_near | 3 ảnh | Máy | Trùng gần đúng theo mã băm phash, máy loại bỏ |
| leak_test | 5 ảnh | Máy | Trùng tập kiểm thử, máy loại bỏ để tránh học vẹt |
| bad_size | 3 ảnh | Máy | Cạnh ngắn dưới 250 pixel, máy loại bỏ theo tiêu chuẩn kích thước |
| corrupt_image | 2 ảnh | Máy | Tệp ảnh hỏng nhị phân, máy loại bỏ |
| bad_format | 3 dòng | Máy | Dòng nhãn chứa giá trị không hợp lệ hoặc sai số cột, máy xóa dòng |
| bad_class_id | 6 dòng | Máy | Chỉ số lớp nằm ngoài phạm vi cho phép, máy xóa dòng |
| bad_class_name | 2 lỗi | Máy | Tên lớp trong cấu hình sai quy ước, máy đổi tên lớp |
| box_zero | 4 dòng | Máy | Chiều rộng hoặc chiều cao không dương, máy xóa dòng |
| dup_box | 7 dòng | Máy | Trùng lặp cùng lớp với chỉ số iou lớn hơn 0.9, máy xóa dòng |
| box_out_of_image | 8 dòng | Máy | Tọa độ vượt ra ngoài khung hình, máy cắt gọn viền về đoạn từ 0 đến 1 |
| missing_label_file | 6 ảnh | Người | Thiếu tệp nhãn, máy không tự đoán được nên đưa người gán bổ sung |
| empty_label | 12 ảnh | Người | Tệp nhãn rỗng, cần người xác nhận ảnh không có vật thể hay bị bỏ sót |
| box_tiny | 6 dòng | Người | Cạnh ngắn dưới 12 pixel, cần người đánh giá vật thể ở xa hay nhiễu |
| box_huge | 3 dòng | Người | Hộp chiếm trên 95% khung hình, cần người kiểm tra độ bao trùm |
| possible_missing | 68 hộp | Người | Mô hình nhận diện thấy vật rõ nhưng nhãn thiếu, cần người vẽ bù |
| possible_wrong_class | 18 hộp | Người | Khớp vị trí với mô hình nhưng lệch lớp, cần người chọn lại lớp |
| possible_loose_box | 31 hộp | Người | Đúng lớp nhưng viền lệch, cần người nắn lại tọa độ |
| possible_false_pos | 29 dòng | Người | Hộp trong nhãn không có mô hình nào phát hiện, cần người kiểm tra |
| class_rare | 4 lỗi | Không sửa | Cảnh báo mất cân bằng dữ liệu, sinh ra trước khâu sửa tự động |

Cơ chế sắp xếp hàng đợi duyệt:
Hàng đợi tính độ ưu tiên theo tổng trọng số các cảnh báo trong từng ảnh. Nhóm ảnh thiếu nhãn có trọng số cao nhất là 10 nên tự động đứng đầu hàng đợi. Tiếp theo là các ảnh dồn nhiều lỗi và cảnh báo. Với ngân sách duyệt 80 ảnh, người duyệt đã xử lý toàn bộ 6 ảnh thiếu nhãn cùng các lỗi sai lớp và thiếu hộp lớn. 50 ảnh còn lại ở nửa sau hàng đợi đều là các cảnh báo đơn lẻ như lệch viền nhẹ hoặc hộp kích thước nhỏ.

## 3. Calibration
Kết quả quét thử nghiệm trên 39 ảnh thuộc tập hiệu chuẩn:

| Tham số | Ban đầu | Đã chọn | Thay đổi độ chính xác và độ bao phủ | Lý do lựa chọn |
|---|:---:|:---:|---|---|
| duplicates.phash_dist | 2 | 8 | Tỉ lệ phát hiện tăng từ 0.50 lên 0.67 trong khi độ chính xác giữ nguyên 1.00 | Ưu tiên độ chính xác 1.00 vì khâu tiếp nhận xóa trực tiếp tệp ảnh. Ngưỡng 8 bắt được ảnh thu nhỏ 75% so với ảnh gốc. Không chọn mức 16 vì trên tập dữ liệu thô sẽ xóa nhầm hai ảnh khác nhau chụp lệch góc. |
| second_opinion.conf | 0.25 | 0.50 | Độ chính xác tăng từ 0.50 lên 0.57 và giữ nguyên độ bao phủ 1.00 | Ngưỡng 0.25 khiến một nửa số cảnh báo là báo động giả. Ngưỡng 0.50 giảm bớt báo động giả giúp tăng độ chính xác mà vẫn bắt trọn toàn bộ các hộp thiếu. Không tăng quá 0.70 vì độ bao phủ sẽ giảm mạnh. |

Hạn chế của tập hiệu chuẩn:
Tập hiệu chuẩn chỉ có 39 ảnh nên việc bắt thêm một trường hợp làm tỉ lệ biến động rất lớn. Điển hình là mức phash bằng 16 cho điểm số cao nhất trên tập hiệu chuẩn nhưng khi áp dụng vào tập dữ liệu thô lại xóa nhầm ảnh hợp lệ. Tập hiệu chuẩn cũng không có trường hợp rò rỉ dữ liệu kiểm thử và các ca kiểm tra chỉ xoay quanh hai lớp người và xe con, chưa bao quát được các loại phương tiện khác.

## 4. Cửa chặn và điều pipeline không bắt được
Chứng minh cổng quyết định chặn đúng:
Khi chạy thử nghiệm với ngân sách duyệt bằng 0 qua lệnh python -m pipeline.run --budget 0, các ảnh thiếu nhãn không có người bổ sung nên lỗi bắt buộc còn nguyên. Cổng quyết định lập tức đưa ra phán quyết Rework, tiến trình dừng lại và không xuất bất kỳ tệp dữ liệu sạch nào.

Các điểm mù pipeline bỏ sót:
1. Hộp lệch nhẹ: Những hộp người vẽ lệch nhưng chỉ số iou so với mô hình vẫn đạt từ 0.5 trở lên thì pipeline vẫn bỏ qua.
2. Hai nguồn cùng đoán sai: Nếu người gán nhãn nhầm xe tải thành xe con và mô hình tham chiếu cũng đoán sai tương tự thì hệ thống coi như trùng khớp và không đưa ra cảnh báo.
3. Ảnh biến dạng lớn: Những ảnh bị cắt khung hình quá một nửa hoặc bị lật gương có độ lệch phash lớn hơn 16 sẽ lọt qua ngưỡng lọc của khâu tiếp nhận.

## 5. So sánh huấn luyện raw và clean
Thử nghiệm huấn luyện được thực hiện cục bộ trên máy với cấu hình rút gọn gồm 15 epoch, kích thước ảnh 416, batch 16 qua 2 seed ngẫu nhiên 0 và 1 trên mô hình yolo26n.

Bảng tổng hợp kết quả đo trên 100 ảnh tập kiểm thử:

| Biến thể | Số ảnh train | Số seed | map50 trung bình | map50_95 trung bình | precision trung bình | recall trung bình |
|---|---:|---:|---|---|---|---|
| raw | 224 | 2 | 0.621 ± 0.006 | 0.419 ± 0.018 | 0.639 ± 0.002 | 0.577 ± 0.013 |
| clean | 203 | 2 | 0.663 ± 0.039 | 0.436 ± 0.022 | 0.708 ± 0.002 | 0.548 ± 0.037 |

Độ chênh lệch map50 giữa dữ liệu sạch và dữ liệu thô là dương 0.042.
Chênh lệch này cao hơn độ lệch chuẩn giữa các seed của tập raw là 0.006 và xấp xỉ độ lệch chuẩn của tập clean là 0.039, cho thấy dữ liệu sạch đem lại cải thiện thực tế thay vì chỉ là nhiễu ngẫu nhiên.
Hai nguyên nhân chính dẫn đến sự cải thiện:
1. Loại bỏ rò rỉ và trùng lặp: Tập thô chứa 5 ảnh rò rỉ từ tập kiểm thử và 8 ảnh trùng lặp byte làm mô hình bị học vẹt. Việc loại bỏ các ảnh này giúp mô hình tổng quát hóa tốt hơn trên tập kiểm thử độc lập.
2. Sửa lỗi nhãn và nắn viền hộp: Khâu sửa tự động đã chỉnh sửa 35 trường hợp hộp tràn viền, xóa hộp rác và bổ sung nhãn thiếu, giúp độ chính xác precision tăng mạnh từ 0.639 lên 0.708.

## 6. Quyết định và ghi chú sử dụng công cụ
Quyết định cuối cùng: Hold.
Để đưa dữ liệu sang trạng thái Release, dự án cần cấp thêm 50 lượt duyệt để người kiểm tra xử lý nốt các cảnh báo còn lại trong hàng đợi, hoặc điều chỉnh nâng ngưỡng tỉ lệ cảnh báo cho phép nếu chấp nhận các cảnh báo nhỏ.

Ghi chú sử dụng công cụ:
- Yêu cầu ban đầu: Tạo khung mã nguồn cho các mô đun kiểm tra định dạng, cổng quyết định, sửa tự động và mô hình tham chiếu theo đúng tài liệu thiết kế và quy trình kiểm thử.
- Phương pháp kiểm tra: Chạy toàn bộ 84 bài kiểm thử đơn vị, chạy kịch bản kiểm tra bài nộp và thử nghiệm các trường hợp biên như ngân sách duyệt bằng 0 hoặc dữ liệu rỗng.
- Xử lý lỗi mã nguồn: Trong mô đun mô hình tham chiếu, mã nguồn sinh ra tự động có thêm điều kiện lọc diện tích vào hàm kiểm tra dương tính giả, làm sai lệch yêu cầu kiểm tra mọi dự đoán đạt ngưỡng tin cậy. Lỗi này được phát hiện qua bài kiểm thử đơn vị và đã được loại bỏ để hàm chạy chính xác.

Mở rộng kiểm tra và đối chiếu công cụ:
- Kiểm tra tỉ lệ khung hình: Đã bổ sung thêm mô đun kiểm tra tỉ lệ cạnh bất thường nhằm phát hiện các hộp quá dẹt hoặc quá mảnh có tỉ lệ cạnh vượt quá 10 lần, đi kèm bộ 5 bài kiểm thử đơn vị đạt chuẩn.
- Đối chiếu bộ lọc hộp nhỏ: Khi lọc hộp có chiều rộng dưới 20 pixel, các ảnh như img_0161 và img_0051 đều khớp với các cảnh báo box_tiny của pipeline. Ngưỡng 20 pixel rộng hơn ngưỡng 12 pixel của pipeline nên sẽ bắt thêm các hộp ở cự ly xa hơn.
- Thuộc tính can_review: Người gán đánh dấu thuộc tính này khi gặp vật thể bị che khuất hoặc nhập nhằng về lớp để báo hiệu cho người kiểm duyệt cấp cao. Trong pipeline, thông tin tương tự được tự động chuyển hóa thành các cảnh báo nghi ngờ sai lớp hoặc lệch viền và tính trọng số đẩy lên đầu hàng đợi duyệt.
