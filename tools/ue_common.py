#!/usr/bin/env python3
"""Wspolny rdzen czytnikow pamieci Unreala — uzywany przez ue-objects.py,
ue-snapshot.py i ue-props.py.

Po co powstal
-------------
`ue-objects.py` sprawdzil sie jako dowod, ze da sie czytac obiekty gry
z zewnatrz. Ale kazdy odczyt to byl osobny `seek`+`read`, czyli dwa wywolania
systemowe na 8 bajtow. Przy 200 tysiacach obiektow i lancuchu Outer dla kazdego
robi sie z tego kilka milionow wywolan — przejscie calej tablicy trwa wtedy
minuty. A pomiar, ktory trwa minute, NIE JEST zrzutem stanu: to smuga, w ktorej
poczatek i koniec pochodza z dwoch roznych chwil gry. Przy badaniu zjawiska,
ktore dzieje sie w jednej sekundzie (dolaczenie klienta), to unieważnia wynik.

Co jest tu zrobione inaczej
---------------------------
1. `os.pread` zamiast `seek`+`read` — jedno wywolanie zamiast dwoch.
2. Bufor stron 4 KB. Obiekty UE leza gesto w pulach alokatora, wiec jedna
   strona obsluguje kilkanascie-kilkadziesiat obiektow. Zejscie z ~14 wywolan
   na obiekt do ulamka jednego.
3. Bufor nazw klas po WSKAZNIKU klasy (klas jest kilka tysiecy, nie 200 tysiecy).
4. Tryb migawkowy: przy przejsciu tablicy zapisujemy SUROWE wskazniki, a nazwy
   rozwiazujemy dopiero po zakonczeniu przejscia. Sam przemial tablicy jest
   wtedy krotki, a to on musi trafic w moment objawu.

Uwaga o spojnosci: bufor stron celowo NIE odswieza sie sam. Migawka ma byc
z jednej chwili. Do odczytow "na zywo" wolaj `odswiez()`.
"""
import os
import struct

BASE = 0x140000000
GUOBJECTARRAY = BASE + 0x6543810
NAMEPOOL      = BASE + 0x64EA8C0

# ── uklad struktur UE 4.27 ──────────────────────────────────────────────────
OBJOBJECTS_OFF   = 0x10
CHUNKS_PTR_OFF   = 0x00
NUM_ELEMENTS_OFF = 0x14
NUM_CHUNKS_OFF   = 0x1C
ELEMS_PER_CHUNK  = 64 * 1024
UOBJECTITEM_SIZE = 0x18

# UObject: vtable 0x00, Flags 0x08, InternalIndex 0x0C, Class 0x10,
#          Name (FName) 0x18, Outer 0x20  → naglowek ma 0x28 bajtow
UOBJ_CLASS_OFF   = 0x10
UOBJ_NAME_OFF    = 0x18
UOBJ_OUTER_OFF   = 0x20
UOBJ_HEADER      = 0x28

NAMEPOOL_BLOCKS_OFF = 0x10

# UStruct — offset SuperStruct zalezy od tego, czy build ma wkompilowany
# FStructBaseChain (dwa dodatkowe pola przed SuperStruct). Dlatego NIE jest
# staly: wykrywamy go empirycznie (patrz `wykryj_superstruct`). Reszta pol
# lezy zawsze w tych samych odstepach OD NIEGO:
SS_TO_CHILDREN        = 0x08   # UField*  — funkcje, enumy (NIE wlasciwosci!)
SS_TO_CHILDPROPERTIES = 0x10   # FField*  — wlasciwosci (UE 4.25+)
SS_TO_PROPERTIESSIZE  = 0x18   # int32

STRONA = 0x1000
MAX_STRON = 60000          # ~240 MB sufitu na bufor; wyzej przestajemy buforowac


