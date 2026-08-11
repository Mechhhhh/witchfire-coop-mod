#!/usr/bin/env python3
"""Analiza obrazu pliku wykonywalnego — BEZ dzialajacej gry.

Po co
-----
Pytania „co robi ta funkcja", „kto ja wola", „gdzie jest ten napis" wymagaly
dotad dzialajacej gry: trzy minuty startu i klikniecie gracza w CONTINUE. Tu
odpowiedzi daje analiza obrazu pliku wykonywalnego, prowadzona offline.

Skad obraz
----------
Obraz wskazuje zmienna srodowiskowa `WF_OBRAZ_DIR` (katalog z `obraz.json`
i `obraz.bin`) i DOSTARCZA GO UZYTKOWNIK WE WLASNYM ZAKRESIE. Repozytorium nie
zawiera ani obrazu, ani zadnego narzedzia do jego pozyskania — to narzedzie
tylko czyta to, co juz lezy we wskazanym katalogu.

Co potrafi
----------
  obraz.py fun 0x14177F520              deasembluj funkcje (do RET)
  obraz.py fun 0x14177F520 --ile 300    ile instrukcji
  obraz.py xref 0x141923AA0             kto wola BEZPOSREDNIO (call/jmp rel32)
  obraz.py dane 0x141923AA0             gdzie adres LEZY JAKO DANA (tablice metod!)
  obraz.py napis "SaveLoadItem"         znajdz literal (ascii i utf-16)
  obraz.py lea 0x1448xxxxx              kto siega po ten adres przez lea/mov rip
  obraz.py bajty 0x14177F520 64         surowe bajty

„dane" jest tu najwazniejsze: odpowiada na pytanie, na ktore skan `call rel32`
NIE odpowiada — czyli kto wola funkcje posrednio, przez tablice metod albo
wskaznik. To bylo brakujace ogniwo w sprawie podwojnego napelniania ekwipunku.
"""
import argparse
import json
import os
import re
import struct
import sys

import capstone

# Katalog z obrazem pliku wykonywalnego — dostarcza go uzytkownik, w repozytorium
# go nie ma. Sciezka domyslna liczona wzgledem polozenia TEGO pliku
# (<korzen repozytorium>/obraz), zeby dzialalo niezaleznie od tego, gdzie
# repozytorium lezy. WF_OBRAZ_DIR nadpisuje.
KATALOG = os.environ.get(
    "WF_OBRAZ_DIR",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "obraz"))


