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
    # REALISTIC WORK TEMPLATES — Django + FastAPI Project
    # ══════════════════════════════════════════════════════════════

    # ── Django: Product model with custom manager ──
    {
        "filename": "models.py",
        "code": """\
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal


class PublishedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            is_published=True,
            published_at__lte=timezone.now(),
        )


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def full_path(self):
        parts = [self.name]
        current = self.parent
        while current:
            parts.insert(0, current.name)
            current = current.parent
        return " > ".join(parts)


class Product(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("review", "In Review"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    sku = models.CharField(max_length=50, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT,
        related_name="products",
    )
    tags = models.ManyToManyField("Tag", blank=True, related_name="products")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    published = PublishedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["status", "is_published"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_on_sale(self):
        return (
            self.compare_at_price is not None
            and self.compare_at_price > self.price
        )

    @property
    def discount_percentage(self):
        if not self.is_on_sale:
            return 0
        diff = self.compare_at_price - self.price
        return int((diff / self.compare_at_price) * 100)

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    def publish(self):
        self.status = "published"
        self.is_published = True
        self.published_at = timezone.now()
        self.save(update_fields=["status", "is_published", "published_at", "updated_at"])


class Tag(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name
""",
    },
    # ── Django: Serializers ──
    {
        "filename": "serializers.py",
        "code": """\
from rest_framework import serializers
from django.utils.text import slugify

from products.models import Product, Category, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]
        read_only_fields = ["slug"]


class CategorySerializer(serializers.ModelSerializer):
    full_path = serializers.ReadOnlyField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "sort_order", "full_path", "product_count"]

    def get_product_count(self, obj):
        return obj.products.filter(is_published=True).count()


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    in_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "price", "compare_at_price",
            "sku", "stock_quantity", "category", "category_name",
            "status", "is_published", "is_on_sale",
            "discount_percentage", "in_stock", "created_at",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="category",
        write_only=True,
    )
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        source="tags",
        many=True,
        write_only=True,
        required=False,
    )
    is_on_sale = serializers.ReadOnlyField()
    discount_percentage = serializers.ReadOnlyField()
    in_stock = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "description", "price",
            "compare_at_price", "sku", "stock_quantity",
            "category", "category_id", "tags", "tag_ids",
            "status", "is_published", "published_at",
            "is_on_sale", "discount_percentage", "in_stock",
            "created_by", "created_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_by", "published_at"]

    def validate_sku(self, value):
        qs = Product.objects.filter(sku=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A product with this SKU already exists.")
        return value

    def validate(self, data):
        price = data.get("price", getattr(self.instance, "price", None))
        compare = data.get("compare_at_price", getattr(self.instance, "compare_at_price", None))
        if compare is not None and compare <= price:
            raise serializers.ValidationError({
                "compare_at_price": "Compare-at price must be greater than the selling price."
            })
        return data

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        validated_data["created_by"] = self.context["request"].user
        if not validated_data.get("slug"):
            validated_data["slug"] = slugify(validated_data["title"])
        product = Product.objects.create(**validated_data)
        if tags:
            product.tags.set(tags)
        return product

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tags is not None:
            instance.tags.set(tags)
        return instance
""",
    },
    # ── Django: ViewSet with filters ──
    {
        "filename": "views.py",
        "code": """\
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg

from products.models import Product, Category
from products.serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    CategorySerializer,
)
from products.filters import ProductFilter
from products.pagination import StandardPagination


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["title", "sku", "description"]
    ordering_fields = ["price", "created_at", "stock_quantity", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Product.objects.select_related("category", "created_by").prefetch_related("tags")
        if not self.request.user.is_staff:
            qs = qs.filter(is_published=True)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductDetailSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def publish(self, request, pk=None):
        product = self.get_object()
        if product.status == "published":
            return Response(
                {"detail": "Product is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product.publish()
        serializer = self.get_serializer(product)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def archive(self, request, pk=None):
        product = self.get_object()
        product.status = "archived"
        product.is_published = False
        product.save(update_fields=["status", "is_published", "updated_at"])
        return Response({"detail": "Product archived."})

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        data = {
            "total": qs.count(),
            "published": qs.filter(is_published=True).count(),
            "draft": qs.filter(status="draft").count(),
            "out_of_stock": qs.filter(stock_quantity=0).count(),
            "avg_price": qs.aggregate(avg=Avg("price"))["avg"],
            "by_category": list(
                qs.values("category__name")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            ),
        }
        return Response(data)

    @action(detail=True, methods=["post"])
    def adjust_stock(self, request, pk=None):
        product = self.get_object()
        delta = request.data.get("delta", 0)
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return Response(
                {"detail": "delta must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_qty = product.stock_quantity + delta
        if new_qty < 0:
            return Response(
                {"detail": "Stock cannot go below zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product.stock_quantity = new_qty
        product.save(update_fields=["stock_quantity", "updated_at"])
        return Response({"stock_quantity": product.stock_quantity})


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.annotate(
        product_count=Count("products", filter=Q(products__is_published=True))
    ).select_related("parent")
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]
""",
    },
    # ── Django: URL configuration ──
    {
        "filename": "urls.py",
        "code": """\
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from products.views import ProductViewSet, CategoryViewSet

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register(r"categories", CategoryViewSet, basename="category")

app_name = "products"

urlpatterns = [
    path("api/v1/", include(router.urls)),
]
""",
    },
    # ── Django: FilterSet ──
    {
        "filename": "filters.py",
        "code": """\
import django_filters
from django.db.models import Q

from products.models import Product


class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    category = django_filters.NumberFilter(field_name="category_id")
    category_slug = django_filters.CharFilter(field_name="category__slug")
    status = django_filters.ChoiceFilter(choices=Product.STATUS_CHOICES)
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    on_sale = django_filters.BooleanFilter(method="filter_on_sale")
    tag = django_filters.CharFilter(method="filter_by_tag")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Product
        fields = [
            "min_price", "max_price", "category", "category_slug",
            "status", "in_stock", "on_sale", "tag",
            "created_after", "created_before",
        ]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock_quantity__gt=0)
        return queryset.filter(stock_quantity=0)

    def filter_on_sale(self, queryset, name, value):
        if value:
            return queryset.filter(
                compare_at_price__isnull=False,
                compare_at_price__gt=models.F("price"),
            )
        return queryset

    def filter_by_tag(self, queryset, name, value):
        return queryset.filter(
            Q(tags__slug=value) | Q(tags__name__iexact=value)
        ).distinct()
""",
    },
    # ── Django: Custom pagination ──
    {
        "filename": "pagination.py",
        "code": """\
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ("count", self.page.paginator.count),
            ("page", self.page.number),
            ("page_size", self.get_page_size(self.request)),
            ("total_pages", self.page.paginator.num_pages),
            ("next", self.get_next_link()),
            ("previous", self.get_previous_link()),
            ("results", data),
        ]))

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
                "total_pages": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": schema,
            },
        }
""",
    },
    # ── Django: Admin configuration ──
    {
        "filename": "admin.py",
        "code": """\
from django.contrib import admin
from django.utils.html import format_html

from products.models import Product, Category, Tag


class ProductInline(admin.TabularInline):
    model = Product
    extra = 0
    fields = ["title", "sku", "price", "stock_quantity", "status"]
    readonly_fields = ["title", "sku"]
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "sort_order", "product_count"]
    list_editable = ["sort_order"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]
    list_filter = ["parent"]
    inlines = [ProductInline]

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = "Products"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "title", "sku", "price_display", "stock_quantity",
        "category", "status", "is_published", "created_at",
    ]
    list_filter = ["status", "is_published", "category", "created_at"]
    search_fields = ["title", "sku", "description"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at", "created_by"]
    filter_horizontal = ["tags"]
    list_per_page = 25
    date_hierarchy = "created_at"
    actions = ["publish_selected", "archive_selected"]

    fieldsets = (
        (None, {
            "fields": ("title", "slug", "description"),
        }),
        ("Pricing & Inventory", {
            "fields": ("price", "compare_at_price", "sku", "stock_quantity"),
        }),
        ("Classification", {
            "fields": ("category", "tags", "status", "is_published"),
        }),
        ("Metadata", {
            "classes": ("collapse",),
            "fields": ("created_by", "created_at", "updated_at"),
        }),
    )

    def price_display(self, obj):
        if obj.is_on_sale:
            return format_html(
                '<span style="text-decoration:line-through;color:#999">${}</span> '
                '<span style="color:#e53e3e;font-weight:bold">${}</span>',
                obj.compare_at_price, obj.price,
            )
        return f"${obj.price}"
    price_display.short_description = "Price"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Publish selected products")
    def publish_selected(self, request, queryset):
        count = 0
        for product in queryset.filter(status__in=["draft", "review"]):
            product.publish()
            count += 1
        self.message_user(request, f"{count} product(s) published.")

    @admin.action(description="Archive selected products")
    def archive_selected(self, request, queryset):
        count = queryset.update(status="archived", is_published=False)
        self.message_user(request, f"{count} product(s) archived.")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "product_count"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = "Products"
""",
    },
    # ── Django: Management command ──
    {
        "filename": "import_products.py",
        "code": """\
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from products.models import Product, Category, Tag


class Command(BaseCommand):
    help = "Import products from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to CSV file")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Validate without saving to database",
        )
        parser.add_argument(
            "--update-existing", action="store_true",
            help="Update products that already exist (matched by SKU)",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_file"])
        if not csv_path.exists():
            raise CommandError(f"File not found: {csv_path}")

        dry_run = options["dry_run"]
        update_existing = options["update_existing"]
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_fields = {"title", "sku", "price", "category"}
            if not required_fields.issubset(set(reader.fieldnames or [])):
                missing = required_fields - set(reader.fieldnames or [])
                raise CommandError(f"Missing required columns: {', '.join(missing)}")

            rows = list(reader)

        self.stdout.write(f"Found {len(rows)} rows to process...")

        with transaction.atomic():
            for i, row in enumerate(rows, start=2):
                try:
                    sku = row["sku"].strip()
                    if not sku:
                        errors.append(f"Row {i}: empty SKU")
                        continue

                    price = Decimal(row["price"].strip())
                    if price <= 0:
                        errors.append(f"Row {i}: invalid price {row['price']}")
                        continue

                    category, _ = Category.objects.get_or_create(
                        slug=slugify(row["category"].strip()),
                        defaults={"name": row["category"].strip()},
                    )

                    existing = Product.objects.filter(sku=sku).first()
                    if existing:
                        if update_existing:
                            existing.title = row["title"].strip()
                            existing.price = price
                            existing.category = category
                            existing.description = row.get("description", "").strip()
                            stock = row.get("stock_quantity", "").strip()
                            if stock:
                                existing.stock_quantity = int(stock)
                            if not dry_run:
                                existing.save()
                            updated_count += 1
                        else:
                            skipped_count += 1
                        continue

                    product = Product(
                        title=row["title"].strip(),
                        slug=slugify(row["title"].strip()),
                        sku=sku,
                        price=price,
                        category=category,
                        description=row.get("description", "").strip(),
                        stock_quantity=int(row.get("stock_quantity", 0) or 0),
                        status="draft",
                    )
                    if not dry_run:
                        product.save()

                    tag_str = row.get("tags", "").strip()
                    if tag_str and not dry_run:
                        for tag_name in tag_str.split(","):
                            tag_name = tag_name.strip()
                            if tag_name:
                                tag, _ = Tag.objects.get_or_create(
                                    slug=slugify(tag_name),
                                    defaults={"name": tag_name},
                                )
                                product.tags.add(tag)

                    created_count += 1
                except (InvalidOperation, ValueError) as e:
                    errors.append(f"Row {i}: {e}")

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("DRY RUN — no changes saved"))

        self.stdout.write(self.style.SUCCESS(
            f"Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}"
        ))
        if errors:
            self.stdout.write(self.style.ERROR(f"Errors ({len(errors)}):"))
            for err in errors:
                self.stdout.write(f"  {err}")
""",
    },
    # ── Django: Tests ──
    {
        "filename": "test_products.py",
        "code": """\
import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from products.models import Product, Category, Tag


@pytest.fixture
def api_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="testuser", password="testpass123"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def category(db):
    return Category.objects.create(name="Electronics", slug="electronics")


@pytest.fixture
def sample_product(db, category):
    return Product.objects.create(
        title="Wireless Keyboard",
        slug="wireless-keyboard",
        sku="KB-001",
        price=Decimal("79.99"),
        stock_quantity=50,
        category=category,
        status="published",
        is_published=True,
    )


class TestProductModel:
    def test_str_representation(self, sample_product):
        assert str(sample_product) == "Wireless Keyboard"

    def test_in_stock_property(self, sample_product):
        assert sample_product.in_stock is True
        sample_product.stock_quantity = 0
        assert sample_product.in_stock is False

    def test_not_on_sale_without_compare_price(self, sample_product):
        assert sample_product.is_on_sale is False
        assert sample_product.discount_percentage == 0

    def test_on_sale_with_compare_price(self, sample_product):
        sample_product.compare_at_price = Decimal("99.99")
        assert sample_product.is_on_sale is True
        assert sample_product.discount_percentage == 20

    def test_publish_sets_fields(self, sample_product):
        sample_product.status = "draft"
        sample_product.is_published = False
        sample_product.published_at = None
        sample_product.publish()
        sample_product.refresh_from_db()
        assert sample_product.status == "published"
        assert sample_product.is_published is True
        assert sample_product.published_at is not None


class TestProductAPI:
    def test_list_products(self, api_client, sample_product):
        client, _ = api_client
        url = reverse("product-list")
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_create_product(self, api_client, category):
        client, _ = api_client
        url = reverse("product-list")
        data = {
            "title": "USB-C Hub",
            "sku": "HUB-001",
            "price": "49.99",
            "category_id": category.id,
            "stock_quantity": 100,
        }
        response = client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Product.objects.filter(sku="HUB-001").exists()

    def test_create_duplicate_sku_fails(self, api_client, sample_product, category):
        client, _ = api_client
        url = reverse("product-list")
        data = {
            "title": "Another Product",
            "sku": "KB-001",
            "price": "29.99",
            "category_id": category.id,
        }
        response = client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_filter_by_category(self, api_client, sample_product, category):
        client, _ = api_client
        url = reverse("product-list")
        response = client.get(url, {"category": category.id})
        assert response.status_code == status.HTTP_200_OK
        for item in response.data["results"]:
            assert item["category"] == category.id

    def test_search_products(self, api_client, sample_product):
        client, _ = api_client
        url = reverse("product-list")
        response = client.get(url, {"search": "wireless"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_adjust_stock(self, api_client, sample_product):
        client, _ = api_client
        url = reverse("product-adjust-stock", args=[sample_product.pk])
        response = client.post(url, {"delta": -10}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["stock_quantity"] == 40

    def test_adjust_stock_below_zero_fails(self, api_client, sample_product):
        client, _ = api_client
        url = reverse("product-adjust-stock", args=[sample_product.pk])
        response = client.post(url, {"delta": -999}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
""",
    },
    # ── FastAPI: Main app with middleware ──
    {
        "filename": "main.py",
        "code": """\
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import logging
import time

from app.config import settings
from app.database import engine, Base
from app.routers import products, categories, auth, health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating database tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    logger.info("Shutting down — disposing engine")
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)


@app.middleware("http")
async def add_timing_header(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(products.router, prefix="/api/v1", tags=["products"])
app.include_router(categories.router, prefix="/api/v1", tags=["categories"])
""",
    },
    # ── FastAPI: Database & models ──
    {
        "filename": "database.py",
        "code": """\
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Numeric, Text
from datetime import datetime
from typing import Optional

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_size=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
""",
    },
    # ── FastAPI: Product routes ──
    {
        "filename": "products_router.py",
        "code": """\
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional

from app.database import get_db, Product, Category
from app.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
)
from app.auth import get_current_user, require_admin

router = APIRouter()


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    sort_by: str = Query("created_at", regex="^(title|price|created_at|stock_quantity)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    query = select(Product)

    if not user.is_admin:
        query = query.where(Product.is_published == True)

    if category_id:
        query = query.where(Product.category_id == category_id)
    if status:
        query = query.where(Product.status == status)
    if search:
        query = query.where(
            Product.title.ilike(f"%{search}%")
            | Product.sku.ilike(f"%{search}%")
        )
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)
    if in_stock is True:
        query = query.where(Product.stock_quantity > 0)
    elif in_stock is False:
        query = query.where(Product.stock_quantity == 0)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    sort_column = getattr(Product, sort_by)
    if sort_dir == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    products = result.scalars().all()

    return {
        "results": products,
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.is_published and not user.is_admin:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    existing = await db.execute(select(Product).where(Product.sku == payload.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU already exists")

    cat = await db.execute(select(Category).where(Category.id == payload.category_id))
    if not cat.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invalid category")

    product = Product(**payload.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    await db.flush()
    await db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(product)
""",
    },
    # ── FastAPI: Pydantic schemas ──
    {
        "filename": "schemas.py",
        "code": """\
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: str = Field(..., min_length=1, max_length=120)
    parent_id: Optional[int] = None
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = None
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    compare_at_price: Optional[float] = None
    sku: str = Field(..., min_length=1, max_length=50)
    stock_quantity: int = Field(default=0, ge=0)
    category_id: int

    @field_validator("sku")
    @classmethod
    def sku_must_be_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @model_validator(mode="after")
    def check_compare_price(self):
        if self.compare_at_price is not None and self.compare_at_price <= self.price:
            raise ValueError("compare_at_price must be greater than price")
        return self


class ProductCreate(ProductBase):
    status: str = Field(default="draft", pattern="^(draft|review|published)$")


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    compare_at_price: Optional[float] = None
    sku: Optional[str] = Field(None, min_length=1, max_length=50)
    stock_quantity: Optional[int] = Field(None, ge=0)
    category_id: Optional[int] = None
    status: Optional[str] = Field(None, pattern="^(draft|review|published|archived)$")
    is_published: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    status: str
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @property
    def is_on_sale(self) -> bool:
        return (
            self.compare_at_price is not None
            and self.compare_at_price > self.price
        )

    @property
    def discount_percentage(self) -> int:
        if not self.is_on_sale:
            return 0
        diff = self.compare_at_price - self.price
        return int((diff / self.compare_at_price) * 100)


class ProductListResponse(BaseModel):
    results: list[ProductResponse]
    count: int
    page: int
    page_size: int
    total_pages: int
""",
    },
    # ── FastAPI: Auth with JWT ──
    {
        "filename": "auth.py",
        "code": """\
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, User

security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, email: str, is_admin: bool) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    user_id = int(payload["sub"])

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
""",
    },
    # ── FastAPI: Config with Pydantic settings ──
    {
        "filename": "config.py",
        "code": """\
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Product Catalog API"
    DEBUG: bool = False
    VERSION: str = "1.0.0"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/catalog"
    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = "change-me-in-production"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: str = "noreply@example.com"

    S3_BUCKET: Optional[str] = None
    S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
""",
    },
    # ── Django: Celery tasks ──
    {
        "filename": "tasks.py",
        "code": """\
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import F, Q

from products.models import Product, Category

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_low_stock(self, threshold=10):
    low_stock = Product.objects.filter(
        is_published=True,
        stock_quantity__lte=threshold,
        stock_quantity__gt=0,
    ).select_related("category")

    count = low_stock.count()
    if count == 0:
        logger.info("No low-stock products found")
        return {"checked": True, "low_stock_count": 0}

    product_lines = []
    for p in low_stock[:50]:
        product_lines.append(
            f"  - {p.title} (SKU: {p.sku}) — {p.stock_quantity} remaining"
        )

    body = f"The following {count} product(s) are running low on stock:\\n\\n"
    body += "\\n".join(product_lines)
    if count > 50:
        body += f"\\n  ... and {count - 50} more"

    try:
        send_mail(
            subject=f"[Catalog] {count} product(s) low on stock",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.STOCK_ALERT_EMAIL],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error("Failed to send low-stock email: %s", exc)
        raise self.retry(exc=exc)

    return {"checked": True, "low_stock_count": count}


@shared_task
def sync_category_counts():
    categories = Category.objects.all()
    updated = 0
    for cat in categories:
        count = cat.products.filter(is_published=True).count()
        if hasattr(cat, "cached_product_count") and cat.cached_product_count != count:
            cat.cached_product_count = count
            cat.save(update_fields=["cached_product_count"])
            updated += 1
    logger.info("Updated %d category counts", updated)
    return {"updated": updated}


@shared_task
def archive_stale_drafts(days=90):
    cutoff = timezone.now() - timedelta(days=days)
    stale = Product.objects.filter(
        status="draft",
        updated_at__lt=cutoff,
    )
    count = stale.update(status="archived")
    logger.info("Archived %d stale draft products older than %d days", count, days)
    return {"archived": count}


@shared_task(bind=True, max_retries=2)
def generate_price_report(self, category_id=None):
    from django.db.models import Avg, Min, Max, Count

    qs = Product.objects.filter(is_published=True)
    if category_id:
        qs = qs.filter(category_id=category_id)

    stats = qs.aggregate(
        total=Count("id"),
        avg_price=Avg("price"),
        min_price=Min("price"),
        max_price=Max("price"),
    )

    by_category = (
        qs.values("category__name")
        .annotate(
            count=Count("id"),
            avg_price=Avg("price"),
        )
        .order_by("-count")
    )

    report = {
        "generated_at": timezone.now().isoformat(),
        "overall": stats,
        "by_category": list(by_category),
    }

    logger.info("Price report generated: %d products", stats["total"])
    return report
""",
    },
    # ── FastAPI: Tests ──
    {
        "filename": "test_api.py",
        "code": """\
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.database import Base, get_db
from app.auth import hash_password

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"
engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSession() as session:
        yield session
        await session.commit()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client):
    from app.database import User
    async with TestSession() as db:
        user = User(
            email="admin@test.com",
            name="Admin User",
            hashed_password=hash_password("password123"),
            is_active=True,
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    response = await client.post("/api/auth/login", json={
        "email": "admin@test.com",
        "password": "password123",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_category(auth_headers):
    async with TestSession() as db:
        from app.database import Category
        cat = Category(name="Electronics", slug="electronics")
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        return cat


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_health(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
class TestProducts:
    async def test_create_product(self, client, auth_headers, sample_category):
        response = await client.post(
            "/api/v1/products",
            headers=auth_headers,
            json={
                "title": "Wireless Mouse",
                "sku": "MOUSE-001",
                "price": 29.99,
                "category_id": sample_category.id,
                "stock_quantity": 100,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Wireless Mouse"
        assert data["sku"] == "MOUSE-001"

    async def test_list_products(self, client, auth_headers, sample_category):
        await client.post(
            "/api/v1/products",
            headers=auth_headers,
            json={
                "title": "Keyboard",
                "sku": "KB-001",
                "price": 79.99,
                "category_id": sample_category.id,
                "status": "published",
            },
        )
        response = await client.get("/api/v1/products", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["count"] >= 1

    async def test_duplicate_sku_rejected(self, client, auth_headers, sample_category):
        payload = {
            "title": "Product A",
            "sku": "DUP-001",
            "price": 10.00,
            "category_id": sample_category.id,
        }
        await client.post("/api/v1/products", headers=auth_headers, json=payload)
        response = await client.post("/api/v1/products", headers=auth_headers, json={
            **payload, "title": "Product B",
        })
        assert response.status_code == 409

    async def test_update_product(self, client, auth_headers, sample_category):
        create_resp = await client.post(
            "/api/v1/products",
            headers=auth_headers,
            json={
                "title": "Old Name",
                "sku": "UPD-001",
                "price": 50.00,
                "category_id": sample_category.id,
            },
        )
        product_id = create_resp.json()["id"]
        response = await client.patch(
            f"/api/v1/products/{product_id}",
            headers=auth_headers,
            json={"title": "New Name", "price": 55.00},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New Name"
        assert response.json()["price"] == 55.00

    async def test_delete_product(self, client, auth_headers, sample_category):
        create_resp = await client.post(
            "/api/v1/products",
            headers=auth_headers,
            json={
                "title": "To Delete",
                "sku": "DEL-001",
                "price": 10.00,
                "category_id": sample_category.id,
            },
        )
        product_id = create_resp.json()["id"]
        response = await client.delete(
            f"/api/v1/products/{product_id}", headers=auth_headers
        )
        assert response.status_code == 204

    async def test_filter_by_price_range(self, client, auth_headers, sample_category):
        for i, price in enumerate([10, 50, 100]):
            await client.post(
                "/api/v1/products",
                headers=auth_headers,
                json={
                    "title": f"Product {i}",
                    "sku": f"PRICE-{i}",
                    "price": price,
                    "category_id": sample_category.id,
                    "is_published": True,
                    "status": "published",
                },
            )
        response = await client.get(
            "/api/v1/products",
            headers=auth_headers,
            params={"min_price": 20, "max_price": 80},
        )
        assert response.status_code == 200
        for item in response.json()["results"]:
            assert 20 <= item["price"] <= 80
""",
    },
    # ── Django: Middleware ──
    {
        "filename": "middleware.py",
        "code": """\
import logging
import time
import uuid
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("api.requests")


class RequestLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._start_time = time.perf_counter()
        request._request_id = str(uuid.uuid4())[:8]

    def process_response(self, request, response):
        if not hasattr(request, "_start_time"):
            return response

        elapsed = time.perf_counter() - request._start_time
        response["X-Request-ID"] = request._request_id
        response["X-Process-Time"] = f"{elapsed:.4f}"

        logger.info(
            "%(method)s %(path)s %(status)s %(time).4fs [%(request_id)s]",
            {
                "method": request.method,
                "path": request.get_full_path(),
                "status": response.status_code,
                "time": elapsed,
                "request_id": request._request_id,
            },
        )

        return response


class CORSMiddleware(MiddlewareMixin):
    ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    def process_response(self, request, response):
        origin = request.META.get("HTTP_ORIGIN")
        if origin in self.ALLOWED_ORIGINS:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response["Access-Control-Allow-Credentials"] = "true"
            response["Access-Control-Max-Age"] = "86400"
        return response

    def process_request(self, request):
        if request.method == "OPTIONS":
            from django.http import HttpResponse
            response = HttpResponse()
            origin = request.META.get("HTTP_ORIGIN")
            if origin in self.ALLOWED_ORIGINS:
                response["Access-Control-Allow-Origin"] = origin
                response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                response["Access-Control-Max-Age"] = "86400"
            response.status_code = 204
            return response
        return None
""",
    },
    # ── Django: Signals ──
    {
        "filename": "signals.py",
        "code": """\
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.core.cache import cache

from products.models import Product, Category

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Product)
def auto_generate_slug(sender, instance, **kwargs):
    if not instance.slug:
        base_slug = slugify(instance.title)
        slug = base_slug
        counter = 1
        while Product.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        instance.slug = slug


@receiver(post_save, sender=Product)
def invalidate_product_cache(sender, instance, **kwargs):
    cache_keys = [
        f"product:{instance.pk}",
        f"product:slug:{instance.slug}",
        f"product_list:category:{instance.category_id}",
        "product_stats",
    ]
    cache.delete_many(cache_keys)
    logger.debug("Invalidated cache keys for product %s: %s", instance.pk, cache_keys)


@receiver(post_save, sender=Product)
def log_product_changes(sender, instance, created, **kwargs):
    if created:
        logger.info(
            "Product created: %s (SKU: %s, Price: %s, Category: %s)",
            instance.title,
            instance.sku,
            instance.price,
            instance.category_id,
        )
    else:
        logger.info(
            "Product updated: %s (SKU: %s, Status: %s)",
            instance.title,
            instance.sku,
            instance.status,
        )


@receiver(post_save, sender=Product)
def notify_on_publish(sender, instance, **kwargs):
    if instance.status == "published" and instance.is_published:
        try:
            from products.tasks import notify_product_published
            notify_product_published.delay(instance.pk)
        except Exception as exc:
            logger.warning("Failed to queue publish notification: %s", exc)


@receiver(pre_save, sender=Category)
def auto_category_slug(sender, instance, **kwargs):
    if not instance.slug:
        base_slug = slugify(instance.name)
        slug = base_slug
        counter = 1
        while Category.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        instance.slug = slug
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
