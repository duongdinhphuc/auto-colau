# -*- coding: utf-8 -*-
"""
Bảng điều khiển auto Cờ Lau Loạn Thế (PC Windows) - chạy:  python app.py
"""
import os
import queue
import sys
import time
import tkinter as tk
import unicodedata
from tkinter import messagebox, simpledialog, ttk

import bot as B

if B.pyautogui is None:
    sys.exit("Chưa cài thư viện. Chạy:  pip install pyautogui opencv-python numpy pillow")

from PIL import Image, ImageTk  # noqa: E402  (Pillow được cài kèm pyautogui)

B.set_dpi_aware()

GEM_LABELS = {
    "dao": "Quả đào", "tim": "Trái tim", "vang": "Thỏi vàng", "sao": "Ngôi sao",
    "kiem": "Thanh kiếm", "amduong": "Âm dương", "giot": "Giọt tím",
    "kiem_do": "Kiếm đỏ (đặc biệt)",
}
UI_TEMPLATES = [
    ("dau_hang.png", "Nút 'Đầu hàng' (chỉ có trong trận)", True),
    ("dong.png", "Nút 'Đóng' ở bảng kết quả trận", True),
    ("nut_danh.png", "Nút đánh (thanh kiếm tròn) trên map", True),
    ("thua.png", "Chữ 'THUA' ở bảng kết quả", False),
    ("ky_nang.png", "Nút 'Kỹ năng' trong trận", False),
    ("tui_do.png", "Nút 'Túi đồ' trong trận", False),
    ("binh_mau.png", "Bình máu trong túi đồ (không cần nữa)", False),
    ("luot_doi_thu.png", "Chữ 'Lượt của đối thủ'", False),
    ("thang.png", "Thang dùng chung khi map chưa chụp thang riêng (nút 'Chụp thang' ở tab Tự động)", False),
]


slug = B.slug


