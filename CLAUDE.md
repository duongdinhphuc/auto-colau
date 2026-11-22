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
  - Match-3 solver: `find_matches` → `clusters` (L/T shapes counted as one cluster) → `collapse` → `simulate` (cascades; newly dropped cells are unknown/`None`). `best_move` searches `search_depth` plies ahead (config, default 3; Settings spinbox 1–4): `valid_moves` (fast local match check) → `_play` → `_search`, a minimax where a run ≥ `extra_turn_len` keeps the turn (plus `extra_bonus`), opponent gains count `look_ahead` (0.5)×, each deeper ply is multiplied by `discount` (0.8), and deeper plies only expand the top `beam` (6) moves. Deeper plies only see known gems (dropped cells are `None`). Depth 3 is ~50 ms avg / ~160 ms max per board; depth 4 ~200 / ~700 ms. `with_plan=True` returns the predicted line, logged via `plan_text`. On top of that, `TIER_BONUS` makes the ranking lexicographic by the biggest cluster the swap itself clears: 5+ beats 4 beats 3 regardless of gem type; `gem_priority` only decides within a tier (user's wish).
  - `Bot`: the state machine run on a daemon thread. `loop()` each tick: re-attach + `ensure_size()` → if the "Đầu hàng" template is visible, `battle_turn()`; else if the "Đóng" result popup is visible, record win/loss (via `thua.png`) and close it; else check stop conditions, then `engage()`: find the nearest target relative to the player's own name label (rendered cyan, not white, so the OCR mask includes cyan), then walk in short key-press steps (`key_left/right`, `key_up/down` when vertically misaligned), re-reading positions after each step, and press the attack button when within `attack_range_px`. `player_pos` tries OCR first, then a name merged with a neighbour's (substring), then `cyan_name_pos` (the player's name is the only cyan label; picks a cyan text blob of the right width), then `recent_player_pos` (last seen within 4 s). Only if all fail does it fall back to clicking the monster.
- **`app.py`** — Tkinter control panel ("Tự động" and "Cài đặt" tabs). Talks to `Bot` directly; the bot logs through a `queue.Queue` polled by `App.poll()` so worker-thread output lands on the Tk thread. `Picker` freezes a full-screen screenshot for the user to drag a rectangle / click a point; results are converted to client coords and saved to `config.json` or cropped into `templates/`.

### Key conventions

- **All coordinates in `config.json` are client-area coordinates of the game window**, not screen coordinates. Convert with `GameWindow.to_screen` / `to_client`. Templates and regions are only valid at the window size recorded in `window_size`; `ensure_size()` forcibly resizes the game back to it. The process is made DPI-aware (`set_dpi_aware`) before anything else so screenshot pixels match Win32 coords.
- **Stopping**: `Bot.sleep()` polls `stop_event` and raises `StopIteration`, which `start()`'s thread wrapper catches. Use `self.sleep` (not `time.sleep`) in any new wait inside the loop so the Stop button stays responsive. `pyautogui.FAILSAFE` (mouse to top-left corner) is the emergency stop.
- **Keyboard input**: the game is a GLFW window (`GLFW30`), which maps keys by scancode. `pyautogui.keyDown/press` sends scancode 0, so arrow keys arrive as numpad keys and the character doesn't move. Always use `bot.key_down` / `key_up` / `key_press` (SendInput with scancode + EXTENDED flag). Mouse clicks via pyautogui are fine. The camera follows the player, so the player's screen position barely changes while walking — detect movement via the distance to the target, not the player's position.
- **Image I/O**: use `bot.imread` / `bot.imwrite` (via `np.fromfile` + `imdecode`), because `cv2.imread` fails on Windows paths containing Vietnamese characters.
- `config.json` and `maps.json` are rewritten by the GUI on most edits (`App.save()`), with `ensure_ascii=False`. `Bot.reload()` re-reads both at the start of each run.
- Board reading (`read_board`) scores each cell as 0.5 × template match + 0.5 × HSV hue/sat histogram correlation, and returns `None` (never matched) for near-empty cells or when the top two gem scores are within `gem_margin`. `calibrate_board` snaps the 8×8 grid to the real gem centers found by template matching; the user-dragged region is only a rough hint. It runs in memory on the first battle turn of each run, and is saved via the "Tự căn lưới" button. A move the game rejects (board unchanged ~1 s later) is excluded for that board state, and an annotated image is written to `debug/`.
- Before each move, `stable_screen` requires the board to be still twice in a row, measured per cell (`board_motion`: max per-cell diff < `still_cell_diff`, default 20; a passing mouse cursor is ~7–13, a falling/swapping gem 50+). A whole-board mean dilutes 3–4 falling gems and made the bot move mid-refill, missing 4/5 moves among unknown cells. `battle_turn` also waits up to `wait_unknown_s` (2 s) while any cell is still unread, and logs each move's size plus how many 4+ moves the board had (`move_sizes`). After a move the cursor is parked below the board.
- Turn timer: the game gives `turn_limit_s` (default 30, Settings spinbox) per move or the turn is lost. `turn_clock()` measures from when `luot_doi_thu.png` disappears (reset on the banner, after each accepted move, and when ticks pause > 5 s). Past 50% it stops waiting (`stable_screen(4)`, no `wait_unknown_s`, shorter sleeps); past 75% it grabs the screen without a stability check, accepts boards ≥ 50% read, and if no sure move exists tries a swap of an unread cell with a known neighbour.
- Low HP (< `potion_hp`): `battle_turn` computes the move first. If any move clears 4+ or clears a sword (`urgent_moves`, `URGENT_GEMS`; red sword counts as sword), it plays the best such move (and skips the skill that turn); only when none exists does it open the bag and press Enter for a potion (user's rule). The same rule gates the skill: when energy is ready but such a move exists, it plays the move instead and casts later (`pick_urgent` inside `battle_turn`).
- Special gems (`DEFAULT_GEM_ALIAS` / `gem_alias` in config, e.g. `kiem_do` → `kiem`) have their own template but are stored in the grid as their base type so they match with normal gems. Their positions go in `Bot.board_special`, and clearing one in the first match step adds its `gem_priority` value (default 30) via the `special` arg of `simulate`/`best_move`.
- `bar_fill` measures the contiguous coloured run from the left of the bar (tolerating ≤5 px divider gaps), not the rightmost coloured column — the energy bar's right frame is blue and would always read ~97%. The energy bar has 4 segments; a skill needs only the first one, so the skill threshold is `energy_need` (default 0.26 of the `energy_bar` rect, editable in Settings); the old `energy_full` key is unused.
- `gem_priority` values are additive per-gem points in `simulate` (higher = preferred), not a rank order.
- Round buttons sit on backgrounds that change per map and day/night (`nut_danh` scored 0.41 on another map, `dau_hang` 0.79 on the daytime battle background, so `in_battle` failed). `TEMPLATE_BOX` makes `Templates.find` compare only the inside of the circle (fractions of the template; also overridable with `box=`). `press_attack` logs when the button isn't found.
- The game switches between a day and a night theme by real-world time, so every detection must work on both. Background-independent tricks in use: `TEMPLATE_BOX` (round buttons), `TEMPLATE_COLOR` + `color_key` (text drawn over the board: `luot_doi_thu.png` is matched as a red-text binary image, ~0.87 when present vs ≤ 0.4 otherwise; the raw template never passed 0.76 because the gems behind the text change; threshold `opponent_threshold` 0.6), `hp_fill` (OCRs the "349/543" text on the HP bar; colour measuring stops at the white digits and capped at ~33%, falling back to `bar_fill` only if OCR fails), and the strict `cyan_mask`. Verification footage: night recordings from 2026-11-21 and day recordings `20261122-0212*` (map) / `20261122-0227*` (battle) in the ScreenSketch Recordings folder.
- Every map has its own ladder style (wooden in Trại Vân Sơn, rope in Hồng Giang), so ladder templates are per map: `Bot.ladder_tpl(map)` uses `maps.json[map]["ladder"]`, else `templates/ladders/<slug(map)>.png` if present, else `ui/thang.png`. The "Chụp thang" button on the Tự động tab captures one for the selected map. One capture works for both themes (rope ladder: ≥ 0.8 with a ladder on screen, ~0.3 without). `templates/ladders/hong_giang.png` was cropped from a day recording.
- Hearts (`tim`) have a near-zero colour-histogram score (pink sits on the hue wraparound; bright sky shows through the cells by day), so they often fell below `gem_threshold`. `read_board` also accepts a cell when its best shape match is ≥ `gem_shape_sure` (0.85) and beats the next different kind by ≥ `gem_shape_margin` (0.2). On 88 night frames this only added 44 heart reads and changed nothing else.
- Template files under `templates/ui/`, `templates/gems/`, `templates/skills/` are user captures. Required UI templates are `dau_hang.png`, `dong.png`, `nut_danh.png` (see `UI_TEMPLATES` in `app.py`); `thua.png`, `dung.png`, etc. are optional and code must tolerate them missing (`Templates.find` returns `None`).
- Hồng Giang has day/night: the daytime sky is pale cyan (H≈90, S 68–100), which the old cyan mask (S>60, V>130) swallowed whole, so the player name was never found. `cyan_mask` (shared by OCR and `cyan_name_pos`) now needs S>140, V>170 (`ocr_cyan_s`/`ocr_cyan_v`); on 93 sampled day+night frames the player was found correctly in all of them (was 10/31 wrong by day). `pick_me` rejects player candidates in the top/bottom UI bands or > 250 px from the last position (camera follows the player).
- Walking: `nearest_target` always prefers same-level monsters (+1000 penalty for other floors) and, given `prefer` (last relative offset + name), keeps chasing the same monster instead of switching to a nearer one each step. `engage` tolerates `max_misses` (2) OCR misses by walking toward the last seen offset before giving up.
- Tunables read with `cfg.get(key, default)` that aren't in the shipped `config.json` (e.g. `ocr_white_v`, `ocr_white_s`) are documented in `HUONG_DAN.md` under OCR troubleshooting.
