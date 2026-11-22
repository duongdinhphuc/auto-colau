# -*- coding: utf-8 -*-
"""
Lõi auto Cờ Lau Loạn Thế (PC Windows) - phần chơi đơn: đánh quái trên map.
Mọi toạ độ lưu trong config.json đều tính theo VÙNG TRONG CỬA SỔ GAME.
"""
import ctypes
import difflib
import json
import unicodedata
import os
import random
import re
import threading
import time

import cv2
import numpy as np

try:
    import pyautogui
except ImportError:
    pyautogui = None

BASE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(BASE, "templates")
CONFIG_PATH = os.path.join(BASE, "config.json")
MAPS_PATH = os.path.join(BASE, "maps.json")


def P(*parts):
    return os.path.join(BASE, *parts)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def imread(path):
    """cv2.imread không đọc được đường dẫn có dấu tiếng Việt trên Windows -> dùng imdecode."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    except Exception:
        return None


def imwrite(path, img):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(path)
    return ok


# =================================================================== bàn phím
# Game dùng GLFW: GLFW nhận phím theo mã vật lý (scancode). pyautogui gửi scancode = 0,
# GLFW tự đoán ra phím số bên phải (numpad) thay vì phím mũi tên -> nhân vật không đi.
# Vì vậy gửi phím bằng SendInput kèm scancode, phím mở rộng (mũi tên...) có cờ EXTENDED.
class _KI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _MI(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _IU(ctypes.Union):
    _fields_ = [("ki", _KI), ("mi", _MI)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _IU)]


_EXTENDED_VK = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x6F, 0xA3, 0xA5}


def _vk(key):
    key = str(key).lower()
    try:
        from pyautogui import _pyautogui_win
        vk = _pyautogui_win.keyboardMapping.get(key)
        if vk:
            return vk & 0xFF
    except Exception:
        pass
    if len(key) == 1:
        vk = ctypes.windll.user32.VkKeyScanW(ord(key))
        if vk != -1:
            return vk & 0xFF
    raise ValueError(f"Không biết phím '{key}'")


def _send_key(key, up):
    vk = _vk(key)
    user32 = ctypes.windll.user32
    flags = (0x0001 if vk in _EXTENDED_VK else 0) | (0x0002 if up else 0)
    inp = _INPUT(1, _IU(ki=_KI(vk, user32.MapVirtualKeyW(vk, 0), flags, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def key_down(key):
    _send_key(key, False)


def key_up(key):
    _send_key(key, True)


def key_press(key):
    _send_key(key, False)
    time.sleep(0.03)
    _send_key(key, True)


# =================================================================== cửa sổ game
class GameWindow:
    def __init__(self):
        self.offset = [0, 0, None, None]  # x, y, w, h vùng client trên màn hình
        self.found = False

    @staticmethod
    def list_windows():
        out = []
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return out

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    out.append((hwnd, buf.value))
            return True

        user32.EnumWindows(cb, 0)
        return out

    def attach(self, title, focus=False):
        title = (title or "").lower()
        self.found = False
        if title:
            try:
                import ctypes.wintypes as wt
                user32 = ctypes.windll.user32
                me = os.getpid()

                def owner(h):
                    pid = wt.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    return pid.value

                # bỏ cửa sổ của chính bot (bảng điều khiển "Tự động - Cờ Lau Loạn Thế"),
                # ưu tiên cửa sổ có tên trùng khớp hoàn toàn
                cands = [(h, n) for h, n in self.list_windows()
                         if title in n.lower() and owner(h) != me]
                cands.sort(key=lambda hn: hn[1].strip().lower() != title)
                for hwnd, name in cands:
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)
                    if focus:
                        user32.SetForegroundWindow(hwnd)
                    rect, pt = wt.RECT(), wt.POINT(0, 0)
                    user32.GetClientRect(hwnd, ctypes.byref(rect))
                    user32.ClientToScreen(hwnd, ctypes.byref(pt))
                    self.offset = [pt.x, pt.y, rect.right, rect.bottom]
                    self.hwnd = hwnd
                    self.found = True
                    return True
            except Exception:
                pass
        self.offset = [0, 0, None, None]
        return False

    def size(self):
        return [self.offset[2], self.offset[3]] if self.found else None

    def focus(self):
        """Đưa game lên trên cùng để nhận phím. Trả về True nếu game đang được focus."""
        if not self.found:
            return False
        try:
            user32 = ctypes.windll.user32
            if user32.GetForegroundWindow() == self.hwnd:
                return True
            # KHÔNG gõ Alt: Alt nhả ra khi game đã lên trên sẽ làm game vào chế độ menu cửa sổ,
            # phím mũi tên khi đó không tới được game. Dùng AttachThreadInput thay thế.
            kernel32 = ctypes.windll.kernel32
            fg = user32.GetForegroundWindow()
            cur = kernel32.GetCurrentThreadId()
            other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
            attached = bool(other and other != cur and user32.AttachThreadInput(cur, other, True))
            try:
                user32.BringWindowToTop(self.hwnd)
                user32.SetForegroundWindow(self.hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(cur, other, False)
            time.sleep(0.1)
            if user32.GetForegroundWindow() == self.hwnd:
                return True
            # vẫn không được -> bấm chuột vào thanh tiêu đề game (không ảnh hưởng gì trong game)
            x, y, w, h = self.offset
            old = pyautogui.position()
            pyautogui.click(x + w // 2, max(0, y - 12))
            pyautogui.moveTo(*old)
            time.sleep(0.15)
            return user32.GetForegroundWindow() == self.hwnd
        except Exception:
            return False

    def resize_client(self, w, h):
        """Đưa vùng trong cửa sổ game về đúng w x h (tính cả viền cửa sổ)."""
        if not self.found:
            return False
        try:
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            if user32.IsZoomed(self.hwnd):
                user32.ShowWindow(self.hwnd, 9)  # bỏ phóng to
                time.sleep(0.3)
            wr, cr = wt.RECT(), wt.RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(wr))
            user32.GetClientRect(self.hwnd, ctypes.byref(cr))
            bw = (wr.right - wr.left) - cr.right
            bh = (wr.bottom - wr.top) - cr.bottom
            SWP_NOMOVE, SWP_NOZORDER = 0x0002, 0x0004
            return bool(user32.SetWindowPos(self.hwnd, 0, 0, 0, w + bw, h + bh,
                                            SWP_NOMOVE | SWP_NOZORDER))
        except Exception:
            return False

    def grab(self):
        if self.offset[2]:
            img = pyautogui.screenshot(region=tuple(self.offset))
        else:
            img = pyautogui.screenshot()
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def to_screen(self, x, y):
        return int(x + self.offset[0]), int(y + self.offset[1])

    def to_client(self, x, y):
        return int(x - self.offset[0]), int(y - self.offset[1])


# =================================================================== tìm ảnh mẫu
# Nút tròn đặt trên nền map / nền trận (đổi theo map và ngày/đêm): chỉ so phần lòng nút,
# bỏ nền ở góc và dòng chữ bên dưới. (x1, y1, x2, y2) theo tỉ lệ ảnh mẫu.
TEMPLATE_BOX = {
    "ui/nut_danh.png": (0.2, 0.2, 0.8, 0.8),
    "ui/dau_hang.png": (0.2, 0.1, 0.8, 0.65),
    "ui/tui_do.png": (0.2, 0.1, 0.8, 0.65),
}

# Ảnh mẫu là chữ in đè lên bàn cờ / nền (nền phía sau mỗi lần một khác): chỉ so phần chữ.
# Cả ảnh mẫu lẫn màn hình được đổi thành ảnh đen-trắng theo màu chữ rồi mới so.
# Khung có chữ "Lượt của đối thủ" đạt ~0.87 (ngày lẫn đêm), khung không có chữ <= 0.4.
TEMPLATE_COLOR = {
    "ui/luot_doi_thu.png": "red_text",
}


def color_key(img, kind):
    """Ảnh đen-trắng (float32) chỉ giữ điểm ảnh đúng màu chữ."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    if kind == "red_text":
        m = ((h < 20) | (h > 165)) & (s > 120) & (v > 150)
    else:
        raise ValueError(kind)
    return m.astype(np.float32)


