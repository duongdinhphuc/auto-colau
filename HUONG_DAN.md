# Bảng điều khiển auto Cờ Lau Loạn Thế (PC Windows)

## Cài đặt (làm 1 lần)
1. Cài Python 3.10 trở lên từ python.org. Lúc cài nhớ tích **Add Python to PATH**.
2. Mở CMD trong thư mục này rồi chạy:
   `pip install pyautogui opencv-python numpy pillow pytesseract`
3. **Cài Tesseract-OCR**: đây là chương trình đọc chữ, bot dùng nó để đọc tên quái. Tải bản cài cho Windows ở github.com/UB-Mannheim/tesseract/wiki.
   Lúc cài, ở mục *Additional language data*, tích chọn **Vietnamese**. Cài vào thư mục mặc định `C:\Program Files\Tesseract-OCR`.
4. Mở game ở chế độ **cửa sổ**, giữ nguyên kích thước cửa sổ (kéo đi chỗ khác thì không sao).
5. Bấm đúp vào **chay.bat** để mở bảng điều khiển. Nếu script không click được vào game: chuột phải vào chay.bat → Run as administrator.

## Tab "Cài đặt" (làm theo thứ tự)
Mỗi lần bấm **Chụp** hoặc **Chọn**, màn hình sẽ đứng hình để bạn **kéo chuột chọn vùng**. Nhấn Esc để bỏ qua.

1. **Cửa sổ game**: để nguyên tên "Cờ Lau Loạn Thế" rồi bấm **Tìm**.
   Nhập **Tên nhân vật** của bạn (vd: phucdd). Đứng ngoài map rồi bấm **Kiểm tra đọc chữ** để xem bot có đọc được tên trên màn hình không.
2. **Bàn cờ**: vào một trận, bấm *Chọn vùng bàn cờ*, rồi kéo từ góc trên-trái ô đầu tiên tới góc dưới-phải ô cuối cùng.
   Sau đó bấm *Lấy mẫu tất cả viên* và lần lượt bấm vào 1 viên mỗi loại: đào, tim, vàng, sao, kiếm, âm dương, giọt tím.
   Cột **Ưu tiên** là điểm cộng khi ăn loại viên đó. Mặc định mình để Kiếm = 10; viên nào quan trọng hơn thì bạn tăng lên.
   Bấm *Kiểm tra bàn cờ* để xem script đọc bàn cờ có đúng không.
3. **Thanh máu và thanh nội lực**: trong trận, kéo chọn phần bên trong thanh đỏ (máu) và thanh nội lực của bạn.
   Nếu nội lực là thanh xanh dương chứ không phải xanh lá, đổi ô Màu sang `blue`.
4. **Ảnh mẫu các nút**: bắt buộc phải chụp *Đầu hàng*, *Đóng* và *Nút đánh*.
   Các nút còn lại cần cho tự dùng bình máu, tự dùng kỹ năng và đếm số trận thua.
5. **Di chuyển**: nhập phím đi trái/phải nếu bản PC dùng phím. Nếu không, script sẽ bấm thẳng vào quái.

## Tab "Tự động"
- **Bản đồ**: bấm *+ Map* rồi gõ tên map đúng như ở góc trên-phải game. Bấm *Nhận diện* để bot tự đọc tên map đang đứng.
- **Quái**: gõ **tên quái** đúng như dòng chữ trên đầu con quái và cấp (nếu muốn), rồi bấm **Thêm**. Tích chọn những con muốn đánh.
  Bot đọc chữ trên màn hình để tìm con đó. Gõ có dấu hay không dấu đều được, và bot chấp nhận đọc sai 1–2 ký tự.
- **Quét màn hình**: báo mỗi con trong danh sách đang thấy mấy con trên màn hình, kèm toàn bộ chữ bot đọc được (xem ở ô log).
  Nếu bot không thấy con nào dù quái đang hiện, xem phần "Khi bot không đọc được tên" ở cuối.
