"""
Stealth desktop automation — opens Windsurf, creates random scripts,
types them with human-like keystrokes and natural mouse movement.
Loops forever with different code each time. Ctrl+C to stop.

Usage:
    source venv/bin/activate
    python stealth_coder.py

NOTE: Grant Accessibility permissions to Terminal / iTerm in
      System Settings → Privacy & Security → Accessibility
"""

import json
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime

import Quartz
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventCreateMouseEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGEventScrollWheel,
    kCGHIDEventTap,
    kCGEventFlagMaskShift,
    CGEventCreateScrollWheelEvent,
    kCGScrollEventUnitLine,
)

# Strip automation-related env vars
for _env_key in list(os.environ):
    if any(kw in _env_key.upper() for kw in ("AUTOMATE", "SELENIUM", "PUPPET", "PLAYWRIGHT", "WEBDRIVER", "BOT")):
        del os.environ[_env_key]


# ── Config ──────────────────────────────────────────────────────────────────

WINDSURF_APP = "Windsurf"
WORKSPACE_DIR = os.path.expanduser("~/Desktop/work-mate/scratch")

PAUSE_BETWEEN_MIN = 5
PAUSE_BETWEEN_MAX = 15

SCREEN_W = 0
SCREEN_H = 0
LOGS_DIR = os.path.expanduser("~/Desktop/work-mate/logs")


# ── Action Logger ───────────────────────────────────────────────────────────

class ActionLogger:
    """Records every input event with timestamps for post-run analysis."""

    def __init__(self):
        self.session_start = time.time()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.events = []
        self.stats = {
            "keys_pressed": 0,
            "mouse_moves": 0,
            "mouse_clicks": 0,
            "scrolls": 0,
            "typos_simulated": 0,
            "thinking_pauses": 0,
            "files_typed": [],
            "total_chars_typed": 0,
            "focus_lost_count": 0,
            "ai_chats": 0,
        }
        self._last_mouse_log = 0  # throttle mouse move logs

    def _ts(self):
        return round(time.time() - self.session_start, 4)

    def log_key(self, char, shift=False, special=None):
        self.stats["keys_pressed"] += 1
        self.stats["total_chars_typed"] += 1
        self.events.append({
            "t": self._ts(),
            "type": "key",
            "char": special or char,
            "shift": shift,
        })

    def log_cmd(self, key, method="applescript"):
        self.events.append({
            "t": self._ts(),
            "type": "cmd_key",
            "key": key,
            "method": method,
        })

    def log_mouse_move(self, x, y):
        self.stats["mouse_moves"] += 1
        # Throttle: log every 20ms (still manageable, but captures enough for analysis)
        now = time.time()
        if now - self._last_mouse_log < 0.02:
            return
        self._last_mouse_log = now
        self.events.append({
            "t": self._ts(),
            "type": "mouse_move",
            "x": round(x, 1),
            "y": round(y, 1),
        })

    def log_click(self, x, y, hold_ms):
        self.stats["mouse_clicks"] += 1
        self.events.append({
            "t": self._ts(),
            "type": "click",
            "x": round(x, 1),
            "y": round(y, 1),
            "hold_ms": round(hold_ms, 1),
        })

    def log_scroll(self, amount):
        self.stats["scrolls"] += 1
        self.events.append({
            "t": self._ts(),
            "type": "scroll",
            "amount": amount,
        })

    def log_typo(self, intended, typed):
        self.stats["typos_simulated"] += 1
        self.events.append({
            "t": self._ts(),
            "type": "typo",
            "intended": intended,
            "typed": typed,
        })

    def log_pause(self, kind, duration):
        if kind == "thinking":
            self.stats["thinking_pauses"] += 1
        self.events.append({
            "t": self._ts(),
            "type": "pause",
            "kind": kind,
            "duration_s": round(duration, 3),
        })

    def log_action(self, action, detail=""):
        if action == "focus_lost":
            self.stats["focus_lost_count"] += 1
        if action == "ai_chat":
            self.stats["ai_chats"] += 1
        self.events.append({
            "t": self._ts(),
            "type": "action",
            "action": action,
            "detail": detail,
        })

    def log_iteration(self, num, filename, code_len):
        self.stats["files_typed"].append(filename)
        self.events.append({
            "t": self._ts(),
            "type": "iteration_start",
            "iteration": num,
            "filename": filename,
            "code_length": code_len,
        })

    def save(self):
        """Save the full log to a JSON file."""
        os.makedirs(LOGS_DIR, exist_ok=True)
        duration = time.time() - self.session_start
        self.stats["session_duration_s"] = round(duration, 2)
        self.stats["session_duration_human"] = _fmt_duration(duration)
        self.stats["avg_keys_per_sec"] = round(
            self.stats["keys_pressed"] / max(duration, 1), 2
        )

        log_data = {
            "session_id": self.session_id,
            "started_at": datetime.fromtimestamp(self.session_start).isoformat(),
            "ended_at": datetime.now().isoformat(),
            "summary": self.stats,
            "events": self.events,
        }

        filepath = os.path.join(LOGS_DIR, f"session_{self.session_id}.json")
        with open(filepath, "w") as f:
            json.dump(log_data, f, indent=2)

        # Also write a human-readable summary
        summary_path = os.path.join(LOGS_DIR, f"session_{self.session_id}_summary.txt")
        with open(summary_path, "w") as f:
            f.write(f"Session: {self.session_id}\n")
            f.write(f"Duration: {self.stats['session_duration_human']}\n")
            f.write(f"Keys pressed: {self.stats['keys_pressed']}\n")
            f.write(f"Chars typed: {self.stats['total_chars_typed']}\n")
            f.write(f"Avg keys/sec: {self.stats['avg_keys_per_sec']}\n")
            f.write(f"Mouse moves: {self.stats['mouse_moves']}\n")
            f.write(f"Mouse clicks: {self.stats['mouse_clicks']}\n")
            f.write(f"Scrolls: {self.stats['scrolls']}\n")
            f.write(f"Typos simulated: {self.stats['typos_simulated']}\n")
            f.write(f"Thinking pauses: {self.stats['thinking_pauses']}\n")
            f.write(f"Files typed: {', '.join(self.stats['files_typed'])}\n")
            f.write(f"\n--- Timing Analysis ---\n")
            key_events = [e for e in self.events if e["type"] == "key"]
            if len(key_events) >= 2:
                delays = [
                    key_events[i + 1]["t"] - key_events[i]["t"]
                    for i in range(len(key_events) - 1)
                ]
                import statistics
                f.write(f"Keystroke delays (seconds):\n")
                f.write(f"  Min:    {min(delays):.4f}\n")
                f.write(f"  Max:    {max(delays):.4f}\n")
                f.write(f"  Mean:   {statistics.mean(delays):.4f}\n")
                f.write(f"  Median: {statistics.median(delays):.4f}\n")
                f.write(f"  Stdev:  {statistics.stdev(delays):.4f}\n")

        print(f"[stealth] logs saved to:")
        print(f"  {filepath}")
        print(f"  {summary_path}")
        return filepath


def _fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


# Global logger instance
logger = ActionLogger()


# ── macOS keycode map ───────────────────────────────────────────────────────

KEYCODE_MAP = {
    'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14, 'f': 3, 'g': 5, 'h': 4,
    'i': 34, 'j': 38, 'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31, 'p': 35,
    'q': 12, 'r': 15, 's': 1, 't': 17, 'u': 32, 'v': 9, 'w': 13, 'x': 7,
    'y': 16, 'z': 6,
    '0': 29, '1': 18, '2': 19, '3': 20, '4': 21, '5': 23, '6': 22, '7': 26,
    '8': 28, '9': 25,
    ' ': 49, '\t': 48,
    '-': 27, '=': 24, '[': 33, ']': 30, '\\': 42, ';': 41, "'": 39,
    ',': 43, '.': 47, '/': 44, '`': 50,
    'enter': 36, 'return': 36, 'delete': 51, 'backspace': 51,
    'tab': 48, 'escape': 53,
    'up': 126, 'down': 125, 'left': 123, 'right': 124,
}

# Characters that require Shift + base key
SHIFT_MAP = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7',
    '*': '8', '(': '9', ')': '0', '_': '-', '+': '=', '{': '[', '}': ']',
    '|': '\\', ':': ';', '"': "'", '<': ',', '>': '.', '?': '/', '~': '`',
}


# ── Low-level keyboard/mouse via Quartz (no Python dock icon!) ──────────────

def press_key(keycode, shift=False, _log_char=None):
    """Press and release a key using CGEvents — doesn't steal focus."""
    event_down = CGEventCreateKeyboardEvent(None, keycode, True)
    event_up = CGEventCreateKeyboardEvent(None, keycode, False)
    if shift:
        CGEventSetFlags(event_down, kCGEventFlagMaskShift)
    CGEventSetFlags(event_up, 0)
    CGEventPost(kCGHIDEventTap, event_down)
    time.sleep(random.uniform(0.005, 0.025))
    CGEventPost(kCGHIDEventTap, event_up)
    time.sleep(random.uniform(0.004, 0.018))
    # Log
    if _log_char:
        logger.log_key(_log_char, shift=shift)
    else:
        # Reverse lookup keycode
        name = next((k for k, v in KEYCODE_MAP.items() if v == keycode), f"kc:{keycode}")
        logger.log_key(name, shift=shift, special=name if len(name) > 1 else None)


