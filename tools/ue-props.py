#!/usr/bin/env python3
"""Czyta WLASCIWOSCI obiektow gry przez refleksje Unreala — z zewnatrz, biernie.

Po co powstalo
--------------
`ue-objects.py` odpowiada na pytanie "czy obiekt istnieje". Przy broni to za
malo: trzeba rozroznic trzy rozlaczne wyniki, bo kazdy prowadzi gdzie indziej:

  A) nie ma aktora broni                       -> zniszczony, szukac w `Login`
  B) aktor jest, ale `AttachParent`/`Owner` zle -> przyczepienie przy possession
  C) aktor jest i przyczepiony, ale `bVisible`/`bOnlyOwnerSee` zle -> rysowanie

Rozroznic je da sie WYLACZNIE czytajac pola obiektu. Stad to narzedzie.

Jak to dziala
-------------
UE trzyma opis wlasnych klas w pamieci. `UClass` (a scislej `UStruct`) ma liste
wlasciwosci, a kazda wlasciwosc zna swoj typ i offset w bajtach wewnatrz
obiektu. Idziemy ta lista i czytamy wartosci pod wyliczonymi adresami.

PULAPKA, ktora zjada dzien pracy: UE 4.25 przenioslo wlasciwosci z `UProperty`
(bedacego UObject) na `FProperty` (bedacego FField). Od 4.25 `UStruct` ma DWIE
osobne listy: `Children` (UField* — funkcje, enumy) i `ChildProperties`
(FField* — wlasciwosci). Kto pojdzie po `Children`, znajdzie same UFunction
i uzna, ze klasa nie ma pol. Gra zglasza 4.27.2, wiec idziemy po `ChildProperties`.

Offsety struktur to hipoteza, nie pewnik — dlatego jest `--sprawdz`, ktore je
weryfikuje o rzeczy niezalezne od tego narzedzia (m.in. o pozycje postaci znana
z `WFCoop.log`). Bez przejscia tej weryfikacji zadnemu odczytowi nie wierzyc.

Uzycie
------
  ue-props.py <pid> --sprawdz                 weryfikacja ukladu struktur
  ue-props.py <pid> --obj 0x123456            wszystkie pola obiektu
  ue-props.py <pid> --szukaj Weapon --dump    znajdz po sciezce i wypisz pola
  ue-props.py <pid> --klasa Actor             sam UKLAD klasy (offsety, typy)
  ue-props.py <pid> --obj 0x.. --pole Owner   jedno pole
  ue-props.py <pid> --drzewo 0x123456         drzewo przyczepienia komponentow
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import (Pamiec, SS_TO_CHILDPROPERTIES, SS_TO_PROPERTIESSIZE,
                       UOBJ_OUTER_OFF)

# ── FField (UE 4.25+) ───────────────────────────────────────────────────────
FF_CLASS  = 0x08      # FFieldClass* — stad bierze sie NAZWA TYPU wlasciwosci
FF_OWNER  = 0x10      # FFieldVariant
FF_NEXT   = 0x20      # FField*  — nastepna wlasciwosc w klasie
FF_NAME   = 0x28      # FName
FF_SIZE   = 0x38

# ── FProperty (zaraz za FField) ─────────────────────────────────────────────
FP_ARRAYDIM   = 0x38
FP_ELEMSIZE   = 0x3C
FP_FLAGS      = 0x40
FP_OFFSET     = 0x4C   # Offset_Internal — bajty od poczatku obiektu
FP_SIZE       = 0x78   # tyle zajmuje sam FProperty; podtypy dokladaja pola za tym

# podtypy: pola wlasne zaczynaja sie na FP_SIZE
FBOOL_FIELDSIZE   = FP_SIZE + 0x00
FBOOL_BYTEOFFSET  = FP_SIZE + 0x01
FBOOL_BYTEMASK    = FP_SIZE + 0x02
FBOOL_FIELDMASK   = FP_SIZE + 0x03
FSTRUCT_STRUCT    = FP_SIZE + 0x00   # UScriptStruct*
FARRAY_INNER      = FP_SIZE + 0x00   # FProperty*
FOBJ_CLASS        = FP_SIZE + 0x00   # UClass* (typ wskazywanego obiektu)
FENUM_UNDERLYING  = FP_SIZE + 0x00   # FNumericProperty*

# FFieldClass: Name (FName) na +0x00
FFC_NAME = 0x00

CALKOWITE = {
    "Int8Property": ("<b", 1), "ByteProperty": ("<B", 1),
    "Int16Property": ("<h", 2), "UInt16Property": ("<H", 2),
    "IntProperty": ("<i", 4), "UInt32Property": ("<I", 4),
    "Int64Property": ("<q", 8), "UInt64Property": ("<Q", 8),
}


class Refleksja:
    def __init__(self, m: Pamiec):
        self.m = m
        self.super_off = m.wykryj_superstruct()
        self._pola_klasy = {}

    # ── chodzenie po liscie wlasciwosci ─────────────────────────────────────
    def typ(self, prop):
        """Nazwa typu wlasciwosci, np. 'ObjectProperty', 'BoolProperty'."""
        fc = self.m.wskaznik(prop + FF_CLASS)
        return self.m.nazwa(self.m.u32(fc + FFC_NAME)) if fc else "?"

    def nazwa_pola(self, prop):
        return self.m.nazwa(self.m.u32(prop + FF_NAME))

    def wlasciwosci_klasy(self, klasa):
        """Wlasciwosci zadeklarowane w TEJ klasie (bez odziedziczonych)."""
        if self.super_off is None:
            return []
        wynik = []
        p = self.m.wskaznik(klasa + self.super_off + SS_TO_CHILDPROPERTIES)
        g = 0
        while p and g < 4000:
            wynik.append(p)
            p = self.m.wskaznik(p + FF_NEXT)
            g += 1
        return wynik

    def wszystkie_wlasciwosci(self, klasa):
        """(klasa_deklarujaca, wlasciwosc) dla calego lancucha dziedziczenia,
        od klasy bazowej do najbardziej pochodnej — czyli w kolejnosci, w jakiej
        pola leza w pamieci."""
        if klasa in self._pola_klasy:
            return self._pola_klasy[klasa]
        wynik = []
        for k in reversed(self.m.lancuch_klas(klasa)):
            for p in self.wlasciwosci_klasy(k):
                wynik.append((k, p))
        self._pola_klasy[klasa] = wynik
        return wynik

    def znajdz_pole(self, klasa, nazwa):
        n = nazwa.lower()
        for _k, p in self.wszystkie_wlasciwosci(klasa):
            if self.nazwa_pola(p).lower() == n:
                return p
        return None

    def rozmiar_klasy(self, klasa):
        if self.super_off is None:
            return None
        return self.m.i32(klasa + self.super_off + SS_TO_PROPERTIESSIZE)

    # ── odczyt wartosci ─────────────────────────────────────────────────────
    def opis_obiektu(self, o):
        if not o:
            return "null"
        kl = self.m.nazwa_klasy(o)
        if not kl:
            return f"0x{o:X} <?>"
        return f"0x{o:X} {kl} {self.m.sciezka(o)}"

    def wartosc(self, prop, baza, glebokosc=1):
        """Wartosc wlasciwosci `prop` obiektu lezacego pod adresem `baza`."""
        m = self.m
        t = self.typ(prop)
        off = m.i32(prop + FP_OFFSET)
        if off is None:
            return "<brak offsetu>"
        a = baza + off
        rozm = m.i32(prop + FP_ELEMSIZE) or 0
        wymiar = m.i32(prop + FP_ARRAYDIM) or 1
        if wymiar > 1:
            return f"<tablica stala [{wymiar}] {t}>"
        return self._wartosc_pod(t, prop, a, rozm, glebokosc)

    def _wartosc_pod(self, t, prop, a, rozm, glebokosc):
        m = self.m
        if t == "BoolProperty":
            bo = m.u8(prop + FBOOL_BYTEOFFSET) or 0
            maska = m.u8(prop + FBOOL_FIELDMASK) or 0xFF
            b = m.u8(a + bo)
            return "?" if b is None else str(bool(b & maska))
        if t in CALKOWITE:
            fmt, n = CALKOWITE[t]
            d = m.czytaj(a, n)
            return str(struct.unpack(fmt, d)[0]) if d else "?"
        if t == "FloatProperty":
            v = m.f32(a)
            return f"{v:.3f}" if v is not None else "?"
        if t == "DoubleProperty":
            d = m.czytaj(a, 8)
            return f"{struct.unpack('<d', d)[0]:.3f}" if d else "?"
        if t == "NameProperty":
            d = m.czytaj(a, 8)
            if not d:
                return "?"
            return m.nazwa_z_para(*struct.unpack("<II", d)) or "None"
        if t == "StrProperty":
            return self._fstring(a)
        if t == "TextProperty":
            return "<FText>"
        if t in ("ObjectProperty", "ClassProperty", "ObjectPtrProperty",
                 "InterfaceProperty"):
            return self.opis_obiektu(m.wskaznik(a))
        if t == "WeakObjectProperty":
            idx = m.i32(a)
            return f"<slaby #{idx}>" if idx not in (None, -1) else "null"
        if t in ("SoftObjectProperty", "SoftClassProperty", "LazyObjectProperty"):
            return f"<{t}>"
        if t == "EnumProperty":
            d = m.czytaj(a, max(1, min(rozm, 8)))
            return str(int.from_bytes(d, "little")) if d else "?"
        if t == "StructProperty":
            return self._struct(prop, a, glebokosc)
        if t == "ArrayProperty":
            return self._tablica(prop, a, glebokosc)
        if t in ("MapProperty", "SetProperty"):
            n = m.i32(a + 8)
            return f"<{t} n={n}>"
        if t.endswith("DelegateProperty"):
            return "<delegat>"
        return f"<{t}>"

    def _fstring(self, a):
        """FString = TArray<TCHAR>: wskaznik, liczba, pojemnosc."""
        p = self.m.wskaznik(a)
        n = self.m.i32(a + 8) or 0
        if not p or n <= 0 or n > 4096:
            return '""'
        d = self.m.czytaj(p, n * 2)
        if not d:
            return '""'
        return '"' + d.decode("utf-16-le", errors="replace").rstrip("\x00") + '"'

    def _struct(self, prop, a, glebokosc):
        st = self.m.wskaznik(prop + FSTRUCT_STRUCT)
        nazwa = self.m.nazwa_obiektu(st) if st else "?"
        # Wektory i obroty czytamy wprost — to najczestszy przypadek i chcemy
        # miec liczbe, a nie "<FVector>".
        if nazwa in ("Vector", "Rotator") :
            v = [self.m.f32(a + i * 4) for i in range(3)]
            if all(x is not None for x in v):
                et = "XYZ" if nazwa == "Vector" else "PYR"
                return "(" + ", ".join(f"{e}={x:.1f}" for e, x in zip(et, v)) + ")"
        if nazwa == "Vector2D":
            v = [self.m.f32(a + i * 4) for i in range(2)]
            if all(x is not None for x in v):
                return f"(X={v[0]:.1f}, Y={v[1]:.1f})"
        if glebokosc > 0 and st:
            srodek = []
            for _k, p in self.wszystkie_wlasciwosci(st)[:12]:
                srodek.append(f"{self.nazwa_pola(p)}={self.wartosc(p, a, glebokosc - 1)}")
            if srodek:
                return f"{nazwa}{{" + ", ".join(srodek) + "}"
        return f"<{nazwa}>"

    def _tablica(self, prop, a, glebokosc):
        wew = self.m.wskaznik(prop + FARRAY_INNER)
        p = self.m.wskaznik(a)
        n = self.m.i32(a + 8) or 0
        if not wew:
            return f"<tablica n={n}>"
        tw = self.typ(wew)
        if not p or n <= 0:
            return f"[{tw}] puste"
        if n > 4096:
            return f"[{tw}] n={n} (podejrzanie duzo — nie czytam)"
        rozm = self.m.i32(wew + FP_ELEMSIZE) or 8
        ile_pokazac = min(n, 8 if glebokosc > 0 else 3)
        elementy = [self._wartosc_pod(tw, wew, p + i * rozm, rozm, glebokosc - 1)
                    for i in range(ile_pokazac)]
        ogon = f" ... (+{n - ile_pokazac})" if n > ile_pokazac else ""
        return f"[{tw}] n={n}: " + "; ".join(elementy) + ogon

    # ── wypisywanie ─────────────────────────────────────────────────────────
    def wypisz_obiekt(self, o, filtr=None, glebokosc=1, pokaz_puste=True):
        m = self.m
        klasa = m.wsk_klasy(o)
        print(f"obiekt   0x{o:X}")
        print(f"  nazwa   {m.nazwa_obiektu(o)}")
        print(f"  sciezka {m.sciezka(o)}")
        lancuch = [m.nazwa_obiektu(k) for k in m.lancuch_klas(klasa)]
        print(f"  klasa   {' <- '.join(lancuch)}")
        print(f"  rozmiar {self.rozmiar_klasy(klasa)} B")
        print()
        biezaca = None
        for k, p in self.wszystkie_wlasciwosci(klasa):
            nazwa = self.nazwa_pola(p)
            if filtr and filtr.lower() not in nazwa.lower():
                continue
            if k != biezaca:
                biezaca = k
                print(f"  ── z {m.nazwa_obiektu(k)} " + "─" * 40)
            off = m.i32(p + FP_OFFSET)
            v = self.wartosc(p, o, glebokosc)
            if not pokaz_puste and v in ("null", '""', "False", "0"):
                continue
            print(f"    +0x{off or 0:04X}  {self.typ(p)[:-8]:14s} {nazwa:38s} = {v}")


# ── weryfikacja ukladu struktur ─────────────────────────────────────────────
def _zywe_obiekty(m):
    """Obiekty bez CDO. Bez tego filtra kazda kontrola konczy sie na
    `Default__Cos` — wzorcach klas, ktore stoja w (0,0,0), nie maja
    RootComponentu i nie mowia NIC o stanie gry. Pierwsza wersja tej
    weryfikacji zglosila przez to falszywy blad."""
    for idx, o in m.obiekty():
        n = m.nazwa_obiektu(o)
        if n and not n.startswith("Default__"):
            yield idx, o, n


def _pozycje_z_logu(sciezka_logu):
    """Ostatnia linia `RUCH:` z WFCoop.log -> {nazwa: (x, y, z)}.
    To jest niezalezne zrodlo prawdy: pisze ja mod z WNETRZA gry, przez
    K2_GetActorLocation, a wiec zupelnie inna droga niz nasz odczyt pamieci."""
    import re
    ostatnia = None
    try:
        with open(sciezka_logu, errors="replace") as f:
            for linia in f:
                if "RUCH:" in linia:
                    ostatnia = linia
    except OSError:
        return {}
    if not ostatnia:
        return {}
    wynik = {}
    for nazwa, x, y, z in re.findall(
            r"\*?([A-Za-z0-9_]+)\((-?\d+),(-?\d+),(-?\d+)\)", ostatnia):
        wynik[nazwa] = (float(x), float(y), float(z))
    return wynik


def sprawdz(m: Pamiec, log_ruchu=None):
    """Cztery niezalezne kontrole. Kazda moze zawiesc osobno i kazda mowi
    co innego — dlatego nie skracam ich do jednego "OK"."""
    r = Refleksja(m)
    ok_wszystko = True

    print("── 1. lancuch dziedziczenia (UStruct::SuperStruct) ──────────────")
    print(f"   wykryty offset SuperStruct: "
          f"{'0x%X' % r.super_off if r.super_off else 'NIE WYKRYTO'}")
    if r.super_off is None:
        print("   BLAD: bez tego nic dalej nie zadziala.")
        return False
    postac = None
    for _idx, o, _n in _zywe_obiekty(m):
        if m.nazwa_klasy(o) == "BPDimensionPlayerCharacter_C":
            postac = o
            break
    if postac:
        lancuch = [m.nazwa_obiektu(k) for k in m.lancuch_klas(m.wsk_klasy(postac))]
        print(f"   postac gracza: {' <- '.join(lancuch)}")
        if "Actor" not in lancuch or lancuch[-1] != "Object":
            print("   BLAD: lancuch nie dochodzi do Actor/Object")
            ok_wszystko = False
    else:
        print("   (brak zywej postaci gracza — kontrola pominieta)")

    print("\n── 2. RootComponent musi wskazywac na komponent ─────────────────")
    # Przechodzi tylko wtedy, gdy i przejscie po ChildProperties, i Offset_Internal
    # sa dobre. Zly offset da wskaznik w smieci.
    # Pusty RootComponent liczymy OSOBNO: aktory bez czesci wizualnej (AInfo,
    # GameMode, PlayerState) legalnie go nie maja, wiec wliczanie ich do bledow
    # zanizaloby wynik bez powodu.
    zbadane, dobre, puste = 0, 0, 0
    for _idx, o, _n in _zywe_obiekty(m):
        if not m.dziedziczy_po(o, "Actor"):
            continue
        p = r.znajdz_pole(m.wsk_klasy(o), "RootComponent")
        if not p:
            continue
        cel = m.wskaznik(o + (m.i32(p + FP_OFFSET) or 0))
        zbadane += 1
        if cel is None:
            puste += 1
        elif m.nazwa_klasy(cel).endswith("Component"):
            dobre += 1
        if zbadane >= 120:
            break
    niepuste = zbadane - puste
    print(f"   aktorow zbadanych: {zbadane}  (pusty RootComponent: {puste})")
    print(f"   niepustych: {niepuste}, wskazuje na komponent: {dobre}")
    if niepuste == 0:
        print("   (nie ma na czym sprawdzic — kontrola pominieta)")
    elif dobre < niepuste * 0.95:
        print("   BLAD: offsety wlasciwosci sa zle")
        ok_wszystko = False

    print("\n── 3. pozycja z pamieci vs pozycja z logu moda ──────────────────")
    # Najmocniejsza kontrola, bo porownuje DWIE NIEZALEZNE DROGI do tej samej
    # liczby: nasz odczyt pamieci i K2_GetActorLocation wolane w grze przez mod.
    z_logu = _pozycje_z_logu(log_ruchu) if log_ruchu else {}
    znalezione = []
    for _idx, o, nazwa in _zywe_obiekty(m):
        if not m.dziedziczy_po(o, "Pawn"):
            continue
        korzen = r.znajdz_pole(m.wsk_klasy(o), "RootComponent")
        if not korzen:
            continue
        kc = m.wskaznik(o + (m.i32(korzen + FP_OFFSET) or 0))
        if not kc:
            continue
        pl = r.znajdz_pole(m.wsk_klasy(kc), "RelativeLocation")
        if not pl:
            continue
        a = kc + (m.i32(pl + FP_OFFSET) or 0)
        v = [m.f32(a + i * 4) for i in range(3)]
        if all(x is not None for x in v):
            znalezione.append((nazwa, v))
        if len(znalezione) >= 10:
            break
    zgodne, niezgodne = 0, 0
    for nazwa, v in znalezione:
        oczek = z_logu.get(nazwa)
        if oczek:
            blad = max(abs(v[i] - oczek[i]) for i in range(3))
            # Prog 2 jednostki: mod loguje pozycje zaokraglona do calkowitych,
            # a postac miedzy jednym a drugim odczytem moze drgnac.
            czy = "ZGODNE" if blad <= 2.0 else f"ROZNICA {blad:.0f}"
            if blad <= 2.0:
                zgodne += 1
            else:
                niezgodne += 1
            print(f"   {nazwa:44s} ({v[0]:.0f}, {v[1]:.0f}, {v[2]:.0f})"
                  f"  log=({oczek[0]:.0f}, {oczek[1]:.0f}, {oczek[2]:.0f})  {czy}")
        else:
            print(f"   {nazwa:44s} ({v[0]:.0f}, {v[1]:.0f}, {v[2]:.0f})  (brak w logu)")
    if z_logu:
        print(f"   zgodnych: {zgodne}, niezgodnych: {niezgodne}")
        if niezgodne or not zgodne:
            print("   BLAD: odczyt z pamieci nie zgadza sie z tym, co widzi gra")
            ok_wszystko = False
    else:
        print("   (bez --log nie ma z czym porownac; podaj sciezke do WFCoop.log)")

    print("\n── 4. offsety nie moga wychodzic poza rozmiar klasy ─────────────")
    zle, sprawdzonych = 0, 0
    for _idx, o, _n in _zywe_obiekty(m):
        klasa = m.wsk_klasy(o)
        if not klasa or not m.dziedziczy_po(o, "Actor"):
            continue
        rozm = r.rozmiar_klasy(klasa) or 0
        for _k, p in r.wszystkie_wlasciwosci(klasa):
            koniec = (m.i32(p + FP_OFFSET) or 0) + \
                     (m.i32(p + FP_ELEMSIZE) or 0) * (m.i32(p + FP_ARRAYDIM) or 1)
            if koniec > rozm:
                zle += 1
        sprawdzonych += 1
        if sprawdzonych >= 40:
            break
    print(f"   klas sprawdzonych: {sprawdzonych}, pol poza rozmiarem: {zle}")
    if zle:
        print("   BLAD: to znaczy, ze Offset_Internal albo PropertiesSize jest zly")
        ok_wszystko = False

    print("\n" + ("WERDYKT: uklad struktur POTWIERDZONY" if ok_wszystko
                  else "WERDYKT: uklad struktur NIEPOTWIERDZONY — odczytom nie ufac"))
    return ok_wszystko


# ── drzewo przyczepienia ────────────────────────────────────────────────────
def drzewo(m: Pamiec, r: Refleksja, korzen, wciecie=0, widziane=None):
    """Do czego jest przyczepiony komponent i co wisi na nim. Wprost odpowiada
    na pytanie o bron: 'jest w swiecie, ale czy trzyma sie postaci?'"""
    widziane = widziane if widziane is not None else set()
    if not korzen or korzen in widziane or wciecie > 8:
        return
    widziane.add(korzen)
    klasa = m.wsk_klasy(korzen)
    wl = m.wskaznik(korzen + UOBJ_OUTER_OFF)
    dodatki = []
    for pole in ("bVisible", "bHiddenInGame", "bOnlyOwnerSee", "bOwnerNoSee"):
        p = r.znajdz_pole(klasa, pole)
        if p:
            dodatki.append(f"{pole}={r.wartosc(p, korzen)}")
    ps = r.znajdz_pole(klasa, "AttachSocketName")
    gniazdo = r.wartosc(ps, korzen) if ps else ""
    print(f"{'  ' * wciecie}{m.nazwa_obiektu(korzen)} [{m.nazwa_klasy(korzen)}]"
          f"{' @' + gniazdo if gniazdo and gniazdo != 'None' else ''}")
    print(f"{'  ' * wciecie}    wlasciciel={m.nazwa_obiektu(wl)}  {'  '.join(dodatki)}")
    pd = r.znajdz_pole(klasa, "AttachChildren")
    if not pd:
        return
    a = korzen + (m.i32(pd + FP_OFFSET) or 0)
    tab = m.wskaznik(a)
    n = m.i32(a + 8) or 0
    for i in range(min(n, 64)):
        drzewo(m, r, m.wskaznik(tab + i * 8), wciecie + 1, widziane)


def main():
    ap = argparse.ArgumentParser(description="czytnik wlasciwosci obiektow UE")
    ap.add_argument("pid", type=int)
    ap.add_argument("--sprawdz", action="store_true", help="weryfikacja ukladu struktur")
    ap.add_argument("--log", help="WFCoop.log — niezalezne zrodlo pozycji do kontroli 3")
    ap.add_argument("--obj", help="adres szesnastkowy obiektu")
    ap.add_argument("--szukaj", help="znajdz obiekty po fragmencie sciezki/klasy")
    ap.add_argument("--isa", help="zawez --szukaj do potomkow tej klasy, np. Actor")
    ap.add_argument("--dump", action="store_true", help="przy --szukaj: wypisz pola znalezionych")
    ap.add_argument("--klasa", help="uklad klasy o tej nazwie (offsety i typy, bez instancji)")
    ap.add_argument("--pole", help="tylko wlasciwosci zawierajace ten tekst w nazwie")
    ap.add_argument("--drzewo", help="drzewo przyczepienia od komponentu pod tym adresem")
    ap.add_argument("--glebokosc", type=int, default=1)
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()

    m = Pamiec(a.pid)
    r = Refleksja(m)

    if a.sprawdz:
        return 0 if sprawdz(m, a.log) else 2

    if r.super_off is None:
        print("NIE WYKRYTO ukladu UStruct — przerywam (uruchom --sprawdz)")
        return 2

    if a.drzewo:
        cel = int(a.drzewo, 16)
        # Wygoda, ktora oszczedza jeden krok w kazdym uzyciu: drzewo
        # przyczepienia wisi na KOMPONENTACH, ale szuka sie zwykle po AKTORZE.
        # Jesli dostalismy aktora — schodzimy do jego RootComponent sami.
        if m.dziedziczy_po(cel, "Actor"):
            p = r.znajdz_pole(m.wsk_klasy(cel), "RootComponent")
            korzen = m.wskaznik(cel + (m.i32(p + FP_OFFSET) or 0)) if p else None
            if not korzen:
                print(f"aktor {m.nazwa_obiektu(cel)} nie ma RootComponent")
                return 1
            print(f"aktor {m.nazwa_obiektu(cel)} -> RootComponent 0x{korzen:X}")
            cel = korzen
        drzewo(m, r, cel)
        return 0

    if a.obj:
        r.wypisz_obiekt(int(a.obj, 16), a.pole, a.glebokosc)
        return 0

    if a.klasa:
        cel = None
        for _idx, o in m.obiekty():
            if m.nazwa_klasy(o) in ("Class", "BlueprintGeneratedClass", "ScriptStruct") \
                    and m.nazwa_obiektu(o).lower() == a.klasa.lower():
                cel = o
                break
        if not cel:
            print(f"nie znalazlem klasy {a.klasa}")
            return 1
        print(f"klasa {m.sciezka(cel)}  0x{cel:X}  rozmiar {r.rozmiar_klasy(cel)} B")
        print(f"  {' <- '.join(m.nazwa_obiektu(k) for k in m.lancuch_klas(cel))}\n")
        biezaca = None
        for k, p in r.wszystkie_wlasciwosci(cel):
            if a.pole and a.pole.lower() not in r.nazwa_pola(p).lower():
                continue
            if k != biezaca:
                biezaca = k
                print(f"  ── z {m.nazwa_obiektu(k)} " + "─" * 40)
            print(f"    +0x{m.i32(p + FP_OFFSET) or 0:04X}  {r.typ(p)[:-8]:16s} "
                  f"{r.nazwa_pola(p)}")
        return 0

    if a.szukaj:
        igla = a.szukaj.lower()
        ile = 0
        for _idx, o in m.obiekty():
            kl = m.nazwa_klasy(o)
            nz = m.nazwa_obiektu(o)
            if igla not in kl.lower() and igla not in nz.lower():
                continue
            if a.isa and not m.dziedziczy_po(o, a.isa):
                continue
            print(f"0x{o:X}  {kl:34s} {m.sciezka(o)}")
            if a.dump:
                r.wypisz_obiekt(o, a.pole, a.glebokosc)
                print()
            ile += 1
            if ile >= a.limit:
                print(f"... (przerwano na {a.limit})")
                break
        if ile == 0:
            print("nic nie znaleziono")
        return 0

    print("podaj --sprawdz, --obj, --szukaj, --klasa albo --drzewo")
    return 1


if __name__ == "__main__":
    sys.exit(main())