- **Kỹ năng**: mở bảng Kỹ năng trong trận, bấm *Chụp* để chụp biểu tượng từng kỹ năng, rồi chọn 1 kỹ năng (hoặc "Không dùng").
- **Bình máu**: tích ô và đặt mức % máu.
- **Tự dừng khi**: mặc định dừng khi thua 2 trận liên tiếp (vì thua bị trừ kinh nghiệm) hoặc khi đã chạy 120 phút.
- Bấm **Bắt đầu**. Dừng khẩn cấp: kéo chuột lên **góc trên-trái** màn hình.

## Cách bot đánh trong trận
- Chờ bàn cờ đứng yên và nhận ra được ít nhất 80% số ô thì mới đi (lúc tới lượt đối thủ, bot sẽ chờ).
- Ưu tiên nước **ăn 4 viên trở lên** để được đi thêm lượt, rồi tới chuỗi ăn liên tiếp và viên có điểm ưu tiên cao.
  Bot cũng tránh nước đi để lại nước ăn ngon cho đối thủ.
- Đầu lượt: nếu máu dưới mức đã đặt thì dùng bình; nếu nội lực đầy thì dùng kỹ năng đã chọn.

## Kích thước cửa sổ
- Lần đầu chụp mẫu hoặc chọn vùng, bot ghi lại kích thước cửa sổ game.
- Mỗi lần bấm Bắt đầu, và cả trong lúc đang chạy, nếu cửa sổ bị phóng to hay kéo giãn thì bot tự đưa về đúng kích thước cũ.
- Nếu game khoá kích thước cửa sổ, bot sẽ ghi cảnh báo trong ô log. Khi đó bạn tự kéo cửa sổ lại cho đúng, hoặc cài lại vùng bàn cờ và các ảnh mẫu.

## Khi bot không đọc được tên
- Phóng to cửa sổ game: chữ càng to thì đọc càng chuẩn.
- Mở `config.json` và tăng `ocr_scale` (3 → 4).
- Nếu tên quái không phải chữ trắng, giảm `ocr_white_v` (185 → 150).
- Không nhận ra map: bot đọc riêng ô tên map ở góc trên-phải (25% bên phải, 12% phía trên). Nếu giao diện khác, thêm `"map_region": [x1, y1, x2, y2]` (toạ độ trong cửa sổ game) vào `config.json`.
- Nếu bot hay nhận nhầm tên quái này thành quái khác, tăng `name_match` (0.72 → 0.8).

## Thang leo
Mỗi map có một kiểu thang riêng (thang gỗ, thang dây...). Khi đứng ở map mới, chọn map đó ở tab **Tự động** rồi bấm **Chụp thang**, kéo chọn sát một đoạn thang khoảng 4–6 bậc. Bên cạnh nút sẽ hiện "thang: ✔" khi map đã có ảnh thang. Một ảnh dùng được cho cả ban ngày lẫn ban đêm. Map Hồng Giang đã có sẵn.

## Theme ngày / đêm
Game đổi theme ban ngày / ban đêm theo giờ thật. Bot đã được chỉnh để chạy được cả hai:
- Các nút tròn (Đánh, Đầu hàng, Túi đồ): bot chỉ so phần lòng nút, không so nền quanh nút.
- Chữ "Lượt của đối thủ": bot chỉ so phần chữ đỏ, không so các viên cờ phía sau.
- Thanh máu: bot đọc dòng số (vd 349/543) trên thanh.
- Tên nhân vật màu xanh ngọc: lọc chặt để không lẫn với bầu trời ban ngày (`ocr_cyan_s`, `ocr_cyan_v` trong `config.json`).
Khi chụp lại ảnh mẫu, nên cắt sát nút, đừng lấy nhiều nền xung quanh. Nếu thấy bot chỉ hỏng vào một buổi (ngày hoặc đêm), hãy quay video gửi lại.

## Lưu ý
- Game có sẵn tính năng "Tự động" nhưng giới hạn số giờ mỗi ngày. Chạy bot ngoài là vi phạm điều khoản của game và có thể bị khoá tài khoản.
- Chỉ dùng cho đánh quái (PvE), không dùng cho PvP.
- Nhớ nghỉ ngơi: chính game cũng cảnh báo chơi quá 180 phút mỗi ngày ảnh hưởng sức khoẻ.