class Pamiec:
    """Czytanie pamieci procesu. Bledne adresy zwracaja None, nie wyjatek —
    obiekty potrafia znikac w trakcie chodzenia po tablicy."""

    def __init__(self, pid, buforuj=True):
        self.pid = pid
        self.fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        self.strony = {} if buforuj else None
        self.cache_nazw = {}       # FNameEntryId -> tekst
        self.cache_klas = {}       # wskaznik UClass -> nazwa
        self.cache_blokow = {}     # numer bloku FNamePool -> wskaznik
        self._super_off = None

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def odswiez(self):
        """Porzuca bufor stron. Wolac przed odczytem, ktory ma pokazac stan
        BIEZACY, a nie ten z chwili poprzedniego zapytania."""
        if self.strony is not None:
            self.strony.clear()

    # ── surowy odczyt ───────────────────────────────────────────────────────
    def _wprost(self, addr, n):
        try:
            d = os.pread(self.fd, n, addr)
            return d if len(d) == n else None
        except OSError:
            return None

    def _strona(self, baza):
        s = self.strony.get(baza)
        if s is None:
            s = self._wprost(baza, STRONA) or b""
            if len(self.strony) < MAX_STRON:
                self.strony[baza] = s
        return s

    def czytaj(self, addr, n):
        if addr is None or addr < 0x10000 or addr > 0x7FFFFFFFFFFF:
            return None
        if self.strony is None or n > STRONA:
            return self._wprost(addr, n)
        baza = addr & ~(STRONA - 1)
        off = addr - baza
        if off + n <= STRONA:
            s = self._strona(baza)
            return s[off:off + n] if s else None
        a = self._strona(baza)
        b = self._strona(baza + STRONA)
        if not a or not b:
            return self._wprost(addr, n)
        return (a + b)[off:off + n]

    def u64(self, a):
        d = self.czytaj(a, 8)
        return struct.unpack("<Q", d)[0] if d else None

    def u32(self, a):
        d = self.czytaj(a, 4)
        return struct.unpack("<I", d)[0] if d else None

    def i32(self, a):
        d = self.czytaj(a, 4)
        return struct.unpack("<i", d)[0] if d else None

    def u16(self, a):
        d = self.czytaj(a, 2)
        return struct.unpack("<H", d)[0] if d else None

    def u8(self, a):
        d = self.czytaj(a, 1)
        return d[0] if d else None

    def f32(self, a):
        d = self.czytaj(a, 4)
        return struct.unpack("<f", d)[0] if d else None

    def wskaznik(self, a):
        """Wskaznik z podstawowa kontrola sensownosci — chroni przed chodzeniem
        po smieciach, gdy trafimy na zle pole."""
        p = self.u64(a)
        if not p or p < 0x10000 or p > 0x7FFFFFFFFFFF or (p & 0x3):
            return None
        return p

    # ── nazwy ───────────────────────────────────────────────────────────────
    # FNameEntryId: starsze 16 bitow to numer bloku, mlodsze 16 to offset
    # w bloku liczony w jednostkach 2 bajtow (wyrownanie FNameEntry).
    # Wpis zaczyna sie naglowkiem uint16: bit 0 = napis szeroki, bity 6..15 = dlugosc.
    def nazwa(self, idx):
        if not idx:
            return ""
        s = self.cache_nazw.get(idx)
        if s is not None:
            return s
        blok, off = idx >> 16, idx & 0xFFFF
        p_blok = self.cache_blokow.get(blok)
        if p_blok is None:
            p_blok = self.u64(NAMEPOOL + NAMEPOOL_BLOCKS_OFF + blok * 8) or 0
            self.cache_blokow[blok] = p_blok
        if not p_blok:
            return f"<blok {blok}?>"
        wpis = p_blok + off * 2
        naglowek = self.u16(wpis)
        if naglowek is None:
            return "<?>"
        szeroki, dlugosc = naglowek & 1, naglowek >> 6
        if dlugosc == 0 or dlugosc > 1024:
            return "<?>"
        surowe = self.czytaj(wpis + 2, dlugosc * (2 if szeroki else 1))
        if not surowe:
            return "<?>"
        try:
            s = surowe.decode("utf-16-le" if szeroki else "ascii", errors="replace")
        except Exception:
            return "<?>"
        self.cache_nazw[idx] = s
        return s

    def nazwa_z_para(self, idx, numer):
        """FName to PARA: indeks wpisu i numer instancji. Gra pokazuje
        `Foo_2147481064`, gdzie czlon liczbowy siedzi wlasnie w `numer`
        (przesuniety o jeden). Pominiecie go zlewa WSZYSTKIE instancje danej
        klasy w jedna nazwe — a wtedy migawka nie odroznia dwoch aktorow od
        jednego i cala roznica jest bezwartosciowa. Kosztowalo mnie to jedna
        nieudana kontrole, zanim wyszlo na jaw."""
        s = self.nazwa(idx)
        return f"{s}_{numer - 1}" if numer else s

    def nazwa_obiektu(self, obj):
        if not obj:
            return ""
        d = self.czytaj(obj + UOBJ_NAME_OFF, 8)
        if not d:
            return ""
        idx, numer = struct.unpack("<II", d)
        return self.nazwa_z_para(idx, numer)

    def wsk_klasy(self, obj):
        return self.wskaznik(obj + UOBJ_CLASS_OFF) if obj else None

    def nazwa_klasy(self, obj):
        k = self.wsk_klasy(obj)
        if not k:
            return ""
        s = self.cache_klas.get(k)
        if s is None:
            s = self.nazwa_obiektu(k)
            self.cache_klas[k] = s
        return s

    def sciezka(self, obj, glebokosc=8):
        """Nazwa z lancuchem obiektow nadrzednych. Dopiero to wskazuje obiekt
        jednoznacznie — samych nazw jest w swiecie mnostwo powtorzonych.
        Dla KOMPONENTU pierwszy Outer to aktor-wlasciciel."""
        czesci, o = [], obj
        while o and glebokosc > 0:
            n = self.nazwa_obiektu(o)
            if not n:
                break
            czesci.append(n)
            o = self.wskaznik(o + UOBJ_OUTER_OFF)
            glebokosc -= 1
        return ".".join(reversed(czesci))

    # ── chodzenie po tablicy obiektow ───────────────────────────────────────
    def naglowek_tablicy(self):
        tab = GUOBJECTARRAY + OBJOBJECTS_OFF
        return (self.u64(tab + CHUNKS_PTR_OFF),
                self.u32(tab + NUM_ELEMENTS_OFF),
                self.u32(tab + NUM_CHUNKS_OFF))

    def obiekty(self):
        """(indeks, adres) dla kazdego zyjacego obiektu."""
        chunks, ile, n_chunk = self.naglowek_tablicy()
        if not chunks or not ile:
            return
        for ci in range(n_chunk or 0):
            p = self.u64(chunks + ci * 8)
            if not p:
                continue
            ile_tu = min(ELEMS_PER_CHUNK, ile - ci * ELEMS_PER_CHUNK)
            if ile_tu <= 0:
                break
            blok = self._wprost(p, ile_tu * UOBJECTITEM_SIZE)
            if not blok:
                continue
            for i in range(ile_tu):
                (obj,) = struct.unpack_from("<Q", blok, i * UOBJECTITEM_SIZE)
                if obj:
                    yield ci * ELEMS_PER_CHUNK + i, obj

    def naglowki(self):
        """Szybkie przejscie: (indeks, adres, wsk_klasy, id_nazwy, wsk_outer).
        Jeden odczyt 0x28 bajtow na obiekt, ZERO rozwiazywania nazw. To jest
        wersja do migawki — nazwy rozwiazuje sie potem, poza pomiarem."""
        for idx, obj in self.obiekty():
            d = self.czytaj(obj, UOBJ_HEADER)
            if not d:
                continue
            klasa, nazwa_id, outer = struct.unpack_from("<Q", d, UOBJ_CLASS_OFF)[0], \
                struct.unpack_from("<I", d, UOBJ_NAME_OFF)[0], \
                struct.unpack_from("<Q", d, UOBJ_OUTER_OFF)[0]
            yield idx, obj, klasa, nazwa_id, outer

    # ── lancuch dziedziczenia (UStruct::SuperStruct) ─────────────────────────
    def wykryj_superstruct(self):
        """Offset SuperStruct rozni sie miedzy buildami (FStructBaseChain).
        Zamiast zgadywac — sprawdzamy: dobry offset prowadzi z dowolnej klasy
        lancuchem, ktory KONCZY sie na `Object`. Zly wpada w smieci albo urywa
        sie od razu. Wynik zapamietujemy."""
        if self._super_off is not None:
            return self._super_off
        probki = []
        for _, obj in self.obiekty():
            k = self.wsk_klasy(obj)
            if k:
                probki.append(k)
            if len(probki) >= 60:
                break
        for kand in (0x40, 0x30, 0x48, 0x38):
            trafienia = 0
            for k in probki:
                lancuch, cur, glebokosc = [], k, 0
                while cur and glebokosc < 24:
                    lancuch.append(self.nazwa_obiektu(cur))
                    cur = self.wskaznik(cur + kand)
                    glebokosc += 1
                if len(lancuch) >= 2 and lancuch[-1] == "Object":
                    trafienia += 1
            if trafienia > len(probki) * 0.8:
                self._super_off = kand
                return kand
        return None

    def lancuch_klas(self, klasa):
        """Klasa i wszystkie jej klasy nadrzedne, od najbardziej pochodnej."""
        off = self.wykryj_superstruct()
        if off is None or not klasa:
            return []
        wynik, cur, glebokosc = [], klasa, 0
        while cur and glebokosc < 32:
            wynik.append(cur)
            cur = self.wskaznik(cur + off)
            glebokosc += 1
        return wynik

    def dziedziczy_po(self, obj, nazwa_bazy):
        """Czy obiekt jest instancja klasy o tej nazwie (albo jej podklasy).
        Potrzebne, bo w grze prawie wszystko to blueprinty `BP..._C`, wiec
        porownanie samej nazwy klasy nie trafia w nic."""
        n = nazwa_bazy.lower()
        for k in self.lancuch_klas(self.wsk_klasy(obj)):
            if self.nazwa_obiektu(k).lower() == n:
                return True
        return False
