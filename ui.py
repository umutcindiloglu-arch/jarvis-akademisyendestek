"""JARVIS HUD — tam ekran, sinematik çok-panelli arayüz.

Iron Man tarzı bir kontrol ekranı: solda saat / hava durumu / sistem durumu,
ortada dönen radar küresi ve parçacıklar, sağda canlı konuşma günlüğü ve metin
girişi, altta LIVE / PAUSE / SHUTDOWN kontrolleri.

Mimari notlar
-------------
* Her şey tek bir tam ekran Canvas'a 30 fps çizilir. Dinamik öğeler "dyn"
  etiketiyle çizilip her karede silinir; metin girişi ve SEND düğmesi ise
  gerçek tkinter widget'larıdır ve canvas'ın üstüne `place` ile yerleştirilir.
* Sistem ölçümleri ve hava durumu arka plan thread'lerinde toplanır.
* Worker thread (main.py) ile iletişim: `add_message`, `paused`, `text_queue`,
  `should_quit`. UI güncellemeleri ana thread'e `root.after` ile aktarılır.
"""

import datetime
import math
import queue
import random
import threading
import time
import tkinter as tk

import sysinfo
import weather

# --- Tema ------------------------------------------------------------------
BG = "#04070b"
PANEL_BG = "#070c12"
CYAN = "#27e0d0"
CYAN_DIM = "#0f6b66"
GREEN = "#39d98a"
AMBER = "#f5a623"
RED = "#ff4d5e"
BLUE = "#4d8cff"
TEXT = "#cfe3ee"
TEXT_DIM = "#5c7080"
GRID = "#0c2230"

STATE_TEXT = {
    "idle": ("Hazır", CYAN),
    "sleeping": ("Uykuda · 'JARVIS wake up'", CYAN_DIM),
    "listening": ("Listening", GREEN),
    "thinking": ("Thinking", AMBER),
    "speaking": ("Speaking", RED),
    "error": ("Error", AMBER),
}

GUNLER = {
    "Monday": "PAZARTESİ", "Tuesday": "SALI", "Wednesday": "ÇARŞAMBA",
    "Thursday": "PERŞEMBE", "Friday": "CUMA", "Saturday": "CUMARTESİ",
    "Sunday": "PAZAR",
}
AYLAR = {
    1: "OCAK", 2: "ŞUBAT", 3: "MART", 4: "NİSAN", 5: "MAYIS", 6: "HAZİRAN",
    7: "TEMMUZ", 8: "AĞUSTOS", 9: "EYLÜL", 10: "EKİM", 11: "KASIM", 12: "ARALIK",
}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(color, t, toward=BG):
    r, g, b = _hex_to_rgb(color)
    tr, tg, tb = _hex_to_rgb(toward)
    return "#%02x%02x%02x" % (
        int(r * (1 - t) + tr * t),
        int(g * (1 - t) + tg * t),
        int(b * (1 - t) + tb * t),
    )


def _load_color(p):
    if p is None:
        return TEXT_DIM
    if p < 60:
        return GREEN
    if p < 85:
        return AMBER
    return RED


