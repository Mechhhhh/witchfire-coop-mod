#!/usr/bin/env python3
"""Wejscie z poziomu JADRA — wirtualne urzadzenie `uinput`, nie syntetyczne zdarzenie.

Po co
-----
Menu Witchfire ignoruje syntetyczne klikniecia i przez to KAZDY przebieg wymaga
czlowieka przy klawiaturze. Ale to, co dotad probowano, dzialalo w warstwie X
(`xdotool`, XTEST) — a ta jest dla gry rozpoznawalna i pomijana. `uinput` lezy
NIZEJ: tworzy urzadzenie, ktore jadro i kompozytor widza jak prawdziwa
klawiature albo mysz, bo zdarzenia ida ta sama sciezka evdev co ze sprzetu.

Czy zadziala w TEJ grze — nie wiadomo, dopoki sie nie sprawdzi. Dlatego
`--sprawdz` wypisuje, co zrobi, i nie wysyla niczego, a `--urzadzenie` tworzy
samo urzadzenie i czeka, zeby dalo sie podejrzec `libinput debug-events`,
czy w ogole je widac.

NIE URUCHAMIAC, gdy czlowiek gra — zdarzenia trafiaja do okna aktywnego.

Uzycie
------
  tools/wejscie.py --sprawdz klawisz e         # nic nie wysyla, tylko mowi co by zrobil
  tools/wejscie.py klawisz e                   # wcisnij i puszcz `E`
  tools/wejscie.py klawisz enter --ile 2       # dwa razy
  tools/wejscie.py klik                        # lewy przycisk myszy
  tools/wejscie.py mysz 200 0                  # ruch wzgledny
  tools/wejscie.py ciag w:800 e enter          # `W` przez 800 ms, potem `E`, potem Enter
  tools/wejscie.py --urzadzenie 30             # samo urzadzenie na 30 s (do podgladu)
"""
import argparse
import fcntl
import os
import struct
import sys
import time

UINPUT = "/dev/uinput"

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_X, REL_Y = 0x00, 0x01

UI_DEV_CREATE  = 0x5501
UI_DEV_DESTROY = 0x5502
UI_SET_EVBIT   = 0x40045564
UI_SET_KEYBIT  = 0x40045565
UI_SET_RELBIT  = 0x40045566

BTN_LEWY, BTN_PRAWY = 0x110, 0x111

KLAWISZE = {
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
    "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20,
    "enter": 28, "ctrl": 29, "a": 30, "s": 31, "d": 32, "f": 33, "g": 34,
    "shift": 42, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "spacja": 57, "space": 57, "f1": 59, "f5": 63, "f10": 68,
    "gora": 103, "lewo": 105, "prawo": 106, "dol": 108,
    "klik": BTN_LEWY, "prawy": BTN_PRAWY,
}


def zdarzenie(typ, kod, wartosc):
    t = time.time()
    return struct.pack("@llHHi", int(t), int((t % 1) * 1e6), typ, kod, wartosc)


class Urzadzenie:
    """Wirtualna klawiatura i mysz w jednym — gra i tak czyta oba z evdev."""

    def __init__(self, nazwa=b"WFCoop wejscie"):
        self.fd = os.open(UINPUT, os.O_WRONLY | os.O_NONBLOCK)
        for ev in (EV_KEY, EV_REL):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)
        for kod in sorted(set(KLAWISZE.values())):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, kod)
        for kod in (REL_X, REL_Y):
            fcntl.ioctl(self.fd, UI_SET_RELBIT, kod)

        # uinput_user_dev: nazwa[80] + input_id(8) + ff_effects_max(4) + 4*64*4
        opis = struct.pack("@80sHHHHi", nazwa, 0x03, 0x1234, 0x5678, 1, 0)
        opis += b"\x00" * (64 * 4 * 4)
        os.write(self.fd, opis)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        # Kompozytor musi zdazyc zauwazyc nowe urzadzenie; bez tego pierwsze
        # zdarzenia gina po cichu i wyglada to na „nie dziala".
        time.sleep(0.4)

    def _wyslij(self, *zdarzenia):
        for z in zdarzenia:
            os.write(self.fd, z)
        os.write(self.fd, zdarzenie(EV_SYN, SYN_REPORT, 0))

    def klawisz(self, kod, trzymaj=0.05):
        self._wyslij(zdarzenie(EV_KEY, kod, 1))
        time.sleep(trzymaj)
        self._wyslij(zdarzenie(EV_KEY, kod, 0))

    def mysz(self, dx, dy):
        self._wyslij(zdarzenie(EV_REL, REL_X, int(dx)),
                     zdarzenie(EV_REL, REL_Y, int(dy)))

    def zamknij(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(self.fd)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("polecenie", nargs="?", choices=["klawisz", "klik", "prawy", "mysz", "ciag"])
    a.add_argument("argumenty", nargs="*")
    a.add_argument("--ile", type=int, default=1)
    a.add_argument("--odstep", type=float, default=0.35)
    a.add_argument("--sprawdz", action="store_true", help="nic nie wysylaj, powiedz co by zrobil")
    a.add_argument("--urzadzenie", type=float, metavar="SEK",
                   help="utworz samo urzadzenie i czekaj (do `libinput debug-events`)")
    x = a.parse_args()

    if x.urzadzenie:
        u = Urzadzenie()
        print(f"urzadzenie utworzone na {x.urzadzenie:.0f} s — sprawdz `libinput list-devices`"
              f" albo `libinput debug-events`")
        time.sleep(x.urzadzenie)
        u.zamknij()
        return 0

    if not x.polecenie:
        print(__doc__)
        return 2

    # Plan powstaje PRZED otwarciem urzadzenia, zeby `--sprawdz` mogl go pokazac
    # bez tworzenia czegokolwiek.
    plan = []
    if x.polecenie in ("klik", "prawy"):
        plan = [("klawisz", KLAWISZE[x.polecenie], 0.05)] * x.ile
    elif x.polecenie == "klawisz":
        if not x.argumenty or x.argumenty[0] not in KLAWISZE:
            print(f"nieznany klawisz; znane: {', '.join(sorted(KLAWISZE))}", file=sys.stderr)
            return 2
        plan = [("klawisz", KLAWISZE[x.argumenty[0]], 0.05)] * x.ile
    elif x.polecenie == "mysz":
        if len(x.argumenty) < 2:
            print("podaj dx i dy", file=sys.stderr)
            return 2
        plan = [("mysz", int(x.argumenty[0]), int(x.argumenty[1]))]
    elif x.polecenie == "ciag":
        for cz in x.argumenty:
            nazwa, _, ms = cz.partition(":")
            if nazwa not in KLAWISZE:
                print(f"nieznany klawisz `{nazwa}`", file=sys.stderr)
                return 2
            plan.append(("klawisz", KLAWISZE[nazwa], (int(ms) / 1000.0) if ms else 0.05))

    if x.sprawdz:
        print("NIC NIE WYSLANO. Plan:")
        for p in plan:
            print(f"   {p[0]}  kod/dx={p[1]}  czas/dy={p[2]}")
        return 0

    u = Urzadzenie()
    try:
        for i, p in enumerate(plan):
            if p[0] == "klawisz":
                u.klawisz(p[1], p[2])
            else:
                u.mysz(p[1], p[2])
            if i + 1 < len(plan):
                time.sleep(x.odstep)
    finally:
        u.zamknij()
    print(f"wyslane: {len(plan)} zdarzen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