def cmd_key(keycode):
    """Cmd + key with proper modifier release."""
    # 0x100000 = kCGEventFlagMaskCommand
    event_down = CGEventCreateKeyboardEvent(None, keycode, True)
    event_up = CGEventCreateKeyboardEvent(None, keycode, False)
    CGEventSetFlags(event_down, 0x100000)
    CGEventSetFlags(event_up, 0)  # CLEAR flags on release!
    CGEventPost(kCGHIDEventTap, event_down)
    time.sleep(0.02)
    CGEventPost(kCGHIDEventTap, event_up)
    # Extra sleep to let OS process the key release before next action
    time.sleep(0.05)


def move_mouse(x, y):
    """Move mouse to (x, y) via CGEvent."""
    point = Quartz.CGPointMake(x, y)
    event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, 0)
    CGEventPost(kCGHIDEventTap, event)
    logger.log_mouse_move(x, y)


def click_mouse(x, y):
    """Click at (x, y) via CGEvent with Gaussian hold time."""
    point = Quartz.CGPointMake(x, y)
    down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0)
    up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0)
    CGEventPost(kCGHIDEventTap, down)
    # Very wide hold range — uniform not Gaussian for max variance
    hold = random.uniform(0.03, 0.25)
    time.sleep(hold)
    CGEventPost(kCGHIDEventTap, up)
    logger.log_click(x, y, hold * 1000)


def scroll_wheel(amount):
    """Scroll via CGEvent."""
    event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, amount)
    CGEventPost(kCGHIDEventTap, event)
    logger.log_scroll(amount)


def clipboard_paste(text):
    """Paste text via clipboard using AppleScript — avoids Cmd key issues."""
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True,
                   capture_output=True)
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to keystroke "v" using command down'
    ], capture_output=True)
    time.sleep(0.05)
    logger.log_cmd("v", method="clipboard_paste")
    logger.log_key(text, special="paste")


def dismiss_raycast():
    """If Raycast is open, press Escape to close it."""
    press_key(KEYCODE_MAP['escape'])
    time.sleep(0.1)


def type_char(ch):
    """Type a single character using native macOS keycodes."""
    lower = ch.lower()
    if lower in KEYCODE_MAP:
        need_shift = ch != lower and ch.isalpha()
        press_key(KEYCODE_MAP[lower], shift=need_shift)
    elif ch in SHIFT_MAP:
        base = SHIFT_MAP[ch]
        if base in KEYCODE_MAP:
            press_key(KEYCODE_MAP[base], shift=True)
    else:
        # Fallback: clipboard paste via AppleScript (no Cmd key CGEvent)
        clipboard_paste(ch)
        time.sleep(0.03)


# ── Focus management via AppleScript ────────────────────────────────────────

WINDSURF_BUNDLE_ID = "com.exafunction.windsurf"
WINDSURF_PROCESS = "Electron"  # Windsurf's actual process name
SCREENSHOTS_DIR = os.path.join(LOGS_DIR, "screenshots")


# ── Vision + Window Intelligence ────────────────────────────────────────────

class WindowManager:
    """Tracks Windsurf's window state, provides safe click regions,
    and captures screenshots on failure for debugging."""

    def __init__(self):
        self.win_x = 0
        self.win_y = 0
        self.win_w = SCREEN_W
        self.win_h = SCREEN_H
        self.last_bounds_check = 0
        self._update_bounds()

    # ── Window bounds ───────────────────────────────────────────

    def _update_bounds(self):
        """Query Windsurf's actual window position and size."""
        try:
            r = subprocess.run([
                "osascript", "-e",
                f'tell application "System Events" to tell process "{WINDSURF_PROCESS}" '
                f'to get {{position, size}} of front window'
            ], capture_output=True, text=True, timeout=3)
            # Output: "0, 33, 1512, 873"
            parts = [int(p.strip()) for p in r.stdout.strip().split(",")]
            if len(parts) == 4:
                self.win_x, self.win_y = parts[0], parts[1]
                self.win_w, self.win_h = parts[2], parts[3]
                self.last_bounds_check = time.time()
                return True
        except Exception:
            pass
        return False

    def get_bounds(self):
        """Return cached bounds, refresh if stale (>10s old)."""
        if time.time() - self.last_bounds_check > 10:
            self._update_bounds()
        return self.win_x, self.win_y, self.win_w, self.win_h

    # ── Safe click regions ──────────────────────────────────────

    def editor_region(self):
        """Return (x_min, y_min, x_max, y_max) of the editor pane.
        Editor: left side of window, after sidebar (~5%), before AI panel (~50%)."""
        x, y, w, h = self.get_bounds()
        return (
            x + int(w * 0.05),   # after sidebar
            y + 60,              # after title bar + tab bar
            x + int(w * 0.48),   # before AI panel
            y + h - 50,          # before status bar
        )

    def ai_panel_region(self):
        """Return (x_min, y_min, x_max, y_max) of the AI chat panel."""
        x, y, w, h = self.get_bounds()
        return (
            x + int(w * 0.50),
            y + 60,
            x + w - 10,
            y + h - 50,
        )

    def ai_input_region(self):
        """Return (x_min, y_min, x_max, y_max) of the AI chat input box."""
        x, y, w, h = self.get_bounds()
        return (
            x + int(w * 0.52),
            y + h - 80,
            x + w - 20,
            y + h - 30,
        )

    def safe_editor_click(self):
        """Return a random (x, y) inside the editor pane."""
        x1, y1, x2, y2 = self.editor_region()
        return (
            random.randint(x1 + 20, x2 - 20),
            random.randint(y1 + 20, y2 - 20),
        )

    def safe_ai_click(self):
        """Return a random (x, y) inside the AI panel."""
        x1, y1, x2, y2 = self.ai_panel_region()
        return (
            random.randint(x1 + 10, x2 - 10),
            random.randint(y1 + 10, y2 - 10),
        )

    def safe_ai_input_click(self):
        """Return a random (x, y) inside the AI chat input."""
        x1, y1, x2, y2 = self.ai_input_region()
        return (
            random.randint(x1 + 10, x2 - 10),
            random.randint(y1 + 5, y2 - 5),
        )

    def is_inside_window(self, px, py):
        """Check if a point is inside the Windsurf window."""
        x, y, w, h = self.get_bounds()
        return x <= px <= x + w and y <= py <= y + h

    # ── Screenshots ─────────────────────────────────────────────

    def capture_screenshot(self, reason="unknown"):
        """Take a screenshot for debugging. Returns the file path."""
        try:
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
            ts = datetime.now().strftime("%H%M%S")
            path = os.path.join(SCREENSHOTS_DIR, f"shot_{ts}_{reason}.png")
            subprocess.run(["screencapture", "-x", path],
                           capture_output=True, timeout=5)
            logger.log_action("screenshot", f"{reason}: {path}")
            return path
        except Exception:
            return None

    # ── Focus checks ────────────────────────────────────────────

    def get_frontmost_app(self):
        """Return (name, bundle_id) of the currently focused application."""
        name, bundle = "unknown", "unknown"
        try:
            r = subprocess.run([
                "osascript", "-e",
                'tell application "System Events" to get bundle identifier '
                'of first application process whose frontmost is true'
            ], capture_output=True, text=True, timeout=3)
            bundle = r.stdout.strip() or "unknown"
        except Exception:
            pass
        try:
            r = subprocess.run([
                "osascript", "-e",
                'tell application "System Events" to get name '
                'of first application process whose frontmost is true'
            ], capture_output=True, text=True, timeout=3)
            name = r.stdout.strip() or "unknown"
        except Exception:
            pass
        return name, bundle

    def is_windsurf_focused(self):
        """Check if Windsurf is the frontmost app."""
        try:
            name, bundle = self.get_frontmost_app()
            combined = (name + " " + bundle).lower()
            return "windsurf" in combined
        except Exception:
            return True

    def activate_windsurf(self):
        """Bring Windsurf to front."""
        try:
            subprocess.run([
                "osascript", "-e",
                f'tell application "{WINDSURF_APP}" to activate'
            ], capture_output=True, timeout=5)
            time.sleep(1.0)
            dismiss_raycast()
            time.sleep(0.3)
            self._update_bounds()
        except Exception as e:
            logger.log_action("activate_failed", str(e))

    def ensure_focus(self):
        """
        If Windsurf lost focus:
          1. Capture screenshot for debugging
          2. Wait up to 15s for natural recovery
          3. Force-activate if needed
          4. Click inside the ACTUAL editor region (window-aware)
        """
        if self.is_windsurf_focused():
            return True

        lost_name, lost_bundle = self.get_frontmost_app()
        logger.log_action("focus_lost", f"{lost_name} ({lost_bundle})")
        print(f"[stealth] focus lost → {lost_name} ({lost_bundle}), waiting 15s ...")
        self.capture_screenshot("focus_lost")

        # Wait up to 15s
        wait_start = time.time()
        while time.time() - wait_start < 15.0:
            time.sleep(gauss_clamp(2.0, 0.5, 1.5, 3.0))
            if self.is_windsurf_focused():
                dur = time.time() - wait_start
                logger.log_action("focus_recovered", f"after {dur:.1f}s")
                print(f"[stealth] Windsurf refocused after {dur:.1f}s")
                self._update_bounds()
                time.sleep(0.5)
                return True

        # Force restore
        logger.log_action("focus_force_restore", "after 15s timeout")
        print("[stealth] 15s timeout — forcing Windsurf to front")
        self.activate_windsurf()
        time.sleep(1.0)

        # Click inside the ACTUAL editor region
        ex, ey = self.safe_editor_click()
        click_mouse(ex, ey)
        time.sleep(0.5)

        # Cmd+End to go to end of file
        try:
            subprocess.run([
                "osascript", "-e",
                'tell application "System Events" to key code 119 using command down'
            ], capture_output=True, timeout=3)
            logger.log_cmd("end", method="applescript")
        except Exception:
            pass
        time.sleep(0.3)

        # Verify recovery
        if not self.is_windsurf_focused():
            self.capture_screenshot("focus_restore_failed")
            logger.log_action("focus_restore_failed")
            print("[stealth] WARNING: could not restore Windsurf focus")

        return self.is_windsurf_focused()


