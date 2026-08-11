#!/usr/bin/env python3
"""Czarna skrzynka przebiegu — gracz gra normalnie, my mamy z tego szereg czasowy.

Po co
-----
Dotad kazde pytanie o pionek zdalnego gracza kosztowalo osobne wejscie do gry
i osobny odczyt „na teraz". To jest droga w dwie strony: gracz musi byc pod
reka, a odczyt i tak trafia w przypadkowa chwile (zasada 6 — pojedynczy odczyt
z zewnatrz zwraca „nic sie nie dzieje", co wyglada jak wynik).

Ten skrypt odwraca ten uklad. Gracz gra ile chce, a my przez caly ten czas
probkujemy OBU graczy naraz i zapisujemy wszystko, co dotad czytalismy recznie:
tryb ruchu, przyspieszenie, predkosc, znacznik wejscia ruchu razem z jego
wiekiem, stan maszyny i KOMPLET warunkow przejsc. Materialu wystarcza potem na
godziny analizy bez uruchamiania gry.

Czego NIE robi: niczego nie zapisuje do pamieci gry. Same odczyty.

Uzycie
------
  tools/rejestrator.py <pid-hosta> <plik.tsv> [minuty] [--hz N]
  tools/rejestrator.py 75171 logs/t-dlugi/szereg.tsv 120

Odczyt wyniku:
  tools/rejestrator.py --podsumuj logs/t-dlugi/szereg.tsv
"""
import argparse
import struct
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from ue_common import Pamiec, UOBJ_CLASS_OFF  # noqa: E402

# offsety — wszystkie potwierdzone refleksja albo deasemblacja (docs/ADRESY.md)
COMP_PREDKOSC   = 0x0C4
COMP_POSTAC     = 0x130
COMP_TRYB       = 0x168
COMP_PRZYSP     = 0x22C
CHAR_KONTROLER  = 0x258
CHAR_MASZYNA    = 0x968
CHAR_ZNACZNIK   = 0xC74
PC_PLAYER       = 0x298
SM_WARUNKI      = 0x110
SM_STAN         = 0x178
KOMP_SWIAT      = 0x0A8
SWIAT_CZAS      = 0x5A0

KLASA_POSTACI = "BPDimensionPlayerCharacter_C"
KLASA_KOMP    = "DimensionMovementComponent"
CHAR_ASC      = 0x528          # DimensionAbilitySystemComponent postaci
ASC_ATTRSETS  = 0x140          # TArray<UAttributeSet*> SpawnedAttributes
FP_OFFSET     = 0x4C           # FProperty::Offset_Internal

# Atrybuty staminy — nazwy z rejestracji refleksji (WIEDZA §3h). Offsety w
# zestawie NIE sa stale i nie da sie ich wziac ze zrzutu: gra siega po nie przez
# `FindProperty` po nazwie. Rozwiazujemy je RAZ, na starcie, i potem czytamy
# surowe floaty — inaczej kazda probka kosztowalaby przejscie lancucha klas.
ATRYBUTY = ["Stamina", "StaminaRegenSpeed", "ActualStaminaRegenSpeed",
            "StaminaMovementModifier"]


def dlugosc3(p, adres):
    b = p.czytaj(adres, 12)
    if not b or len(b) < 12:
        return -1.0
    x, y, z = struct.unpack("<fff", b)
    return (x * x + y * y + z * z) ** 0.5


class Gracz:
    def __init__(self, pionek, komp, kto):
        self.pionek, self.komp, self.kto = pionek, komp, kto
        self.maszyna = 0
        self.warunki = []          # [(nazwa, offset_wpisu)]
        self.atrybuty = []         # [(nazwa, adres_CurrentValue)]


def znajdz_proces(czysty=False):
    """PID gry. `czysty` = instancja SPOZA naszych prefiksow, czyli niemodowana.

    Wzorca szukamy wlasnie tam: dopoki mierzymy tylko wlasne instancje, nie
    wiemy, ktora dziwna wartosc jest skutkiem moda, a ktora normalnym stanem gry.
    """
    import glob
    wyniki = []
    for sc in glob.glob("/proc/[0-9]*/comm"):
        try:
            if open(sc).read().strip() != "Witchfire-Win64":
                continue
            pid = int(sc.split("/")[2])
            env = open(f"/proc/{pid}/environ", "rb").read().decode("utf8", "replace")
            nasz = "witchfire-mp/compat" in env
            if czysty != nasz:
                wyniki.append(pid)
        except Exception:
            continue
    return wyniki[0] if wyniki else None


