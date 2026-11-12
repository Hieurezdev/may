# Mây · E-commerce

Bản riêng từ giao diện và mã nguồn tham khảo của mây., triển khai các luồng dữ liệu theo báo cáo phân tích thiết kế hệ thống. Thư mục tham khảo không bị sửa. API key, tài khoản khách và cơ sở dữ liệu cũ không được sao chép.

## Chạy bản demo

Python 3.12+:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
MAY_DEMO_MODE=1 .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8766
```

Mở http://127.0.0.1:8766. Hợp đồng DTO và tài liệu API: http://127.0.0.1:8766/docs.

CSDL SQLite được khởi tạo tại `data/may.sqlite3` từ hai migration có phiên bản. Dùng `MAY_DB_PATH` để chọn CSDL riêng. Không trỏ bản mới vào database của mã tham khảo vì cấu trúc dữ liệu khác nhau.

Chỉ khi có `MAY_DEMO_MODE=1`, ứng dụng mới tạo ba tài khoản cục bộ:

| Vai trò | Email | Mật khẩu demo |
| --- | --- | --- |
| Nhân viên cửa hàng | merchant@may.local | MayDemo2026! |
| Nhân viên hỗ trợ | support@may.local | MayDemo2026! |
| Người vận hành | operator@may.local | MayDemo2026! |

Đăng nhập bằng biểu tượng tài khoản rồi chọn **Quản trị cửa hàng**. Khách tự đăng ký tài khoản; khách vãng lai cũng có thể mua bằng phiên cookie riêng. Các tài khoản demo không được tạo khi tắt chế độ demo.

## Các chức năng

- Giữ giao diện mây., danh mục 105 sản phẩm, ảnh nguồn, bộ lọc danh mục, chi tiết màu/size, hàng mới, yêu thích và phòng phối đồ camera từ bản tham khảo.
- Giỏ hàng lưu tại máy chủ, quote tính lại giá và voucher. Checkout xác nhận tổng tiền, giữ chỗ tồn kho, tạo snapshot dòng hàng và lần thanh toán trong một giao dịch SQLite.
- Bắt buộc gửi `expected_total` đã xác nhận; giá đổi trả HTTP 409 kèm quote mới để khách xác nhận lại bằng khóa mới. Chống đặt trùng bằng idempotency key; chặn cùng khóa với nội dung khác. Hai khách không thể đặt cùng đơn vị tồn cuối.
- Thanh toán trực tuyến **mô phỏng** qua cùng luồng HMAC callback đã kiểm tra số tiền, loại tiền, mã giao dịch và trùng sự kiện. Không thu tiền thật. Lỗi/hết hạn giải phóng giữ chỗ; thanh toán đến muộn vào trạng thái đối soát.
- Merchant chuẩn bị đơn, nhập mã vận đơn, xuất kho và xác nhận giao hàng. Xuất kho giảm cả on-hand và reserved. COD được ghi nhận đã thu khi xác nhận giao thành công trong bản demo; chưa có API hãng vận chuyển thật.
- Khách theo dõi đơn, vận đơn, hủy đơn và yêu cầu trả từng dòng/số lượng. Support duyệt; merchant kiểm tra hàng và quyết định nhập lại kho; support tạo khoản hoàn. Operator mô phỏng callback hoàn tiền. Khoản hoàn đang chờ và đã hoàn đều tính vào giới hạn tiền đã thu.
- Phân quyền customer/merchant/support/operator kiểm tra tại máy chủ. Cookie phiên HttpOnly, SameSite Strict; mật khẩu scrypt; đổi token khi đăng ký/đăng nhập. API proof dành cho khách cấp mã chỉ đọc một đơn, hết hạn sau 24 giờ.
- Tài khoản lưu địa chỉ; khách chủ động bật/tắt cá nhân hóa.
- DBSCAN phân cụm **khách hàng** từ đơn đã giao, recency, frequency, net spend, basket size, return rate và category shares. Scaler chỉ fit tập train; kiểm tra holdout thời gian, nhiễu và độ ổn định trước khi duyệt. Khi chưa đủ dữ liệu, từ chối train và dùng gợi ý phổ biến có nêu lý do. Không tự tạo lịch sử mua hàng giả trong database chạy ứng dụng.
- Gợi ý từ khách cùng cụm; kết quả được lọc lại sản phẩm đang bán và còn hàng. Thu hồi đồng ý làm mất hiệu lực các mô hình chứa dữ liệu của khách đó và xóa assignment/core vectors liên quan.
- BGE-M3 cho văn bản, visual encoder CLIP riêng cho ảnh; chỉ mục có phiên bản, hash nguồn và được công bố nguyên phiên bản. Tìm kiếm kết hợp hợp nhất thứ hạng và loại trùng. Thiếu encoder/chỉ mục được thông báo rõ; tìm văn bản có thể dùng lexical fallback.
- Giọng nói gửi tới ElevenLabs sau sự đồng ý, hiển thị transcript sửa được trước khi tìm. Ami/Qwen và giọng nói từ mã tham khảo chỉ hoạt động khi cấu hình riêng.
- Outbox và audit lưu cùng giao dịch nghiệp vụ. Worker thông báo tùy chọn có lease, idempotency header và retry giới hạn cho lỗi tạm thời.

## Cấu hình dịch vụ

Sao chép `.env.example` thành `.env.local`, điền cấu hình riêng. Không đưa API key vào frontend hoặc commit. Không có key của bản tham khảo trong dự án này.

Bản web vẫn chạy khi chưa cấu hình AI. Dịch vụ thiếu cấu hình trả lỗi rõ ràng; không tạo kết quả AI hoặc phiên âm giả.

### BGE-M3 và visual encoder chạy cục bộ

```bash
.venv/bin/python -m pip install -e '.[encoders]'
.venv/bin/python scripts/prepare-encoders.py
.venv/bin/python -m uvicorn backend.encoder_server:app --host 127.0.0.1 --port 8768
```

Script tải model vào `data/models` và ghi revision vào cấu hình cục bộ. Lần đầu cần Internet và dung lượng cho model. Sau khi dịch vụ encoder chạy, đăng nhập operator và xây lần lượt chỉ mục văn bản, ảnh tại màn hình vận hành. Không chạy model trong giao dịch checkout. Các kiểm thử tự động dùng vector có kiểm soát để không tải model hoặc gọi dịch vụ trả phí.

Nguồn API và cách dùng model: [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3), [Sentence Transformers image search](https://sbert.net/examples/sentence_transformer/applications/image-search/README.html), [ElevenLabs STT](https://elevenlabs.io/docs/api-reference/speech-to-text/convert).

## Cấu trúc dữ liệu và mã

- `backend/main.py`: application composition, lifecycle, static assets and browser security.
- `backend/api/`: account, catalog, chat and try-on HTTP endpoints; commerce, discovery and speech retain their existing routers.
- `migrations/`: schema SQLite, CHECK, FK, unique key, index và trigger bảo vệ snapshot.
- `backend/models.py`: giá trị domain và quy tắc trạng thái; `backend/dtos/`: input/output được Pydantic kiểm tra, tách theo catalog, accounts, cart, orders, payments, returns, discovery và experience; OpenAPI tự sinh.
- `checkout.py`, `inventory.py`, `payments.py`, `fulfillment.py`, `returns.py`: các giao dịch thương mại.
- `discovery.py`, `clustering.py`, `recommendations.py`, `encoder_server.py`: tìm kiếm và DBSCAN.
- `auth.py`, `notifications.py`: quyền truy cập và outbox.
- `frontend/commerce-ui.js`: các màn hình chức năng mới dùng lại component giao diện mây.
- `docs/openapi.json`: generated API schema, including the required integer `expected_total` on checkout.
- `docs/design.md`: mapping với báo cáo, dữ liệu và hợp đồng nghiệp vụ.
- `output/screenshots/`: ảnh trình duyệt thực tế và manifest của phiên minh họa báo cáo.

## Kiểm thử

```bash
.venv/bin/python -m unittest discover -s tests -v
npm ci --ignore-scripts --no-audit --no-fund
npm run test:camera
MAY_TEST_BASE_URL=http://127.0.0.1:8767 npm run test:browser
```

Chạy server riêng với `MAY_DEMO_MODE=1 MAY_DB_PATH=/private/tmp/assignment06-browser.sqlite3` trên cổng 8767 trước khi kiểm thử trình duyệt. Bộ trình duyệt tạo dữ liệu minh họa trong DB này; không dùng database làm việc. Mặc định dùng Brave trên macOS; đặt `MAY_BROWSER_PATH` nếu dùng Chromium ở đường dẫn khác. `MAY_SCREENSHOT_DIR` chọn nơi lưu ảnh.

## Phạm vi minh họa

Thanh toán, hoàn tiền và xác nhận giao nhận là các thao tác mô phỏng cục bộ được ghi rõ trên UI. Chưa tích hợp cổng tiền thật hay hãng giao vận. Kết quả DBSCAN trên dữ liệu tổng hợp trong kiểm thử chỉ xác minh pipeline; không chứng minh hiệu quả gợi ý trên khách hàng thật. Chưa đo tải lớn hoặc cam kết SLA. Catalog, ảnh, font, runtime camera/Live2D được tái sử dụng từ dự án tham khảo do người dùng cung cấp; giữ các giấy phép tại `frontend/assets`, `frontend/vendor` và `integrations`.