# Global window manager — initialized in run()
wm: WindowManager = None  # type: ignore


# ── Wrapper functions (backward compat) ─────────────────────────────────────

def activate_windsurf():
    if wm:
        wm.activate_windsurf()
    else:
        # Fallback before wm is initialized
        subprocess.run([
            "osascript", "-e",
            f'tell application "{WINDSURF_APP}" to activate'
        ], capture_output=True)
        time.sleep(1.0)
        dismiss_raycast()
        time.sleep(0.3)

def is_windsurf_focused():
    return wm.is_windsurf_focused() if wm else True

def ensure_windsurf_focus():
    return wm.ensure_focus() if wm else True


# ── Code templates ──────────────────────────────────────────────────────────

CODE_TEMPLATES = [
    # ══════════════════════════════════════════════════════════════
    # REALISTIC WORK TEMPLATES — Backend (Node/Express, FastAPI, Go)
    #                             Frontend (React, Next.js, Vue)
    # ══════════════════════════════════════════════════════════════

    # ── Express: User CRUD routes ──
    {
        "filename": "userRoutes.js",
        "code": """\
const express = require("express");
const router = express.Router();
const { authenticate } = require("../middleware/auth");
const UserService = require("../services/userService");

router.get("/api/users", authenticate, async (req, res) => {
  try {
    const { page = 1, limit = 20, search } = req.query;
    const users = await UserService.getUsers({
      page: parseInt(page),
      limit: parseInt(limit),
      search,
      orgId: req.user.orgId,
    });
    res.json({ success: true, data: users });
  } catch (err) {
    console.error("GET /api/users failed:", err.message);
    res.status(500).json({ success: false, error: "Failed to fetch users" });
  }
});

router.get("/api/users/:id", authenticate, async (req, res) => {
  try {
    const user = await UserService.getUserById(req.params.id);
    if (!user) {
      return res.status(404).json({ success: false, error: "User not found" });
    }
    res.json({ success: true, data: user });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

router.post("/api/users", authenticate, async (req, res) => {
  try {
    const { email, name, role } = req.body;
    if (!email || !name) {
      return res.status(400).json({ success: false, error: "Email and name required" });
    }
    const user = await UserService.createUser({ email, name, role, orgId: req.user.orgId });
    res.status(201).json({ success: true, data: user });
  } catch (err) {
    if (err.code === "DUPLICATE_EMAIL") {
      return res.status(409).json({ success: false, error: "Email already exists" });
    }
    res.status(500).json({ success: false, error: err.message });
  }
});

router.patch("/api/users/:id", authenticate, async (req, res) => {
  try {
    const updates = req.body;
    const user = await UserService.updateUser(req.params.id, updates);
    res.json({ success: true, data: user });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

router.delete("/api/users/:id", authenticate, async (req, res) => {
  try {
    await UserService.deleteUser(req.params.id);
    res.json({ success: true, message: "User deleted" });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;
""",
    },
    # ── Express: Auth middleware ──
    {
        "filename": "authMiddleware.js",
        "code": """\
const jwt = require("jsonwebtoken");
const { getRedisClient } = require("../config/redis");

const JWT_SECRET = process.env.JWT_SECRET || "dev-secret";
const TOKEN_EXPIRY = "24h";

async function authenticate(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return res.status(401).json({ error: "Missing authorization header" });
  }

  const token = authHeader.split(" ")[1];

  try {
    const redis = getRedisClient();
    const isBlacklisted = await redis.get(`blacklist:${token}`);
    if (isBlacklisted) {
      return res.status(401).json({ error: "Token has been revoked" });
    }

    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = {
      id: decoded.sub,
      email: decoded.email,
      role: decoded.role,
      orgId: decoded.orgId,
    };
    next();
  } catch (err) {
    if (err.name === "TokenExpiredError") {
      return res.status(401).json({ error: "Token expired" });
    }
    return res.status(401).json({ error: "Invalid token" });
  }
}

function authorize(...roles) {
  return (req, res, next) => {
    if (!req.user || !roles.includes(req.user.role)) {
      return res.status(403).json({ error: "Insufficient permissions" });
    }
    next();
  };
}

function generateToken(user) {
  return jwt.sign(
    { sub: user.id, email: user.email, role: user.role, orgId: user.orgId },
    JWT_SECRET,
    { expiresIn: TOKEN_EXPIRY }
  );
}

module.exports = { authenticate, authorize, generateToken };
""",
    },
    # ── FastAPI: Orders endpoint ──
    {
        "filename": "orders.py",
        "code": """\
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderResponse, OrderListResponse
from app.services.auth import get_current_user
from app.services.inventory import check_stock, reserve_items

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/", response_model=OrderListResponse)
async def list_orders(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(Order).filter(Order.org_id == user.org_id)

    if status:
        query = query.filter(Order.status == status)

    total = query.count()
    orders = query.offset((page - 1) * limit).limit(limit).all()

    return {"total": total, "page": page, "orders": orders}


@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    for item in payload.items:
        available = await check_stock(item.product_id, item.quantity)
        if not available:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for product {item.product_id}",
            )

    order = Order(
        customer_id=payload.customer_id,
        org_id=user.org_id,
        status="pending",
        total=sum(i.price * i.quantity for i in payload.items),
        created_by=user.id,
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        db_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price,
        )
        db.add(db_item)

    await reserve_items(order.id, payload.items)
    db.commit()
    db.refresh(order)

    return order


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.org_id == user.org_id,
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    status: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    valid_transitions = {
        "pending": ["confirmed", "cancelled"],
        "confirmed": ["shipped", "cancelled"],
        "shipped": ["delivered"],
    }

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    allowed = valid_transitions.get(order.status, [])
    if status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {order.status} to {status}",
        )

    order.status = status
    order.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "order_id": order.id, "status": order.status}
""",
    },
    # ── React: Dashboard page with data fetching ──
    {
        "filename": "DashboardPage.tsx",
        "code": """\
import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { StatsCard } from "@/components/StatsCard";
import { OrdersTable } from "@/components/OrdersTable";
import { RevenueChart } from "@/components/RevenueChart";
import { DateRangePicker } from "@/components/ui/DateRangePicker";

interface DashboardStats {
  totalRevenue: number;
  orderCount: number;
  avgOrderValue: number;
  activeCustomers: number;
}

export default function DashboardPage() {
  const [dateRange, setDateRange] = useState({
    from: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000),
    to: new Date(),
  });

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats", dateRange],
    queryFn: () =>
      api.get<DashboardStats>("/api/analytics/stats", {
        params: {
          from: dateRange.from.toISOString(),
          to: dateRange.to.toISOString(),
        },
      }),
  });

  const { data: recentOrders, isLoading: ordersLoading } = useQuery({
    queryKey: ["recent-orders"],
    queryFn: () => api.get("/api/orders?limit=10&sort=-createdAt"),
  });

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Total Revenue"
          value={stats?.totalRevenue}
          format="currency"
          loading={statsLoading}
        />
        <StatsCard
          title="Orders"
          value={stats?.orderCount}
          loading={statsLoading}
        />
        <StatsCard
          title="Avg Order Value"
          value={stats?.avgOrderValue}
          format="currency"
          loading={statsLoading}
        />
        <StatsCard
          title="Active Customers"
          value={stats?.activeCustomers}
          loading={statsLoading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <RevenueChart dateRange={dateRange} />
        </div>
        <div>
          <h2 className="text-lg font-medium mb-4">Recent Orders</h2>
          <OrdersTable
            orders={recentOrders?.data || []}
            loading={ordersLoading}
            compact
          />
        </div>
      </div>
    </div>
  );
}
""",
    },
    # ── React: Form with validation + API call ──
    {
        "filename": "CreateProductForm.tsx",
        "code": """\
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";

const productSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  sku: z.string().regex(/^[A-Z0-9-]+$/, "SKU must be uppercase alphanumeric"),
  price: z.number().min(0.01, "Price must be positive"),
  category: z.string().min(1, "Category is required"),
  description: z.string().max(500).optional(),
  stock: z.number().int().min(0).default(0),
});

type ProductFormData = z.infer<typeof productSchema>;

interface Props {
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function CreateProductForm({ onSuccess, onCancel }: Props) {
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<ProductFormData>({
    resolver: zodResolver(productSchema),
    defaultValues: { stock: 0 },
  });

  const mutation = useMutation({
    mutationFn: (data: ProductFormData) => api.post("/api/products", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast.success("Product created successfully");
      reset();
      onSuccess?.();
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.error || "Failed to create product");
    },
  });

  return (
    <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">Name</label>
        <input
          {...register("name")}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        {errors.name && <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">SKU</label>
          <input
            {...register("sku")}
            placeholder="PROD-001"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {errors.sku && <p className="mt-1 text-sm text-red-600">{errors.sku.message}</p>}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Price</label>
          <input
            type="number"
            step="0.01"
            {...register("price", { valueAsNumber: true })}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {errors.price && <p className="mt-1 text-sm text-red-600">{errors.price.message}</p>}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">Category</label>
        <select
          {...register("category")}
          className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2"
        >
          <option value="">Select category</option>
          <option value="electronics">Electronics</option>
          <option value="clothing">Clothing</option>
          <option value="food">Food & Beverage</option>
          <option value="other">Other</option>
        </select>
        {errors.category && <p className="mt-1 text-sm text-red-600">{errors.category.message}</p>}
      </div>

      <div className="flex justify-end gap-3 pt-4">
        <button type="button" onClick={onCancel} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
          Cancel
        </button>
        <button type="submit" disabled={mutation.isPending} className="px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50">
          {mutation.isPending ? "Creating..." : "Create Product"}
        </button>
      </div>
    </form>
  );
}
""",
    },
    # ── FastAPI: User service with DB ──
    {
        "filename": "userService.py",
        "code": """\
from sqlalchemy.orm import Session
from sqlalchemy import or_
from passlib.context import CryptContext
from datetime import datetime
from typing import Optional

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_users(self, org_id: int, page: int = 1, limit: int = 20, search: Optional[str] = None):
        query = self.db.query(User).filter(User.org_id == org_id, User.is_active == True)

        if search:
            query = query.filter(
                or_(
                    User.name.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                )
            )

        total = query.count()
        users = query.offset((page - 1) * limit).limit(limit).all()

        return {"total": total, "page": page, "users": users}

    def get_by_id(self, user_id: int):
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str):
        return self.db.query(User).filter(User.email == email).first()

    def create_user(self, data: UserCreate, org_id: int):
        existing = self.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=data.email,
            name=data.name,
            role=data.role or "member",
            org_id=org_id,
            password_hash=pwd_context.hash(data.password),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_user(self, user_id: int, data: UserUpdate):
        user = self.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        update_data = data.dict(exclude_unset=True)
        if "password" in update_data:
            update_data["password_hash"] = pwd_context.hash(update_data.pop("password"))

        for field, value in update_data.items():
            setattr(user, field, value)

        user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)
        return user

    def deactivate_user(self, user_id: int):
        user = self.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        user.is_active = False
        user.deactivated_at = datetime.utcnow()
        self.db.commit()
        return True

    def verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)
""",
    },
    # ── Next.js: API route handler ──
    {
        "filename": "apiProducts.ts",
        "code": """\
import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getServerSession } from "@/lib/auth";
import { z } from "zod";

const querySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  limit: z.coerce.number().int().min(1).max(100).default(20),
  category: z.string().optional(),
  search: z.string().optional(),
  sort: z.enum(["name", "price", "createdAt", "-name", "-price", "-createdAt"]).default("-createdAt"),
});

export async function GET(req: NextRequest) {
  const session = await getServerSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const params = Object.fromEntries(req.nextUrl.searchParams);
  const query = querySchema.parse(params);

  const where: any = { orgId: session.user.orgId };
  if (query.category) where.category = query.category;
  if (query.search) {
    where.OR = [
      { name: { contains: query.search, mode: "insensitive" } },
      { sku: { contains: query.search, mode: "insensitive" } },
    ];
  }

  const sortField = query.sort.startsWith("-") ? query.sort.slice(1) : query.sort;
  const sortDir = query.sort.startsWith("-") ? "desc" : "asc";

  const [products, total] = await Promise.all([
    prisma.product.findMany({
      where,
      orderBy: { [sortField]: sortDir },
      skip: (query.page - 1) * query.limit,
      take: query.limit,
      include: { category: true },
    }),
    prisma.product.count({ where }),
  ]);

  return NextResponse.json({
    data: products,
    pagination: {
      page: query.page,
      limit: query.limit,
      total,
      pages: Math.ceil(total / query.limit),
    },
  });
}

const createSchema = z.object({
  name: z.string().min(1),
  sku: z.string().min(1),
  price: z.number().positive(),
  categoryId: z.string().uuid(),
  description: z.string().optional(),
  stock: z.number().int().min(0).default(0),
});

export async function POST(req: NextRequest) {
  const session = await getServerSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const data = createSchema.parse(body);

  const existing = await prisma.product.findFirst({
    where: { sku: data.sku, orgId: session.user.orgId },
  });
  if (existing) {
    return NextResponse.json({ error: "SKU already exists" }, { status: 409 });
  }

  const product = await prisma.product.create({
    data: { ...data, orgId: session.user.orgId },
  });

  return NextResponse.json({ data: product }, { status: 201 });
}
""",
    },
    # ── React: Data table with sorting/filtering ──
    {
        "filename": "ProductsTable.tsx",
        "code": """\
import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { formatCurrency } from "@/lib/utils";

interface Product {
  id: string;
  name: string;
  sku: string;
  price: number;
  stock: number;
  category: { name: string };
  createdAt: string;
}

interface Props {
  onSelect?: (product: Product) => void;
}

export function ProductsTable({ onSelect }: Props) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("-createdAt");

  const { data, isLoading } = useQuery({
    queryKey: ["products", { search, page, sortBy }],
    queryFn: () =>
      api.get("/api/products", {
        params: { search, page, limit: 20, sort: sortBy },
      }),
    keepPreviousData: true,
  });

  const products = data?.data || [];
  const pagination = data?.pagination;

  const handleSort = (field: string) => {
    setSortBy((prev) =>
      prev === field ? `-${field}` : prev === `-${field}` ? field : field
    );
  };

  const stockBadge = (stock: number) => {
    if (stock === 0) return <Badge variant="destructive">Out of stock</Badge>;
    if (stock < 10) return <Badge variant="warning">Low stock</Badge>;
    return <Badge variant="success">In stock</Badge>;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Input
          placeholder="Search products..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="max-w-sm"
        />
        <span className="text-sm text-gray-500">
          {pagination?.total || 0} products
        </span>
      </div>

      <div className="border rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {["name", "sku", "price", "stock"].map((col) => (
                <th
                  key={col}
                  onClick={() => handleSort(col)}
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                >
                  {col}
                  {sortBy === col && " ↑"}
                  {sortBy === `-${col}` && " ↓"}
                </th>
              ))}
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Category
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {products.map((p: Product) => (
              <tr
                key={p.id}
                onClick={() => onSelect?.(p)}
                className="hover:bg-gray-50 cursor-pointer"
              >
                <td className="px-4 py-3 text-sm font-medium">{p.name}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{p.sku}</td>
                <td className="px-4 py-3 text-sm">{formatCurrency(p.price)}</td>
                <td className="px-4 py-3 text-sm">{stockBadge(p.stock)}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{p.category.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination && pagination.pages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 text-sm border rounded disabled:opacity-50"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-sm">
            Page {page} of {pagination.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pagination.pages, p + 1))}
            disabled={page === pagination.pages}
            className="px-3 py-1 text-sm border rounded disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
""",
    },
    # ── Go: HTTP handler ──
    {
        "filename": "handlers.go",
        "code": """\
package handlers

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"

	"github.com/gorilla/mux"
	"myapp/internal/models"
	"myapp/internal/services"
)

type OrderHandler struct {
	service *services.OrderService
}

func NewOrderHandler(svc *services.OrderService) *OrderHandler {
	return &OrderHandler{service: svc}
}

func (h *OrderHandler) ListOrders(w http.ResponseWriter, r *http.Request) {
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	if page < 1 {
		page = 1
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit < 1 || limit > 100 {
		limit = 20
	}
	status := r.URL.Query().Get("status")

	orders, total, err := h.service.ListOrders(r.Context(), page, limit, status)
	if err != nil {
		log.Printf("ListOrders error: %v", err)
		writeError(w, http.StatusInternalServerError, "Failed to fetch orders")
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"data":  orders,
		"total": total,
		"page":  page,
	})
}

func (h *OrderHandler) GetOrder(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(mux.Vars(r)["id"], 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "Invalid order ID")
		return
	}

	order, err := h.service.GetByID(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusNotFound, "Order not found")
		return
	}

	writeJSON(w, http.StatusOK, order)
}

func (h *OrderHandler) CreateOrder(w http.ResponseWriter, r *http.Request) {
	var req models.CreateOrderRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	if len(req.Items) == 0 {
		writeError(w, http.StatusBadRequest, "Order must have at least one item")
		return
	}

	order, err := h.service.CreateOrder(r.Context(), &req)
	if err != nil {
		log.Printf("CreateOrder error: %v", err)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, order)
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}
""",
    },
    # ── Django: Model + Manager ──
    {
        "filename": "models.py",
        "code": """\
from django.db import models
from django.utils import timezone


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Customer(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=255, blank=True)
    org = models.ForeignKey("Organization", on_delete=models.CASCADE, related_name="customers")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["org", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.email})"

    @property
    def order_count(self):
        return self.orders.count()

    @property
    def total_spent(self):
        return self.orders.filter(
            status="completed"
        ).aggregate(
            total=models.Sum("total")
        )["total"] or 0


class CustomerNote(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="customer_notes")
    content = models.TextField()
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note for {self.customer.name} at {self.created_at}"
""",
    },
    # ── Vue: Composable + Component ──
    {
        "filename": "useOrders.ts",
        "code": """\
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/lib/api";
import { useToast } from "@/composables/useToast";

interface Order {
  id: number;
  customerName: string;
  status: string;
  total: number;
  itemCount: number;
  createdAt: string;
}

interface OrderFilters {
  status?: string;
  search?: string;
  page: number;
  limit: number;
}

export function useOrders() {
  const route = useRoute();
  const router = useRouter();
  const toast = useToast();

  const orders = ref<Order[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const filters = ref<OrderFilters>({
    status: (route.query.status as string) || undefined,
    search: (route.query.search as string) || undefined,
    page: parseInt(route.query.page as string) || 1,
    limit: 20,
  });

  const totalPages = computed(() => Math.ceil(total.value / filters.value.limit));

  async function fetchOrders() {
    loading.value = true;
    error.value = null;

    try {
      const params = new URLSearchParams();
      params.set("page", String(filters.value.page));
      params.set("limit", String(filters.value.limit));
      if (filters.value.status) params.set("status", filters.value.status);
      if (filters.value.search) params.set("search", filters.value.search);

      const res = await api.get(`/api/orders?${params}`);
      orders.value = res.data.orders;
      total.value = res.data.total;
    } catch (err: any) {
      error.value = err.response?.data?.error || "Failed to load orders";
      toast.error(error.value);
    } finally {
      loading.value = false;
    }
  }

  async function updateStatus(orderId: number, status: string) {
    try {
      await api.patch(`/api/orders/${orderId}/status`, { status });
      toast.success("Order status updated");
      await fetchOrders();
    } catch (err: any) {
      toast.error(err.response?.data?.error || "Failed to update status");
    }
  }

  function setPage(page: number) {
    filters.value.page = page;
    router.push({ query: { ...route.query, page: String(page) } });
  }

  function setSearch(search: string) {
    filters.value.search = search || undefined;
    filters.value.page = 1;
  }

  watch(filters, fetchOrders, { deep: true, immediate: true });

  return {
    orders,
    total,
    totalPages,
    loading,
    error,
    filters,
    fetchOrders,
    updateStatus,
    setPage,
    setSearch,
  };
}
""",
    },
    # ── Express: Database migration ──
    {
        "filename": "migrationAddInvoices.js",
        "code": """\
exports.up = function (knex) {
  return knex.schema
    .createTable("invoices", (table) => {
      table.increments("id").primary();
      table.integer("order_id").unsigned().references("id").inTable("orders").onDelete("CASCADE");
      table.integer("customer_id").unsigned().references("id").inTable("customers");
      table.string("invoice_number").unique().notNullable();
      table.decimal("subtotal", 10, 2).notNullable();
      table.decimal("tax", 10, 2).defaultTo(0);
      table.decimal("total", 10, 2).notNullable();
      table.enum("status", ["draft", "sent", "paid", "overdue", "cancelled"]).defaultTo("draft");
      table.date("due_date");
      table.date("paid_date");
      table.text("notes");
      table.integer("created_by").unsigned().references("id").inTable("users");
      table.timestamps(true, true);
    })
    .createTable("invoice_items", (table) => {
      table.increments("id").primary();
      table.integer("invoice_id").unsigned().references("id").inTable("invoices").onDelete("CASCADE");
      table.string("description").notNullable();
      table.integer("quantity").notNullable();
      table.decimal("unit_price", 10, 2).notNullable();
      table.decimal("total", 10, 2).notNullable();
    })
    .then(() => {
      return knex.schema.alterTable("orders", (table) => {
        table.integer("invoice_id").unsigned().references("id").inTable("invoices");
      });
    });
};

exports.down = function (knex) {
  return knex.schema
    .alterTable("orders", (table) => {
      table.dropColumn("invoice_id");
    })
    .dropTableIfExists("invoice_items")
    .dropTableIfExists("invoices");
};
""",
    },
    # ── React: Custom hook for auth ──
    {
        "filename": "useAuth.ts",
        "code": """\
import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  orgId: string;
  avatarUrl?: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function useAuthProvider(): AuthContextType {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    isAuthenticated: false,
  });

  const refreshUser = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        setState({ user: null, loading: false, isAuthenticated: false });
        return;
      }

      api.defaults.headers.common.Authorization = `Bearer ${token}`;
      const { data } = await api.get("/api/auth/me");
      setState({ user: data.user, loading: false, isAuthenticated: true });
    } catch {
      localStorage.removeItem("token");
      setState({ user: null, loading: false, isAuthenticated: false });
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    const { data } = await api.post("/api/auth/login", { email, password });
    localStorage.setItem("token", data.token);
    api.defaults.headers.common.Authorization = `Bearer ${data.token}`;
    setState({ user: data.user, loading: false, isAuthenticated: true });
    router.push("/dashboard");
  };

  const logout = async () => {
    try {
      await api.post("/api/auth/logout");
    } finally {
      localStorage.removeItem("token");
      delete api.defaults.headers.common.Authorization;
      setState({ user: null, loading: false, isAuthenticated: false });
      router.push("/login");
    }
  };

  return { ...state, login, logout, refreshUser };
}

export { AuthContext };
""",
    },
]