class Obraz:
    def __init__(self, katalog=KATALOG):
        with open(os.path.join(katalog, "obraz.json")) as f:
            meta = json.load(f)
        self.zakresy = meta["zakresy"]
        with open(os.path.join(katalog, "obraz.bin"), "rb") as f:
            self.dane = f.read()

    def czytaj(self, adres, ile):
        for z in self.zakresy:
            if z["adres"] <= adres < z["adres"] + z["dlugosc"]:
                p = z["plik"] + (adres - z["adres"])
                dostepne = z["dlugosc"] - (adres - z["adres"])
                return self.dane[p:p + min(ile, dostepne)]
        return b""

    def u64(self, adres):
        b = self.czytaj(adres, 8)
        return struct.unpack("<Q", b)[0] if len(b) == 8 else None

    def wykonywalne(self):
        return [z for z in self.zakresy if "x" in z["prawa"]]

    def w_obrazie(self, adres):
        return any(z["adres"] <= adres < z["adres"] + z["dlugosc"] for z in self.zakresy)

    # ── granice funkcji z tablicy wyjatkow PE (.pdata) ───────────────────────
    #
    # Po co: „w ktorej funkcji lezy ten adres powrotu" bylo dotad zgadywaniem —
    # skanowaniem wstecz za prologiem. PE ma to wprost: .pdata to tablica
    # RUNTIME_FUNCTION (poczatek, koniec, dane odwijania), po jednym wpisie na
    # KAZDA funkcje. To zamienia zgadywanie w odczyt.
    def _wczytaj_pdata(self):
        if getattr(self, "_pdata", None) is not None:
            return self._pdata
        baza = 0x140000000
        dos = self.czytaj(baza, 0x40)
        e_lfanew = struct.unpack_from("<I", dos, 0x3C)[0]
        nt = self.czytaj(baza + e_lfanew, 0x108)
        rva, rozmiar = struct.unpack_from("<II", nt, 0x18 + 0x70 + 3 * 8)
        surowe = self.czytaj(baza + rva, rozmiar)
        tab = []
        for i in range(0, len(surowe) - 11, 12):
            p, k, u = struct.unpack_from("<III", surowe, i)
            if p:
                tab.append((baza + p, baza + k, u))
        tab.sort()
        self._pdata = tab
        return tab

    def _rodzic(self, unwind_rva):
        """Fragment funkcji (UNW_FLAG_CHAININFO) wskazuje wpis RODZICA.

        Bez tego kompilator klamie o granicach: MSVC tnie funkcje na kawalki
        i kazdy kawalek dostaje wlasny wpis w .pdata. Kawalek nie ma wolajacych,
        bo wchodzi sie do niego SKOKIEM — i dokladnie na tym utknelo poprzednie
        dochodzenie („zero wolajacych, wiec wywolanie posrednie"). Trzeba zejsc
        po lancuchu do wpisu glownego.
        """
        baza = 0x140000000
        for _ in range(8):
            if not unwind_rva:
                return None
            d = self.czytaj(baza + unwind_rva, 4)
            if not d:
                return None
            wersja_flagi, _prolog, ile_kodow, _ramka = d
            flagi = wersja_flagi >> 3
            if not (flagi & 0x4):          # nie fragment
                return None
            off = 4 + ((ile_kodow + 1) & ~1) * 2
            rf = self.czytaj(baza + unwind_rva + off, 12)
            if not rf or len(rf) < 12:
                return None
            p, k, u = struct.unpack("<III", rf)
            if not (u >> 0):
                return (baza + p, baza + k)
            # rodzic sam moze byc fragmentem — schodzimy dalej
            d2 = self.czytaj(baza + u, 4)
            if d2 and (d2[0] >> 3) & 0x4:
                unwind_rva = u
                continue
            return (baza + p, baza + k)
        return None

    def funkcja(self, adres):
        """(poczatek, koniec) funkcji zawierajacej adres, albo None.

        Fragmenty rozwiazywane do funkcji glownej (patrz `_rodzic`)."""
        import bisect
        tab = self._wczytaj_pdata()
        i = bisect.bisect_right(tab, (adres, 1 << 62, 1 << 62)) - 1
        if i < 0:
            return None
        p, k, u = tab[i]
        if not (p <= adres < k):
            return None
        rodzic = self._rodzic(u)
        return rodzic if rodzic else (p, k)


def md():
    m = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    m.detail = True
    return m


# ── polecenia ───────────────────────────────────────────────────────────────

RIP = re.compile(r"\[rip \+ (0x[0-9a-f]+)\]")


def literal(ob, adres):
    """Jesli pod adresem lezy napis (ascii albo utf-16), zwroc go.

    Po co w deasemblerze: kod gry rozpoznaje sie po literalach — nazwa klasy,
    znacznik `Type.Item.Weapon`, `SaveLoadItemDataContainers`. Bez tego kazdy
    `lea rdx,[rip+X]` trzeba bylo sprawdzac osobnym poleceniem.
    """
    b = ob.czytaj(adres, 96)
    if len(b) < 4:
        return None
    # utf-16: co drugi bajt zerowy
    if b[1] == 0 and 32 <= b[0] < 127:
        try:
            koniec = b.index(b"\x00\x00", 0 if len(b) % 2 == 0 else 1)
        except ValueError:
            koniec = len(b)
        s = b[:koniec + koniec % 2].decode("utf-16-le", "replace")
        if len(s) >= 3 and all(31 < ord(c) < 127 for c in s):
            return s
    if all(32 <= c < 127 for c in b[:4]):
        koniec = b.find(b"\x00")
        s = b[:koniec if koniec > 0 else len(b)].decode("ascii", "replace")
        if len(s) >= 4:
            return s
    return None