class HUD:
    def __init__(self, title="JARVIS", on_ready=None, on_quit=None, show_chat=False,
                 profile=None):
        self.on_ready = on_ready
        self.on_quit = on_quit      # kapanırken çağrılır (ör. çalan sesi durdur)
        self.show_chat = show_chat  # sağ sohbet paneli + metin girişi gösterilsin mi
        # Hava durumu konumu kullanıcı profilinden (kurulum sihirbazı yazar).
        profile = profile or {}
        self.wx_lat = profile.get("enlem", weather.DEFAULT_LAT)
        self.wx_lon = profile.get("boylam", weather.DEFAULT_LON)
        self.wx_city = profile.get("sehir", weather.DEFAULT_CITY)
        self.state = "idle"
        self.amplitude = 0.0
        self.phase = 0.0
        self.start_time = time.time()
        self.wave_until = 0.0       # bu ana kadar küre 'yüz' olup el sallar

        # Worker ile paylaşılan durum.
        self.paused = False
        self.should_quit = False
        self.text_queue = queue.Queue()
        self.messages = []  # (etiket, metin, renk)

        # Arka plan verileri.
        self.cpu = self.ram = self.disk = 0.0
        self.ram_txt = ""
        self.gpu = None
        self.battery = None
        self.net_up = self.net_down = 0.0
        self.weather = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.attributes("-fullscreen", True)
        self.W = self.root.winfo_screenwidth()
        self.H = self.root.winfo_screenheight()

        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._layout()
        self._make_particles()
        if self.show_chat:
            self._build_input()

        self.canvas.bind("<Button-1>", self._on_click)
        self.root.bind("<Escape>", lambda _e: self._quit())
        self.buttons = {}

        self._start_collectors()
        self.root.after(400, self._fire_ready)
        self._animate()

    # --- Yerleşim hesapları -------------------------------------------------

    def _layout(self):
        m = int(self.W * 0.018)
        self.m = m
        self.lp = (m, 96, int(self.W * 0.26), self.H - m)            # sol panel
        self.rp = (int(self.W * 0.71), 96, self.W - m, self.H - m)   # sağ panel
        # Sohbet gizliyse radarı sol panel ile ekran sağ kenarı arasında ortala.
        right_bound = self.rp[0] if self.show_chat else (self.W - m)
        self.cx = (self.lp[2] + right_bound) // 2
        self.cy = int(self.H * 0.50)
        self.R = int(min(self.cx - self.lp[2], right_bound - self.cx, self.H * 0.34) * 0.96)

    def _make_particles(self):
        self.particles = []
        for _ in range(150):
            self.particles.append({
                "ang": random.uniform(0, 2 * math.pi),
                "rad": random.uniform(0.05, 0.98),
                "sz": random.uniform(1.0, 3.2),
                "sp": random.uniform(-0.012, 0.012),
                "br": random.uniform(0.3, 1.0),
            })

    def _build_input(self):
        self.entry = tk.Entry(
            self.root, bg="#0a141c", fg=TEXT, insertbackground=CYAN,
            relief="flat", font=("Helvetica Neue", 14),
            highlightthickness=1, highlightbackground=CYAN_DIM, highlightcolor=CYAN,
        )
        ex0 = self.rp[0] + 14
        ew = (self.rp[2] - self.rp[0]) - 130
        ey = self.rp[3] - 46
        self.entry.place(x=ex0, y=ey, width=ew, height=34)
        self.entry.bind("<Return>", lambda _e: self._submit_text())

        self.send_btn = tk.Button(
            self.root, text="SEND  ▶", command=self._submit_text,
            bg=AMBER, fg="#1a1206", relief="flat", font=("Helvetica Neue", 13, "bold"),
            activebackground="#ffbe4d", cursor="hand2",
        )
        self.send_btn.place(x=ex0 + ew + 12, y=ey, width=100, height=34)

    # --- Worker arayüzü -----------------------------------------------------

    def add_message(self, label, text, color=None):
        self.root.after(0, self._add_message, label, text, color or TEXT)

    def _add_message(self, label, text, color):
        self.messages.append((label, text, color))
        self.messages = self.messages[-40:]

    def set_state(self, state):
        self.root.after(0, self._set_state, state)

    def _set_state(self, state):
        self.state = state if state in STATE_TEXT else "idle"

    def wave(self, seconds=4.5):
        """Küreyi geçici olarak 'yüz'e dönüştürüp katılımcılara el sallatır."""
        self.root.after(0, self._start_wave, seconds)

    def _start_wave(self, seconds):
        self.wave_until = time.time() + seconds

    # main.py geriye dönük uyumluluk için (eski set_caption çağrıları).
    def set_caption(self, text):
        self.add_message("SYS", text, CYAN)

    def _submit_text(self):
        txt = self.entry.get().strip()
        if txt:
            self.text_queue.put(txt)
            self.entry.delete(0, "end")

    # --- Arka plan toplayıcılar --------------------------------------------

    def _start_collectors(self):
        threading.Thread(target=self._stats_loop, daemon=True).start()
        threading.Thread(target=self._weather_loop, daemon=True).start()

    def _stats_loop(self):
        while not self.should_quit:
            self.cpu = sysinfo.cpu_percent()
            self.ram = sysinfo.ram_percent()
            self.ram_txt = sysinfo.ram_detail()
            self.disk = sysinfo.disk_percent()
            self.gpu = sysinfo.gpu_percent()
            self.battery = sysinfo.battery()
            self.net_up, self.net_down = sysinfo.net_rates()
            time.sleep(1.0)

    def _weather_loop(self):
        while not self.should_quit:
            self.weather = weather.fetch(self.wx_lat, self.wx_lon, self.wx_city)
            time.sleep(900)

    # --- Etkileşim ----------------------------------------------------------

    def _on_click(self, e):
        for name, (x0, y0, x1, y1) in self.buttons.items():
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                if name == "shutdown":
                    self._quit()
                elif name == "pause":
                    self.paused = True
                elif name == "live":
                    self.paused = False
                return

    def _quit(self):
        self.should_quit = True
        if self.on_quit:
            try:
                self.on_quit()      # ör. çalan sesi anında kes
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # --- Çizim döngüsü ------------------------------------------------------

    def _target_amplitude(self):
        if self.state == "speaking":
            return 0.85 + random.uniform(0, 0.3)
        if self.state == "listening":
            return 0.5 + random.uniform(0, 0.25)
        if self.state == "thinking":
            return 0.35
        return 0.14

    def _animate(self):
        if self.should_quit:
            return
        self.phase += 0.06
        self.amplitude += (self._target_amplitude() - self.amplitude) * 0.16

        self.canvas.delete("dyn")
        self._draw_frame_chrome()
        self._draw_header()
        self._draw_left_panel()
        self._draw_radar()
        self._draw_controls()
        if self.show_chat:
            self._draw_right_panel()

        self.root.after(33, self._animate)

    def _t(self, *a, **k):
        """create_text kısayolu — her zaman 'dyn' etiketiyle."""
        k.setdefault("tags", "dyn")
        return self.canvas.create_text(*a, **k)

    def _brackets(self, x0, y0, x1, y1, col, L=18):
        c = self.canvas
        for (x, y, dx, dy) in [
            (x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1),
        ]:
            c.create_line(x, y, x + dx * L, y, fill=col, width=2, tags="dyn")
            c.create_line(x, y, x, y + dy * L, fill=col, width=2, tags="dyn")

    def _draw_frame_chrome(self):
        # Köşe çerçeveleri (tüm ekran).
        self._brackets(10, 10, self.W - 10, self.H - 10, CYAN_DIM, L=26)

    def _draw_header(self):
        c = self.canvas
        self._t(self.W / 2, 40, text="J.A.R.V.I.S", fill=CYAN,
                font=("Helvetica Neue", 30, "bold"))
        self._t(self.W / 2, 72, text="Just A Rather Very Intelligent System",
                fill=TEXT_DIM, font=("Helvetica Neue", 12))
        # sol üst panel
        self._brackets(self.m, 22, int(self.W * 0.18), 78, CYAN_DIM, L=14)
        self._t(self.m + 14, 38, text="SYSTEM SETTINGS", anchor="w", fill=CYAN,
                font=("Helvetica Neue", 12, "bold"))
        self._t(self.m + 14, 58, text="VOICE CORE · macOS", anchor="w", fill=TEXT_DIM,
                font=("Helvetica Neue", 10))
        # sağ üst online
        blink = GREEN if int(self.phase * 2) % 2 == 0 else _mix(GREEN, 0.5)
        self._t(self.W - self.m - 16, 40, text="ONLINE", anchor="e", fill=GREEN,
                font=("Helvetica Neue", 13, "bold"))
        c.create_oval(self.W - self.m - 86, 34, self.W - self.m - 76, 44,
                      fill=blink, outline="", tags="dyn")

    # --- Sol panel ----------------------------------------------------------

    def _panel(self, box, title):
        x0, y0, x1, y1 = box
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=GRID, fill=PANEL_BG,
                                     tags="dyn")
        self._brackets(x0, y0, x1, y1, CYAN_DIM, L=16)
        self._t(x0 + 16, y0 + 16, text=title, anchor="w", fill=CYAN,
                font=("Helvetica Neue", 12, "bold"))

    def _draw_left_panel(self):
        x0, y0, x1, _y1 = self.lp
        now = datetime.datetime.now()
        gun = GUNLER.get(now.strftime("%A"), "")
        ay = AYLAR.get(now.month, "")

        # TIME
        self._t(x0 + 16, y0 + 4, text="TIME", anchor="w", fill=CYAN,
                font=("Helvetica Neue", 12, "bold"))
        self._t(x0 + 14, y0 + 56, text=now.strftime("%H:%M"), anchor="w", fill=CYAN,
                font=("Helvetica Neue", 56, "bold"))
        self._t(x0 + 16, y0 + 96, text=now.strftime(":%S"), anchor="w", fill=AMBER,
                font=("Menlo", 16, "bold"))
        self._t(x0 + 16, y0 + 126, text=f"{now.day} {ay} {now.year}", anchor="w",
                fill=AMBER, font=("Helvetica Neue", 14, "bold"))
        self._t(x0 + 16, y0 + 148, text=gun, anchor="w", fill=TEXT_DIM,
                font=("Helvetica Neue", 12))

        # WEATHER
        wy = y0 + 188
        if self.weather:
            city = self.weather["city"]; temp = self.weather["temp"]; desc = self.weather["desc"]
        else:
            city, temp, desc = (self.wx_city or "—").upper(), "—", "alınıyor…"
        self.canvas.create_line(x0 + 14, wy - 8, x1 - 14, wy - 8, fill=GRID, tags="dyn")
        self._t(x0 + 16, wy, text=f"WEATHER · {city}", anchor="w", fill=BLUE,
                font=("Helvetica Neue", 12, "bold"))
        self._t(x0 + 14, wy + 44, text=f"{temp}°C", anchor="w", fill=CYAN,
                font=("Helvetica Neue", 40, "bold"))
        self._t(x0 + 16, wy + 76, text=desc, anchor="w", fill=TEXT_DIM,
                font=("Helvetica Neue", 12))

        # SYSTEM STATUS
        sy = wy + 116
        self.canvas.create_line(x0 + 14, sy - 8, x1 - 14, sy - 8, fill=GRID, tags="dyn")
        self._t(x0 + 16, sy, text="SYSTEM STATUS", anchor="w", fill=CYAN,
                font=("Helvetica Neue", 12, "bold"))
        up = time.time() - self.start_time
        self._t(x0 + 16, sy + 22, anchor="w", fill=TEXT_DIM, font=("Menlo", 10),
                text=f"UPTIME {time.strftime('%H:%M:%S', time.gmtime(up))}")

        bx0, bx1 = x0 + 16, x1 - 16
        rows = [
            ("CPU", self.cpu, f"{self.cpu:.0f}%"),
            ("RAM", self.ram, f"{self.ram:.0f}%"),
            ("GPU", self.gpu, "—" if self.gpu is None else f"{self.gpu:.0f}%"),
            ("DISK", self.disk, f"{self.disk:.0f}%"),
        ]
        by = sy + 44
        for label, pct, val in rows:
            self._bar(label, pct, val, bx0, bx1, by, _load_color(pct))
            by += 34
        if self.battery:
            bp, plugged = self.battery
            col = GREEN if (bp > 30 or plugged) else RED
            self._bar("BATTERY", bp, f"{bp}%" + (" ⚡" if plugged else ""),
                      bx0, bx1, by, col)
            by += 34
        self._t(bx0, by + 6, anchor="w", fill=AMBER, font=("Menlo", 10),
                text=f"▲ {self.net_up:.1f} KB/s")
        self._t(bx1, by + 6, anchor="e", fill=GREEN, font=("Menlo", 10),
                text=f"▼ {self.net_down:.1f} KB/s")

    def _bar(self, label, pct, val, x0, x1, y, col):
        c = self.canvas
        self._t(x0, y - 10, text=label, anchor="w", fill=TEXT_DIM,
                font=("Menlo", 10, "bold"))
        self._t(x1, y - 10, text=val, anchor="e", fill=TEXT, font=("Menlo", 10, "bold"))
        c.create_rectangle(x0, y, x1, y + 5, outline="", fill="#0c1a22", tags="dyn")
        fp = 0 if pct is None else max(0, min(100, pct))
        fw = x0 + (x1 - x0) * fp / 100
        if fw > x0:
            c.create_rectangle(x0, y, fw, y + 5, outline="", fill=col, tags="dyn")

    # --- Merkez radar -------------------------------------------------------

    def _draw_radar(self):
        c = self.canvas
        cx, cy, R = self.cx, self.cy, self.R
        col = STATE_TEXT[self.state][1]

        # dış disk
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=_mix(col, 0.6),
                      fill="#050a0e", width=2, tags="dyn")
        # eşmerkezli ağ halkaları
        for f in (0.32, 0.55, 0.78):
            r = R * f
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=GRID, tags="dyn")
        # ışın çizgileri
        for k in range(12):
            a = math.radians(k * 30 + self.phase * 6)
            c.create_line(cx, cy, cx + R * math.cos(a), cy + R * math.sin(a),
                          fill=_mix(GRID, 0.2, toward=CYAN), tags="dyn")

        # parçacıklar
        for p in self.particles:
            p["ang"] += p["sp"]
            r = R * p["rad"]
            x = cx + r * math.cos(p["ang"]); y = cy + r * math.sin(p["ang"])
            s = p["sz"] * (1 + 0.3 * self.amplitude)
            shade = _mix(GREEN, 1 - p["br"])
            c.create_oval(x - s, y - s, x + s, y + s, fill=shade, outline="", tags="dyn")

        # dönen yaylar (farklı hız/yön)
        for i, (f, ext, spd, w) in enumerate([
            (1.06, 70, 0.9, 3), (0.92, 120, -0.6, 2), (0.70, 200, 1.4, 2)
        ]):
            r = R * f
            start = (self.phase * spd * 40) % 360
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=ext,
                         style="arc", outline=_mix(col, 0.25 + 0.1 * i), width=w, tags="dyn")
        # hızlı tarama
        sweep = (-self.phase * 90) % 360
        r = R * 0.82
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=sweep, extent=8,
                     style="arc", outline=col, width=3, tags="dyn")

        # merkez nabız
        core = 10 + 14 * self.amplitude
        c.create_oval(cx - core, cy - core, cx + core, cy + core, fill=col,
                      outline=_mix(col, 0.4), tags="dyn")

        # merkez etiket
        label, lcol = STATE_TEXT[self.state]
        self._t(cx, cy + R + 28, text="J.A.R.V.I.S", fill=CYAN,
                font=("Helvetica Neue", 18, "bold"))
        self._t(cx, cy + R + 52, text="● " + label, fill=lcol,
                font=("Helvetica Neue", 12, "bold"))

        if time.time() < self.wave_until:
            self._draw_wave_face(cx, cy, R)

    def _draw_wave_face(self, cx, cy, R):
        """Küreye geçici göz + gülümseme + sallanan kol çizer (katılımcıya selam)."""
        c = self.canvas
        # Gözler (parıltılı).
        ex, ey, er = R * 0.34, cy - R * 0.20, R * 0.11
        for sx in (-1, 1):
            x = cx + sx * ex
            c.create_oval(x - er, ey - er, x + er, ey + er,
                          fill=CYAN, outline="", tags="dyn")
            g = er * 0.35
            c.create_oval(x - g - er * 0.3, ey - g - er * 0.3, x - er * 0.3 + g,
                          ey - er * 0.3 + g, fill="#ffffff", outline="", tags="dyn")
        # Gülümseme.
        mw = R * 0.42
        c.create_arc(cx - mw, cy - R * 0.02, cx + mw, cy + R * 0.5,
                     start=200, extent=140, style="arc", outline=CYAN, width=3,
                     tags="dyn")
        # Sallanan kol: omuz → dirsek (sabit), dirsek → el (sallanır).
        sh = (cx + R * 0.78, cy + R * 0.12)
        el = (cx + R * 1.12, cy - R * 0.34)
        swing = math.sin(self.phase * 3.2) * 0.5
        hand_ang = -math.pi / 2 + swing
        fl = R * 0.46
        hand = (el[0] + fl * math.cos(hand_ang), el[1] + fl * math.sin(hand_ang))
        c.create_line(*sh, *el, fill=CYAN, width=6, capstyle="round", tags="dyn")
        c.create_line(*el, *hand, fill=CYAN, width=6, capstyle="round", tags="dyn")
        hr = R * 0.11
        c.create_oval(hand[0] - hr, hand[1] - hr, hand[0] + hr, hand[1] + hr,
                      fill=CYAN, outline=_mix(CYAN, 0.4), width=2, tags="dyn")
        # Selam yazısı.
        self._t(cx, cy - R - 26, text="MERHABA!", fill=AMBER,
                font=("Helvetica Neue", 24, "bold"))

    def _draw_controls(self):
        cy = self.cy + self.R + 92
        specs = [("live", "◉ LIVE", GREEN), ("pause", "❚❚ PAUSE", BLUE),
                 ("shutdown", "⏻ SHUTDOWN", RED)]
        bw, gap = 150, 24
        total = len(specs) * bw + (len(specs) - 1) * gap
        x = self.cx - total // 2
        for name, text, col in specs:
            x0, x1 = x, x + bw
            self.buttons[name] = (x0, cy - 18, x1, cy + 18)
            self._brackets(x0, cy - 18, x1, cy + 18, _mix(col, 0.3), L=10)
            active = (name == "pause" and self.paused) or \
                     (name == "live" and not self.paused)
            self._t((x0 + x1) / 2, cy, text=text,
                    fill=col if active or name == "shutdown" else _mix(col, 0.45),
                    font=("Helvetica Neue", 13, "bold"))
            x += bw + gap

    # --- Sağ panel: konuşma -------------------------------------------------

    def _draw_right_panel(self):
        x0, y0, x1, y1 = self.rp
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=GRID, fill=PANEL_BG,
                                     tags="dyn")
        self._brackets(x0, y0, x1, y1, CYAN_DIM, L=16)
        self._t(x0 + 16, y0 + 16, text="CONVERSATION", anchor="w", fill=CYAN,
                font=("Helvetica Neue", 12, "bold"))
        status = STATE_TEXT[self.state][0].upper()
        self._t(x1 - 16, y0 + 16, text=status, anchor="e",
                fill=STATE_TEXT[self.state][1], font=("Helvetica Neue", 11, "bold"))

        # mesajları aşağıdan yukarı yerleştir (en yeni altta).
        pad = 16
        bottom = y1 - 64
        top = y0 + 40
        width = (x1 - x0) - 2 * pad
        y = bottom
        for label, text, color in reversed(self.messages):
            block = f"{label}: {text}"
            # geçici çiz, yüksekliği ölç, yerleştir
            tid = self.canvas.create_text(
                x0 + pad, 0, anchor="nw", text=block, width=width,
                fill=color, font=("Helvetica Neue", 13), tags="dyn",
            )
            bbox = self.canvas.bbox(tid)
            h = (bbox[3] - bbox[1]) if bbox else 18
            y -= h + 8
            if y < top:
                self.canvas.delete(tid)
                break
            self.canvas.coords(tid, x0 + pad, y)

    def _fire_ready(self):
        if self.on_ready:
            self.on_ready()

    def run(self):
        self.root.mainloop()


