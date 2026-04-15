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
    # REALISTIC WORK TEMPLATES — Django HR / Employee Management
    # ══════════════════════════════════════════════════════════════

    # ── Django: Employee & Department models ──
    {
        "filename": "models.py",
        "code": """\
from django.db import models
from django.conf import settings
from django.utils import timezone


class Department(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=10, unique=True)
    head = models.ForeignKey(
        "Employee", on_delete=models.SET_NULL, null=True,
        blank=True, related_name="headed_department",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True,
        blank=True, related_name="sub_departments",
    )
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def employee_count(self):
        return self.employees.filter(is_active=True).count()

    @property
    def total_salary_expense(self):
        return self.employees.filter(
            is_active=True
        ).aggregate(
            total=models.Sum("salary")
        )["total"] or 0


class Employee(models.Model):
    ROLE_CHOICES = [
        ("engineer", "Engineer"),
        ("designer", "Designer"),
        ("manager", "Manager"),
        ("analyst", "Analyst"),
        ("support", "Support"),
        ("admin", "Admin"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee"
    )
    employee_id = models.CharField(max_length=20, unique=True, db_index=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="employees"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    title = models.CharField(max_length=100)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    hire_date = models.DateField()
    manager = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True,
        blank=True, related_name="direct_reports",
    )
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_remote = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]
        indexes = [
            models.Index(fields=["department", "is_active"]),
            models.Index(fields=["manager"]),
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name()}"

    @property
    def tenure_days(self):
        return (timezone.now().date() - self.hire_date).days

    @property
    def direct_report_count(self):
        return self.direct_reports.filter(is_active=True).count()


class LeaveRequest(models.Model):
    TYPE_CHOICES = [
        ("annual", "Annual Leave"),
        ("sick", "Sick Leave"),
        ("personal", "Personal Leave"),
        ("parental", "Parental Leave"),
        ("unpaid", "Unpaid Leave"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="leave_requests"
    )
    leave_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="reviewed_leaves",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date} to {self.end_date})"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    def approve(self, reviewer):
        self.status = "approved"
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save()

    def reject(self, reviewer):
        self.status = "rejected"
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save()
""",
    },
    # ── Django: DRF Serializers for HR ──
    {
        "filename": "serializers.py",
        "code": """\
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Department, Employee, LeaveRequest

User = get_user_model()


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.ReadOnlyField()
    head_name = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id", "name", "code", "head", "head_name",
            "parent", "budget", "is_active", "employee_count",
        ]

    def get_head_name(self, obj):
        if obj.head:
            return obj.head.user.get_full_name()
        return None


class EmployeeListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id", "employee_id", "full_name", "email", "department_name",
            "role", "title", "is_active", "is_remote", "hire_date",
        ]


class EmployeeDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(is_active=True),
        source="department", write_only=True,
    )
    manager_name = serializers.SerializerMethodField()
    tenure_days = serializers.ReadOnlyField()
    direct_report_count = serializers.ReadOnlyField()

    class Meta:
        model = Employee
        fields = [
            "id", "employee_id", "full_name", "email",
            "department", "department_id", "role", "title",
            "salary", "hire_date", "manager", "manager_name",
            "phone", "is_active", "is_remote", "notes",
            "tenure_days", "direct_report_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["employee_id", "created_at", "updated_at"]

    def get_manager_name(self, obj):
        if obj.manager:
            return obj.manager.user.get_full_name()
        return None

    def validate_salary(self, value):
        if value < 0:
            raise serializers.ValidationError("Salary cannot be negative.")
        return value


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.user.get_full_name", read_only=True
    )
    duration_days = serializers.ReadOnlyField()
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "leave_type", "status",
            "start_date", "end_date", "duration_days", "reason",
            "reviewed_by", "reviewer_name", "reviewed_at", "created_at",
        ]
        read_only_fields = ["status", "reviewed_by", "reviewed_at"]

    def get_reviewer_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.user.get_full_name()
        return None

    def validate(self, data):
        if data["start_date"] > data["end_date"]:
            raise serializers.ValidationError(
                {"end_date": "End date must be after start date."}
            )
        if data["start_date"] < timezone.now().date():
            raise serializers.ValidationError(
                {"start_date": "Cannot request leave in the past."}
            )
        return data
""",
    },
    # ── Django: ViewSets for HR ──
    {
        "filename": "views.py",
        "code": """\
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone

from .models import Department, Employee, LeaveRequest
from .serializers import (
    DepartmentSerializer,
    EmployeeListSerializer,
    EmployeeDetailSerializer,
    LeaveRequestSerializer,
)
from .pagination import StandardPagination


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "employee_count"]

    @action(detail=True, methods=["get"])
    def employees(self, request, pk=None):
        department = self.get_object()
        employees = Employee.objects.filter(
            department=department, is_active=True
        ).select_related("user", "manager")
        serializer = EmployeeListSerializer(employees, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def headcount_report(self, request):
        departments = Department.objects.filter(is_active=True).annotate(
            total_employees=Count("employees", filter=Q(employees__is_active=True)),
            remote_count=Count(
                "employees",
                filter=Q(employees__is_active=True, employees__is_remote=True),
            ),
            avg_salary=Avg(
                "employees__salary",
                filter=Q(employees__is_active=True),
            ),
        ).order_by("-total_employees")

        data = [
            {
                "department": d.name,
                "code": d.code,
                "headcount": d.total_employees,
                "remote": d.remote_count,
                "avg_salary": round(d.avg_salary or 0, 2),
                "budget": float(d.budget),
            }
            for d in departments
        ]
        return Response(data)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related(
        "user", "department", "manager__user"
    )
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__first_name", "user__last_name", "employee_id"]
    filterset_fields = ["department", "role", "is_active", "is_remote"]
    ordering_fields = ["employee_id", "hire_date", "salary"]
    ordering = ["employee_id"]

    def get_serializer_class(self):
        if self.action == "list":
            return EmployeeListSerializer
        return EmployeeDetailSerializer

    @action(detail=True, methods=["get"])
    def direct_reports(self, request, pk=None):
        employee = self.get_object()
        reports = Employee.objects.filter(
            manager=employee, is_active=True
        ).select_related("user", "department")
        serializer = EmployeeListSerializer(reports, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        employee = self.get_object()
        employee.is_active = False
        employee.save(update_fields=["is_active", "updated_at"])
        return Response({"status": "deactivated"})

    @action(detail=False, methods=["get"])
    def me(self, request):
        try:
            employee = Employee.objects.get(user=request.user)
            serializer = EmployeeDetailSerializer(employee)
            return Response(serializer.data)
        except Employee.DoesNotExist:
            return Response(
                {"error": "No employee profile found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class LeaveRequestViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["leave_type", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = LeaveRequest.objects.select_related(
            "employee__user", "reviewed_by__user"
        )
        if self.request.user.is_staff:
            return qs
        return qs.filter(employee__user=self.request.user)

    def perform_create(self, serializer):
        employee = Employee.objects.get(user=self.request.user)
        serializer.save(employee=employee)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        leave = self.get_object()
        if leave.status != "pending":
            return Response(
                {"error": "Can only approve pending requests"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reviewer = Employee.objects.get(user=request.user)
        leave.approve(reviewer)
        return Response(LeaveRequestSerializer(leave).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        leave = self.get_object()
        if leave.status != "pending":
            return Response(
                {"error": "Can only reject pending requests"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reviewer = Employee.objects.get(user=request.user)
        leave.reject(reviewer)
        return Response(LeaveRequestSerializer(leave).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        employee = Employee.objects.get(user=request.user)
        year = timezone.now().year
        leaves = LeaveRequest.objects.filter(
            employee=employee,
            start_date__year=year,
            status="approved",
        )
        by_type = {}
        for leave in leaves:
            key = leave.leave_type
            by_type[key] = by_type.get(key, 0) + leave.duration_days
        return Response({
            "year": year,
            "used_by_type": by_type,
            "total_used": sum(by_type.values()),
        })
""",
    },
    # ── Django: Celery tasks ──
    {
        "filename": "tasks.py",
        "code": """\
from celery import shared_task
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
import logging
import csv
import io

logger = logging.getLogger(__name__)


@shared_task
def send_leave_reminder_to_managers():
    from .models import LeaveRequest, Employee

    pending = LeaveRequest.objects.filter(
        status="pending",
        created_at__lte=timezone.now() - timedelta(days=2),
    ).select_related("employee__user", "employee__manager__user")

    manager_leaves = {}
    for leave in pending:
        mgr = leave.employee.manager
        if mgr:
            manager_leaves.setdefault(mgr, []).append(leave)

    sent = 0
    for manager, leaves in manager_leaves.items():
        names = ", ".join(l.employee.user.get_full_name() for l in leaves)
        send_mail(
            subject=f"Pending leave requests need review ({len(leaves)})",
            message=(
                f"Hi {manager.user.first_name},\\n\\n"
                f"You have {len(leaves)} pending leave request(s) "
                f"from: {names}.\\n\\n"
                f"Please log in to review them."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[manager.user.email],
            fail_silently=True,
        )
        sent += 1

    logger.info(f"Sent leave reminders to {sent} managers")
    return {"managers_notified": sent, "pending_leaves": pending.count()}


@shared_task
def generate_attendance_report(month=None, year=None):
    from .models import Employee, LeaveRequest

    now = timezone.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    employees = Employee.objects.filter(is_active=True).select_related(
        "user", "department"
    )

    report_rows = []
    for emp in employees:
        leaves = LeaveRequest.objects.filter(
            employee=emp,
            status="approved",
            start_date__year=year,
            start_date__month=month,
        )
        total_leave_days = sum(l.duration_days for l in leaves)
        report_rows.append({
            "employee_id": emp.employee_id,
            "name": emp.user.get_full_name(),
            "department": emp.department.name,
            "leave_days": total_leave_days,
            "working_days": 22 - total_leave_days,
        })

    logger.info(
        f"Attendance report for {year}-{month:02d}: {len(report_rows)} employees"
    )
    return {
        "period": f"{year}-{month:02d}",
        "employee_count": len(report_rows),
        "total_leave_days": sum(r["leave_days"] for r in report_rows),
    }


@shared_task
def notify_upcoming_work_anniversaries(days_ahead=7):
    from .models import Employee

    today = timezone.now().date()
    upcoming = []

    for emp in Employee.objects.filter(is_active=True).select_related("user"):
        anniversary = emp.hire_date.replace(year=today.year)
        if anniversary < today:
            anniversary = anniversary.replace(year=today.year + 1)
        delta = (anniversary - today).days
        if 0 <= delta <= days_ahead:
            years = today.year - emp.hire_date.year
            upcoming.append({
                "employee": emp.user.get_full_name(),
                "years": years,
                "date": str(anniversary),
            })

    for item in upcoming:
        logger.info(
            f"Work anniversary: {item['employee']} - "
            f"{item['years']} years on {item['date']}"
        )

    return {"upcoming_anniversaries": len(upcoming)}


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def sync_employee_directory(self):
    from .models import Employee

    try:
        active = Employee.objects.filter(is_active=True).select_related(
            "user", "department"
        )
        directory = []
        for emp in active:
            directory.append({
                "id": emp.employee_id,
                "name": emp.user.get_full_name(),
                "email": emp.user.email,
                "department": emp.department.name,
                "title": emp.title,
                "phone": emp.phone,
                "is_remote": emp.is_remote,
            })

        logger.info(f"Employee directory synced: {len(directory)} entries")
        return {"synced": len(directory)}

    except Exception as exc:
        logger.error(f"Directory sync failed: {exc}")
        raise self.retry(exc=exc)
""",
    },
    # ── Django: Signals ──
    {
        "filename": "signals.py",
        "code": """\
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
import logging

from .models import Employee, LeaveRequest

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Employee)
def handle_new_employee(sender, instance, created, **kwargs):
    if created:
        logger.info(
            f"New employee: {instance.employee_id} - "
            f"{instance.user.get_full_name()} in {instance.department.name}"
        )
        send_mail(
            subject=f"Welcome to the team, {instance.user.first_name}!",
            message=(
                f"Hi {instance.user.first_name},\\n\\n"
                f"Welcome aboard! Your employee ID is {instance.employee_id}.\\n"
                f"Department: {instance.department.name}\\n"
                f"Title: {instance.title}\\n\\n"
                f"Please complete your onboarding checklist."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.user.email],
            fail_silently=True,
        )

        if instance.manager:
            send_mail(
                subject=f"New team member: {instance.user.get_full_name()}",
                message=(
                    f"Hi {instance.manager.user.first_name},\\n\\n"
                    f"{instance.user.get_full_name()} has joined your team "
                    f"as {instance.title}.\\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.manager.user.email],
                fail_silently=True,
            )


@receiver(pre_save, sender=LeaveRequest)
def track_leave_status_change(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = LeaveRequest.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except LeaveRequest.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=LeaveRequest)
def notify_leave_status(sender, instance, created, **kwargs):
    if created:
        if instance.employee.manager:
            send_mail(
                subject=f"Leave request from {instance.employee.user.get_full_name()}",
                message=(
                    f"{instance.employee.user.get_full_name()} has requested "
                    f"{instance.get_leave_type_display()} from "
                    f"{instance.start_date} to {instance.end_date} "
                    f"({instance.duration_days} days).\\n\\n"
                    f"Reason: {instance.reason or 'Not provided'}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.employee.manager.user.email],
                fail_silently=True,
            )
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status and old_status != instance.status:
        logger.info(
            f"Leave {instance.pk}: {old_status} -> {instance.status}"
        )
        if instance.status in ("approved", "rejected"):
            send_mail(
                subject=f"Leave request {instance.status}",
                message=(
                    f"Your {instance.get_leave_type_display()} request "
                    f"from {instance.start_date} to {instance.end_date} "
                    f"has been {instance.status}."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.employee.user.email],
                fail_silently=True,
            )
""",
    },
    # ── Django: Admin configuration ──
    {
        "filename": "admin.py",
        "code": """\
from django.contrib import admin
from django.utils.html import format_html

from .models import Department, Employee, LeaveRequest


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "head_display", "headcount", "budget_display", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    list_editable = ["is_active"]

    def head_display(self, obj):
        if obj.head:
            return obj.head.user.get_full_name()
        return "-"
    head_display.short_description = "Department Head"

    def headcount(self, obj):
        count = obj.employees.filter(is_active=True).count()
        color = "#e53e3e" if count == 0 else "#38a169"
        return format_html('<span style="color:{}">{}</span>', color, count)
    headcount.short_description = "Employees"

    def budget_display(self, obj):
        return f"${obj.budget:,.2f}"
    budget_display.short_description = "Budget"


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        "employee_id", "full_name", "email", "department",
        "role", "title", "status_badge", "hire_date",
    ]
    list_filter = ["department", "role", "is_active", "is_remote", "hire_date"]
    search_fields = [
        "employee_id", "user__first_name", "user__last_name", "user__email"
    ]
    readonly_fields = ["employee_id", "created_at", "updated_at"]
    list_per_page = 50
    date_hierarchy = "hire_date"

    fieldsets = (
        ("Personal", {
            "fields": ("user", "employee_id", "phone"),
        }),
        ("Position", {
            "fields": ("department", "role", "title", "manager", "salary"),
        }),
        ("Status", {
            "fields": ("is_active", "is_remote", "hire_date"),
        }),
        ("Notes", {
            "fields": ("notes",),
            "classes": ("collapse",),
        }),
    )

    def full_name(self, obj):
        return obj.user.get_full_name()

    def email(self, obj):
        return obj.user.email

    def status_badge(self, obj):
        if not obj.is_active:
            return format_html(
                '<span style="color:#e53e3e;font-weight:bold">Inactive</span>'
            )
        if obj.is_remote:
            return format_html(
                '<span style="color:#3182ce;font-weight:bold">Remote</span>'
            )
        return format_html(
            '<span style="color:#38a169;font-weight:bold">Active</span>'
        )
    status_badge.short_description = "Status"


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id", "employee_name", "leave_type", "status_badge",
        "start_date", "end_date", "duration_days", "created_at",
    ]
    list_filter = ["leave_type", "status", "start_date"]
    search_fields = ["employee__user__first_name", "employee__employee_id"]
    readonly_fields = ["reviewed_by", "reviewed_at", "created_at"]

    def employee_name(self, obj):
        return obj.employee.user.get_full_name()

    def status_badge(self, obj):
        colors = {
            "pending": "#d69e2e",
            "approved": "#38a169",
            "rejected": "#e53e3e",
            "cancelled": "#718096",
        }
        color = colors.get(obj.status, "#718096")
        return format_html(
            '<span style="color:{};font-weight:bold">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"
""",
    },
    # ── Django: Middleware ──
    {
        "filename": "middleware.py",
        "code": """\
import time
import logging
import json
from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache

logger = logging.getLogger(__name__)


class RequestTimingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._start_time = time.monotonic()

    def process_response(self, request, response):
        if hasattr(request, "_start_time"):
            duration_ms = (time.monotonic() - request._start_time) * 1000
            response["X-Response-Time"] = f"{duration_ms:.0f}ms"

            if duration_ms > 2000:
                logger.warning(
                    "Slow request: %s %s took %.0fms",
                    request.method, request.get_full_path(), duration_ms,
                )
        return response


class APIRateLimitMiddleware(MiddlewareMixin):
    LIMIT = getattr(settings, "API_RATE_LIMIT", 100)
    WINDOW = getattr(settings, "API_RATE_WINDOW", 60)

    def process_request(self, request):
        if not request.path.startswith("/api/"):
            return None

        if hasattr(request, "user") and request.user.is_staff:
            return None

        ip = self._get_ip(request)
        key = f"rate:{ip}"
        count = cache.get(key, 0)

        if count >= self.LIMIT:
            logger.warning(f"Rate limit hit: {ip}")
            return JsonResponse(
                {"error": "Too many requests", "retry_after": self.WINDOW},
                status=429,
            )

        cache.set(key, count + 1, self.WINDOW)
        return None

    def _get_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")


class AuditLogMiddleware(MiddlewareMixin):
    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def process_response(self, request, response):
        if request.method not in self.AUDIT_METHODS:
            return response
        if not request.path.startswith("/api/"):
            return response

        user = "anonymous"
        if hasattr(request, "user") and request.user.is_authenticated:
            user = request.user.email

        log_entry = {
            "user": user,
            "method": request.method,
            "path": request.get_full_path(),
            "status": response.status_code,
        }

        if response.status_code >= 400:
            logger.warning("Audit: %s", json.dumps(log_entry))
        else:
            logger.info("Audit: %s", json.dumps(log_entry))

        return response
""",
    },
    # ── Django: Tests ──
    {
        "filename": "test_hr.py",
        "code": """\
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from .models import Department, Employee, LeaveRequest

User = get_user_model()


class EmployeeModelTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name="Engineering", code="ENG", budget=Decimal("500000")
        )
        self.user = User.objects.create_user(
            username="jdoe", email="jdoe@company.com",
            password="pass123", first_name="John", last_name="Doe",
        )
        self.employee = Employee.objects.create(
            user=self.user, employee_id="EMP-001",
            department=self.dept, role="engineer",
            title="Senior Developer", salary=Decimal("95000"),
            hire_date=date(2022, 3, 15),
        )

    def test_employee_str(self):
        self.assertIn("EMP-001", str(self.employee))

    def test_tenure_calculation(self):
        self.assertGreater(self.employee.tenure_days, 0)

    def test_department_employee_count(self):
        self.assertEqual(self.dept.employee_count, 1)

    def test_department_salary_expense(self):
        self.assertEqual(self.dept.total_salary_expense, Decimal("95000"))


class LeaveRequestTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Design", code="DSN")
        self.mgr_user = User.objects.create_user(
            username="mgr", email="mgr@company.com", password="pass",
        )
        self.manager = Employee.objects.create(
            user=self.mgr_user, employee_id="EMP-MGR",
            department=self.dept, role="manager",
            title="Design Lead", salary=Decimal("110000"),
            hire_date=date(2020, 1, 10),
        )
        self.emp_user = User.objects.create_user(
            username="emp", email="emp@company.com", password="pass",
        )
        self.employee = Employee.objects.create(
            user=self.emp_user, employee_id="EMP-002",
            department=self.dept, role="designer",
            title="UI Designer", salary=Decimal("75000"),
            hire_date=date(2023, 6, 1), manager=self.manager,
        )

    def test_create_leave_request(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type="annual",
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=14),
            reason="Vacation",
        )
        self.assertEqual(leave.status, "pending")
        self.assertEqual(leave.duration_days, 5)

    def test_approve_leave(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type="sick",
            start_date=date.today() + timedelta(days=1),
            end_date=date.today() + timedelta(days=2),
        )
        leave.approve(self.manager)
        self.assertEqual(leave.status, "approved")
        self.assertEqual(leave.reviewed_by, self.manager)
        self.assertIsNotNone(leave.reviewed_at)

    def test_reject_leave(self):
        leave = LeaveRequest.objects.create(
            employee=self.employee, leave_type="personal",
            start_date=date.today() + timedelta(days=5),
            end_date=date.today() + timedelta(days=5),
        )
        leave.reject(self.manager)
        self.assertEqual(leave.status, "rejected")


class LeaveAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept = Department.objects.create(name="Support", code="SUP")
        self.user = User.objects.create_user(
            username="agent", email="agent@company.com", password="pass",
        )
        self.employee = Employee.objects.create(
            user=self.user, employee_id="EMP-003",
            department=self.dept, role="support",
            title="Support Agent", salary=Decimal("55000"),
            hire_date=date(2024, 1, 15),
        )

    def test_create_leave_authenticated(self):
        self.client.force_authenticate(user=self.user)
        data = {
            "leave_type": "annual",
            "start_date": str(date.today() + timedelta(days=30)),
            "end_date": str(date.today() + timedelta(days=34)),
            "reason": "Family trip",
        }
        response = self.client.post("/api/leave-requests/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_leave_unauthenticated(self):
        data = {
            "leave_type": "sick",
            "start_date": str(date.today() + timedelta(days=1)),
            "end_date": str(date.today() + timedelta(days=1)),
        }
        response = self.client.post("/api/leave-requests/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_sees_only_own_leaves(self):
        self.client.force_authenticate(user=self.user)
        LeaveRequest.objects.create(
            employee=self.employee, leave_type="annual",
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=12),
        )
        other_user = User.objects.create_user(
            username="other", email="other@company.com", password="pass",
        )
        other_emp = Employee.objects.create(
            user=other_user, employee_id="EMP-004",
            department=self.dept, role="support",
            title="Agent", salary=Decimal("50000"),
            hire_date=date(2024, 6, 1),
        )
        LeaveRequest.objects.create(
            employee=other_emp, leave_type="sick",
            start_date=date.today() + timedelta(days=5),
            end_date=date.today() + timedelta(days=5),
        )
        response = self.client.get("/api/leave-requests/")
        self.assertEqual(len(response.data["results"]), 1)
""",
    },
    # ── Django: URL config ──
    {
        "filename": "urls.py",
        "code": """\
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import DepartmentViewSet, EmployeeViewSet, LeaveRequestViewSet

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")

app_name = "hr"

urlpatterns = [
    path("api/", include(router.urls)),
]
""",
    },
    # ── Django: Permissions ──
    {
        "filename": "permissions.py",
        "code": """\
from rest_framework.permissions import BasePermission


class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        try:
            employee = request.user.employee
            return employee.role in ("manager", "admin")
        except AttributeError:
            return False

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        try:
            employee = request.user.employee
            if hasattr(obj, "employee") and obj.employee.manager == employee:
                return True
            return employee.role == "admin"
        except AttributeError:
            return False


class IsHRAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        try:
            return request.user.employee.role == "admin"
        except AttributeError:
            return False


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        if hasattr(obj, "user"):
            return obj.user == request.user
        if hasattr(obj, "employee"):
            return obj.employee.user == request.user
        return False
""",
    },
    # ── Django: Filters ──
    {
        "filename": "filters.py",
        "code": """\
import django_filters
from django.db.models import Q

from .models import Employee, LeaveRequest


class EmployeeFilter(django_filters.FilterSet):
    department = django_filters.CharFilter(field_name="department__code")
    role = django_filters.ChoiceFilter(choices=Employee.ROLE_CHOICES)
    hired_after = django_filters.DateFilter(field_name="hire_date", lookup_expr="gte")
    hired_before = django_filters.DateFilter(field_name="hire_date", lookup_expr="lte")
    min_salary = django_filters.NumberFilter(field_name="salary", lookup_expr="gte")
    max_salary = django_filters.NumberFilter(field_name="salary", lookup_expr="lte")
    is_remote = django_filters.BooleanFilter()
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Employee
        fields = ["department", "role", "is_active", "is_remote"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(user__first_name__icontains=value)
            | Q(user__last_name__icontains=value)
            | Q(employee_id__icontains=value)
            | Q(user__email__icontains=value)
        )


class LeaveFilter(django_filters.FilterSet):
    leave_type = django_filters.ChoiceFilter(choices=LeaveRequest.TYPE_CHOICES)
    status = django_filters.ChoiceFilter(choices=LeaveRequest.STATUS_CHOICES)
    employee_id = django_filters.CharFilter(field_name="employee__employee_id")
    department = django_filters.CharFilter(field_name="employee__department__code")
    date_from = django_filters.DateFilter(field_name="start_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="end_date", lookup_expr="lte")

    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "status"]
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