# ── Human-like helpers ──────────────────────────────────────────────────────

def rand_int(lo, hi):
    return random.randint(lo, hi)


def gauss_clamp(mean, stdev, lo, hi):
    """Gaussian random clamped to [lo, hi]."""
    return max(lo, min(hi, random.gauss(mean, stdev)))


def human_sleep(lo_s, hi_s):
    """Sleep with Gaussian-weighted center bias."""
    mid = (lo_s + hi_s) / 2
    spread = (hi_s - lo_s) / 4
    time.sleep(gauss_clamp(mid, spread, lo_s, hi_s))


def bezier_points(x0, y0, x1, y1, steps):
    """
    Generate mouse path points using a randomly chosen curve type each time.
    No two movements ever use the same parameters — completely unpredictable.
    """
    curve_type = random.choice(["cubic", "cubic", "s_curve", "overshoot", "wobbly"])

    if curve_type == "cubic":
        # Standard Bezier with wildly varying control points
        off_x = random.gauss(0, 80)
        off_y = random.gauss(0, 60)
        t1 = random.uniform(0.15, 0.40)
        t2 = random.uniform(0.55, 0.85)
        cx1 = x0 + (x1 - x0) * t1 + off_x
        cy1 = y0 + (y1 - y0) * t1 + off_y
        cx2 = x0 + (x1 - x0) * t2 - off_x * random.uniform(0.2, 0.8)
        cy2 = y0 + (y1 - y0) * t2 - off_y * random.uniform(0.2, 0.8)

    elif curve_type == "s_curve":
        # S-shaped path — common in real hand movements
        perp_x = -(y1 - y0)
        perp_y = (x1 - x0)
        mag = max(1, math.sqrt(perp_x**2 + perp_y**2))
        perp_x, perp_y = perp_x / mag, perp_y / mag
        bulge = random.uniform(30, 120) * random.choice([-1, 1])
        cx1 = x0 + (x1 - x0) * 0.33 + perp_x * bulge
        cy1 = y0 + (y1 - y0) * 0.33 + perp_y * bulge
        cx2 = x0 + (x1 - x0) * 0.66 - perp_x * bulge
        cy2 = y0 + (y1 - y0) * 0.66 - perp_y * bulge

    elif curve_type == "overshoot":
        # Overshoots target then corrects — very human
        overshoot = random.uniform(1.05, 1.20)
        cx1 = x0 + (x1 - x0) * 0.4 + random.gauss(0, 40)
        cy1 = y0 + (y1 - y0) * 0.4 + random.gauss(0, 30)
        cx2 = x0 + (x1 - x0) * overshoot + random.gauss(0, 20)
        cy2 = y0 + (y1 - y0) * overshoot + random.gauss(0, 15)

    else:  # wobbly
        # Noisy path — like hand is slightly unsteady
        cx1 = x0 + (x1 - x0) * 0.3 + random.gauss(0, 100)
        cy1 = y0 + (y1 - y0) * 0.3 + random.gauss(0, 80)
        cx2 = x0 + (x1 - x0) * 0.7 + random.gauss(0, 100)
        cy2 = y0 + (y1 - y0) * 0.7 + random.gauss(0, 80)

    pts = []
    # Randomize jitter intensity per movement
    jitter = random.uniform(0.5, 2.5)
    for i in range(steps + 1):
        t = i / steps
        inv = 1 - t
        x = (inv**3 * x0
             + 3 * inv**2 * t * cx1
             + 3 * inv * t**2 * cx2
             + t**3 * x1)
        y = (inv**3 * y0
             + 3 * inv**2 * t * cy1
             + 3 * inv * t**2 * cy2
             + t**3 * y1)
        pts.append((
            x + random.gauss(0, jitter),
            y + random.gauss(0, jitter),
        ))
    return pts