def przygotuj_atrybuty(p, g):
    """Adresy `CurrentValue` atrybutow staminy — rozwiazane raz, po nazwie."""
    g.atrybuty = []
    asc = p.wskaznik(g.pionek + CHAR_ASC)
    if not asc:
        return
    tab = p.wskaznik(asc + ASC_ATTRSETS)
    n = p.u32(asc + ASC_ATTRSETS + 8) or 0
    if not tab or not (0 < n <= 32):
        return
    try:
        import importlib.util, os
        sciezka = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue-props.py")
        spec = importlib.util.spec_from_file_location("ue_props", sciezka)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        refl = mod.Refleksja(p)
    except Exception:
        return
    for i in range(n):
        zestaw = p.u64(tab + i * 8)
        if not zestaw:
            continue
        klasa = p.wskaznik(zestaw + UOBJ_CLASS_OFF)
        if not klasa:
            continue
        for nz in ATRYBUTY:
            if any(a[0] == nz for a in g.atrybuty):
                continue
            pole = refl.znajdz_pole(klasa, nz)
            if not pole:
                continue
            off = p.i32(pole + FP_OFFSET)
            if not off or not (0 < off < 0x4000):
                continue
            # TYP, nie zgadywanie. Czesc atrybutow to `FGameplayAttributeData`
            # (8 B: BaseValue, CurrentValue), a czesc ZWYKLE floaty (4 B).
            # Doliczanie `+4` wszystkim przesuwalo etykiety o jedno pole:
            # `StaminaMovementModifier` lezy 4 bajty za `ActualStaminaRegenSpeed`,
            # wiec „CurrentValue" pierwszego bylo w rzeczywistosci drugim.
            # Wylapane przez porownanie z `stan-gracza.py` — bez tego caly
            # wzorzec mialby zle nazwy kolumn i nikt by tego nie zauwazyl.
            t = refl.typ(pole)
            przesun = 4 if t == "StructProperty" else 0
            g.atrybuty.append((nz, zestaw + off + przesun))


def znajdz_graczy(p):
    """Jedno przejscie tablicy obiektow: pionki graczy i ich komponenty ruchu.

    Uzywamy `naglowki()` (jeden odczyt 0x28 B na obiekt, bez rozwiazywania
    nazw), a nazwe klasy rozwiazujemy raz na KLASE, nie raz na obiekt — inaczej
    przejscie 280 tysiecy obiektow trwa minuty zamiast sekund.
    """
    pionki, komponenty = [], []
    nazwy = {}
    for _idx, obj, klasa, _idn, _outer in p.naglowki():
        if not klasa:
            continue
        n = nazwy.get(klasa)
        if n is None:
            n = p.nazwa_obiektu(klasa)
            nazwy[klasa] = n
        if n == KLASA_POSTACI:
            pionki.append(obj)
        elif n == KLASA_KOMP:
            komponenty.append(obj)

    gracze = []
    for k in komponenty:
        wl = p.wskaznik(k + COMP_POSTAC)
        if wl in pionki:
            if p.nazwa_obiektu(wl).startswith("Default__"):
                continue
            gracze.append(Gracz(wl, k, czyj(p, wl)))
    return gracze


def czyj(p, pionek):
    """HOST czy KLIENT — po klasie obiektu `Player` kontrolera.

    Rola sieciowa tego NIE rozstrzyga: na serwerze OBA pionki maja `Role == 3`.
    """
    pc = p.wskaznik(pionek + CHAR_KONTROLER)
    if not pc:
        return "?"
    gracz = p.wskaznik(pc + PC_PLAYER)
    if not gracz:
        return "bez-Player"
    kl = p.wskaznik(gracz + UOBJ_CLASS_OFF)
    if not kl:
        return "?"
    return "HOST" if p.nazwa_obiektu(kl) == "DimensionLocalPlayer" else "KLIENT"


def przygotuj(p, g):
    przygotuj_atrybuty(p, g)
    g.maszyna = p.wskaznik(g.pionek + CHAR_MASZYNA) or 0
    g.warunki = []
    if not g.maszyna:
        return
    d = p.wskaznik(g.maszyna + SM_WARUNKI)
    n = p.u32(g.maszyna + SM_WARUNKI + 8) or 0
    if not d or not (0 < n <= 64):
        return
    for i in range(n):
        tag = p.u64(d + i * 16) or 0
        g.warunki.append((p.nazwa(tag & 0xFFFFFFFF) or f"tag{tag:X}", d + i * 16 + 8))