VOICE_CHOICES = ["marin", "cedar", "alloy", "shimmer", "echo", "sage"]


def run_setup(keys=None, profile=None):
    """Kurulum / Ayarlar sihirbazı.

    Hem ilk açılışta hem de `--setup` ile sonradan çağrılır. Mevcut değerlerle
    alanları önceden doldurur. Kullanıcı 'Kaydet'e basınca güncellenmiş
    (keys, profile) ikilisini döndürür; vazgeçerse None döndürür.
    """
    import store
    import weather

    keys = dict(store.DEFAULT_KEYS, **(keys or {}))
    profile = dict(store.DEFAULT_PROFILE, **(profile or {}))
    result = {"ok": False}

    win = tk.Tk()
    win.title("JARVIS — Kurulum ve Ayarlar")
    win.configure(bg=BG)
    win.geometry("600x720")
    win.resizable(False, False)

    tk.Label(win, text="J.A.R.V.I.S", fg=CYAN, bg=BG,
             font=("Helvetica Neue", 24, "bold")).pack(pady=(22, 2))
    tk.Label(win, text="Kurulum ve kişiselleştirme", fg=TEXT_DIM, bg=BG,
             font=("Helvetica Neue", 12)).pack(pady=(0, 14))

    form = tk.Frame(win, bg=BG)
    form.pack(fill="x", padx=40)

    def field(label, hint=""):
        tk.Label(form, text=label, fg=CYAN, bg=BG, anchor="w",
                 font=("Helvetica Neue", 12, "bold")).pack(fill="x", pady=(10, 0))
        if hint:
            tk.Label(form, text=hint, fg=TEXT_DIM, bg=BG, anchor="w",
                     font=("Helvetica Neue", 10)).pack(fill="x")
        e = tk.Entry(form, font=("Menlo", 12), bg=PANEL_BG, fg=TEXT,
                     insertbackground=TEXT, relief="flat")
        e.pack(fill="x", ipady=5, pady=(3, 0))
        return e

    e_key = field("OpenAI API anahtarı",
                  "platform.openai.com/api-keys adresinden alın (sk-... ile başlar)")
    e_key.config(show="•")
    if keys.get("openai_api_key"):
        e_key.insert(0, keys["openai_api_key"])

    e_name = field("Adınız", "JARVIS sizi tanısın diye")
    e_name.insert(0, profile.get("kullanici_adi", ""))

    e_hitap = field("JARVIS size nasıl hitap etsin?", "ör. hocam, Ahmet Bey, kaptan")
    e_hitap.insert(0, profile.get("hitap", ""))

    e_meslek = field("Mesleğiniz / alanınız", "ör. akademisyen, yazılımcı, doktor")
    e_meslek.insert(0, profile.get("meslek", ""))

    e_assistant = field("Asistanın adı", "varsayılan: JARVIS")
    e_assistant.insert(0, profile.get("asistan_adi", "JARVIS"))

    e_wake = field("Uyandırma kelimesi", "bu kelimeyle uyanır, ör. jarvis, athena")
    e_wake.insert(0, profile.get("uyandirma_kelimesi", "jarvis"))

    e_city = field("Şehir (hava durumu için)", "ör. İstanbul, Ankara, Berlin")
    e_city.insert(0, profile.get("sehir", "İstanbul"))

    tk.Label(form, text="Ses tonu", fg=CYAN, bg=BG, anchor="w",
             font=("Helvetica Neue", 12, "bold")).pack(fill="x", pady=(10, 0))
    voice_var = tk.StringVar(value=keys.get("tts_voice", "marin"))
    tk.OptionMenu(form, voice_var, *VOICE_CHOICES).pack(fill="x", pady=(3, 0))

    msg = tk.Label(win, text="", fg=AMBER, bg=BG, font=("Helvetica Neue", 11))
    msg.pack(pady=(10, 0))

    def submit():
        key = e_key.get().strip()
        if not key.startswith("sk-"):
            msg.config(text="API anahtarı 'sk-' ile başlamalı.")
            return
        msg.config(text="Konum çözümleniyor…", fg=TEXT_DIM)
        win.update_idletasks()

        keys["openai_api_key"] = key
        keys["tts_voice"] = voice_var.get()

        profile["kullanici_adi"] = e_name.get().strip()
        profile["hitap"] = e_hitap.get().strip() or "hocam"
        profile["meslek"] = e_meslek.get().strip() or "kullanıcı"
        profile["asistan_adi"] = e_assistant.get().strip() or "JARVIS"
        profile["uyandirma_kelimesi"] = (e_wake.get().strip() or "jarvis").lower()

        city = e_city.get().strip()
        if city:
            geo = weather.geocode(city)
            if geo:
                profile["sehir"] = geo["sehir"]
                profile["enlem"] = geo["enlem"]
                profile["boylam"] = geo["boylam"]
            else:
                profile["sehir"] = city  # koordinat bulunamadı, varsayılan kalır

        result["ok"] = True
        win.destroy()

    tk.Button(win, text="Kaydet ve Başla", command=submit,
              font=("Helvetica Neue", 14, "bold"), bg=CYAN, fg=BG,
              relief="flat", activebackground=GREEN).pack(pady=18, ipadx=10, ipady=4)
    e_key.focus_set()

    win.mainloop()
    if not result["ok"]:
        return None
    return keys, profile


def ask_api_key():
    """Geriye dönük uyumluluk: yalnızca API anahtarını döndürür (kullanılmıyor)."""
    out = run_setup()
    return out[0]["openai_api_key"] if out else None