# ── Natural mouse ───────────────────────────────────────────────────────────

class NaturalMouse:
    """Human-like mouse movement — every move uses different curve shapes,
    speeds, and step counts so no two movements are alike."""

    def __init__(self):
        self.x = 400.0
        self.y = 300.0

    def move_to(self, tx, ty):
        # Distance-aware step count — farther = more steps but randomized
        dist = math.sqrt((tx - self.x)**2 + (ty - self.y)**2)
        base_steps = max(15, int(dist / random.uniform(8, 20)))
        steps = base_steps + rand_int(-5, 10)
        steps = max(10, min(80, steps))

        pts = bezier_points(self.x, self.y, tx, ty, steps)

        # Variable speed profile: pick a random easing each time
        easing = random.choice(["ease_in_out", "ease_in", "ease_out", "linear"])

        for i, (px, py) in enumerate(pts):
            move_mouse(px, py)
            t = i / max(len(pts) - 1, 1)

            # Base delay varies per movement (some fast, some slow)
            base = random.uniform(0.002, 0.012)

            if easing == "ease_in_out":
                # Slow at start and end, fast in middle
                speed = 1.0 + 2.0 * (0.5 - abs(t - 0.5))
                delay = base / max(speed, 0.3)
            elif easing == "ease_in":
                # Starts slow, accelerates
                delay = base * (1.5 - t)
            elif easing == "ease_out":
                # Starts fast, decelerates
                delay = base * (0.5 + t)
            else:
                delay = base

            # Random micro-stutters (~3% chance)
            if random.random() < 0.03:
                delay += random.uniform(0.02, 0.06)

            time.sleep(max(0.001, delay))

        self.x, self.y = tx, ty

    def click_at(self, tx, ty):
        # Random offset from target — never click exactly on target
        ox = random.gauss(0, 2.5)
        oy = random.gauss(0, 2.5)
        self.move_to(tx + ox, ty + oy)
        # Vary pre-click pause
        time.sleep(random.uniform(0.04, 0.20))
        click_mouse(tx + ox, ty + oy)

    def idle_drift(self, count=3):
        """Drift within Windsurf — sometimes editor, sometimes AI panel."""
        for _ in range(count):
            if random.random() < 0.7:
                # Editor area (left side)
                x = rand_int(int(SCREEN_W * 0.08), int(SCREEN_W * 0.45))
            else:
                # AI panel area (right side)
                x = rand_int(int(SCREEN_W * 0.55), SCREEN_W - 50)
            y = rand_int(100, SCREEN_H - 200)
            self.move_to(x, y)
            # Highly variable pause — sometimes quick, sometimes lingers
            time.sleep(gauss_clamp(0.6, 0.3, 0.15, 1.5))

    def small_drift(self, count=2):
        """Fidget near current position."""
        for _ in range(count):
            dx = random.gauss(0, 50)
            dy = random.gauss(0, 40)
            nx = max(50, min(SCREEN_W - 50, self.x + dx))
            ny = max(50, min(SCREEN_H - 50, self.y + dy))
            self.move_to(nx, ny)
            time.sleep(gauss_clamp(0.35, 0.15, 0.1, 0.8))

    def rest_pause(self):
        """Occasionally just stop and do nothing — like looking at the screen."""
        if random.random() < 0.3:
            time.sleep(gauss_clamp(2.0, 1.0, 0.5, 5.0))