def cmd_fun(ob, a):
    adres = int(a.adres, 16)
    dane = ob.czytaj(adres, a.bajty)
    if not dane:
        print(f"adres 0x{adres:X} poza zrzutem")
        return 1
    n = 0
    for i in md().disasm(dane, adres):
        komentarz = ""
        m = RIP.search(i.op_str)
        if m:
            cel = i.address + i.size + int(m.group(1), 16)
            komentarz = f"   ; 0x{cel:X}"
            lit = literal(ob, cel)
            if lit:
                komentarz += f'  "{lit}"'
        print(f"  0x{i.address:X}  {i.mnemonic:8s} {i.op_str}{komentarz}")
        n += 1
        if n >= a.ile:
            break
        if i.mnemonic in ("ret", "int3"):
            break
    return 0


def cmd_xref(ob, a):
    """call/jmp rel32 wskazujace na adres."""
    cel = int(a.adres, 16)
    trafienia = []
    for z in ob.wykonywalne():
        baza, dl, off = z["adres"], z["dlugosc"], z["plik"]
        buf = ob.dane[off:off + dl]
        for op, nazwa in ((0xE8, "call"), (0xE9, "jmp")):
            szukaj = 0
            while True:
                i = buf.find(bytes([op]), szukaj)
                if i < 0 or i + 5 > dl:
                    break
                szukaj = i + 1
                rel = struct.unpack_from("<i", buf, i + 1)[0]
                if baza + i + 5 + rel == cel:
                    trafienia.append((baza + i, nazwa))
    for adr, nazwa in sorted(trafienia):
        print(f"  0x{adr:X}  {nazwa}")
    print(f"\nrazem: {len(trafienia)}")
    return 0


def cmd_dane(ob, a):
    """8-bajtowa wartosc rowna adresowi — czyli wpis w tablicy metod / wskaznik."""
    cel = int(a.adres, 16)
    wzor = struct.pack("<Q", cel)
    trafienia = []
    for z in ob.zakresy:
        baza, dl, off = z["adres"], z["dlugosc"], z["plik"]
        buf = ob.dane[off:off + dl]
        szukaj = 0
        while True:
            i = buf.find(wzor, szukaj)
            if i < 0:
                break
            szukaj = i + 1
            trafienia.append((baza + i, z["prawa"]))
    for adr, prawa in trafienia:
        print(f"  0x{adr:X}  ({prawa})")
    print(f"\nrazem: {len(trafienia)}")
    return 0


def cmd_napis(ob, a):
    tekst = a.tekst
    warianty = [("ascii", tekst.encode()), ("utf16", tekst.encode("utf-16-le"))]
    for nazwa, wzor in warianty:
        for z in ob.zakresy:
            baza, dl, off = z["adres"], z["dlugosc"], z["plik"]
            buf = ob.dane[off:off + dl]
            szukaj = 0
            while True:
                i = buf.find(wzor, szukaj)
                if i < 0:
                    break
                szukaj = i + 1
                kontekst = buf[max(0, i - 8):i + len(wzor) + 40]
                czysty = re.sub(rb"[^\x20-\x7e]+", b" ", kontekst).decode("ascii", "replace")
                print(f"  0x{baza+i:X}  [{nazwa}] {czysty.strip()}")
    return 0


