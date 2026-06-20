"""Sistem ölçümleri — CPU, RAM ve (mümkünse) GPU kullanımı.

CPU ve RAM `psutil` ile okunur. GPU kullanımı macOS'ta sudo gerektirmeden
güvenilir biçimde okunamaz; Intel/bazı GPU'larda `ioreg` üzerinden 'Device
Utilization %' bulunabilir, Apple Silicon'da genelde bulunamaz ve None döner.
"""

import re
import subprocess
import time

import psutil

# cpu_percent ilk çağrıda 0 döndürür; modül yüklenince bir kez "ısıt".
psutil.cpu_percent(interval=None)

# Ağ hızı için önceki sayaç durumu.
_net_prev = {"t": time.time(), "sent": 0, "recv": 0}


def cpu_percent():
    return psutil.cpu_percent(interval=None)


def disk_percent():
    return psutil.disk_usage("/").percent


def battery():
    """(yüzde, fişte mi) döndürür; okunamazsa None."""
    try:
        b = psutil.sensors_battery()
    except Exception:
        return None
    if b is None:
        return None
    return (round(b.percent), bool(b.power_plugged))


def net_rates():
    """(yükleme_KBps, indirme_KBps) — bir önceki çağrıdan bu yana ortalama."""
    now = time.time()
    io = psutil.net_io_counters()
    dt = max(now - _net_prev["t"], 1e-3)
    up = (io.bytes_sent - _net_prev["sent"]) / dt / 1024
    down = (io.bytes_recv - _net_prev["recv"]) / dt / 1024
    _net_prev.update(t=now, sent=io.bytes_sent, recv=io.bytes_recv)
    return max(up, 0.0), max(down, 0.0)


def ram_percent():
    return psutil.virtual_memory().percent


def ram_detail():
    vm = psutil.virtual_memory()
    used = vm.used / (1024 ** 3)
    total = vm.total / (1024 ** 3)
    return f"{used:.1f}/{total:.0f} GB"


def gpu_percent():
    """GPU kullanımını yüzde olarak döndürür; okunamazsa None."""
    try:
        out = subprocess.run(
            ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],
            capture_output=True, text=True, timeout=2,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    m = re.search(r'"Device Utilization %"\s*=\s*(\d+)', out)
    if m:
        return float(m.group(1))
    return None