# ── Typing ──────────────────────────────────────────────────────────────────

def _cmd_key_native(key_char):
    """Send Cmd+key using pure CGEvent — no osascript, no subprocess.
    This is invisible to process monitors like Time Doctor."""
    keycode = KEYCODE_MAP.get(key_char)
    if keycode is not None:
        cmd_key(keycode)


def human_type_smart(text, mouse=None):
    """
    Type code CHARACTER BY CHARACTER with autocomplete disabled.
    Disables suggestions before typing, re-enables after.
    All interactions are cursor-safe (no clicks, no arrow keys).
    """
    total = len(text)

    # NOTE: Disable autocomplete/Prettier manually in Windsurf extensions
    # We don't modify settings.json — Time Doctor monitors file changes

    # Per-session personality
    base_wpm = random.uniform(35, 75)
    typo_rate = random.uniform(0.015, 0.04)
    think_rate = random.uniform(0.01, 0.04)
    burst_rate = random.uniform(0.03, 0.08)
    fatigue_drift = random.uniform(-0.0003, 0.0003)
    base_delay = 60.0 / (base_wpm * 5)

    recent_delays = []
    last_think_idx = -50

    try:
        for idx, ch in enumerate(text):
            # Focus check every ~50 chars
            if idx % 150 == 149:
                try:
                    if not is_windsurf_focused():
                        ensure_windsurf_focus()
                except Exception:
                    pass

            # Fatigue
            current_base = base_delay + fatigue_drift * idx
            progress = idx / max(total, 1)

            # Speed zone
            if progress < random.uniform(0.05, 0.15):
                zone_mult = random.uniform(1.1, 1.5)
            elif progress > random.uniform(0.85, 0.95):
                zone_mult = random.uniform(1.05, 1.35)
            else:
                zone_mult = gauss_clamp(1.0, 0.12, 0.7, 1.3)

            # Type the character
            if ch == "\n":
                press_key(KEYCODE_MAP['enter'])
                # autoIndent is "none" in settings, so no cleanup needed
                delay = gauss_clamp(0.35, 0.15, 0.10, 0.80)
            elif ch == "\t":
                press_key(KEYCODE_MAP['tab'])
                delay = gauss_clamp(0.07, 0.025, 0.03, 0.15)
            else:
                type_char(ch)
                if ch in "{}()[];:":
                    delay = gauss_clamp(current_base * 1.8, 0.04, 0.06, 0.30)
                elif ch in "'\"<>":
                    delay = gauss_clamp(current_base * 1.5, 0.03, 0.05, 0.25)
                elif ch == " ":
                    delay = gauss_clamp(current_base * 0.6, 0.02, 0.02, 0.10)
                elif ch in "0123456789":
                    delay = gauss_clamp(current_base * 1.2, 0.03, 0.04, 0.20)
                else:
                    delay = gauss_clamp(current_base, 0.025, 0.03, 0.18)

            delay *= zone_mult

            # Digraph noise — extra wide to ensure CV>0.3 for all pairs
            if idx > 0:
                delay *= random.choice([
                    random.uniform(0.3, 0.7),   # sometimes much faster
                    random.uniform(0.7, 1.3),   # normal range
                    random.uniform(1.3, 2.2),   # sometimes much slower
                ])

            # Burst
            if random.random() < burst_rate:
                delay *= random.uniform(0.3, 0.6)
            # Pareto spike
            if random.random() < 0.01:
                delay += random.paretovariate(1.5) * 0.5
            # FFT breaker
            if random.random() < 0.08:
                delay += random.uniform(0.05, 0.3)
            # Proportional noise — very wide to maximize randomness of above/below median
            delay *= random.uniform(0.5, 1.6)
            delay += random.gauss(0, delay * 0.25)
            delay = max(0.015, delay)

            # Anti-pattern jitter
            recent_delays.append(delay)
            if len(recent_delays) > 5:
                recent_delays.pop(0)
            if len(recent_delays) >= 3:
                r = recent_delays[-3:]
                a = sum(r) / 3
                v = sum((d - a) ** 2 for d in r) / 3
                if v < 0.0001:
                    delay += random.uniform(0.05, 0.2)

            time.sleep(delay)

            # Typo + correction (~2-4% of alpha chars)
            if random.random() < typo_rate and ch.isalpha():
                neighbors = _nearby_keys(ch.lower())
                wrong = random.choice(neighbors) if neighbors else random.choice("asdfghjkl")
                logger.log_typo(ch, wrong)
                type_char(wrong)
                time.sleep(gauss_clamp(0.25, 0.1, 0.08, 0.6))
                press_key(KEYCODE_MAP['backspace'])
                time.sleep(gauss_clamp(0.12, 0.05, 0.05, 0.35))

            # Thinking pause (cooldown 30 chars)
            if random.random() < think_rate and (idx - last_think_idx) > 30:
                last_think_idx = idx
                pause_dur = gauss_clamp(1.2, 0.5, 0.3, 3.0)
                logger.log_pause("thinking", pause_dur)
                time.sleep(pause_dur)

            # Cursor-safe interactions (~5% per char)
            if mouse and random.random() < 0.05:
                action = random.choices(
                    ["fidget", "save", "read_pause", "scroll_peek"],
                    weights=[30, 20, 25, 25], k=1,
                )[0]
                if action == "fidget":
                    logger.log_action("mid_type_fidget")
                    mouse.small_drift(1)
                elif action == "save":
                    logger.log_action("mid_type_save")
                    _cmd_key_native('s')
                    time.sleep(gauss_clamp(0.3, 0.1, 0.1, 0.6))
                elif action == "read_pause":
                    logger.log_action("mid_type_read_pause")
                    dur = gauss_clamp(2.0, 0.8, 0.5, 4.0)
                    logger.log_pause("reading", dur)
                    t0 = time.time()
                    while time.time() - t0 < dur:
                        dx, dy = random.gauss(0, 15), random.gauss(0, 8)
                        mouse.move_to(
                            max(100, min(SCREEN_W - 100, mouse.x + dx)),
                            max(100, min(SCREEN_H - 100, mouse.y + dy)),
                        )
                        time.sleep(gauss_clamp(0.4, 0.15, 0.15, 0.8))
                elif action == "scroll_peek":
                    logger.log_action("mid_type_scroll")
                    scroll_wheel(random.choice([-2, -1, 1, 2]))
                    time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))
                    scroll_wheel(random.choice([-1, 1]))
                    time.sleep(gauss_clamp(0.3, 0.1, 0.15, 0.6))
    finally:
        pass  # autocomplete managed manually via Windsurf extensions


