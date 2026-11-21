# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows-only desktop automation bot for the PC game "Cờ Lau Loạn Thế" (a match-3 RPG). It walks the map, finds selected monsters by OCR-reading their name labels, enters battle, and plays the 8x8 match-3 board. PvE only. All user-facing text (UI labels, log messages, `HUONG_DAN.md`) is Vietnamese; keep new strings in Vietnamese to match.

## Running

```powershell
pip install pyautogui opencv-python numpy pillow pytesseract
```

```powershell
python app.py
```

`chay.bat` does the same (double-click launcher; may need "Run as administrator" for clicks to reach the game). Tesseract-OCR must also be installed separately with the Vietnamese language pack (default path `C:\Program Files\Tesseract-OCR\tesseract.exe`, set via `tesseract_path` in config).

There is no test suite, linter config, build step, or git repo. The pure match-3 solver in `bot.py` (`find_matches`, `simulate`, `best_move`) has no game/GUI dependencies and can be exercised directly, e.g.:

```powershell
python -c "import bot; g=[['dao','tim','dao','dao']]*4; print(bot.best_move(g))"
```

Anything else needs the live game window. The GUI's "Kiểm tra bàn cờ" and "Quét màn hình" / "Kiểm tra đọc chữ" buttons are the in-app diagnostics for board recognition and OCR.

## Architecture

Two files:

- **`bot.py`** — all logic, no Tk. Layers, top to bottom:
  - `GameWindow`: finds the game window by title substring via Win32 `ctypes` (`EnumWindows`), records the client-area offset/size, grabs screenshots of just that region, converts client↔screen coords, and can resize the window back to a saved client size.
  - `Templates`: loads PNGs from `templates/` (cached by mtime, so recaptured images take effect without restart) and does `cv2.matchTemplate` lookups.
  - `OCR`: thresholds near-white low-saturation pixels, upscales by `ocr_scale`, runs Tesseract `--psm 11`, and returns word boxes. `find_name` groups adjacent words on a line and fuzzy-matches against a target using accent-stripped text (`norm_text`) + `difflib` ratio ≥ `name_match`.
  - Match-3 solver: `find_matches` → `clusters` (L/T shapes counted as one cluster) → `collapse` → `simulate` (cascades; newly dropped cells are unknown/`None`). `best_move` tries every adjacent swap, adds a bonus for runs ≥ `extra_turn_len` (extra turn), and otherwise subtracts `look_ahead × best opponent reply`.
  - `Bot`: the state machine run on a daemon thread. `loop()` each tick: re-attach + `ensure_size()` → if the "Đầu hàng" template is visible, `battle_turn()`; else if the "Đóng" result popup is visible, record win/loss (via `thua.png`) and close it; else check stop conditions, then `engage()`: find the nearest target relative to the player's own name label (rendered cyan, not white, so the OCR mask includes cyan), then walk in short key-press steps (`key_left/right`, `key_up/down` when vertically misaligned), re-reading positions after each step, and press the attack button when within `attack_range_px`. If the player's name isn't found, it falls back to clicking the monster.
- **`app.py`** — Tkinter control panel ("Tự động" and "Cài đặt" tabs). Talks to `Bot` directly; the bot logs through a `queue.Queue` polled by `App.poll()` so worker-thread output lands on the Tk thread. `Picker` freezes a full-screen screenshot for the user to drag a rectangle / click a point; results are converted to client coords and saved to `config.json` or cropped into `templates/`.

### Key conventions

- **All coordinates in `config.json` are client-area coordinates of the game window**, not screen coordinates. Convert with `GameWindow.to_screen` / `to_client`. Templates and regions are only valid at the window size recorded in `window_size`; `ensure_size()` forcibly resizes the game back to it. The process is made DPI-aware (`set_dpi_aware`) before anything else so screenshot pixels match Win32 coords.
- **Stopping**: `Bot.sleep()` polls `stop_event` and raises `StopIteration`, which `start()`'s thread wrapper catches. Use `self.sleep` (not `time.sleep`) in any new wait inside the loop so the Stop button stays responsive. `pyautogui.FAILSAFE` (mouse to top-left corner) is the emergency stop.
- **Image I/O**: use `bot.imread` / `bot.imwrite` (via `np.fromfile` + `imdecode`), because `cv2.imread` fails on Windows paths containing Vietnamese characters.
- `config.json` and `maps.json` are rewritten by the GUI on most edits (`App.save()`), with `ensure_ascii=False`. `Bot.reload()` re-reads both at the start of each run.
- Board reading (`read_board`) scores each cell as 0.5 × template match + 0.5 × HSV hue/sat histogram correlation, and returns `None` (never matched) for near-empty cells or when the top two gem scores are within `gem_margin`. `calibrate_board` snaps the 8×8 grid to the real gem centers found by template matching; the user-dragged region is only a rough hint. It runs in memory on the first battle turn of each run, and is saved via the "Tự căn lưới" button. A move the game rejects (board unchanged ~1 s later) is excluded for that board state, and an annotated image is written to `debug/`.
- Special gems (`DEFAULT_GEM_ALIAS` / `gem_alias` in config, e.g. `kiem_do` → `kiem`) have their own template but are stored in the grid as their base type so they match with normal gems. Their positions go in `Bot.board_special`, and clearing one in the first match step adds its `gem_priority` value (default 30) via the `special` arg of `simulate`/`best_move`.
- `gem_priority` values are additive per-gem points in `simulate` (higher = preferred), not a rank order.
- Template files under `templates/ui/`, `templates/gems/`, `templates/skills/` are user captures. Required UI templates are `dau_hang.png`, `dong.png`, `nut_danh.png` (see `UI_TEMPLATES` in `app.py`); `thua.png`, `dung.png`, etc. are optional and code must tolerate them missing (`Templates.find` returns `None`).
- Tunables read with `cfg.get(key, default)` that aren't in the shipped `config.json` (e.g. `ocr_white_v`, `ocr_white_s`) are documented in `HUONG_DAN.md` under OCR troubleshooting.
