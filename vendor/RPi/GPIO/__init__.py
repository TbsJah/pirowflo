"""RPi.GPIO compatibility shim using pigpio.

Drop-in replacement for RPi.GPIO on Raspberry Pi OS Bookworm where
RPi.GPIO / lgpio require lgpiod which is not always available.
Requires pigpiod to be running:  sudo systemctl start pigpiod
"""

import time
import threading
import pigpio

# ── Constants (match RPi.GPIO values) ────────────────────────────────────────
BCM    = 11
BOARD  = 10
IN     = 1
OUT    = 0
HIGH   = 1
LOW    = 0
RISING  = 31
FALLING = 32
BOTH    = 33
PUD_UP   = 2
PUD_DOWN = 21
PUD_OFF  = 20

# ── Module-level pigpio connection ────────────────────────────────────────────
_pi: pigpio.pi | None = None
_callbacks: dict = {}   # pin -> pigpio callback handle
_lock = threading.Lock()


def _get_pi() -> pigpio.pi:
    global _pi
    with _lock:
        if _pi is None or not _pi.connected:
            _pi = pigpio.pi()
            if not _pi.connected:
                raise RuntimeError(
                    "Cannot connect to pigpiod. "
                    "Run:  sudo systemctl start pigpiod"
                )
    return _pi


# ── Public API ────────────────────────────────────────────────────────────────

def setmode(mode: int) -> None:
    """No-op: pigpio always uses BCM numbering."""
    pass


def setup(pin: int, direction: int, pull_up_down: int = PUD_OFF) -> None:
    pi = _get_pi()
    if direction == IN:
        pi.set_mode(pin, pigpio.INPUT)
        pud = {PUD_UP: pigpio.PUD_UP, PUD_DOWN: pigpio.PUD_DOWN}.get(
            pull_up_down, pigpio.PUD_OFF
        )
        pi.set_pull_up_down(pin, pud)
    elif direction == OUT:
        pi.set_mode(pin, pigpio.OUTPUT)


def output(pin: int, value) -> None:
    _get_pi().write(pin, 1 if value else 0)


def input(pin: int) -> int:
    return _get_pi().read(pin)


def add_event_detect(
    pin: int, edge: int, callback=None, bouncetime: int = 0
) -> None:
    pi = _get_pi()
    pigpio_edge = {
        RISING:  pigpio.RISING_EDGE,
        FALLING: pigpio.FALLING_EDGE,
    }.get(edge, pigpio.EITHER_EDGE)

    bounce_s = (bouncetime / 1000.0) if bouncetime else 0.0
    last_call = [0.0]

    def _wrapped(gpio: int, level: int, tick: int) -> None:
        if bounce_s > 0:
            now = time.monotonic()
            if now - last_call[0] < bounce_s:
                return
            last_call[0] = now
        if callback:
            callback(gpio)

    _callbacks[pin] = pi.callback(pin, pigpio_edge, _wrapped)


def cleanup() -> None:
    global _pi
    with _lock:
        for cb in _callbacks.values():
            try:
                cb.cancel()
            except Exception:
                pass
        _callbacks.clear()
        if _pi:
            _pi.stop()
            _pi = None