def cmd_lea(ob, a):
    """Kto siega po adres przez adresowanie rip-wzgledne (`lea`, `mov`, `call`).

    Instrukcja rip-wzgledna trzyma 4-bajtowe przesuniecie liczone od KONCA
    instrukcji, a jej dlugosci nie znamy z gory. Dlatego szukamy odwrotnie:
    dla kazdej pozycji w kodzie sprawdzamy, czy lezace tam 4 bajty daja nasz
    adres przy ktorymkolwiek z sensownych ogonow (0-8 bajtow argumentu),
    a potem POTWIERDZAMY trafienie deasemblacja — bez tego byloby pelno
    przypadkowych liczb.
    """
    cel = int(a.adres, 16)
    m = md()
    trafienia = 0
    for z in ob.wykonywalne():
        baza, dl, off = z["adres"], z["dlugosc"], z["plik"]
        buf = ob.dane[off:off + dl]
        for p in range(0, dl - 4):
            rel = struct.unpack_from("<i", buf, p)[0]
            koniec = baza + p + 4          # koniec instrukcji bez argumentu
            if not (0 <= cel - (koniec + rel) <= 8):
                continue
            ogon = cel - (koniec + rel)
            for wstecz in range(2, 12):
                for ins in m.disasm(ob.czytaj(baza + p - wstecz, 20), baza + p - wstecz):
                    if (ins.size == wstecz + 4 + ogon and "rip" in ins.op_str):
                        print(f"  0x{ins.address:X}  {ins.mnemonic:8s} {ins.op_str}")
                        trafienia += 1
                    break
    print(f"\nrazem: {trafienia}")
    return 0


def cmd_gdzie(ob, a):
    """W ktorej funkcji lezy ten adres — z tablicy .pdata, bez zgadywania."""
    for tekst in a.adresy:
        adres = int(tekst, 16)
        f = ob.funkcja(adres)
        if f:
            print(f"  0x{adres:X}  w funkcji 0x{f[0]:X}-0x{f[1]:X}  (+0x{adres-f[0]:X}, dlugosc {f[1]-f[0]})")
        else:
            print(f"  0x{adres:X}  brak wpisu w .pdata")
    return 0


def cmd_bajty(ob, a):
    adres = int(a.adres, 16)
    dane = ob.czytaj(adres, a.ile)
    for i in range(0, len(dane), 16):
        w = dane[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in w)
        tx = "".join(chr(b) if 32 <= b < 127 else "." for b in w)
        print(f"  0x{adres+i:X}  {hx:<48s} {tx}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--katalog", default=KATALOG)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fun"); p.add_argument("adres"); p.add_argument("--ile", type=int, default=200); p.add_argument("--bajty", type=int, default=4096)
    p = sub.add_parser("xref"); p.add_argument("adres")
    p = sub.add_parser("dane"); p.add_argument("adres")
    p = sub.add_parser("napis"); p.add_argument("tekst")
    p = sub.add_parser("lea"); p.add_argument("adres")
    p = sub.add_parser("bajty"); p.add_argument("adres"); p.add_argument("ile", type=int, nargs="?", default=64)
    p = sub.add_parser("gdzie"); p.add_argument("adresy", nargs="+")

    a = ap.parse_args()
    # Obrazu nie ma w repozytorium — dostarcza go uzytkownik. Bez tego komunikatu
    # brak katalogu wygladal jak awaria narzedzia (goly FileNotFoundError).
    try:
        ob = Obraz(a.katalog)
    except FileNotFoundError as e:
        print(f"brak obrazu w {a.katalog!r} ({e.filename})\n"
              "Obraz (obraz.json + obraz.bin) NIE jest czescia repozytorium — "
              "dostarczasz go sam.\n"
              "Wskaz katalog przez WF_OBRAZ_DIR albo --katalog.", file=sys.stderr)
        return 2
    return {"fun": cmd_fun, "xref": cmd_xref, "dane": cmd_dane, "napis": cmd_napis,
            "lea": cmd_lea, "bajty": cmd_bajty, "gdzie": cmd_gdzie}[a.cmd](ob, a)


if __name__ == "__main__":
    sys.exit(main())
