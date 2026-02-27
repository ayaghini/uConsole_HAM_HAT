#!/usr/bin/env python3
"""Shared UI widget helpers and reusable components."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


# ---------------------------------------------------------------------------
# Row helper
# ---------------------------------------------------------------------------

def add_row(frame: ttk.Frame, label: str, widget: tk.Widget, row: int) -> None:
    ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
    widget.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=2)


def scrollable_frame(parent: ttk.Frame) -> tuple[tk.Canvas, ttk.Scrollbar, ttk.Frame]:
    """Return (canvas, scrollbar, inner_frame) for a scrollable tab."""
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)
    canvas = tk.Canvas(container, highlightthickness=0)
    vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    inner = ttk.Frame(canvas, padding=10)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_config(_e: tk.Event) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_config(_e: tk.Event) -> None:
        new_w = canvas.winfo_width()
        new_h = max(canvas.winfo_height(), inner.winfo_reqheight())
        canvas.itemconfigure(win_id, width=new_w, height=new_h)

    def _on_mousewheel(e: tk.Event) -> None:
        delta = -1 * int(e.delta / 120) if e.delta else 0
        if delta:
            canvas.yview_scroll(delta, "units")

    inner.bind("<Configure>", _on_inner_config)
    canvas.bind("<Configure>", _on_canvas_config)
    canvas.bind("<MouseWheel>", _on_mousewheel)
    return canvas, vsb, inner


# ---------------------------------------------------------------------------
# Bounded log widget (auto-trims to max_lines)
# ---------------------------------------------------------------------------

class BoundedLog(ScrolledText):
    """ScrolledText that keeps at most max_lines lines to prevent memory growth."""

    MAX_LINES = 800

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, **kwargs)

    def append(self, msg: str) -> None:
        was_disabled = str(self.cget("state")) == "disabled"
        if was_disabled:
            self.configure(state="normal")
        self.insert("end", msg + "\n")
        self.see("end")
        # Trim if over limit
        lines = int(self.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            excess = lines - self.MAX_LINES
            self.delete("1.0", f"{excess + 1}.0")
        if was_disabled:
            self.configure(state="disabled")


# ---------------------------------------------------------------------------
# Waterfall canvas
# ---------------------------------------------------------------------------

# Pre-computed 256-entry colour LUT for waterfall (deep-blue → cyan → yellow → red)
_WF_LUT: list[str] = []

def _build_wf_lut() -> list[str]:
    lut: list[str] = []
    for x in range(256):
        if x < 64:
            r, g, b = 0, 0, 30 + (x * 2)
        elif x < 128:
            t = x - 64
            r, g, b = 0, t * 3, 160 + (t // 2)
        elif x < 192:
            t = x - 128
            r, g, b = t * 3, 180 + t, 255 - t * 3
        else:
            t = x - 192
            r, g, b = 200 + t * 2, 255 - t, 60 - min(60, t * 2)
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        lut.append(f"#{r:02x}{g:02x}{b:02x}")
    return lut

_WF_LUT = _build_wf_lut()


class WaterfallCanvas(tk.Canvas):
    """Rolling waterfall display. Call push_spectrum(row_array) to update."""

    def __init__(self, parent: tk.Widget, width: int = 640, height: int = 96, **kwargs) -> None:
        super().__init__(parent, width=width, height=height,
                         background="#081018", highlightthickness=1,
                         highlightbackground="#1d3448", **kwargs)
        self._w = width
        self._h = height
        self._buf = np.zeros((self._h, self._w), dtype=np.uint8)
        self._photo: Optional[tk.PhotoImage] = tk.PhotoImage(width=self._w, height=self._h)
        self.create_image(0, 0, image=self._photo, anchor="nw")
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event: tk.Event) -> None:
        new_w = max(240, int(event.width))
        new_h = max(64, min(140, int(event.height)))
        if new_w == self._w and new_h == self._h:
            return
        self._w = new_w
        self._h = new_h
        self._buf = np.zeros((self._h, self._w), dtype=np.uint8)
        self._photo = tk.PhotoImage(width=self._w, height=self._h)
        self.delete("all")
        self.create_image(0, 0, image=self._photo, anchor="nw")

    def push_spectrum(self, rate: int, mono: np.ndarray) -> None:
        """Compute spectrum row from audio samples and push to waterfall."""
        row = self._spectrum_row(rate, mono)
        if row is None:
            return
        self._buf[:-1, :] = self._buf[1:, :]
        self._buf[-1, :] = row
        self._redraw()

    def _spectrum_row(self, rate: int, mono: np.ndarray) -> Optional[np.ndarray]:
        x = np.asarray(mono, dtype=np.float32).reshape(-1)
        if len(x) < 256:
            return None
        x = x - float(np.mean(x))
        nfft = 1024
        if len(x) < nfft:
            pad = np.zeros(nfft, dtype=np.float32)
            pad[:len(x)] = x
            xw = pad
        else:
            xw = x[-nfft:]
        xw = xw * np.hanning(len(xw)).astype(np.float32)
        spec = np.fft.rfft(xw)
        mag = np.abs(spec)
        freqs = np.fft.rfftfreq(len(xw), d=1.0 / float(rate))
        mask = (freqs >= 0.0) & (freqs <= 3000.0)
        mag = mag[mask]
        if len(mag) < 8:
            return None
        tgt = np.linspace(0, len(mag) - 1, self._w)
        vals = np.interp(tgt, np.arange(len(mag)), mag)
        vals = np.log10(1.0 + vals)
        vmax = float(np.max(vals))
        if vmax > 1e-9:
            vals /= vmax
        return np.clip((vals * 255.0).astype(np.int32), 0, 255).astype(np.uint8)

    def _redraw(self) -> None:
        if self._photo is None:
            return
        rows_str = []
        for y in range(self._h):
            # Build row from LUT — much faster than calling _wf_color per pixel
            rows_str.append("{" + " ".join(_WF_LUT[v] for v in self._buf[y, :]) + "}")
        self._photo.put(" ".join(rows_str), to=(0, 0, self._w, self._h))


# ---------------------------------------------------------------------------
# Simple offline map canvas
# ---------------------------------------------------------------------------

class AprsMapCanvas(tk.Canvas):
    """Offline lat/lon map with zoom + pan."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, background="#10212b", highlightthickness=0, **kwargs)
        self._points: list[tuple[float, float, str]] = []
        self._last_pos: Optional[tuple[float, float, str]] = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_last: Optional[tuple[int, int]] = None
        self._pick_radius = 8.0
        self._on_pick: Optional[callable] = None

        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_wheel)

    def set_on_pick(self, cb) -> None:
        self._on_pick = cb

    def add_point(self, lat: float, lon: float, label: str) -> None:
        self._points.append((lat, lon, label))
        if len(self._points) > 200:
            self._points = self._points[-120:]
        if len(self._points) == 1:
            w = max(10, self.winfo_width() or 400)
            h = max(10, self.winfo_height() or 300)
            wx = ((max(-180.0, min(180.0, lon)) + 180.0) / 360.0) * w * self._zoom
            wy = ((90.0 - max(-90.0, min(90.0, lat))) / 180.0) * h * self._zoom
            self._pan_x = wx - w / 2.0
            self._pan_y = wy - h / 2.0
        self._last_pos = (lat, lon, label)
        self._draw()

    def clear(self) -> None:
        self._points.clear()
        self._last_pos = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._draw()

    @property
    def last_position(self) -> Optional[tuple[float, float, str]]:
        return self._last_pos

    def _latlon_to_xy(self, lat: float, lon: float, w: int, h: int) -> tuple[float, float]:
        ww = w * self._zoom
        wh = h * self._zoom
        wx = ((max(-180.0, min(180.0, lon)) + 180.0) / 360.0) * ww
        wy = ((90.0 - max(-90.0, min(90.0, lat))) / 180.0) * wh
        return wx - self._pan_x, wy - self._pan_y

    def _xy_to_latlon(self, x: float, y: float, w: int, h: int) -> tuple[float, float]:
        ww = w * self._zoom
        wh = h * self._zoom
        wx = x + self._pan_x
        wy = y + self._pan_y
        lon = (wx / max(1.0, ww)) * 360.0 - 180.0
        lat = 90.0 - (wy / max(1.0, wh)) * 180.0
        return max(-90.0, min(90.0, lat)), max(-180.0, min(180.0, lon))

    def _draw(self) -> None:
        self.delete("all")
        w = max(10, self.winfo_width() or 400)
        h = max(10, self.winfo_height() or 300)
        self.create_rectangle(0, 0, w, h, fill="#0f2531", outline="")
        for lon in range(-180, 181, 30):
            x, _ = self._latlon_to_xy(0.0, float(lon), w, h)
            if -5 < x < w + 5:
                self.create_line(x, 0, x, h, fill="#21465d")
        for lat in range(-90, 91, 15):
            _, y = self._latlon_to_xy(float(lat), 0.0, w, h)
            if -5 < y < h + 5:
                self.create_line(0, y, w, y, fill="#21465d")
        self.create_text(8, 8, anchor="nw", text="Offline APRS Map  (drag=pan  wheel=zoom)", fill="#d9edf7")
        if not self._points:
            self.create_text(w / 2, h / 2, text="No APRS positions yet", fill="#9cc4dd")
            return
        for lat, lon, label in self._points[-120:]:
            x, y = self._latlon_to_xy(lat, lon, w, h)
            if x < -10 or y < -10 or x > w + 10 or y > h + 10:
                continue
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#ffd166", outline="")
            self.create_text(x + 6, y - 6, anchor="nw", text=label[:18], fill="#f5f7fa")

    def _on_press(self, event: tk.Event) -> None:
        self._drag_last = (int(event.x), int(event.y))

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_last is None:
            return
        lx, ly = self._drag_last
        self._pan_x -= int(event.x) - lx
        self._pan_y -= int(event.y) - ly
        self._drag_last = (int(event.x), int(event.y))
        self._draw()

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_last is None:
            return
        was_click = abs(int(event.x) - self._drag_last[0]) < 4 and abs(int(event.y) - self._drag_last[1]) < 4
        self._drag_last = None
        if not was_click or not self._on_pick:
            return
        w = max(10, self.winfo_width() or 400)
        h = max(10, self.winfo_height() or 300)
        ex, ey = float(event.x), float(event.y)
        nearest: Optional[tuple[float, float, str, float]] = None
        for lat, lon, label in self._points[-120:]:
            x, y = self._latlon_to_xy(lat, lon, w, h)
            d = math.hypot(x - ex, y - ey)
            if nearest is None or d < nearest[3]:
                nearest = (lat, lon, label, d)
        if nearest and nearest[3] <= self._pick_radius:
            self._on_pick(nearest[0], nearest[1], nearest[2])

    def _on_wheel(self, event: tk.Event) -> None:
        w = max(10, self.winfo_width() or 400)
        h = max(10, self.winfo_height() or 300)
        px, py = float(event.x), float(event.y)
        lat0, lon0 = self._xy_to_latlon(px, py, w, h)
        factor = 1.15 if event.delta > 0 else (1.0 / 1.15)
        self._zoom = max(1.0, min(8.0, self._zoom * factor))
        nx, ny = self._latlon_to_xy(lat0, lon0, w, h)
        self._pan_x += nx - px
        self._pan_y += ny - py
        self._draw()
