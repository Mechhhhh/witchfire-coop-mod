#!/usr/bin/env python3
"""Znajduje GLOBALNE ZMIENNE wskazujace na podany obiekt.

Po co: proxy DLL (M4) potrzebuje `GEngine` i `GWorld`, a nie samych obiektow.
UE4SS potrafi podac ADRES OBIEKTU (`UObject:GetAddress()`), ale nie adres
globalnej zmiennej, ktora go trzyma. Ta zmienna jest jednak zwykla komorka
w sekcji danych exe i mozna ja znalezc skanem: szukamy 8-bajtowych wartosci
rownych adresowi obiektu.

Binarka laduje sie zawsze pod 0x140000000 (brak ASLR — potwierdzone w zrzutach
awaryjnych i przez nasza wlasna DLL), wiec znaleziony adres jest STALY i mozna
go zaszyc w proxy DLL.

Uzycie: find-globals.py <pid> <adres_obiektu_hex> [...]
"""
import re
import sys

# Zakres modulu gry. Wszystko poza nim to sterta albo cudze biblioteki —
# globalne zmienne silnika siedza w sekcji danych exe.
EXE_LO = 0x140000000
EXE_HI = 0x147000000


def regions(pid):
    """Czytelne, zapisywalne obszary — tam mieszkaja globalne zmienne."""
    out = []
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            m = re.match(r"([0-9a-f]+)-([0-9a-f]+) (\S{4})", line)
            if not m:
                continue
            lo, hi, perm = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            if perm[0] != "r":
                continue
            out.append((lo, hi, perm, line.rstrip()))
    return out


def scan(pid, targets):
    hits = {t: [] for t in targets}
    tset = set(targets)
    with open(f"/proc/{pid}/mem", "rb", 0) as mem:
        for lo, hi, perm, _line in regions(pid):
            # Skanujemy tylko obszar modulu gry — reszta to szum ze sterty,
            # ktory i tak zmienia sie miedzy uruchomieniami.
            if hi <= EXE_LO or lo >= EXE_HI:
                continue
            lo = max(lo, EXE_LO)
            hi = min(hi, EXE_HI)
            try:
                mem.seek(lo)
                data = mem.read(hi - lo)
            except Exception:
                continue
            for off in range(0, len(data) - 8, 8):
                val = int.from_bytes(data[off:off + 8], "little")
                if val in tset:
                    hits[val].append(lo + off)
    return hits


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    pid = int(sys.argv[1])
    targets = [int(a, 16) for a in sys.argv[2:]]

    hits = scan(pid, targets)
    for t in targets:
        found = hits[t]
        print(f"\nobiekt 0x{t:X}  ->  {len(found)} wskaznikow w module gry")
        for a in found[:12]:
            print(f"    globalna pod 0x{a:X}   (offset od bazy: +0x{a - EXE_LO:X})")
        if len(found) > 12:
            print(f"    ... i jeszcze {len(found) - 12}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