# ── AI Chat prompts — typed into Windsurf's AI panel ────────────────────────

# SAFE prompts only — questions that explain, don't modify code
# Avoid: "add", "refactor", "help me", "can you" + verb = triggers code edits
AI_PROMPTS = [
    "explain what this function does",
    "what is the time complexity of this approach",
    "what does this variable represent",
    "what design pattern is this using",
    "explain how this loop works",
    "what are the edge cases here",
    "is this the right data structure for this",
    "what is the difference between these two approaches",
    "why would you use a class here instead of a function",
    "what does this error message mean",
    "explain the purpose of this import",
    "what is the Big O notation for this",
    "how does this sorting algorithm work",
    "explain the difference between a list and a tuple",
    "what are the tradeoffs of this approach",
    "when should I use recursion vs iteration",
    "explain what this return statement does",
    "what is memoization and when to use it",
    "explain the difference between shallow and deep copy",
    "what does the yield keyword do in python",
]


def _do_ai_chat(mouse):
    """Open Windsurf AI chat via Cmd+L, type a prompt, wait for response,
    then return to the editor. Uses keyboard shortcuts — no blind clicking."""
    ensure_windsurf_focus()

    prompt = random.choice(AI_PROMPTS)

    # Cmd+L opens/focuses Windsurf's AI chat input
    logger.log_action("ai_open_chat")
    applescript_cmd("l")
    time.sleep(gauss_clamp(1.0, 0.3, 0.5, 1.5))

    # Type the prompt naturally
    logger.log_action("ai_type_prompt", prompt)
    for ch in prompt:
        if ch == " ":
            delay = gauss_clamp(0.06, 0.02, 0.03, 0.10)
        else:
            delay = gauss_clamp(0.08, 0.025, 0.04, 0.16)
        type_char(ch)
        time.sleep(delay)

    time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))

    # Press Enter to send
    press_key(KEYCODE_MAP['enter'])
    logger.log_action("ai_send_prompt")

    # Wait for AI response
    wait_dur = gauss_clamp(5.0, 2.5, 2.0, 12.0)
    logger.log_pause("ai_waiting_response", wait_dur)
    start = time.time()
    while time.time() - start < wait_dur:
        # Mouse drifts over the AI panel (window-aware)
        if wm:
            rx, ry = wm.safe_ai_click()
        else:
            rx = rand_int(int(SCREEN_W * 0.6), SCREEN_W - 50)
            ry = rand_int(100, SCREEN_H - 100)
        mouse.move_to(rx, ry)
        time.sleep(gauss_clamp(0.6, 0.25, 0.2, 1.2))
        if random.random() < 0.25:
            scroll_wheel(random.choice([-1, -2, 1]))
            time.sleep(gauss_clamp(0.4, 0.15, 0.2, 0.8))

    # Read the response a bit more
    read_dur = gauss_clamp(3.0, 1.5, 1.0, 6.0)
    logger.log_pause("ai_reading_response", read_dur)
    start = time.time()
    while time.time() - start < read_dur:
        if wm:
            rx, ry = wm.safe_ai_click()
        else:
            rx = rand_int(int(SCREEN_W * 0.6), SCREEN_W - 50)
            ry = rand_int(100, SCREEN_H - 100)
        mouse.move_to(rx, ry)
        time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))

    # Aggressively dismiss any AI "Apply changes" dialogs, popups, suggestions
    for _ in range(3):
        press_key(KEYCODE_MAP['escape'])
        time.sleep(0.15)

    # Close the AI chat panel entirely (Cmd+L toggles it)
    applescript_cmd("l")
    time.sleep(0.5)

    # Click editor to refocus
    if wm:
        editor_x, editor_y = wm.safe_editor_click()
    else:
        editor_x = int(SCREEN_W * random.uniform(0.15, 0.40))
        editor_y = int(SCREEN_H * random.uniform(0.3, 0.5))
    logger.log_action("ai_back_to_editor")
    mouse.click_at(editor_x, editor_y)
    time.sleep(gauss_clamp(0.5, 0.2, 0.2, 0.8))

    # Triple Escape: dismiss autocomplete, any remaining popups
    for _ in range(3):
        press_key(KEYCODE_MAP['escape'])
        time.sleep(0.1)

    # Navigate to end of file to resume typing
    try:
        subprocess.run([
            "osascript", "-e",
            'tell application "System Events" to key code 119 using command down'
        ], capture_output=True, timeout=3)
        logger.log_cmd("end", method="applescript")
    except Exception:
        pass
    time.sleep(gauss_clamp(0.3, 0.1, 0.15, 0.5))


# Adjacent keys on QWERTY for realistic typos
_QWERTY_NEIGHBORS = {
    'q': 'wa', 'w': 'qeas', 'e': 'wrds', 'r': 'etdf', 't': 'ryfg',
    'y': 'tugh', 'u': 'yijh', 'i': 'uojk', 'o': 'iplk', 'p': 'ol',
    'a': 'qwsz', 's': 'awedxz', 'd': 'serfcx', 'f': 'drtgvc',
    'g': 'ftyhbv', 'h': 'gyujnb', 'j': 'huiknm', 'k': 'jiolm',
    'l': 'kop', 'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb',
    'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
}

def _nearby_keys(ch):
    """Return keys adjacent to ch on QWERTY."""
    return list(_QWERTY_NEIGHBORS.get(ch, ""))


# ── Windsurf interaction ────────────────────────────────────────────────────

def open_windsurf():
    """Open Windsurf in fullscreen and wait for it to be ready."""
    print("[stealth] opening Windsurf ...")
    logger.log_action("open_windsurf")
    subprocess.Popen(["open", "-a", WINDSURF_APP])
    human_sleep(3.0, 5.0)
    activate_windsurf()
    # Maximize window (Cmd+Ctrl+F for macOS fullscreen, or set bounds)
    try:
        subprocess.run([
            "osascript", "-e",
            f'tell application "System Events" to tell process "{WINDSURF_PROCESS}" '
            f'to set position of front window to {{0, 0}}'
        ], capture_output=True, timeout=3)
        subprocess.run([
            "osascript", "-e",
            f'tell application "System Events" to tell process "{WINDSURF_PROCESS}" '
            f'to set size of front window to {{{SCREEN_W}, {SCREEN_H}}}'
        ], capture_output=True, timeout=3)
        logger.log_action("windsurf_fullscreen")
    except Exception:
        pass
    human_sleep(0.5, 1.0)


def open_file_via_terminal(filename):
    """Open a file in Windsurf."""
    filepath = os.path.join(WORKSPACE_DIR, filename)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write("")

    print(f"[stealth] opening {filepath} in Windsurf ...")
    logger.log_action("open_file", filepath)
    subprocess.run(["open", "-a", WINDSURF_APP, filepath], check=False,
                    capture_output=True)
    human_sleep(2.0, 4.0)
    activate_windsurf()
    human_sleep(0.5, 1.0)