class Templates:
    def __init__(self):
        self.cache = {}

    def get(self, rel):
        if not rel:
            return None
        full = os.path.join(TPL, rel)
        mtime = os.path.getmtime(full) if os.path.exists(full) else None
        hit = self.cache.get(rel)
        if hit and hit[0] == mtime:
            return hit[1]
        img = imread(full) if mtime else None
        self.cache[rel] = (mtime, img)
        return img

    def exists(self, rel):
        return self.get(rel) is not None

    def find(self, screen, rel, threshold=0.85, region=None, box=None):
        """box: chỉ so phần (x1, y1, x2, y2) theo tỉ lệ của ảnh mẫu - mặc định lấy ở TEMPLATE_BOX
        cho các nút tròn (nền quanh nút đổi theo map / ngày đêm nên không so phần nền)."""
        tpl = self.get(rel)
        if tpl is None:
            return None
        kind = TEMPLATE_COLOR.get(rel)
        if kind:
            tpl, screen = color_key(tpl, kind), color_key(screen, kind)
        box = box or TEMPLATE_BOX.get(rel)
        if box:
            h, w = tpl.shape[:2]
            tpl = tpl[int(h * box[1]):max(int(h * box[1]) + 8, int(h * box[3])),
                      int(w * box[0]):max(int(w * box[0]) + 8, int(w * box[2]))]
        ox = oy = 0
        if region:
            x1, y1, x2, y2 = region
            screen = screen[y1:y2, x1:x2]
            ox, oy = x1, y1
        if screen.shape[0] < tpl.shape[0] or screen.shape[1] < tpl.shape[1]:
            return None
        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        _, mv, _, ml = cv2.minMaxLoc(res)
        if mv >= threshold:
            h, w = tpl.shape[:2]
            return ml[0] + w // 2 + ox, ml[1] + h // 2 + oy, mv
        return None

    def find_all(self, screen, rel, threshold=0.8, max_n=20):
        tpl = self.get(rel)
        if tpl is None or screen.shape[0] < tpl.shape[0] or screen.shape[1] < tpl.shape[1]:
            return []
        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        h, w = tpl.shape[:2]
        out = []
        for _ in range(max_n):
            _, mv, _, ml = cv2.minMaxLoc(res)
            if mv < threshold:
                break
            out.append((ml[0] + w // 2, ml[1] + h // 2, mv))
            x0, y0 = max(0, ml[0] - w // 2), max(0, ml[1] - h // 2)
            res[y0:ml[1] + h // 2 + 1, x0:ml[0] + w // 2 + 1] = -1
        return out


# =================================================================== đọc chữ (OCR)
def slug(s):
    """Tên file không dấu từ tên map, vd 'Hồng Giang' -> 'hong_giang'."""
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_") or "x"


def norm_text(s):
    """Bỏ dấu, chữ thường, chỉ giữ chữ/số -> so sánh tên không phụ thuộc dấu."""
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


# Chữ trắng (tên quái) gần như không có màu; bầu trời xanh nhạt (vd map Hồng Giang) có độ bão hoà ~70-100
OCR_WHITE_S = 70
# Tên nhân vật màu xanh ngọc đậm (bão hoà 150-255); trời xanh ngọc nhạt chỉ ~70-100 -> phải lọc chặt
OCR_CYAN_S, OCR_CYAN_V = 140, 170


def cyan_mask(hsv, cfg):
    """Điểm ảnh màu xanh ngọc của tên nhân vật mình."""
    return ((hsv[..., 0] >= 78) & (hsv[..., 0] <= 100) &
            (hsv[..., 1] > cfg.get("ocr_cyan_s", OCR_CYAN_S)) &
            (hsv[..., 2] > cfg.get("ocr_cyan_v", OCR_CYAN_V)))


class OCR:
    """Đọc chữ trắng (tên quái, tên nhân vật, tên map) trên màn hình bằng Tesseract."""

    def __init__(self):
        self.ok = None
        self.err = ""
        self.lang = "vie"

    def setup(self, cfg):
        try:
            import pytesseract
        except ImportError:
            self.ok, self.err = False, "Chưa cài pytesseract (pip install pytesseract)"
            return False
        path = cfg.get("tesseract_path")
        if path and os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
        try:
            langs = pytesseract.get_languages()
        except Exception:
            self.ok, self.err = False, ("Không tìm thấy Tesseract-OCR. Cài từ "
                                        "github.com/UB-Mannheim/tesseract/wiki và kiểm tra đường dẫn")
            return False
        want = cfg.get("ocr_lang", "vie")
        self.lang = want if want in langs else "eng"
        self.ok, self.pt = True, pytesseract
        return True

    def words(self, screen, cfg, band=None):
        """Trả về list (chữ, x1, y1, x2, y2) theo toạ độ cửa sổ game.
        band=(y1, y2): chỉ đọc dải ngang này (nhanh hơn nhiều so với cả màn hình)."""
        if not self.ok:
            return []
        oy = 0
        if band:
            oy = max(0, int(band[0]))
            screen = screen[oy:max(oy + 1, int(band[1]))]
        scale = cfg.get("ocr_scale", 3)
        hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
        white = ((hsv[..., 2] > cfg.get("ocr_white_v", 185)) &
                 (hsv[..., 1] < cfg.get("ocr_white_s", OCR_WHITE_S)))
        # tên nhân vật của mình hiện màu xanh ngọc (cyan), không phải trắng
        white = (white | cyan_mask(hsv, cfg)).astype(np.uint8) * 255
        img = 255 - cv2.resize(white, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        d = self.pt.image_to_data(img, lang=self.lang, config="--psm 11",
                                  output_type=self.pt.Output.DICT)
        out = []
        for i, t in enumerate(d["text"]):
            t = t.strip()
            if t and float(d["conf"][i]) > 20 and norm_text(t):
                x, y, w, h = (d[k][i] / scale for k in ("left", "top", "width", "height"))
                out.append((t, int(x), int(y) + oy, int(x + w), int(y + h) + oy))
        return out

    @staticmethod
    def find_name(words, name, min_ratio=0.72, max_len_diff=None):
        """Tìm cụm từ giống 'name' (cho phép sai dấu/sai 1-2 ký tự). Trả về list (x, y, độ_giống).
        max_len_diff: nếu đặt, số ký tự đọc được không được lệch quá bấy nhiêu so với 'name'."""
        target = norm_text(name)
        n = len(target.split())
        if not n:
            return []
        # gom các từ cùng dòng (gần nhau theo chiều dọc, liền nhau theo chiều ngang)
        ws = sorted(words, key=lambda w: (round((w[2] + w[4]) / 2 / 8), w[1]))
        hits = []
        for i in range(len(ws)):
            group = [ws[i]]
            for j in range(i + 1, len(ws)):
                if len(group) >= n:
                    break
                a, b = group[-1], ws[j]
                h = max(4, a[4] - a[2])
                if abs((a[2] + a[4]) / 2 - (b[2] + b[4]) / 2) < h * 0.6 and 0 <= b[1] - a[3] < h * 2:
                    group.append(b)
                else:
                    break
            if len(group) != n:
                continue
            text = norm_text(" ".join(g[0] for g in group))
            if max_len_diff is not None and abs(len(text) - len(target)) > max_len_diff:
                continue
            r = difflib.SequenceMatcher(None, text, target).ratio()
            if r >= min_ratio:
                x1, y1 = min(g[1] for g in group), min(g[2] for g in group)
                x2, y2 = max(g[3] for g in group), max(g[4] for g in group)
                hits.append(((x1 + x2) // 2, (y1 + y2) // 2, r))
        return hits


# =================================================================== nhận diện viên
# Viên đặc biệt: ghép như viên thường cùng loại, ăn được thì cộng thêm điểm
# (điểm cộng = cột "Ưu tiên" của viên đặc biệt, mặc định 30).
DEFAULT_GEM_ALIAS = {"kiem_do": "kiem"}


def gem_aliases(cfg):
    return cfg.get("gem_alias", DEFAULT_GEM_ALIAS)


def gem_names(cfg):
    """Viên thường + viên đặc biệt."""
    return list(cfg["gems"]) + [k for k in gem_aliases(cfg) if k not in cfg["gems"]]


def energy_need(cfg):
    """Nội lực tối thiểu để dùng kỹ năng (tỉ lệ vùng energy_bar). Thanh chia 4 khúc, chỉ cần hết
    khúc đầu (~26% vùng đã chọn) là dùng được. Khoá mới 'energy_need' (khoá cũ 'energy_full'
    0.95 = đợi đầy thanh, không dùng nữa)."""
    return cfg.get("energy_need", 0.26)


def special_bonus(cfg, cells):
    """cells: {(r, c): tên viên đặc biệt} -> {(r, c): điểm cộng}."""
    pri = cfg.get("gem_priority", {})
    return {pos: pri.get(name, 30) for pos, name in cells.items()}

def gem_hist(img):
    """Biểu đồ màu (Hue x Saturation) của phần có màu rõ - phân biệt đào / tim / vàng / sao..."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 1] > 50) & (hsv[..., 2] > 70)).astype(np.uint8) * 255
    h = cv2.calcHist([hsv], [0, 1], mask, [30, 4], [0, 180, 50, 256])
    cv2.normalize(h, h, 1.0, 0, cv2.NORM_L1)
    return h


# =================================================================== giải ghép 3
def find_matches(g):
    R, C = len(g), len(g[0])
    hit, runs = set(), []
    for r in range(R):
        c = 0
        while c < C:
            k = c
            while k + 1 < C and g[r][c] is not None and g[r][k + 1] == g[r][c]:
                k += 1
            if g[r][c] is not None and k - c + 1 >= 3:
                hit.update((r, x) for x in range(c, k + 1))
                runs.append((k - c + 1, g[r][c]))
            c = k + 1
    for c in range(C):
        r = 0
        while r < R:
            k = r
            while k + 1 < R and g[r][c] is not None and g[k + 1][c] == g[r][c]:
                k += 1
            if g[r][c] is not None and k - r + 1 >= 3:
                hit.update((y, c) for y in range(r, k + 1))
                runs.append((k - r + 1, g[r][c]))
            r = k + 1
    return hit, clusters(g, hit)


def clusters(g, hit):
    """Gom các ô bị ăn cùng loại và dính liền nhau thành 1 cụm.
    Hình L / T / chữ thập (3 ngang + 3 dọc) = 1 cụm 5 viên -> tính như ăn 5."""
    seen, out = set(), []
    for start in hit:
        if start in seen:
            continue
        kind, stack, size = g[start[0]][start[1]], [start], 0
        seen.add(start)
        while stack:
            r, c = stack.pop()
            size += 1
            for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if nb in hit and nb not in seen and g[nb[0]][nb[1]] == kind:
                    seen.add(nb)
                    stack.append(nb)
        out.append((size, kind))
    return out


def collapse(g, hit):
    R, C = len(g), len(g[0])
    out = [[None] * C for _ in range(R)]
    for c in range(C):
        col = [g[r][c] for r in range(R) if (r, c) not in hit]
        for i, v in enumerate(reversed(col)):
            out[R - 1 - i][c] = v
    return out


def simulate(g, priority, extra_len, special=None):
    """Trả về (điểm, có_được_thêm_lượt). Ô mới rơi xuống coi là chưa biết (None).
    special: {(r, c): điểm cộng} - viên đặc biệt bị ăn ở lượt ăn đầu tiên được cộng điểm."""
    total, chain, cur, extra = 0.0, 0, g, False
    while True:
        hit, runs = find_matches(cur)
        if not hit:
            break
        chain += 1
        s = 0.0
        if special and chain == 1:
            s += sum(v for pos, v in special.items() if pos in hit)
        for n, kind in runs:
            s += n * 10 + priority.get(kind, 0) * n
            if n >= extra_len:
                extra = True
        total += s * (1 + 0.5 * (chain - 1))
        cur = collapse(cur, hit)
    return total, extra, cur


def all_swaps(R, C):
    for r in range(R):
        for c in range(C):
            if c + 1 < C:
                yield (r, c), (r, c + 1)
            if r + 1 < R:
                yield (r, c), (r + 1, c)


def _makes_match(g, r, c):
    """Ô (r, c) có nằm trong hàng/cột 3 viên giống nhau không (chỉ xét quanh ô này - nhanh)."""
    v = g[r][c]
    if v is None:
        return False
    R, C = len(g), len(g[0])
    n, x = 1, c - 1
    while x >= 0 and g[r][x] == v:
        n, x = n + 1, x - 1
    x = c + 1
    while x < C and g[r][x] == v:
        n, x = n + 1, x + 1
    if n >= 3:
        return True
    n, y = 1, r - 1
    while y >= 0 and g[y][c] == v:
        n, y = n + 1, y - 1
    y = r + 1
    while y < R and g[y][c] == v:
        n, y = n + 1, y + 1
    return n >= 3


def valid_moves(grid, exclude=()):
    """Các nước đổi chỗ ăn được ít nhất 3 viên (bỏ qua ô chưa biết và các nước trong exclude)."""
    R, C = len(grid), len(grid[0])
    g = [row[:] for row in grid]
    out = []
    for (r1, c1), (r2, c2) in all_swaps(R, C):
        a, b = g[r1][c1], g[r2][c2]
        if a is None or b is None or a == b or ((r1, c1), (r2, c2)) in exclude:
            continue
        g[r1][c1], g[r2][c2] = b, a
        if _makes_match(g, r1, c1) or _makes_match(g, r2, c2):
            out.append(((r1, c1), (r2, c2)))
        g[r1][c1], g[r2][c2] = a, b
    return out


def _play(grid, move, priority, extra_len, extra_bonus, special=None):
    """Đi thử 1 nước -> (điểm ngay, được thêm lượt?, bàn cờ sau khi rơi, cụm lớn nhất ăn ngay)."""
    (r1, c1), (r2, c2) = move
    g = [row[:] for row in grid]
    g[r1][c1], g[r2][c2] = g[r2][c2], g[r1][c1]
    sp = None
    if special:  # viên đặc biệt đi theo ô bị đổi chỗ
        swap = {(r1, c1): (r2, c2), (r2, c2): (r1, c1)}
        sp = {swap.get(pos, pos): v for pos, v in special.items()}
    big = max((n for n, _ in find_matches(g)[1]), default=0)
    s, extra, after = simulate(g, priority, extra_len, sp)
    if extra:
        s += extra_bonus
    return s, extra, after, big


def _search(grid, depth, mine, priority, extra_len, extra_bonus, opp_weight, discount, beam):
    """Giá trị (theo phía bot) của bàn cờ khi tới lượt `mine` (True = bot, False = đối thủ),
    tính trước `depth` nước. Viên mới rơi xuống là ô chưa biết nên chỉ dùng các viên đã thấy.
    Trả về (giá trị, [(nước, của_bot?, được_thêm_lượt?), ...])."""
    if depth <= 0:
        return 0.0, []
    tries = [(m,) + _play(grid, m, priority, extra_len, extra_bonus)[:3] for m in valid_moves(grid)]
    if not tries:
        return 0.0, []
    tries.sort(key=lambda t: -t[1])
    best = None
    for m, s, extra, after in tries[:beam]:
        nxt = mine if extra else not mine  # ăn 4+ -> đi tiếp, không thì tới lượt bên kia
        f, line = _search(after, depth - 1, nxt, priority, extra_len, extra_bonus,
                          opp_weight, discount, beam)
        v = (s if mine else -opp_weight * s) + discount * f
        if best is None or (v > best[0] if mine else v < best[0]):
            best = (v, [(m, mine, extra)] + line)
    return best


# Điểm cộng theo tầng: lớn hơn hẳn mọi điểm khác -> ăn 5 > ăn 4 > ăn 3, bất kể loại viên
TIER_BONUS = {5: 20000, 4: 10000}


def move_info(grid, exclude=()):
    """{nước: (số viên của cụm lớn nhất ăn được ngay, {các loại viên bị ăn ngay})} cho mọi nước hợp lệ."""
    out = {}
    for (r1, c1), (r2, c2) in all_swaps(len(grid), len(grid[0])):
        a, b = grid[r1][c1], grid[r2][c2]
        if a is None or b is None or a == b or ((r1, c1), (r2, c2)) in exclude:
            continue
        g = [row[:] for row in grid]
        g[r1][c1], g[r2][c2] = b, a
        runs = find_matches(g)[1]
        if runs:
            out[((r1, c1), (r2, c2))] = (max(n for n, _ in runs), {k for _, k in runs})
    return out


def move_sizes(grid, exclude=()):
    """{nước: số viên của cụm lớn nhất ăn được ngay} - để ghi log/kiểm tra."""
    return {m: n for m, (n, _) in move_info(grid, exclude).items()}


# Máu thấp: vẫn đi nước này trước khi uống bình nếu ăn được 4+ hoặc ăn được loại viên này
URGENT_GEMS = ("kiem",)


def urgent_moves(grid, exclude=(), gems=URGENT_GEMS):
    """Các nước 'đáng đi trước khi uống bình': ăn 4+ hoặc ăn được kiếm (kiếm đỏ lưu là kiếm)."""
    return {m for m, (n, kinds) in move_info(grid, exclude).items() if n >= 4 or kinds & set(gems)}


def plan_text(plan):
    """Chuỗi nước dự tính -> chữ để ghi log, vd "bot (1,2)-(1,3) +lượt → bot ... → đối thủ ..."."""
    parts = []
    for ((r1, c1), (r2, c2)), mine, extra in plan:
        parts.append(f"{'bot' if mine else 'đối thủ'} ({r1 + 1},{c1 + 1})-({r2 + 1},{c2 + 1})"
                     + (" +lượt" if extra else ""))
    return " → ".join(parts)


def best_move(grid, priority=None, extra_len=4, extra_bonus=80, look_ahead=0.5, exclude=(),
              special=None, depth=3, discount=0.8, beam=6, with_plan=False):
    """Chọn nước đi, tính trước `depth` nước (nước này + các nước sau của 2 bên).
    - Ăn 4+ được thêm lượt -> tính tiếp nước sau của bot; không thì tính nước đáp trả của đối thủ
      (trừ look_ahead x điểm của đối thủ) rồi tới bot.
    - Nước càng xa càng nhân thêm `discount` (viên mới rơi chưa biết nên kém chắc chắn hơn).
    - Ở các nước sau chỉ xét `beam` nước điểm cao nhất cho nhanh.
    - Luôn xếp theo tầng trước: nước ăn 5 > ăn 4 > ăn 3 (chỉ tính cụm ăn ngay bằng nước này).
    exclude: các nước (ô1, ô2) đã bị game từ chối trên bàn cờ này -> bỏ qua.
    special: {(r, c): điểm cộng} cho viên đặc biệt (vd kiếm đỏ).
    with_plan=True -> trả thêm chuỗi nước dự tính [(nước, của_bot?, được_thêm_lượt?), ...]."""
    special = special or {}
    priority = priority or {}
    best, best_s, plan = None, 0.0, []
    for m in valid_moves(grid, exclude):
        s, extra, after, big = _play(grid, m, priority, extra_len, extra_bonus, special)
        if s <= 0:
            continue
        f, line = _search(after, depth - 1, extra, priority, extra_len, extra_bonus,
                          look_ahead, discount, beam)
        s += discount * f + TIER_BONUS.get(min(big, 5), 0)
        if best is None or s > best_s:
            best, best_s, plan = m, s, [(m, True, extra)] + line
    return (best, best_s, plan) if with_plan else (best, best_s)


# =================================================================== bot
class Bot:
    def __init__(self, log=print):
        self.log = log
        self.win = GameWindow()
        self.tpl = Templates()
        self.ocr = OCR()
        self.stop_event = threading.Event()
        self.thread = None
        self.stats = {"battles": 0, "wins": 0, "losses": 0, "start": None, "lose_streak": 0}
        self.reload()

    # ---------------------------------------------------------- cấu hình
    def reload(self):
        self.cfg = load_json(CONFIG_PATH)
        self.maps = load_json(MAPS_PATH)
        if hasattr(self, "ocr"):
            self.ocr.ok = None  # đọc lại cài đặt Tesseract

    def attach(self, focus=False):
        ok = self.win.attach(self.cfg.get("window_title"), focus)
        return ok

    def ensure_size(self):
        """Nếu cửa sổ game khác kích thước lúc cài đặt -> tự chỉnh về đúng. Trả về True nếu khớp."""
        want = self.cfg.get("window_size")
        cur = self.win.size()
        if not want or not cur or list(cur) == list(want):
            return True
        self.log(f"Cửa sổ game đang {cur[0]}x{cur[1]}, lúc cài đặt là {want[0]}x{want[1]} -> chỉnh lại")
        self.win.resize_client(*want)
        time.sleep(1.0)
        self.attach(focus=True)
        if self.win.size() == list(want):
            self.log("  Đã đưa cửa sổ về đúng kích thước")
            return True
        self.log("[!] Không chỉnh được kích thước cửa sổ (game có thể khoá). "
                 "Hãy tự kéo lại, hoặc cài đặt lại vùng bàn cờ / ảnh mẫu.")
        return False

    @property
    def th(self):
        return self.cfg.get("match_threshold", 0.85)

    # ---------------------------------------------------------- chuột / phím
    def sleep(self, a, b=None):
        end = time.time() + random.uniform(a, b if b is not None else a * 1.4)
        while time.time() < end:
            if self.stop_event.is_set():
                raise StopIteration
            time.sleep(0.05)

    def click(self, x, y, jitter=None):
        j = self.cfg.get("click_jitter_px", 3) if jitter is None else jitter
        sx, sy = self.win.to_screen(x + random.randint(-j, j), y + random.randint(-j, j))
        pyautogui.moveTo(sx, sy, duration=random.uniform(0.07, 0.18))
        pyautogui.click()

    def click_tpl(self, screen, rel, delay=0.6, threshold=None):
        pos = self.tpl.find(screen, rel, threshold or self.th)
        if pos:
            self.click(pos[0], pos[1])
            self.sleep(delay)
            return True
        return False

    def ensure_focus(self):
        if self.win.focus():
            return True
        if time.time() - getattr(self, "_focus_warn", 0) > 10:
            self._focus_warn = time.time()
            self.log("[!] Không đưa được game lên trên cùng, phím đi sẽ không có tác dụng. "
                     "Bấm chuột vào game một lần (hoặc chạy chay.bat bằng Run as administrator)")
        return False

    def hold_key(self, key, seconds):
        self.ensure_focus()
        key_down(key)
        try:
            self.sleep(seconds, seconds)
        finally:
            key_up(key)

    # ---------------------------------------------------------- bàn cờ
    def cell_rects(self):
        b = self.cfg["board"]
        x1, y1 = b["top_left"]
        x2, y2 = b["bottom_right"]
        R, C = b["rows"], b["cols"]
        cw, ch = (x2 - x1) / C, (y2 - y1) / R
        return [[(x1 + cw * c, y1 + ch * r, cw, ch) for c in range(C)] for r in range(R)]

    def cell_center(self, r, c):
        x, y, w, h = self.cell_rects()[r][c]
        return int(x + w / 2), int(y + h / 2)

    @staticmethod
    def crop_inner(img, rect, ratio):
        x, y, w, h = rect
        mx, my = w * (1 - ratio) / 2, h * (1 - ratio) / 2
        return img[int(y + my):int(y + h - my), int(x + mx):int(x + w - mx)]

    def board_problem(self, screen):
        """Trả về lý do nếu vùng bàn cờ không dùng được (chưa chọn / nằm ngoài cửa sổ game)."""
        b = self.cfg["board"]
        (x1, y1), (x2, y2) = b["top_left"], b["bottom_right"]
        H, W = screen.shape[:2]
        if x2 <= x1 or y2 <= y1:
            return "Chưa chọn vùng bàn cờ"
        if x1 < 0 or y1 < 0 or x2 > W or y2 > H:
            return (f"Vùng bàn cờ ({x1},{y1})-({x2},{y2}) nằm ngoài cửa sổ game {W}x{H}. "
                    "Vào tab Cài đặt chọn lại vùng bàn cờ và lấy mẫu lại các viên")
        return None

    def read_board(self, screen):
        b = self.cfg["board"]
        gems = {}
        alias = gem_aliases(self.cfg)
        for name in gem_names(self.cfg):
            t = self.tpl.get(f"gems/{name}.png")
            if t is not None:
                gems[name] = t
        self.board_special = {}
        if not gems or self.board_problem(screen):
            return None
        gth = b.get("gem_threshold", 0.55)
        margin = b.get("gem_margin", 0.08)
        hists = {name: gem_hist(t) for name, t in gems.items()}
        grid, self.board_scores = [], []
        for row in self.cell_rects():
            out, sc_row = [], []
            for rect in row:
                cell = self.crop_inner(screen, rect, 0.92)
                if cell.shape[0] < 3 or cell.shape[1] < 3:
                    out.append(None)
                    sc_row.append(0.0)
                    continue
                core = self.crop_inner(cell, (0, 0, cell.shape[1], cell.shape[0]), 0.75)
                hsv = cv2.cvtColor(core, cv2.COLOR_BGR2HSV)
                if ((hsv[..., 1] > 50) & (hsv[..., 2] > 70)).mean() < b.get("gem_min_color", 0.2):
                    out.append(None)  # ô trống (viên đang rơi) -> không đoán
                    sc_row.append(0.0)
                    continue
                ch = gem_hist(core)
                scores, shapes = [], {}
                for name, t in gems.items():
                    if cell.shape[0] < t.shape[0] or cell.shape[1] < t.shape[1]:
                        t = cv2.resize(t, (max(1, cell.shape[1] - 2), max(1, cell.shape[0] - 2)))
                    shape = cv2.minMaxLoc(cv2.matchTemplate(cell, t, cv2.TM_CCOEFF_NORMED))[1]
                    color = cv2.compareHist(ch, hists[name], cv2.HISTCMP_CORREL)
                    scores.append((0.5 * shape + 0.5 * color, name))
                    shapes[name] = shape
                scores.sort(reverse=True)
                top, top_name = scores[0]
                base = alias.get(top_name, top_name)
                # loại đứng thứ 2 phải là loại KHÁC (kiếm đỏ vs kiếm thường không tính là nhầm)
                second = next((v for v, n in scores[1:] if alias.get(n, n) != base), -1)
                # không chắc chắn (giống 2 loại gần bằng nhau) -> coi như không biết, không ghép ô này
                ok = top >= gth and top - second >= margin
                if not ok:
                    # Màu lệch (nền trời sáng xuyên qua ô; viên tim hồng nằm ở chỗ thang màu quay vòng)
                    # nhưng hình dạng khớp rất chắc và hơn hẳn loại khác -> vẫn nhận
                    s_name = max(shapes, key=shapes.get)
                    s_base = alias.get(s_name, s_name)
                    s_second = max((v for n, v in shapes.items() if alias.get(n, n) != s_base), default=-1)
                    if shapes[s_name] >= b.get("gem_shape_sure", 0.85) and                             shapes[s_name] - s_second >= b.get("gem_shape_margin", 0.2):
                        ok, top_name, base = True, s_name, s_base
                out.append(base if ok else None)
                if ok and top_name != base:
                    self.board_special[(len(grid), len(out) - 1)] = top_name
                sc_row.append(top)
            grid.append(out)
            self.board_scores.append(sc_row)
        return grid

    def calibrate_board(self, screen):
        """Tự căn lưới 8x8 theo vị trí thật của các viên (tìm bằng ảnh mẫu).
        Sửa self.cfg["board"] nếu tìm được. Trả về (top_left, bottom_right) hoặc None."""
        b = self.cfg["board"]
        R, C = b["rows"], b["cols"]
        (x1, y1), (x2, y2) = b["top_left"], b["bottom_right"]
        H, W = screen.shape[:2]
        m = int(max(x2 - x1, y2 - y1) / C)  # tìm rộng ra thêm 1 ô mỗi phía
        ox, oy = max(0, x1 - m), max(0, y1 - m)
        crop = screen[oy:min(H, y2 + m), ox:min(W, x2 + m)]
        pts = []
        for name in gem_names(self.cfg):
            pts += [(x + ox, y + oy) for x, y, _ in
                    self.tpl.find_all(crop, f"gems/{name}.png", 0.8, R * C)]
        if len(pts) < R * C * 0.4:
            return None

        def fit(vals, n, lo, hi):
            vals = sorted(vals)
            groups = [[vals[0]]]
            for v in vals[1:]:
                if v - groups[-1][-1] <= 8:
                    groups[-1].append(v)
                else:
                    groups.append([v])
            groups = [g for g in groups if len(g) >= 2]
            cs = [sum(g) / len(g) for g in groups]
            if len(cs) < max(4, n // 2):
                return None
            diffs = sorted(d for d in (b_ - a for a, b_ in zip(cs, cs[1:])) if d > 20)
            if not diffs:
                return None
            pitch = diffs[0] if len(diffs) < 3 else diffs[len(diffs) // 2]
            idx = [round((c - cs[0]) / pitch) for c in cs]
            # bình phương tối thiểu: c = start + i * pitch
            k = len(cs)
            mi, mc = sum(idx) / k, sum(cs) / k
            var = sum((i - mi) ** 2 for i in idx)
            if not var:
                return None
            pitch = sum((i - mi) * (c - mc) for i, c in zip(idx, cs)) / var
            start = mc - pitch * mi
            if max(idx) > n - 1 or not 25 < pitch < 120:
                return None
            # thiếu cột/hàng ở rìa -> chọn cách đặt khớp nhất với vùng người dùng đã chọn
            best = min(range(n - max(idx)),
                       key=lambda s_: abs((start - s_ * pitch - pitch / 2) - lo) +
                       abs((start + (n - 1 - s_) * pitch + pitch / 2) - hi))
            first = start - best * pitch
            return int(round(first - pitch / 2)), int(round(first + (n - 0.5) * pitch))

        fx = fit([p[0] for p in pts], C, x1, x2)
        fy = fit([p[1] for p in pts], R, y1, y2)
        if not fx or not fy:
            return None
        b["top_left"], b["bottom_right"] = [fx[0], fy[0]], [fx[1], fy[1]]
        return b["top_left"], b["bottom_right"]

    def save_board_debug(self, screen, grid, tag, move=None):
        """Lưu ảnh bàn cờ kèm tên viên bot đọc được vào thư mục debug/ (giữ 15 ảnh gần nhất)."""
        try:
            img = screen.copy()
            for r, row in enumerate(self.cell_rects()):
                for c, (x, y, w, h) in enumerate(row):
                    v = grid[r][c]
                    if (r, c) in getattr(self, "board_special", {}):
                        v = self.board_special[(r, c)].replace("_", "")
                    color = (0, 255, 0) if v else (0, 0, 255)
                    cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), color, 1)
                    cv2.putText(img, (v or "?")[:3], (int(x) + 3, int(y + h) - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
                    cv2.putText(img, (v or "?")[:3], (int(x) + 3, int(y + h) - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            if move:
                p1, p2 = (self.cell_center(*move[0]), self.cell_center(*move[1]))
                cv2.arrowedLine(img, p1, p2, (0, 255, 255), 3, tipLength=0.3)
            b = self.cfg["board"]
            (x1, y1), (x2, y2) = b["top_left"], b["bottom_right"]
            img = img[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10]
            d = P("debug")
            path = os.path.join(d, time.strftime(f"%H%M%S_{tag}.png"))
            imwrite(path, img)
            files = sorted(f for f in os.listdir(d) if f.endswith(".png"))
            for f in files[:-15]:
                os.remove(os.path.join(d, f))
            return path
        except Exception:
            return None

    def board_crop(self, screen):
        b = self.cfg["board"]
        (x1, y1), (x2, y2) = b["top_left"], b["bottom_right"]
        return screen[y1:y2, x1:x2]

    def board_motion(self, a, b):
        """Độ thay đổi lớn nhất của một ô giữa 2 ảnh bàn cờ. Lấy trung bình cả bàn thì 3-4 viên
        đang rơi bị 'pha loãng' -> tưởng bàn cờ đã đứng yên, đi nước khi viên mới chưa rơi xong."""
        if not a.size or a.shape != b.shape:
            return 999.0
        b_ = self.cfg["board"]
        R, C = b_["rows"], b_["cols"]
        d = cv2.cvtColor(cv2.absdiff(a, b), cv2.COLOR_BGR2GRAY).astype(np.float32)
        d = cv2.resize(d, (C, R), interpolation=cv2.INTER_AREA)  # trung bình theo từng ô
        return float(d.max())

    def stable_screen(self, tries=10):
        """Chờ bàn cờ đứng yên (hết hiệu ứng rơi viên): không ô nào thay đổi rõ, 2 lần liên tiếp."""
        # con trỏ chuột lướt qua 1 ô ~7-13; viên đang rơi / đổi chỗ ~50+
        th = self.cfg["board"].get("still_cell_diff", 20)
        prev = self.win.grab()
        calm = 0
        for _ in range(tries):
            self.sleep(0.2, 0.25)
            cur = self.win.grab()
            if self.board_motion(self.board_crop(prev), self.board_crop(cur)) < th:
                calm += 1
                if calm >= 2:
                    return cur
            else:
                calm = 0
            prev = cur
        return None

    def do_move(self, move):
        (r1, c1), (r2, c2) = move
        x1, y1 = self.win.to_screen(*self.cell_center(r1, c1))
        x2, y2 = self.win.to_screen(*self.cell_center(r2, c2))
        if self.cfg["board"].get("move_style", "drag") == "drag":
            pyautogui.moveTo(x1, y1, duration=random.uniform(0.08, 0.16))
            pyautogui.mouseDown()
            pyautogui.moveTo(x2, y2, duration=random.uniform(0.12, 0.22))
            pyautogui.mouseUp()
        else:
            pyautogui.moveTo(x1, y1, duration=random.uniform(0.08, 0.16))
            pyautogui.click()
            time.sleep(random.uniform(0.1, 0.2))
            pyautogui.moveTo(x2, y2, duration=random.uniform(0.08, 0.16))
            pyautogui.click()
        # đưa chuột ra dưới bàn cờ (chỉ di, không bấm): con trỏ đè lên viên làm đọc sai / tưởng còn động
        b = self.cfg["board"]
        (bx1, _), (bx2, by2) = b["top_left"], b["bottom_right"]
        h = self.win.size()[1] if self.win.size() else by2 + 40
        pyautogui.moveTo(*self.win.to_screen((bx1 + bx2) // 2, min(by2 + 35, h - 10)),
                         duration=random.uniform(0.05, 0.1))

    # ---------------------------------------------------------- thanh máu / nội lực
    @staticmethod
    def bar_fill(screen, rect, hue):
        """Tỉ lệ đầy của thanh = vị trí cột có màu xa nhất bên phải / chiều rộng."""
        if not rect or rect[2] <= rect[0]:
            return None
        x1, y1, x2, y2 = rect
        hsv = cv2.cvtColor(screen[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        colored = (s > 90) & (v > 110)
        if hue == "red":
            m = colored & ((h < 12) | (h > 165))
        elif hue == "green":
            m = colored & (h > 35) & (h < 90)
        elif hue == "blue":
            m = colored & (h > 90) & (h < 130)
        else:
            m = colored
        on = m.mean(axis=0) > 0.3
        # đi từ trái sang: phần đã đầy là đoạn có màu liền mạch (cho phép vạch chia mảnh <= 5px).
        # Không lấy cột có màu xa nhất: viền khung bên phải cũng có màu -> thanh luôn bị tính là đầy.
        first = np.argmax(on) if on.any() else -1
        if first < 0 or first > (x2 - x1) * 0.25:
            return 0.0
        end, gap = first, 0
        for i in range(first, len(on)):
            if on[i]:
                end, gap = i, 0
            else:
                gap += 1
                if gap > 5:
                    break
        return (end + 1) / (x2 - x1)

    def hp_fill(self, screen):
        """Tỉ lệ máu. Đọc số "349/543" in trên thanh máu (chính xác ở cả theme ngày/đêm);
        không đọc được thì đo phần màu đỏ (dòng số đè lên giữa thanh nên kém chính xác hơn
        - chỉ đúng khi máu dưới khoảng 1/3)."""
        rect = self.cfg.get("hp_bar")
        if not rect or rect[2] <= rect[0]:
            return None
        if self.ocr.ok is None:
            self.ocr.setup(self.cfg)
        if self.ocr.ok:
            x1, y1, x2, y2 = rect
            crop = screen[max(0, y1 - 2):y2 + 2, x1:x2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            _, bw = cv2.threshold(big, 200, 255, cv2.THRESH_BINARY_INV)  # chữ số trắng
            try:
                t = self.ocr.pt.image_to_string(
                    bw, config="--psm 7 -c tessedit_char_whitelist=0123456789/")
            except Exception:
                t = ""
            m = re.search(r"(\d+)\s*/\s*(\d+)", t)
            if m and 0 < int(m.group(2)) and int(m.group(1)) <= int(m.group(2)):
                return int(m.group(1)) / int(m.group(2))
        return self.bar_fill(screen, rect, "red")

    # ---------------------------------------------------------- trong trận
    def in_battle(self, screen):
        return bool(self.tpl.find(screen, "ui/dau_hang.png", self.th))

    def confirm_use(self):
        """Game không có nút 'Dùng': chọn bình / kỹ năng xong thì bấm Enter để dùng."""
        self.sleep(0.2, 0.3)
        key_press(self.cfg["move"].get("key_use", "enter") or "enter")
        self.sleep(0.4)

    def use_potion(self):
        """Mở túi đồ: game đã chọn sẵn bình máu (Hoàn Linh Dược) -> chỉ cần bấm Enter.
        KHÔNG bấm vào bình: ảnh mẫu bình máu dễ khớp nhầm sang bình mana (Kim Đan Dược).
        Trả về True nếu đã dùng."""
        s = self.win.grab()
        if not self.click_tpl(s, "ui/tui_do.png", 0.8):
            # lượt đối thủ: nút Túi đồ bị mờ -> chờ tới lượt mình
            return False
        self.sleep(0.5, 0.6)
        self.confirm_use()
        self.log("  + Dùng bình máu (Enter)")
        return True

    def use_skill(self, idx):
        s = self.win.grab()
        if not self.click_tpl(s, "ui/ky_nang.png", 0.8):
            return
        if self.click_tpl(self.win.grab(), f"skills/skill_{idx}.png", 0.6):
            self.confirm_use()
            self.log(f"  + Dùng kỹ năng {idx}")
        else:
            self.log(f"[!] Không thấy kỹ năng {idx}")
            key_press("esc")

    def turn_clock(self):
        """(số giây đã trôi trong lượt của bot, đang gấp?, sắp hết giờ?).
        Mỗi lượt chỉ có `turn_limit_s` giây (mặc định 30), quá giờ là mất lượt."""
        now = time.time()
        if now - getattr(self, "_last_tick", 0) > 5:  # trận mới / vừa quay lại trận
            self._turn_start = None
        self._last_tick = now
        start = getattr(self, "_turn_start", None)
        el = now - start if start else 0.0
        limit = self.cfg.get("turn_limit_s", 30)
        return el, el >= limit * 0.5, el >= limit * 0.75

    def battle_turn(self):
        cfg = self.cfg
        elapsed, hurry, panic = self.turn_clock()
        if panic:  # sắp hết giờ: không chờ bàn cờ đứng yên nữa
            screen = self.win.grab()
        else:
            screen = self.stable_screen(4 if hurry else 10)
        if screen is None:
            # có viên nhấp nháy mãi -> không bao giờ "đứng yên" hẳn: sau vài lần chờ vẫn đi
            self._unstable = getattr(self, "_unstable", 0) + 1
            if self._unstable < (1 if hurry else 3):
                return
            screen = self.win.grab()
        self._unstable = 0
        if not self.in_battle(screen):
            return
        if self.tpl.find(screen, "ui/luot_doi_thu.png", self.cfg.get("opponent_threshold", 0.6)):
            self._turn_start = None  # lượt đối thủ: đồng hồ của bot bắt đầu lại khi tới lượt mình
            self.sleep(0.6)
            return
        if self._turn_start is None:
            self._turn_start = time.time()
            elapsed, hurry, panic = self.turn_clock()
        if not getattr(self, "_calibrated", False) and not self.board_problem(screen):
            self._calibrated = True
            old = [list(self.cfg["board"]["top_left"]), list(self.cfg["board"]["bottom_right"])]
            r = self.calibrate_board(screen)
            if r and [list(r[0]), list(r[1])] != old:
                self.log(f"  Đã tự căn lưới bàn cờ: {old[0]}-{old[1]} -> {list(r[0])}-{list(r[1])} "
                         "(bấm 'Tự căn lưới' ở tab Cài đặt để lưu hẳn)")
        grid = self.read_board(screen)
        if grid is None:
            self.log("[!] " + (self.board_problem(screen) or "Chưa lấy mẫu các viên"))
            self.sleep(0.5 if hurry else 2)
            return
        known = sum(v is not None for row in grid for v in row)
        total = len(grid) * len(grid[0])
        if known < total * (0.5 if panic else 0.8):
            self.sleep(0.4)  # bàn cờ đang tối / có chữ đè -> chưa tới lượt
            return
        if known < total and not hurry:
            # còn ô chưa đọc được (thường là viên đang rơi) -> chờ, kẻo bỏ sót nước ăn 4/5.
            # Ô lạ mãi không hết (viên chưa có ảnh mẫu) thì sau ~2 giây vẫn đi.
            first = getattr(self, "_unknown_since", None) or time.time()
            self._unknown_since = first
            if time.time() - first < cfg["board"].get("wait_unknown_s", 2.0):
                self.sleep(0.3)
                return
        self._unknown_since = None

        key = tuple(map(tuple, grid))
        if getattr(self, "_bad_grid", None) != key:
            self._bad_grid, self._bad_moves = key, set()
        pri, ext = cfg.get("gem_priority", {}), cfg.get("extra_turn_len", 4)
        special = special_bonus(cfg, self.board_special)
        depth = cfg.get("search_depth", 3)

        def solve(exclude):
            return best_move(grid, pri, ext, exclude=exclude, special=special, depth=depth,
                             with_plan=True)
        move, score, plan = solve(self._bad_moves)

        def pick_urgent():
            """Nước tốt nhất trong các nước ăn 4+ / ăn kiếm (None nếu không có)."""
            urgent = urgent_moves(grid, self._bad_moves)
            if not urgent:
                return None
            if move in urgent:
                return move, plan
            others = {m for m in move_info(grid, self._bad_moves) if m not in urgent}
            m, _, p = solve(set(self._bad_moves) | others)
            return (m, p) if m else None

        ui = cfg["auto"]
        eat_first = False  # máu thấp nhưng có nước ăn 4+/ăn kiếm -> đi nước đó ngay lượt này
        hp = self.hp_fill(screen)
        if ui.get("use_potion") and hp is not None and hp * 100 < ui.get("potion_hp", 30) \
                and time.time() - getattr(self, "_last_potion", 0) > 8:
            # Máu thấp: chưa vào túi đồ vội. Có nước ăn 4+ hoặc ăn kiếm thì ăn trước.
            urgent_move = pick_urgent()
            if urgent_move:
                (move, plan), eat_first = urgent_move, True
                self.log(f"  HP còn ~{hp * 100:.0f}%: có nước ăn 4+ / ăn kiếm, ăn trước rồi mới uống bình")
            elif self.use_potion():
                self._last_potion = time.time()
                self.log(f"  HP còn ~{hp * 100:.0f}%")
                return
            # không mở được túi đồ (nút mờ / không thấy) -> vẫn đi nước bình thường
        sk = ui.get("skill", 0)
        if sk and not eat_first:
            en = self.bar_fill(screen, cfg.get("energy_bar"), cfg.get("energy_color", "any"))
            if en is not None and en >= energy_need(cfg) \
                    and time.time() - getattr(self, "_last_skill", 0) > 5:
                # Đủ nội lực: chưa dùng kỹ năng vội. Có nước ăn 4+ hoặc ăn kiếm thì ăn trước.
                urgent_move = pick_urgent()
                if urgent_move:
                    move, plan = urgent_move
                    self.log("  Đủ nội lực nhưng có nước ăn 4+ / ăn kiếm, ăn trước rồi mới dùng kỹ năng")
                else:
                    self._last_skill = time.time()
                    self.use_skill(sk)
                    return

        if not move and panic:
            # sắp mất lượt mà không thấy nước chắc chắn: thử đổi 1 viên chưa đọc được với ô bên cạnh
            cands = [m for m in all_swaps(len(grid), len(grid[0]))
                     if (grid[m[0][0]][m[0][1]] is None) != (grid[m[1][0]][m[1][1]] is None)
                     and m not in self._bad_moves]
            if cands:
                move, plan = random.choice(cands), []
                self.log(f"[!] Lượt đã {elapsed:.0f} giây, sắp hết giờ: thử nước {move} với ô chưa đọc được")
        if not move:
            self.sleep(0.3 if hurry else 0.5)
            return
        sizes = move_sizes(grid, self._bad_moves)
        n4 = sum(1 for v in sizes.values() if v >= 4)
        unk = sum(v is None for row in grid for v in row)
        self.log(f"  Nước {move}: ăn {sizes.get(move, '?')}"
                 f" | bàn có {n4} nước ăn 4+" + (f" | {unk} ô chưa đọc được" if unk else "")
                 + (f" | lượt đã {elapsed:.0f} giây" if elapsed >= 10 else ""))
        if len(plan) > 1:
            self.log("    tính trước: " + plan_text(plan))
        before = self.board_crop(screen).copy()
        self.do_move(move)
        # nước sai: game đổi 2 viên rồi trả lại -> sau ~1 giây bàn cờ y như cũ
        self.sleep(1.0, 1.1)
        after = self.board_crop(self.win.grab())
        if float(np.mean(cv2.absdiff(before, after))) < 2.5:
            self._bad_moves.add(move)
            path = self.save_board_debug(screen, grid, "nuoc_sai", move)
            self.log(f"[!] Nước {move} không ăn được (bot đọc nhầm viên?). Đã lưu ảnh: "
                     f"{os.path.relpath(path, BASE) if path else '-'}")
        else:
            self._turn_start = time.time()  # được thêm lượt -> tính lại giờ (an toàn)
            self.sleep(cfg.get("delay_after_move", 1.0))

    # ---------------------------------------------------------- trên map
    def read_words(self, screen, band=None):
        if self.ocr.ok is None:
            self.ocr.setup(self.cfg)
            if not self.ocr.ok:
                self.log("[!] " + self.ocr.err)
        return self.ocr.words(screen, self.cfg, band)

    def targets(self, screen, map_name, selected, words=None):
        """Tìm quái đã chọn theo TÊN bạn nhập (đọc chữ trên đầu quái)."""
        mons = self.maps.get(map_name, {}).get("monsters", [])
        words = self.read_words(screen) if words is None else words
        ratio = self.cfg.get("name_match", 0.72)
        found = []
        for m in mons:
            if m["name"] not in selected:
                continue
            hits = [(x, y, r) for x, y, r in OCR.find_name(words, m["name"], ratio)]
            if not hits and m.get("image"):  # dự phòng: ảnh tên đã chụp (nếu có)
                hits = self.tpl.find_all(screen, m["image"], self.cfg.get("monster_threshold", 0.8))
            found += [(x, y, m["name"], r) for x, y, r in hits]
        return found

    def player_pos(self, screen, words=None):
        name = self.cfg.get("player_name")
        if not name:
            return None
        words = self.read_words(screen) if words is None else words
        # khắt khe hơn tên quái: tránh nhận nhầm chữ "Phúc" (nút Phúc lợi) thành "phucdd"
        hits = OCR.find_name(words, name, max(0.8, self.cfg.get("name_match", 0.72)), max_len_diff=1)
        # bỏ tên ở khung thông tin góc trên-trái, chỉ lấy tên trên đầu nhân vật
        H, W = screen.shape[:2]
        if not hits:
            # tên bị dính với tên người chơi đứng sát (vd "phucddVaK") -> tìm tên mình nằm trong từ
            target = norm_text(name).replace(" ", "")
            if len(target) >= 4:
                for t, x1, y1, x2, y2 in words:
                    text = norm_text(t).replace(" ", "")
                    i = text.find(target)
                    if i >= 0 and len(text) > len(target):
                        cx = x1 + (x2 - x1) * (i + len(target) / 2) / len(text)
                        hits.append((int(cx), (y1 + y2) // 2, 0.9))
        me = self.pick_me([h[:2] for h in hits], W, H)
        if not me:
            me = self.cyan_name_pos(screen, len(norm_text(name).replace(" ", "")))
        if me:
            self._last_me = (me, time.time())
        return me

    def pick_me(self, cands, W, H):
        """Chọn vị trí tên nhân vật hợp lý trong các ứng viên.
        Camera đi theo nhân vật nên tên mình luôn ở quanh giữa màn hình và không nhảy xa giữa
        2 lần đọc: bỏ chỗ ở dải giao diện trên/dưới và chỗ cách vị trí vừa thấy quá xa."""
        cands = [p for p in cands if H * 0.12 <= p[1] <= H * 0.88]
        ref, t = getattr(self, "_last_me", (None, 0))
        age = time.time() - t
        if ref and age <= 4:
            cands = [p for p in cands if abs(p[0] - ref[0]) + abs(p[1] - ref[1]) <= 250]
        if not ref or age > 30:
            ref = (W // 2, int(H * 0.45))
        return min(cands, key=lambda p: abs(p[0] - ref[0]) + abs(p[1] - ref[1])) if cands else None

    def cyan_name_pos(self, screen, n_chars):
        """Dự phòng khi OCR đọc sai tên (bị chồng chữ với người khác): tên mình là dòng chữ
        màu xanh ngọc duy nhất, tên người khác màu trắng. Tìm cụm chữ cyan dài cỡ tên mình."""
        H, W = screen.shape[:2]
        hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
        m = cyan_mask(hsv, self.cfg).astype(np.uint8) * 255
        m[:int(H * 0.12), :] = 0  # dải giao diện phía trên (khung thông tin, tên map, nút)
        m[:int(H * 0.15), :int(W * 0.3)] = 0
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3)))
        n, _, st, _ = cv2.connectedComponentsWithStats(m)
        cands = []
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if n_chars * 6 <= w <= n_chars * 13 + 10 and 8 <= h <= 22 and a >= 0.45 * w * h:
                cands.append((int(x + w / 2), int(y + h / 2)))
        # camera đi theo nhân vật: ưu tiên chỗ vừa thấy nhân vật, không có thì gần giữa màn hình
        return self.pick_me(cands, W, H)

    def recent_player_pos(self, seconds=4):
        """Vị trí nhân vật đọc được gần nhất (nếu chưa quá 'seconds' giây) - dùng khi tên bị che."""
        me, t = getattr(self, "_last_me", (None, 0))
        return me if me and time.time() - t <= seconds else None

    def map_label_lines(self, screen):
        """Đọc riêng ô tên map ở góc trên-phải (chữ trắng trên nền xanh đậm).
        Vùng mặc định: 25% bên phải, 12% phía trên; đổi bằng 'map_region' [x1, y1, x2, y2] trong config."""
        if self.ocr.ok is None:
            self.ocr.setup(self.cfg)
        if not self.ocr.ok:
            return []
        H, W = screen.shape[:2]
        x1, y1, x2, y2 = self.cfg.get("map_region") or [int(W * 0.75), 0, W, int(H * 0.12)]
        crop = screen[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]
        if crop.size == 0:
            return []
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        g = 255 - cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        lines = []
        for psm in (11, 6):
            t = self.ocr.pt.image_to_string(g, lang=self.ocr.lang, config=f"--psm {psm}")
            lines += [norm_text(l) for l in t.splitlines() if norm_text(l)]
        return lines

    def detect_map(self, screen, words=None):
        # 1) đọc riêng ô tên map góc trên-phải (chính xác hơn đọc cả màn hình)
        best, bv = None, 0
        lines = self.map_label_lines(screen)
        for name in self.maps:
            target = norm_text(name)
            for line in lines:
                r = difflib.SequenceMatcher(None, line, target).ratio()
                if target in line:
                    r = max(r, 0.95)
                if r >= 0.75 and r > bv:
                    best, bv = name, r
        if best:
            return best
        # 2) dự phòng: tìm trong chữ đọc được trên cả màn hình
        words = self.read_words(screen) if words is None else words
        for name in self.maps:
            for _, _, r in OCR.find_name(words, name, 0.7):
                if r > bv:
                    best, bv = name, r
        return best

    def wait_battle(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.in_battle(self.win.grab()):
                return True
            self.sleep(0.3)
        return False

    def press_attack(self):
        """Bấm đánh ngay, không chờ. Vị trí nút đánh được nhớ lại (tìm lại sau mỗi 30 giây)."""
        key = self.cfg["move"].get("key_attack")
        if key:
            key_press(key)
            return
        pos, t = getattr(self, "_atk", (None, 0))
        if pos is None or time.time() - t > 30:
            # nút tròn nằm trên nền map (mỗi map một màu) -> chỉ so phần giữa nút
            found = self.tpl.find(self.win.grab(), "ui/nut_danh.png", 0.75)
            pos = found[:2] if found else None
            self._atk = (pos, time.time())
            if not pos and time.time() - getattr(self, "_atk_warn", 0) > 30:
                self._atk_warn = time.time()
                self.log("[!] Không thấy nút Đánh trên màn hình (chụp lại ảnh 'nut_danh' ở tab Cài đặt?)")
        if pos:
            self.click(pos[0], pos[1], jitter=2)

    def nearest_target(self, screen, map_name, selected, band=None, prefer=None):
        """Trả về (quái gần nhất, vị trí nhân vật). Toạ độ là tâm dòng tên trên đầu.
        band: chỉ đọc chữ trong dải ngang này; không thấy đủ thì đọc lại cả màn hình.
        prefer: (dx, dy) của con đang đuổi so với nhân vật ở lần đọc trước -> bám tiếp con đó
        (không đổi sang con khác giữa đường, kẻo lúc đi trái lúc đi phải)."""
        words = self.read_words(screen, band)
        found = self.targets(screen, map_name, selected, words)
        me = self.player_pos(screen, words)
        if band and not (found and me):
            return self.nearest_target(screen, map_name, selected, prefer=prefer)
        # bỏ những con vừa bấm đánh mà không vào trận (thường là đang bị người khác đánh)
        now = time.time()
        self._skip = [k for k in getattr(self, "_skip", []) if k[2] > now]
        found = [f for f in found
                 if not any(abs(f[0] - k[0]) < 60 and abs(f[1] - k[1]) < 40 for k in self._skip)]
        if me:  # bỏ trường hợp đọc nhầm chính tên mình
            found = [f for f in found if abs(f[0] - me[0]) + abs(f[1] - me[1]) > 10]
            level_y = self.cfg["move"].get("same_level_px", 60)
            # quái cùng tầng luôn được chọn trước quái ở tầng khác (phải leo thang / nhảy, hay hỏng)
            found.sort(key=lambda t: abs(t[0] - me[0]) + 2 * abs(t[1] - me[1]) +
                       (0 if abs(t[1] - me[1]) <= level_y else 1000))
            if prefer:
                same = [f for f in found if f[2] == prefer[2]
                        and abs(f[0] - me[0] - prefer[0]) <= 150 and abs(f[1] - me[1] - prefer[1]) <= 50]
                if same:
                    return min(same, key=lambda f: abs(f[0] - me[0] - prefer[0]) +
                               2 * abs(f[1] - me[1] - prefer[1])), me
        return (found[0] if found else None), me

    def engage(self, screen, map_name, selected):
        target, me = self.nearest_target(screen, map_name, selected)
        if not target:
            return False
        mv = self.cfg["move"]
        self.log(f"-> Tìm thấy {target[2]}, tiến tới đánh")
        if not me:
            me = self.recent_player_pos()
            if me:
                self.log("  Tên nhân vật bị che, dùng vị trí vừa thấy")

        if not me or not mv.get("key_left"):
            # không biết nhân vật ở đâu / không có phím đi -> bấm vào quái rồi bấm nút đánh
            if not me:
                self.log("[!] Không thấy tên nhân vật trên màn hình, thử bấm thẳng vào quái")
            self.click(target[0], target[1] + mv.get("monster_click_offset_y", 35))
            if self.wait_battle(mv.get("walk_wait", 2.5)):
                return True
            return self.try_attack(target)

        # đi từng bước bằng phím, sau mỗi bước đọc lại vị trí nhân vật và quái
        near_x = mv.get("attack_range_px", 120)  # trong khoảng này: lao tới + bấm đánh
        level_y = mv.get("same_level_px", 60)
        speed = mv.get("speed_px_per_s", 250)
        direction = 1 if target[0] >= me[0] else -1  # hướng đi tìm mép khi cần rơi xuống
        searching_edge = False
        stuck = 0
        misses = 0  # số lần liền đọc trượt tên quái
        for _ in range(mv.get("max_steps", 25)):
            x, y = target[0], target[1]
            dx, dy = x - me[0], y - me[1]
            searching_edge = False
            long_walk = False  # chỉ tính "kẹt" khi đã giữ phím đủ lâu
            if abs(dx) <= near_x and abs(dy) <= level_y:
                self.log(f"  Tới gần {target[2]} (cách {dx:+d}px), lao tới và bấm đánh")
                return self.charge(1 if dx > 0 else -1, target)

            if abs(dy) <= level_y:
                # cùng tầng -> đi ngang tới quái
                self.log(f"  Đi {'phải' if dx > 0 else 'trái'} (còn cách {abs(dx)}px)")
                t = (abs(dx) - near_x / 2) / speed
                long_walk = t >= 0.4
                # còn cách dưới ~300px: vừa đi vừa bấm đánh, không để quái đi ngang qua
                if self.walk(1 if dx > 0 else -1, t, attack=abs(dx) <= mv.get("attack_spam_px", 300)):
                    return True
            else:
                vkey = mv.get("key_down", "down") if dy > 0 else mv.get("key_up", "up")
                ladder = self.find_ladder(screen, me, target, map_name)
                if ladder and abs(ladder[0] - me[0]) > 15:
                    # Cách 1: có thang -> đi tới thang
                    self.log(f"  Quái ở tầng {'dưới' if dy > 0 else 'trên'}, đi tới thang")
                    t = (abs(ladder[0] - me[0]) - 5) / speed
                    long_walk = t >= 0.4
                    self.walk(1 if ladder[0] > me[0] else -1, t)
                elif ladder and vkey:
                    # đang đứng ở thang -> leo lên / xuống
                    self.log(f"  Leo {'xuống' if dy > 0 else 'lên'} thang")
                    self.hold_key(vkey, 1.0)
                elif dy < 0:
                    # quái ở tầng trên, không thấy thang -> nhảy về phía quái
                    self.log("  Quái ở tầng trên, nhảy lên")
                    long_walk = True
                    self.walk(1 if dx > 0 else -1, 0.5, jump=True)
                elif abs(dx) > near_x:
                    # quái ở chỗ thấp hơn nhưng còn xa theo chiều ngang -> cứ đi về phía quái:
                    # đường dốc sẽ dẫn xuống, hoặc tới mép thì rơi xuống
                    self.log(f"  Quái ở chỗ thấp hơn, đi {'phải' if dx > 0 else 'trái'} về phía quái "
                             f"(còn cách {abs(dx)}px)")
                    t = (abs(dx) - near_x / 2) / speed
                    long_walk = t >= 0.4
                    direction = 1 if dx > 0 else -1
                    if self.walk(direction, t, attack=abs(dx) <= mv.get("attack_spam_px", 300)):
                        return True
                else:
                    # Cách 2: quái ở tầng dưới, không thấy thang -> đi ra mép để rơi xuống
                    searching_edge = True
                    self.log(f"  Quái ở tầng dưới, đi {'phải' if direction > 0 else 'trái'} tìm mép để xuống")
                    long_walk = True
                    self.walk(direction, 0.5)
                    if vkey:
                        key_press(vkey)
            self.sleep(0.2, 0.3)

            screen = self.win.grab()
            if self.in_battle(screen):
                return True
            prev, last = me, target
            band = (me[1] - 150, me[1] + 150) if abs(dy) <= level_y else None
            prefer = (last[0] - prev[0], last[1] - prev[1], last[2])
            target, me = self.nearest_target(screen, map_name, selected, band, prefer)
            if not target:
                ldx = last[0] - prev[0]
                if abs(ldx) <= near_x * 2 and abs(last[1] - prev[1]) <= level_y:
                    # đứng sát quái thì tên 2 bên đè lên nhau, OCR hay đọc trượt -> cứ lao tới đánh
                    self.log("  Mất dấu quái ở gần (tên bị đè), lao tới và bấm đánh")
                    return self.charge(1 if ldx > 0 else -1, last)
                misses += 1
                if misses > mv.get("max_misses", 2):
                    self.log("  Không còn thấy quái trên màn hình")
                    return False
                # OCR hay đọc trượt 1-2 lần: coi quái vẫn ở chỗ vừa thấy, đi tiếp về phía đó
                self.log("  Tạm không đọc được tên quái, đi tiếp về chỗ vừa thấy")
                base = me or prev
                target, me = (base[0] + prefer[0], base[1] + prefer[1], last[2], 0.0), base
                stuck = 0
                continue
            misses = 0
            if not me:
                self.log("  Không thấy tên nhân vật (bị che?), dùng vị trí cũ")
                me = prev
            # camera đi theo nhân vật -> vị trí nhân vật trên màn hình gần như đứng yên khi đi.
            # Coi là "kẹt" chỉ khi cả vị trí nhân vật lẫn khoảng cách tới quái đều không đổi.
            moved_me = abs(me[0] - prev[0]) + abs(me[1] - prev[1])
            moved_rel = abs((target[0] - me[0]) - (last[0] - prev[0])) + \
                abs((target[1] - me[1]) - (last[1] - prev[1]))
            if long_walk and moved_me < 5 and moved_rel < 8:
                stuck += 1
                if searching_edge:
                    direction = -direction  # đụng tường -> quay lại tìm mép bên kia
                if stuck >= 4:
                    self.log("[!] Nhân vật không di chuyển. Kiểm tra phím đi ở tab Cài đặt "
                             "(phím có đi được trong game không?)")
                    return False
            elif long_walk:
                stuck = 0
        return False

    def charge(self, direction, target):
        """Giữ phím đi về phía quái và bấm nút đánh liên tục (quái hay đi lòng vòng)."""
        mv = self.cfg["move"]
        key = mv["key_right"] if direction > 0 else mv["key_left"]
        end = time.time() + mv.get("charge_seconds", 1.5)
        self.ensure_focus()
        key_down(key)
        try:
            while time.time() < end:
                self.press_attack()
                self.sleep(0.15, 0.2)
                if self.in_battle(self.win.grab()):
                    return True
        finally:
            key_up(key)
        return self.try_attack(target)

    def try_attack(self, target):
        """Bấm nút đánh. Không vào trận -> bỏ qua con này 20 giây (có thể đang bị người khác đánh)."""
        self.press_attack()
        if self.wait_battle(1.5):
            return True
        self.log(f"  Bấm đánh nhưng không vào trận, bỏ qua {target[2]} này 20 giây "
                 "(có thể đang bị người khác đánh hoặc còn xa)")
        self._skip = getattr(self, "_skip", []) + [(target[0], target[1], time.time() + 20)]
        return False

    def walk(self, direction, seconds, jump=False, attack=False):
        """Giữ phím trái/phải trong 'seconds' giây (0.15-1.0s). jump=True: bấm phím nhảy lúc đang đi.
        attack=True: vừa đi vừa bấm đánh, trả về True nếu đã vào trận."""
        mv = self.cfg["move"]
        key = mv["key_right"] if direction > 0 else mv["key_left"]
        seconds = max(0.15, min(1.0, seconds))
        self.ensure_focus()
        end = time.time() + seconds
        key_down(key)
        try:
            if jump and mv.get("key_up", "up"):
                self.sleep(0.1, 0.1)
                key_press(mv.get("key_up", "up"))
            while attack and time.time() < end - 0.1:
                self.press_attack()
                if self.in_battle(self.win.grab()):
                    return True
                self.sleep(0.15, 0.2)
            rest = max(0.0, end - time.time())
            self.sleep(rest, rest)
        finally:
            key_up(key)
        return False

    def ladder_tpl(self, map_name):
        """Ảnh mẫu thang của map (mỗi map một kiểu thang). Map chưa chụp -> dùng ui/thang.png.
        Một ảnh dùng được cho cả theme ngày lẫn đêm (thang có ~0.8-1.0, chỗ không có thang ~0.3)."""
        rel = self.maps.get(map_name or "", {}).get("ladder")
        if rel and self.tpl.exists(rel):
            return rel
        rel = f"ladders/{slug(map_name)}.png" if map_name else None  # file đặt sẵn theo tên map
        return rel if rel and self.tpl.exists(rel) else "ui/thang.png"

    def find_ladder(self, screen, me, target, map_name=None):
        """Thang gần nhân vật nhất nằm giữa tầng của nhân vật và tầng của quái."""
        ladders = self.tpl.find_all(screen, self.ladder_tpl(map_name), self.cfg.get("ladder_threshold", 0.7))
        lo, hi = min(me[1], target[1]) - 40, max(me[1], target[1]) + 80
        ladders = [lad for lad in ladders if lo <= lad[1] <= hi]
        return min(ladders, key=lambda lad: abs(lad[0] - me[0])) if ladders else None

    # ---------------------------------------------------------- vòng lặp chính
    def stop_reason(self):
        a = self.cfg["auto"]
        st = self.stats
        if a.get("max_minutes") and time.time() - st["start"] > a["max_minutes"] * 60:
            return f"Đã chạy đủ {a['max_minutes']} phút"
        if a.get("max_battles") and st["battles"] >= a["max_battles"]:
            return f"Đã đánh đủ {a['max_battles']} trận"
        if a.get("max_lose_streak") and st["lose_streak"] >= a["max_lose_streak"]:
            return f"Thua liên tiếp {st['lose_streak']} trận (bị trừ kinh nghiệm), dừng để bạn kiểm tra"
        return None

    def loop(self, map_name, selected):
        self.stats.update(battles=0, wins=0, losses=0, lose_streak=0, start=time.time())
        self.attach(focus=True)
        self.ensure_size()
        self.log(f"Bắt đầu: map '{map_name}', quái: {', '.join(selected) or '(chưa chọn)'}")
        if not self.win.found:
            self.log("[!] Không thấy cửa sổ game, dùng toàn màn hình")
        was_battle, idle = False, time.time()
        while not self.stop_event.is_set():
            self.attach()
            if not self.ensure_size():
                self.sleep(5)
                continue
            screen = self.win.grab()

            if self.in_battle(screen):
                if not was_battle:
                    self.stats["battles"] += 1
                    self.log(f"[Trận {self.stats['battles']}]")
                was_battle = True
                self.battle_turn()
                idle = time.time()
                continue

            # popup kết quả trận. Ngưỡng nút Đóng thấp hơn ngưỡng chung: ảnh mẫu dính nền bản đồ
            # phía sau nút (thay đổi theo chỗ đứng) nên chỉ khớp ~0.82-0.86.
            close_th = self.cfg.get("close_threshold", 0.7)
            close_pos = self.tpl.find(screen, "ui/dong.png", close_th)
            lost = bool(self.tpl.find(screen, "ui/thua.png", 0.8))
            if close_pos or lost:
                if was_battle:
                    self.stats["losses" if lost else "wins"] += 1
                    self.stats["lose_streak"] = self.stats["lose_streak"] + 1 if lost else 0
                    self.log("  => THUA" if lost else "  => Thắng")
                was_battle = False
                if close_pos:
                    self.click(close_pos[0], close_pos[1])
                    self.log("  Bấm nút Đóng")
                else:
                    key_press("esc")  # thấy chữ THUA mà không thấy nút Đóng -> thử Esc
                self.sleep(1.0)
                idle = time.time()
                r = self.stop_reason()
                if r:
                    self.log("Dừng: " + r)
                    break
                continue
            was_battle = False

            r = self.stop_reason()
            if r:
                self.log("Dừng: " + r)
                break

            if self.engage(screen, map_name, selected):
                idle = time.time()
                continue

            if time.time() - idle > self.cfg.get("stuck_seconds", 60):
                self.log("[!] Lâu không thấy quái/nút nào. Nhấn ESC và đi dạo một chút...")
                key_press("esc")
                mv = self.cfg["move"]
                if mv.get("key_left"):
                    self.hold_key(random.choice([mv["key_left"], mv["key_right"]]), 1.0)
                idle = time.time()
            self.sleep(0.7)

    def start(self, map_name, selected, on_done=None):
        if self.thread and self.thread.is_alive():
            return
        self.reload()
        self._calibrated = False
        self.stop_event.clear()
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.02

        def run():
            try:
                self.loop(map_name, selected)
            except StopIteration:
                self.log("Đã dừng.")
            except pyautogui.FailSafeException:
                self.log("Dừng khẩn cấp (chuột ở góc màn hình).")
            except Exception as e:
                self.log(f"Lỗi: {e!r}")
            finally:
                if on_done:
                    on_done()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