def wiersz(p, g, t):
    tryb = p.czytaj(g.komp + COMP_TRYB, 1)
    if not tryb:
        return None                      # obiekt zniknal — trzeba szukac od nowa
    zn = p.czytaj(g.pionek + CHAR_ZNACZNIK, 4)
    znacznik = struct.unpack("<f", zn)[0] if zn else -999.0
    swiat = p.wskaznik(g.maszyna + KOMP_SWIAT) if g.maszyna else 0
    zegar = -1.0
    if swiat:
        cb = p.czytaj(swiat + SWIAT_CZAS, 4)
        if cb:
            zegar = struct.unpack("<f", cb)[0]
    stan = p.u32(g.maszyna + SM_STAN) if g.maszyna else -1
    war = [str(p.u32(off) if p.u32(off) is not None else -1) for _n, off in g.warunki]
    for _nz, adr in g.atrybuty:
        b = p.czytaj(adr, 4)
        war.append(f"{struct.unpack('<f', b)[0]:.2f}" if b else "-1")
    return "\t".join([f"{t:.1f}", g.kto, str(tryb[0]),
                      f"{dlugosc3(p, g.komp + COMP_PRZYSP):.0f}",
                      f"{dlugosc3(p, g.komp + COMP_PREDKOSC):.0f}",
                      f"{znacznik:.3f}", f"{zegar:.1f}",
                      f"{zegar - znacznik:.2f}", str(stan if stan is not None else -1)]
                     + war)