# =================================================================== chọn vùng trên màn hình
class Picker:
    """Chụp màn hình, phủ ảnh tĩnh toàn màn hình để người dùng kéo chọn vùng hoặc bấm 1 điểm."""

    def __init__(self, root):
        self.root = root

    def shot(self):
        self.root.withdraw()
        self.root.update()
        time.sleep(0.35)
        img = B.pyautogui.screenshot()
        return img

    def ask(self, img, prompt, mode="rect"):
        res = {}
        top = tk.Toplevel(self.root)
        top.attributes("-fullscreen", True)
        top.attributes("-topmost", True)
        cv = tk.Canvas(top, cursor="cross", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        photo = ImageTk.PhotoImage(img)
        cv.create_image(0, 0, image=photo, anchor="nw")
        txt = prompt + "   (Esc = bỏ qua)"
        t = cv.create_text(20, 20, text=txt, anchor="nw", fill="yellow", font=("Segoe UI", 16, "bold"))
        cv.create_rectangle(cv.bbox(t), fill="black", outline="")
        cv.tag_raise(t)
        st = {"x": 0, "y": 0, "r": None}

        def down(e):
            st["x"], st["y"] = e.x, e.y
            if mode == "point":
                res["point"] = (e.x, e.y)
                top.destroy()
                return
            st["r"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

        def move(e):
            if st["r"]:
                cv.coords(st["r"], st["x"], st["y"], e.x, e.y)

        def up(e):
            if mode == "rect" and st["r"]:
                x1, x2 = sorted((st["x"], e.x))
                y1, y2 = sorted((st["y"], e.y))
                if x2 - x1 > 3 and y2 - y1 > 3:
                    res["rect"] = (x1, y1, x2, y2)
                top.destroy()

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        top.bind("<Escape>", lambda e: top.destroy())
        top.focus_force()
        top.grab_set()
        self.root.wait_window(top)
        return res.get("rect") or res.get("point")

    def done(self):
        self.root.deiconify()


# =================================================================== ứng dụng
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Tự động - Cờ Lau Loạn Thế")
        self.root.geometry("470x760")
        self.q = queue.Queue()
        self.bot = B.Bot(log=lambda m: self.q.put(("log", m)))
        self.cfg, self.maps = self.bot.cfg, self.bot.maps
        self.picker = Picker(self.root)
        self.thumbs = []
        self.mon_vars = {}

        style = ttk.Style()
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=6)
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tab_auto = ttk.Frame(nb, padding=8)
        self.tab_set = ttk.Frame(nb, padding=8)
        nb.add(self.tab_auto, text="  Tự động  ")
        nb.add(self.tab_set, text="  Cài đặt  ")
        self.build_auto()
        self.build_settings()
        self.root.after(200, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------------------------------------------------- lưu
    def remember_size(self):
        """Ghi lại kích thước cửa sổ game lúc cài đặt."""
        sz = self.bot.win.size()
        if sz and self.cfg.get("window_size") != sz:
            old = self.cfg.get("window_size")
            self.cfg["window_size"] = sz
            if old:
                self.log(f"[!] Kích thước cửa sổ đổi từ {old[0]}x{old[1]} sang {sz[0]}x{sz[1]}. "
                         "Nên cài lại bàn cờ, các viên và các nút cho khớp.")
            else:
                self.log(f"Đã lưu kích thước cửa sổ game: {sz[0]}x{sz[1]}")

    def save(self):
        B.save_json(B.CONFIG_PATH, self.cfg)
        B.save_json(B.MAPS_PATH, self.maps)

    def log(self, m):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", time.strftime("%H:%M:%S ") + m + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def thumb(self, rel, size=36):
        path = os.path.join(B.TPL, rel)
        if not os.path.exists(path):
            return None
        im = Image.open(path)
        im.thumbnail((size, size))
        ph = ImageTk.PhotoImage(im)
        self.thumbs.append(ph)
        return ph

    # ---------------------------------------------------------- chụp mẫu
    def capture(self, rel, prompt):
        """Kéo chọn một vùng, lưu thành templates/<rel>. Trả về True nếu thành công."""
        self.bot.attach()
        img = self.picker.shot()
        r = self.picker.ask(img, prompt)
        self.picker.done()
        if not r:
            return False
        self.remember_size()
        crop = img.crop(r)
        os.makedirs(os.path.dirname(os.path.join(B.TPL, rel)), exist_ok=True)
        crop.save(os.path.join(B.TPL, rel))
        self.log(f"Đã lưu mẫu {rel}")
        return True

    def pick_rect_client(self, prompt):
        self.bot.attach()
        img = self.picker.shot()
        r = self.picker.ask(img, prompt)
        self.picker.done()
        if not r:
            return None
        self.remember_size()
        x1, y1 = self.bot.win.to_client(r[0], r[1])
        x2, y2 = self.bot.win.to_client(r[2], r[3])
        return [x1, y1, x2, y2]

    # ================================================================ TAB TỰ ĐỘNG
    def build_auto(self):
        f = self.tab_auto
        self.stat_var = tk.StringVar(value="Đã chạy: 0:00:00 | Trận: 0 (thắng 0 / thua 0)")
        ttk.Label(f, textvariable=self.stat_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(8, 2))
        ttk.Label(row, text="Bản đồ:").pack(side="left")
        self.map_var = tk.StringVar(value=self.cfg["auto"].get("map") or next(iter(self.maps), ""))
        self.map_cb = ttk.Combobox(row, textvariable=self.map_var, values=list(self.maps), width=18,
                                   state="readonly")
        self.map_cb.pack(side="left", padx=4)
        self.map_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_monsters())
        ttk.Button(row, text="Nhận diện", command=self.detect_map).pack(side="left")
        ttk.Button(row, text="+ Map", width=6, command=self.add_map).pack(side="left", padx=2)
        # mỗi map một kiểu thang (gỗ, dây...) -> ảnh mẫu thang lưu riêng cho từng map
        ttk.Button(row, text="Chụp thang", command=self.capture_ladder).pack(side="left", padx=2)
        self.ladder_lbl = ttk.Label(row, text="")
        self.ladder_lbl.pack(side="left", padx=2)

        hdr = ttk.Frame(f)
        hdr.pack(fill="x", pady=(8, 0))
        ttk.Label(hdr, text="Chọn quái đánh (bản đồ đang đứng):").pack(side="left")
        ttk.Button(hdr, text="Quét màn hình", command=self.scan_screen).pack(side="right")
        self.mon_frame = ttk.Frame(f, relief="groove", padding=6)
        self.mon_frame.pack(fill="x", pady=4)

        add = ttk.Frame(f)
        add.pack(fill="x")
        ttk.Label(add, text="Tên quái:").pack(side="left")
        self.new_name = tk.StringVar()
        e = ttk.Entry(add, textvariable=self.new_name, width=18)
        e.pack(side="left", padx=3)
        e.bind("<Return>", lambda ev: self.add_monster())
        ttk.Label(add, text="Cấp:").pack(side="left")
        self.new_lv = tk.StringVar()
        ttk.Entry(add, textvariable=self.new_lv, width=4).pack(side="left", padx=3)
        ttk.Button(add, text="Thêm", command=self.add_monster).pack(side="left")
        ttk.Label(f, text="Gõ đúng tên như trên đầu con quái trong game (có dấu hay không đều được)",
                  foreground="gray").pack(anchor="w")
        self.refresh_monsters()

        ttk.Label(f, text="Kỹ năng tự dùng khi đủ nội lực (chọn 1):").pack(anchor="w", pady=(8, 0))
        self.skill_frame = ttk.Frame(f)
        self.skill_frame.pack(fill="x", pady=2)
        self.skill_var = tk.IntVar(value=self.cfg["auto"].get("skill", 0))
        self.refresh_skills()

        pr = ttk.Frame(f)
        pr.pack(fill="x", pady=(8, 0))
        self.pot_var = tk.BooleanVar(value=self.cfg["auto"].get("use_potion", True))
        ttk.Checkbutton(pr, text="Dùng bình máu khi HP dưới", variable=self.pot_var).pack(side="left")
        self.pot_hp = tk.IntVar(value=self.cfg["auto"].get("potion_hp", 30))
        ttk.Spinbox(pr, from_=5, to=95, width=4, textvariable=self.pot_hp).pack(side="left", padx=4)
        ttk.Label(pr, text="%").pack(side="left")

        lim = ttk.LabelFrame(f, text="Tự dừng khi", padding=6)
        lim.pack(fill="x", pady=8)
        self.lose_var = tk.IntVar(value=self.cfg["auto"].get("max_lose_streak", 2))
        self.min_var = tk.IntVar(value=self.cfg["auto"].get("max_minutes", 120))
        self.bat_var = tk.IntVar(value=self.cfg["auto"].get("max_battles", 0))
        for i, (t, v) in enumerate([("Thua liên tiếp (trận)", self.lose_var),
                                    ("Chạy quá (phút)", self.min_var),
                                    ("Đủ số trận", self.bat_var)]):
            ttk.Label(lim, text=t).grid(row=0, column=i * 2, sticky="w")
            ttk.Spinbox(lim, from_=0, to=9999, width=5, textvariable=v).grid(row=0, column=i * 2 + 1,
                                                                             padx=(2, 10))
        ttk.Label(lim, text="(0 = không giới hạn)", foreground="gray").grid(row=1, column=0,
                                                                          columnspan=6, sticky="w")

        btn = ttk.Frame(f)
        btn.pack(pady=4)
        self.start_btn = ttk.Button(btn, text="Bắt đầu", style="Big.TButton", command=self.start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(btn, text="Dừng", style="Big.TButton", command=self.stop,
                                   state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.top_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Bảng luôn nằm trên cùng", variable=self.top_var,
                        command=lambda: self.root.attributes("-topmost", self.top_var.get())).pack()
        self.root.attributes("-topmost", True)
        ttk.Label(f, text="Dừng khẩn cấp: kéo chuột lên góc trên-trái màn hình",
                  foreground="gray").pack()

        self.logbox = tk.Text(f, height=9, state="disabled", font=("Consolas", 9))
        self.logbox.pack(fill="both", expand=True, pady=(6, 0))

    def capture_ladder(self):
        """Chụp thang của map đang chọn (mỗi map một kiểu thang). Một ảnh dùng được cả ngày lẫn đêm."""
        m = self.map_var.get()
        if not m:
            self.log("[!] Chọn bản đồ trước khi chụp thang")
            return
        rel = f"ladders/{slug(m)}.png"
        if self.capture(rel, f"Kéo chọn sát một đoạn thang của map '{m}' "
                             "(khoảng 4-6 bậc, cắt sát 2 bên dây/thanh thang)"):
            self.maps.setdefault(m, {"monsters": []})["ladder"] = rel
            self.save()
            self.update_ladder_label()

    def update_ladder_label(self):
        m = self.map_var.get()
        has = self.bot.ladder_tpl(m) != "ui/thang.png"
        self.ladder_lbl.config(text="thang: ✔" if has else "thang: chưa chụp",
                               foreground="green" if has else "gray")

    def refresh_monsters(self):
        self.update_ladder_label()
        for w in self.mon_frame.winfo_children():
            w.destroy()
        m = self.map_var.get()
        mons = self.maps.get(m, {}).get("monsters", [])
        sel = set(self.cfg["auto"].get("selected", {}).get(m, []))
        self.mon_vars = {}
        if not mons:
            ttk.Label(self.mon_frame, text="(Chưa có quái - nhập tên bên dưới rồi bấm Thêm)",
                      foreground="gray").pack(anchor="w")
        for i, mon in enumerate(mons):
            v = tk.BooleanVar(value=mon["name"] in sel)
            self.mon_vars[mon["name"]] = v
            lv = f" (Lv.{mon['level']})" if mon.get("level") else ""
            ttk.Checkbutton(self.mon_frame, text=mon["name"] + lv, variable=v).grid(row=i, column=0,
                                                                                    sticky="w")
            st = getattr(self, "seen", {}).get(mon["name"])
            if st is not None:
                ttk.Label(self.mon_frame, text=f"thấy {st} con" if st else "không thấy",
                          foreground="green" if st else "gray").grid(row=i, column=1, padx=6)
            ttk.Button(self.mon_frame, text="Xoá", width=4,
                       command=lambda mo=mon: self.del_monster(mo)).grid(row=i, column=2, padx=2)
        self.mon_frame.columnconfigure(0, weight=1)

    def del_monster(self, mon):
        if messagebox.askyesno("Xoá quái", f"Xoá '{mon['name']}' khỏi map này?"):
            self.maps[self.map_var.get()]["monsters"].remove(mon)
            self.save()
            self.refresh_monsters()

    def add_monster(self):
        m = self.map_var.get()
        if not m:
            return self.add_map()
        name = " ".join(self.new_name.get().split())
        if not name:
            return
        mons = self.maps[m].setdefault("monsters", [])
        if any(B.norm_text(x["name"]) == B.norm_text(name) for x in mons):
            self.log(f"'{name}' đã có trong danh sách")
            return
        lv = self.new_lv.get().strip()
        mons.append({"name": name, "level": int(lv) if lv.isdigit() else None})
        self.save()
        self.new_name.set("")
        self.new_lv.set("")
        self.refresh_monsters()

    def add_map(self):
        name = simpledialog.askstring("Thêm bản đồ", "Tên bản đồ, gõ đúng như góc trên-phải game\n"
                                      "(vd: Trại Vân Sơn):", parent=self.root)
        if not name:
            return
        name = " ".join(name.split())
        self.maps.setdefault(name, {"monsters": []})
        self.save()
        self.map_cb["values"] = list(self.maps)
        self.map_var.set(name)
        self.refresh_monsters()

    def scan_screen(self):
        """Đọc chữ trên màn hình game, báo con quái nào trong danh sách đang thấy."""
        self.collect_auto()
        self.bot.reload()
        self.bot.attach()
        s = self.bot.win.grab()
        words = self.bot.read_words(s)
        if not self.bot.ocr.ok:
            messagebox.showerror("Thiếu Tesseract", self.bot.ocr.err)
            return
        m = self.map_var.get()
        names = [x["name"] for x in self.maps.get(m, {}).get("monsters", [])]
        found = self.bot.targets(s, m, names, words)
        self.seen = {n: sum(1 for f in found if f[2] == n) for n in names}
        me = self.bot.player_pos(s, words)
        mp = self.bot.detect_map(s, words)
        self.log("Chữ đọc được: " + " | ".join(w[0] for w in words[:60]))
        self.log(f"Nhân vật: {'thấy ' + str(me) if me else 'không thấy (kiểm tra Tên nhân vật ở Cài đặt)'}"
                 f" | Map: {mp or 'không nhận ra'}")
        self.refresh_monsters()

    def detect_map(self):
        self.bot.reload()
        self.bot.attach()
        name = self.bot.detect_map(self.bot.win.grab())
        if name:
            self.map_var.set(name)
            self.refresh_monsters()
            self.log(f"Đang ở map: {name}")
        else:
            self.log("Không nhận ra map. Chọn tay, hoặc '+ Map' để chụp tên map hiện tại.")

    def refresh_skills(self):
        for w in self.skill_frame.winfo_children():
            w.destroy()
        for i in range(1, 5):
            col = ttk.Frame(self.skill_frame)
            col.pack(side="left", padx=4)
            ph = self.thumb(f"skills/skill_{i}.png", 40)
            if ph:
                ttk.Label(col, image=ph).pack()
            else:
                ttk.Label(col, text=f"KN {i}\n(chưa có)", foreground="gray", justify="center").pack()
            ttk.Radiobutton(col, variable=self.skill_var, value=i).pack()
            ttk.Button(col, text="Chụp", width=5,
                       command=lambda k=i: self.capture_skill(k)).pack()
        col = ttk.Frame(self.skill_frame)
        col.pack(side="left", padx=8)
        ttk.Label(col, text="Không\ndùng", justify="center").pack()
        ttk.Radiobutton(col, variable=self.skill_var, value=0).pack()

    def capture_skill(self, i):
        self.capture(f"skills/skill_{i}.png",
                     f"Mở bảng Kỹ năng trong trận, kéo chọn sát biểu tượng kỹ năng {i}")
        self.refresh_skills()

    def collect_auto(self):
        a = self.cfg["auto"]
        m = self.map_var.get()
        a["map"] = m
        a.setdefault("selected", {})[m] = [n for n, v in self.mon_vars.items() if v.get()]
        a["skill"] = self.skill_var.get()
        a["use_potion"] = self.pot_var.get()
        a["potion_hp"] = int(self.pot_hp.get())
        a["max_lose_streak"] = int(self.lose_var.get())
        a["max_minutes"] = int(self.min_var.get())
        a["max_battles"] = int(self.bat_var.get())
        self.save()
        return m, a["selected"][m]

    def check_ready(self, m, selected):
        miss = [f for f, _, need in UI_TEMPLATES if need and not os.path.exists(P_ui(f))]
        gems = [g for g in self.cfg["gems"] if not os.path.exists(os.path.join(B.TPL, "gems", g + ".png"))]
        msgs = []
        if miss:
            msgs.append("Chưa chụp mẫu nút: " + ", ".join(miss))
        if self.cfg["board"]["bottom_right"][0] <= self.cfg["board"]["top_left"][0]:
            msgs.append("Chưa chọn vùng bàn cờ")
        if gems:
            msgs.append("Chưa lấy mẫu viên: " + ", ".join(GEM_LABELS.get(g, g) for g in gems))
        if not selected:
            msgs.append("Chưa chọn quái nào")
        if not self.cfg.get("player_name"):
            msgs.append("Chưa nhập Tên nhân vật (Cài đặt) - bot sẽ không biết quái nào gần nhất")
        if self.pot_var.get() and not self.cfg.get("hp_bar"):
            msgs.append("Chưa chọn thanh máu (tab Cài đặt) - sẽ không tự dùng bình")
        if self.skill_var.get() and not self.cfg.get("energy_bar"):
            msgs.append("Chưa chọn thanh nội lực (tab Cài đặt) - sẽ không tự dùng kỹ năng")
        return msgs

    def start(self):
        m, selected = self.collect_auto()
        msgs = self.check_ready(m, selected)
        if msgs and not messagebox.askyesno("Chưa cài đặt đủ",
                                            "\n".join("• " + x for x in msgs) + "\n\nVẫn chạy?"):
            return
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.bot.start(m, selected, on_done=lambda: self.q.put(("done", None)))

    def stop(self):
        self.bot.stop()
        self.log("Đang dừng...")

    # ================================================================ TAB CÀI ĐẶT
    def build_settings(self):
        outer = self.tab_set
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        f = ttk.Frame(canvas)
        f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=f, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.set_frame = f
        self.refresh_settings()

    def refresh_settings(self):
        f = self.set_frame
        for w in f.winfo_children():
            w.destroy()
        ok = lambda b: ("✔", "green") if b else ("✘", "red")  # noqa: E731

        # cửa sổ
        g = ttk.LabelFrame(f, text="1. Cửa sổ game", padding=6)
        g.pack(fill="x", pady=4)
        self.title_var = tk.StringVar(value=self.cfg.get("window_title", ""))
        ttk.Label(g, text="Tên cửa sổ chứa:").grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.title_var, width=20).grid(row=0, column=1, padx=4)
        ttk.Button(g, text="Tìm", command=self.find_window).grid(row=0, column=2)
        rows = [("Tên nhân vật:", "player_name", 20), ("Tesseract:", "tesseract_path", 34)]
        for i, (t, k, wdt) in enumerate(rows, start=1):
            ttk.Label(g, text=t).grid(row=i, column=0, sticky="w")
            v = tk.StringVar(value=self.cfg.get(k) or "")
            e = ttk.Entry(g, textvariable=v, width=wdt)
            e.grid(row=i, column=1, columnspan=2, sticky="w", padx=4, pady=2)
            e.bind("<FocusOut>", lambda ev, kk=k, vv=v: self._set(self.cfg, kk, vv.get().strip()))
        ttk.Button(g, text="Kiểm tra đọc chữ", command=self.scan_screen).grid(row=3, column=1,
                                                                             sticky="w", pady=2)

        # bàn cờ
        g = ttk.LabelFrame(f, text="2. Bàn cờ (vào một trận rồi làm)", padding=6)
        g.pack(fill="x", pady=4)
        b = self.cfg["board"]
        s, c = ok(b["bottom_right"][0] > b["top_left"][0])
        ttk.Label(g, text=s, foreground=c).grid(row=0, column=0)
        ttk.Button(g, text="Chọn vùng bàn cờ", command=self.pick_board).grid(row=0, column=1, sticky="w")
        ttk.Label(g, text="Kiểu đổi viên:").grid(row=0, column=2, padx=(10, 2))
        self.move_style = tk.StringVar(value=b.get("move_style", "drag"))
        cb = ttk.Combobox(g, textvariable=self.move_style, values=["drag", "click"], width=6,
                          state="readonly")
        cb.grid(row=0, column=3)
        cb.bind("<<ComboboxSelected>>", lambda e: self._set(b, "move_style", self.move_style.get()))

        ttk.Button(g, text="Lấy mẫu tất cả viên", command=self.pick_gems).grid(row=1, column=1,
                                                                              sticky="w", pady=4)
        gf = ttk.Frame(g)
        gf.grid(row=2, column=0, columnspan=4, sticky="w")
        pri = self.cfg.setdefault("gem_priority", {})
        ttk.Label(gf, text="Viên").grid(row=0, column=1)
        ttk.Label(gf, text="Ưu tiên").grid(row=0, column=3)
        for i, gname in enumerate(B.gem_names(self.cfg)):
            rel = f"gems/{gname}.png"
            ph = self.thumb(rel, 26)
            if ph:
                ttk.Label(gf, image=ph).grid(row=i + 1, column=0)
            else:
                ttk.Label(gf, text="✘", foreground="red").grid(row=i + 1, column=0)
            ttk.Label(gf, text=GEM_LABELS.get(gname, gname)).grid(row=i + 1, column=1, sticky="w")
            ttk.Button(gf, text="Lấy lại", width=7,
                       command=lambda n=gname: self.pick_gems([n])).grid(row=i + 1, column=2, padx=4)
            v = tk.IntVar(value=pri.get(gname, 30 if gname in B.gem_aliases(self.cfg) else 0))
            sp = ttk.Spinbox(gf, from_=-20, to=50, width=4, textvariable=v,
                             command=lambda n=gname, vv=v: self._set(pri, n, int(vv.get())))
            sp.grid(row=i + 1, column=3)
            sp.bind("<FocusOut>", lambda e, n=gname, vv=v: self._set(pri, n, int(vv.get())))
        ttk.Button(g, text="Kiểm tra bàn cờ", command=self.test_board).grid(row=3, column=1, sticky="w",
                                                                           pady=4)
        ttk.Button(g, text="Tự căn lưới", command=self.calibrate_board).grid(row=3, column=2, columnspan=2,
                                                                             sticky="w", pady=4)

        # thanh máu / nội lực
        g = ttk.LabelFrame(f, text="3. Thanh máu & nội lực của bạn (trong trận)", padding=6)
        g.pack(fill="x", pady=4)
        s, c = ok(self.cfg.get("hp_bar"))
        ttk.Label(g, text=s, foreground=c).grid(row=0, column=0)
        ttk.Button(g, text="Chọn thanh máu (đỏ)", command=lambda: self.pick_bar("hp_bar")).grid(
            row=0, column=1, sticky="w")
        s, c = ok(self.cfg.get("energy_bar"))
        ttk.Label(g, text=s, foreground=c).grid(row=1, column=0)
        ttk.Button(g, text="Chọn thanh nội lực", command=lambda: self.pick_bar("energy_bar")).grid(
            row=1, column=1, sticky="w")
        ttk.Label(g, text="Màu:").grid(row=1, column=2)
        self.en_color = tk.StringVar(value=self.cfg.get("energy_color", "green"))
        cb = ttk.Combobox(g, textvariable=self.en_color, values=["green", "blue", "any"], width=6,
                          state="readonly")
        cb.grid(row=1, column=3)
        cb.bind("<<ComboboxSelected>>", lambda e: self._set(self.cfg, "energy_color", self.en_color.get()))
        ttk.Label(g, text="Dùng kỹ năng khi nội lực đạt (% thanh):").grid(row=2, column=0, columnspan=2,
                                                                       sticky="w")
        # giữ biến trên self: biến Tk cục bộ bị thu hồi -> ô số hiện trống
        self.need_var = need = tk.IntVar(value=int(round(B.energy_need(self.cfg) * 100)))

        def set_need(*_):
            try:
                self._set(self.cfg, "energy_need", max(1, min(100, int(need.get()))) / 100)
            except (tk.TclError, ValueError):
                pass
        sp = ttk.Spinbox(g, from_=5, to=100, width=4, textvariable=need, command=set_need)
        sp.grid(row=2, column=2, sticky="w")
        sp.bind("<FocusOut>", set_need)
        ttk.Label(g, text="26 = hết khúc đầu; 100 = đầy thanh", foreground="gray").grid(
            row=3, column=0, columnspan=4, sticky="w")
        ttk.Label(g, text="Tính trước bao nhiêu nước:").grid(row=4, column=0, columnspan=2, sticky="w")
        self.depth_var = depth = tk.IntVar(value=int(self.cfg.get("search_depth", 3)))

        def set_depth(*_):
            try:
                self._set(self.cfg, "search_depth", max(1, min(4, int(depth.get()))))
            except (tk.TclError, ValueError):
                pass
        sp = ttk.Spinbox(g, from_=1, to=4, width=4, textvariable=depth, command=set_depth)
        sp.grid(row=4, column=2, sticky="w")
        sp.bind("<FocusOut>", set_depth)
        ttk.Label(g, text="1 = chỉ nhìn nước hiện tại; 3 = nên dùng; 4 = kỹ hơn nhưng chậm hơn",
                  foreground="gray").grid(row=5, column=0, columnspan=4, sticky="w")
        ttk.Label(g, text="Thời gian mỗi lượt của game (giây):").grid(row=6, column=0, columnspan=2,
                                                                    sticky="w")
        self.limit_var = limit = tk.IntVar(value=int(self.cfg.get("turn_limit_s", 30)))

        def set_limit(*_):
            try:
                self._set(self.cfg, "turn_limit_s", max(5, min(120, int(limit.get()))))
            except (tk.TclError, ValueError):
                pass
        sp = ttk.Spinbox(g, from_=5, to=120, width=4, textvariable=limit, command=set_limit)
        sp.grid(row=6, column=2, sticky="w")
        sp.bind("<FocusOut>", set_limit)
        ttk.Label(g, text="Quá nửa thời gian bot thôi chờ; quá 3/4 bot đi ngay nước tìm được",
                  foreground="gray").grid(row=7, column=0, columnspan=4, sticky="w")

        # nút giao diện
        g = ttk.LabelFrame(f, text="4. Ảnh mẫu các nút (cắt sát nút)", padding=6)
        g.pack(fill="x", pady=4)
        for i, (fn, desc, need) in enumerate(UI_TEMPLATES):
            s, c = ok(os.path.exists(P_ui(fn)))
            ttk.Label(g, text=s, foreground=c if (need or s == "✔") else "gray").grid(row=i, column=0)
            # nút "Chụp" đứng trước mô tả: mô tả dài không đẩy nút ra ngoài cửa sổ
            ttk.Button(g, text="Chụp", width=6,
                       command=lambda n=fn, d=desc: self.capture_ui(n, d)).grid(row=i, column=1, padx=4)
            ttk.Label(g, text=desc + ("" if need else " (tuỳ chọn)"), wraplength=330,
                      justify="left").grid(row=i, column=2, sticky="w")

        # di chuyển
        g = ttk.LabelFrame(f, text="5. Di chuyển trên map", padding=6)
        g.pack(fill="x", pady=4)
        mv = self.cfg["move"]
        for i, (k, t) in enumerate([("key_left", "Phím sang trái"), ("key_right", "Phím sang phải"),
                                    ("key_up", "Phím lên / nhảy"), ("key_down", "Phím xuống (thang)"),
                                    ("key_attack", "Phím đánh (trống = bấm nút)"),
                                    ("key_use", "Phím dùng bình / kỹ năng")]):
            ttk.Label(g, text=t).grid(row=i, column=0, sticky="w")
            v = tk.StringVar(value=mv.get(k, {"key_up": "up", "key_down": "down", "key_use": "enter"}.get(k)) or "")
            e = ttk.Entry(g, textvariable=v, width=10)
            e.grid(row=i, column=1, sticky="w", padx=4)
            e.bind("<FocusOut>", lambda ev, kk=k, vv=v: self._set(mv, kk, vv.get().strip() or None))
        ttk.Label(g, text="Tên phím theo pyautogui: left, right, a, d, space...",
                  foreground="gray").grid(row=6, column=0, columnspan=2, sticky="w")

    def _set(self, d, k, v):
        d[k] = v
        self.save()

    def find_window(self):
        self.cfg["window_title"] = self.title_var.get().strip()
        self.save()
        self.bot.reload()
        if self.bot.attach(focus=True):
            self.bot.ensure_size()
            o = self.bot.win.offset
            self.log(f"Đã thấy cửa sổ game: {o[2]}x{o[3]} tại ({o[0]},{o[1]})")
        else:
            names = [n for _, n in B.GameWindow.list_windows()]
            self.log("Không thấy. Các cửa sổ đang mở:\n  " + "\n  ".join(names[:25]))

    def pick_board(self):
        r = self.pick_rect_client("Kéo từ GÓC TRÊN-TRÁI ô đầu tiên tới GÓC DƯỚI-PHẢI ô cuối của bàn cờ 8x8")
        if r:
            self.cfg["board"]["top_left"], self.cfg["board"]["bottom_right"] = r[:2], r[2:]
            self.save()
            self.calibrate_board(quiet=True)
        self.refresh_settings()

    def calibrate_board(self, quiet=False):
        """Căn lưới 8x8 theo vị trí thật của các viên rồi lưu vào config (cần đang trong trận)."""
        self.bot.reload()
        self.bot.attach()
        s = self.bot.win.grab()
        prob = self.bot.board_problem(s)
        if prob:
            self.log(prob)
            return
        old = [list(self.cfg["board"]["top_left"]), list(self.cfg["board"]["bottom_right"])]
        r = self.bot.calibrate_board(s)
        if not r:
            if not quiet:
                self.log("Không tự căn được lưới: cần đang trong trận và đã lấy mẫu đủ các viên")
            return
        self.cfg["board"]["top_left"], self.cfg["board"]["bottom_right"] = list(r[0]), list(r[1])
        self.save()
        self.log(f"Đã căn lưới bàn cờ: {old[0]}-{old[1]} -> {list(r[0])}-{list(r[1])}")
        grid = self.bot.read_board(s)
        path = self.bot.save_board_debug(s, grid, "can_luoi") if grid else None
        if path:
            self.log(f"Ảnh kiểm tra: {os.path.relpath(path, B.BASE)}")
        self.refresh_settings()

    def pick_gems(self, names=None):
        b = self.cfg["board"]
        if b["bottom_right"][0] <= b["top_left"][0]:
            messagebox.showinfo("", "Chọn vùng bàn cờ trước.")
            return
        names = names or self.cfg["gems"]
        self.bot.reload()
        self.bot.attach()
        img = self.picker.shot()
        rects = self.bot.cell_rects()
        R, C = b["rows"], b["cols"]
        (x1, y1), (x2, y2) = b["top_left"], b["bottom_right"]
        for n in names:
            p = self.picker.ask(img, f"Bấm vào một viên: {GEM_LABELS.get(n, n).upper()}", mode="point")
            if not p:
                continue
            cx, cy = self.bot.win.to_client(*p)
            c = int((cx - x1) / ((x2 - x1) / C))
            r = int((cy - y1) / ((y2 - y1) / R))
            if not (0 <= r < R and 0 <= c < C):
                self.log("Điểm bấm nằm ngoài bàn cờ, bỏ qua")
                continue
            x, y, w, h = rects[r][c]
            m = 0.15
            sx, sy = self.bot.win.to_screen(x + w * m, y + h * m)
            ex, ey = self.bot.win.to_screen(x + w * (1 - m), y + h * (1 - m))
            os.makedirs(os.path.join(B.TPL, "gems"), exist_ok=True)
            img.crop((sx, sy, ex, ey)).save(os.path.join(B.TPL, "gems", n + ".png"))
            self.log(f"Đã lấy mẫu viên {GEM_LABELS.get(n, n)}")
        self.picker.done()
        self.refresh_settings()

    def pick_bar(self, key):
        what = "thanh MÁU (đỏ)" if key == "hp_bar" else "thanh NỘI LỰC"
        r = self.pick_rect_client(f"Kéo chọn phần BÊN TRONG {what} của bạn, từ đầu trái tới hết bên phải")
        if r:
            self.cfg[key] = r
            self.save()
        self.refresh_settings()

    def capture_ui(self, fn, desc):
        self.capture(f"ui/{fn}", f"Kéo chọn sát: {desc}")
        self.refresh_settings()

    def test_board(self):
        self.bot.reload()
        self.bot.attach()
        s = self.bot.win.grab()
        grid = self.bot.read_board(s)
        if grid is None:
            self.log(self.bot.board_problem(s) or "Chưa lấy mẫu các viên")
            return
        short = {g: g[:3] for g in self.cfg["gems"]}
        lines = [" ".join((short.get(v, "?") if v else " ? ").ljust(3) for v in row) for row in grid]
        self.log("Bàn cờ nhận diện:\n" + "\n".join(lines))
        path = self.bot.save_board_debug(s, grid, "kiem_tra")
        if path:
            self.log(f"Ảnh kiểm tra (tên viên bot đọc được trên từng ô): {os.path.relpath(path, B.BASE)}")
        unk = sum(v is None for row in grid for v in row)
        if unk:
            self.log(f"[!] {unk} ô không nhận ra (ô đặc biệt hoặc cần lấy mẫu lại)")
        mv, sc, plan = B.best_move(grid, self.cfg.get("gem_priority", {}), self.cfg.get("extra_turn_len", 4),
                                   special=B.special_bonus(self.cfg, self.bot.board_special),
                                   depth=self.cfg.get("search_depth", 3), with_plan=True)
        if self.bot.board_special:
            self.log("Viên đặc biệt: " + ", ".join(f"{n} ở hàng {r + 1} cột {c + 1}"
                                                  for (r, c), n in self.bot.board_special.items()))
        self.log(f"Nước đi gợi ý: {mv} (điểm {sc:.0f})")
        if len(plan) > 1:
            self.log("Tính trước: " + B.plan_text(plan))
        hp = self.bot.hp_fill(s)
        en = self.bot.bar_fill(s, self.cfg.get("energy_bar"), self.cfg.get("energy_color", "green"))
        self.log(f"HP ~ {hp * 100:.0f}%" if hp is not None else "HP: chưa chọn thanh máu")
        self.log(f"Nội lực ~ {en * 100:.0f}%" if en is not None else "Nội lực: chưa chọn thanh")
        self.log("Đang trong trận: " + ("có" if self.bot.in_battle(s) else "không (thiếu mẫu 'Đầu hàng'?)"))

    # ---------------------------------------------------------- vòng cập nhật
    def poll(self):
        try:
            while True:
                kind, m = self.q.get_nowait()
                if kind == "log":
                    self.log(m)
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
        except queue.Empty:
            pass
        st = self.bot.stats
        if st["start"] and self.bot.thread and self.bot.thread.is_alive():
            sec = int(time.time() - st["start"])
            self.stat_var.set(f"Đã chạy: {sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d} | "
                              f"Trận: {st['battles']} (thắng {st['wins']} / thua {st['losses']})")
        self.root.after(300, self.poll)

    def on_close(self):
        self.bot.stop()
        try:
            self.collect_auto()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def P_ui(fn):
    return os.path.join(B.TPL, "ui", fn)


if __name__ == "__main__":
    App().run()