def applescript_cmd(key):
    """Send Cmd+key via AppleScript — safe, no Raycast trigger."""
    subprocess.run([
        "osascript", "-e",
        f'tell application "System Events" to keystroke "{key}" using command down'
    ], capture_output=True)
    time.sleep(0.05)
    logger.log_cmd(key, method="applescript")


def select_all_and_delete():
    """Clear editor content via Cmd+A then Delete — pure CGEvent."""
    _cmd_key_native('a')
    human_sleep(0.3, 0.5)
    press_key(KEYCODE_MAP['backspace'])
    human_sleep(0.3, 0.5)


def save_file():
    """Cmd+S to save — pure CGEvent."""
    _cmd_key_native('s')
    human_sleep(0.5, 1.0)


def scroll_through_code(mouse):
    """Scroll up and down like reading your own code — mouse over editor."""
    # Move mouse to editor area first
    editor_x = int(SCREEN_W * random.uniform(0.5, 0.7))
    editor_y = int(SCREEN_H * random.uniform(0.3, 0.5))
    mouse.move_to(editor_x, editor_y)
    time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))

    scroll_count = rand_int(2, 6)
    for i in range(scroll_count):
        direction = random.choice([-3, -2, -1, 1, 2, 3])
        scroll_wheel(direction)
        # Variable pause between scrolls — sometimes skim, sometimes read
        time.sleep(gauss_clamp(0.7, 0.3, 0.2, 2.0))
        # Occasionally move mouse while scrolling like tracking a line
        if random.random() < 0.3:
            mouse.small_drift(1)
    mouse.rest_pause()


# ── Main loop ───────────────────────────────────────────────────────────────

def run():
    global SCREEN_W, SCREEN_H, wm

    # Get screen size via Quartz
    main_display = Quartz.CGMainDisplayID()
    SCREEN_W = Quartz.CGDisplayPixelsWide(main_display)
    SCREEN_H = Quartz.CGDisplayPixelsHigh(main_display)
    print(f"[stealth] screen size: {SCREEN_W}x{SCREEN_H}")

    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    mouse = NaturalMouse()
    used_templates = []
    iteration = 0

    # Open Windsurf once and init window manager
    open_windsurf()
    wm = WindowManager()
    wx, wy, ww, wh = wm.get_bounds()
    print(f"[stealth] Windsurf window: {ww}x{wh} at ({wx},{wy})")
    ex1, ey1, ex2, ey2 = wm.editor_region()
    print(f"[stealth] editor region: ({ex1},{ey1}) to ({ex2},{ey2})")

    print("[stealth] entering main loop — Ctrl+C to stop\n")

    consecutive_errors = 0

    while True:
        iteration += 1

        # Pick a random template (avoid immediate repeats)
        available = [t for t in CODE_TEMPLATES if t not in used_templates]
        if not available:
            used_templates.clear()
            available = CODE_TEMPLATES
        template = random.choice(available)
        used_templates.append(template)

        filename = template["filename"]
        code = template["code"]

        try:
            print(f"-- iteration {iteration}: {filename} ({len(code)} chars) --")
            logger.log_iteration(iteration, filename, len(code))

            # Idle drift before starting
            mouse.idle_drift(rand_int(2, 3))

            # Open the file in Windsurf
            open_file_via_terminal(filename)

            # Ensure Windsurf is focused
            ensure_windsurf_focus()
            human_sleep(0.3, 0.5)

            # Close AI panel if open (it steals keystrokes)
            for _ in range(3):
                press_key(KEYCODE_MAP['escape'])
                time.sleep(0.1)

            # Click inside the ACTUAL editor region (window-aware)
            editor_x, editor_y = wm.safe_editor_click()
            mouse.click_at(editor_x, editor_y)
            human_sleep(0.5, 0.8)

            # Second click to confirm focus
            editor_x2, editor_y2 = wm.safe_editor_click()
            mouse.click_at(editor_x2, editor_y2)
            human_sleep(0.3, 0.5)

            # Dismiss any autocomplete/popup
            press_key(KEYCODE_MAP['escape'])
            human_sleep(0.2, 0.4)

            # Clear any existing content
            ensure_windsurf_focus()
            select_all_and_delete()

            # Type the code
            ensure_windsurf_focus()
            print("[stealth] typing ...")
            human_type_smart(code, mouse=mouse)

            # Save
            ensure_windsurf_focus()
            print("[stealth] saving ...")
            save_file()

            # Post-typing behaviour — randomize the order and selection
            post_actions = ["scroll", "review_click", "review_click",
                            "idle", "rest", "browse_docs", "read_code"]
            random.shuffle(post_actions)
            for action in post_actions[:rand_int(3, 5)]:
                try:
                    if action == "scroll":
                        scroll_through_code(mouse)
                    elif action == "review_click":
                        for _ in range(rand_int(3, 8)):
                            cx, cy = wm.safe_editor_click()
                            mouse.click_at(cx, cy)
                            time.sleep(gauss_clamp(0.8, 0.4, 0.3, 2.0))
                            if random.random() < 0.4:
                                mouse.small_drift(1)
                    elif action == "idle":
                        mouse.idle_drift(rand_int(1, 3))
                    elif action == "rest":
                        mouse.rest_pause()
                    elif action == "browse_docs":
                        logger.log_action("post_browse_docs")
                        subprocess.run([
                            "osascript", "-e",
                            'tell application "System Events" to keystroke tab using command down'
                        ], capture_output=True)
                        logger.log_cmd("tab", method="applescript_cmdtab")
                        browse_dur = gauss_clamp(6.0, 3.0, 2.0, 15.0)
                        logger.log_pause("browsing_docs", browse_dur)
                        start = time.time()
                        while time.time() - start < browse_dur:
                            mx = rand_int(200, SCREEN_W - 200)
                            my = rand_int(150, SCREEN_H - 150)
                            mouse.move_to(mx, my)
                            time.sleep(gauss_clamp(0.6, 0.25, 0.2, 1.2))
                            if random.random() < 0.4:
                                scroll_wheel(random.choice([-3, -2, -1, 1, 2, 3]))
                                time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))
                            if random.random() < 0.15:
                                click_mouse(mx, my)
                                time.sleep(gauss_clamp(1.5, 0.5, 0.5, 3.0))
                        activate_windsurf()
                        time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))
                    elif action == "read_code":
                        logger.log_action("post_read_code")
                        read_dur = gauss_clamp(5.0, 2.0, 2.0, 12.0)
                        logger.log_pause("reading_code", read_dur)
                        start = time.time()
                        while time.time() - start < read_dur:
                            rx, ry = wm.safe_editor_click()
                            mouse.move_to(rx, ry)
                            time.sleep(gauss_clamp(0.8, 0.3, 0.3, 1.5))
                            if random.random() < 0.2:
                                scroll_wheel(random.choice([-1, 1]))
                                time.sleep(gauss_clamp(0.5, 0.2, 0.2, 1.0))
                    # ai_review disabled — Windsurf AI corrupts typed code
                except Exception as post_err:
                    logger.log_action("post_action_error", f"{action}: {post_err}")
                    if wm:
                        wm.capture_screenshot(f"post_error_{action}")

            consecutive_errors = 0  # reset on success

        except Exception as e:
            consecutive_errors += 1
            logger.log_action("iteration_error", f"#{iteration}: {e}")
            print(f"[stealth] ERROR in iteration {iteration}: {e}")
            if wm:
                wm.capture_screenshot(f"iter_error_{iteration}")

            if consecutive_errors >= 5:
                print("[stealth] 5 consecutive errors — taking recovery pause")
                logger.log_action("recovery_pause", "5 consecutive errors")
                time.sleep(10)
                activate_windsurf()
                consecutive_errors = 0

            # Always try to recover Windsurf focus
            try:
                activate_windsurf()
            except Exception:
                pass

        # Between-iteration pause — variable with occasional "coffee break"
        if random.random() < 0.15:
            pause = gauss_clamp(40.0, 15.0, 20.0, 90.0)
            print(f"[stealth] taking a break ({pause:.0f}s) ...\n")
            logger.log_pause("coffee_break", pause)
            start = time.time()
            while time.time() - start < pause:
                if random.random() < 0.1:
                    mouse.small_drift(1)
                time.sleep(gauss_clamp(3.0, 1.5, 1.0, 8.0))
        else:
            pause = gauss_clamp(
                (PAUSE_BETWEEN_MIN + PAUSE_BETWEEN_MAX) / 2,
                3.0,
                PAUSE_BETWEEN_MIN,
                PAUSE_BETWEEN_MAX * 1.5,
            )
            print(f"[stealth] pausing {pause:.0f}s before next ...\n")
            logger.log_pause("between_iterations", pause)
            time.sleep(pause)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[stealth] stopped by user.")
        print("[stealth] saving session logs ...")
        logger.save()
        sys.exit(0)
    except Exception as e:
        print(f"\n[stealth] error: {e}")
        print("[stealth] saving session logs before exit ...")
        logger.save()
        raise