def podsumuj(sciezka):
    """Co z tego wyszlo — bez wczytywania calosci do pamieci."""
    naglowek, wiersze = None, 0
    stat = {}
    for l in open(sciezka):
        l = l.rstrip("\n")
        if l.startswith("#"):
            continue
        if naglowek is None and l.startswith("czas\t"):
            naglowek = l.split("\t"); continue
        if not naglowek:
            continue
        c = l.split("\t")
        if len(c) != len(naglowek):
            continue
        wiersze += 1
        kto = c[1]
        s = stat.setdefault(kto, {"n": 0, "tryby": {}, "stany": {}, "war": {},
                                  "maxv": 0.0, "maxa": 0.0})
        s["n"] += 1
        s["tryby"][c[2]] = s["tryby"].get(c[2], 0) + 1
        s["stany"][c[8]] = s["stany"].get(c[8], 0) + 1
        try:
            s["maxa"] = max(s["maxa"], float(c[3])); s["maxv"] = max(s["maxv"], float(c[4]))
        except ValueError:
            pass
        for i, nz in enumerate(naglowek[9:], start=9):
            if i >= len(c):
                continue
            if "." in c[i]:                      # atrybut liczbowy, nie warunek 0/1
                w = s.setdefault("atr", {}).setdefault(nz, [1e30, -1e30, None])
                try:
                    v = float(c[i])
                except ValueError:
                    continue
                w[0] = min(w[0], v); w[1] = max(w[1], v); w[2] = v
            elif c[i] == "1":
                s["war"][nz] = s["war"].get(nz, 0) + 1

    print(f"probek: {wiersze}\n")
    TRYBY = {"0": "None", "1": "Walking", "2": "NavWalking", "3": "Falling",
             "4": "Swimming", "5": "Flying", "6": "Custom"}
    for kto, s in sorted(stat.items()):
        print(f"══ {kto}   ({s['n']} probek, maks |przysp| {s['maxa']:.0f}, "
              f"maks |predk| {s['maxv']:.0f})")
        t = "  ".join(f"{TRYBY.get(k,k)}={100*v/s['n']:.0f}%"
                      for k, v in sorted(s["tryby"].items(), key=lambda x: -x[1]))
        print(f"   tryb ruchu:   {t}")
        st = "  ".join(f"{k}={100*v/s['n']:.0f}%"
                       for k, v in sorted(s["stany"].items(), key=lambda x: -x[1]))
        print(f"   stan maszyny: {st}")
        print("   warunki prawdziwe (% czasu):")
        for nz, v in sorted(s["war"].items(), key=lambda x: -x[1]):
            print(f"      {nz:<48} {100*v/s['n']:5.1f}%")
        if not s["war"]:
            print("      (zaden ani razu)")
        if s.get("atr"):
            print("   atrybuty (min / maks / ostatni):")
            for nz, (lo, hi, ost) in sorted(s["atr"].items()):
                print(f"      {nz:<48} {lo:8.2f} {hi:8.2f} {ost if ost is None else f'{ost:8.2f}'}")
        print()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("pid", nargs="?", help="PID gry albo `auto` / `wzorzec`")
    a.add_argument("plik", nargs="?")
    a.add_argument("minuty", nargs="?", type=float, default=120.0)
    a.add_argument("--hz", type=float, default=2.0)
    a.add_argument("--podsumuj", metavar="PLIK")
    a.add_argument("--policz", metavar="PID",
                   help="wypisz LICZBE zywych postaci gracza i wyjdz (sygnal 'host na wyprawie')")
    x = a.parse_args()

    if x.podsumuj:
        podsumuj(x.podsumuj); return 0
    if x.policz:
        # Uzywane przez `dozorca.sh` jako jednoznaczny sygnal wejscia na wyprawe:
        # postac gracza istnieje TYLKO na wyprawie, w odroznieniu od `GWorld`,
        # ktore zmienia sie takze przy starcie gry i przy ladowaniu hubu.
        try:
            print(len(znajdz_graczy(Pamiec(int(x.policz), buforuj=True))))
        except Exception:
            print(0)
        return 0
    if not x.pid or not x.plik:
        print(__doc__); return 2

    if x.pid in ("wzorzec", "auto"):
        pid = znajdz_proces(czysty=(x.pid == "wzorzec"))
        if not pid:
            print("nie znalazlem " + ("CZYSTEJ (niemodowanej)" if x.pid == "wzorzec"
                  else "zadnej") + " instancji Witchfire", file=sys.stderr)
            return 1
        print(f"znaleziona instancja: pid {pid}"
              + ("  (czysta, spoza naszych prefiksow)" if x.pid == "wzorzec" else ""))
    else:
        pid = int(x.pid)
    # Bufor stron WYLACZONY: probkujemy wartosci, ktore sie zmieniaja.
    p = Pamiec(pid, buforuj=False)

    gracze = znajdz_graczy(p)
    for g in gracze:
        przygotuj(p, g)
    if not gracze:
        print("nie znalazlem zadnego pionka gracza — czy host jest na wyprawie?",
              file=sys.stderr)
        return 1

    wzor = max(gracze, key=lambda g: len(g.warunki))
    naglowek = ["czas", "kto", "tryb", "przysp", "predk", "znacznik", "zegar",
                "wiek", "stan"] + [n for n, _ in wzor.warunki] \
               + [n for n, _ in wzor.atrybuty]

    f = open(x.plik, "w", buffering=1)
    f.write(f"# rejestrator, pid={pid}, {len(gracze)} graczy, {x.hz} Hz\n")
    for g in gracze:
        f.write(f"# {g.kto}: pionek 0x{g.pionek:X} komponent 0x{g.komp:X} "
                f"maszyna 0x{g.maszyna:X}\n")
    f.write("\t".join(naglowek) + "\n")
    print(f"rejestruje {len(gracze)} graczy ({', '.join(g.kto for g in gracze)}) "
          f"-> {x.plik}")

    t0 = time.time()
    okres = 1.0 / max(x.hz, 0.1)
    puste = 0
    while time.time() - t0 < x.minuty * 60:
        czas = time.time() - t0
        zle = 0
        for g in gracze:
            w = wiersz(p, g, czas)
            if w is None:
                zle += 1
            else:
                f.write(w + "\n")
        if zle == len(gracze):
            # Wszyscy znikneli: respawn albo koniec gry. Szukamy od nowa, ale
            # rzadko — przejscie tablicy obiektow kosztuje.
            puste += 1
            if puste >= 10:
                f.write(f"# {czas:.1f} szukam graczy od nowa\n")
                try:
                    gracze = znajdz_graczy(p)
                    for g in gracze:
                        przygotuj(p, g)
                except Exception:
                    pass
                puste = 0
                if not gracze:
                    f.write(f"# {czas:.1f} brak graczy — koncze\n")
                    break
        else:
            puste = 0
        time.sleep(okres)
    f.write(f"# koniec po {time.time() - t0:.0f} s\n")
    f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
