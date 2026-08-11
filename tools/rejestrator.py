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
# Kolumny sa STALE. Gdy atrybutu nie ma, idzie „-" zamiast zniknac — inaczej
# po respawnie naglowek przestalby pasowac do wierszy i caly plik bylby do kosza,
# a wygladalby poprawnie. Przy jednej dlugiej sesji to jest najgorszy mozliwy blad.
ATRYBUTY = ["Health", "MaxHealth",
            "Stamina", "StaminaRegenSpeed", "ActualStaminaRegenSpeed",
            "StaminaMovementModifier"]
ATR_BRONI = ["ClipSize", "CurrentAmmoInClip", "CurrentAmmo", "PendingClipRefill"]
ILE_BRONI = 3                  # stale gniazda, zeby kolumny nie plywaly

CHAR_EKWIPUNEK = 0x960         # DimensionInventoryComponent postaci
INV_BIEZACA    = 0x148         # CurrentWeaponIndex
BRON_ASC       = 0x958
BRON_PIONEK    = 0x998
COMP_AKTUALIZ  = 0x0B0         # UpdatedComponent — z niego bierzemy pozycje


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
        self.atrybuty = {}         # nazwa -> adres wartosci
        self.bronie = []           # [(nazwa_klasy, {atrybut: adres})]
        self.pozycja = 0           # adres FVector RelativeLocation kapsuly
        self.ekwipunek = 0


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


def _refleksja(p):
    """`Refleksja` z `ue-props.py` — plik ma myslnik, wiec przez importlib."""
    import importlib.util, os
    sciezka = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue-props.py")
    spec = importlib.util.spec_from_file_location("ue_props", sciezka)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Refleksja(p)


def _adres_atrybutu(p, refl, obiekt, nazwa):
    """Adres WARTOSCI atrybutu w obiekcie, albo 0.

    Przesuniecie bierze sie z TYPU wlasciwosci, nie z zalozenia: czesc atrybutow
    to `FGameplayAttributeData` (8 B: BaseValue, CurrentValue), a czesc zwykle
    floaty (4 B). Doliczanie `+4` wszystkim przesuwalo etykiety o jedno pole
    (`StaminaMovementModifier` lezy 4 bajty za `ActualStaminaRegenSpeed`),
    a wartosci dalej wygladaly wiarygodnie. Zlapane porownaniem ze `stan-gracza.py`.
    """
    klasa = p.wskaznik(obiekt + UOBJ_CLASS_OFF)
    if not klasa:
        return 0
    pole = refl.znajdz_pole(klasa, nazwa)
    if not pole:
        return 0
    off = p.i32(pole + FP_OFFSET)
    if not off or not (0 < off < 0x4000):
        return 0
    return obiekt + off + (4 if refl.typ(pole) == "StructProperty" else 0)


def przygotuj_atrybuty(p, g, refl):
    """Atrybuty postaci, jej bronie i pozycja — rozwiazane RAZ, po nazwie."""
    g.atrybuty = {}
    asc = p.wskaznik(g.pionek + CHAR_ASC)
    if asc:
        tab = p.wskaznik(asc + ASC_ATTRSETS)
        n = p.u32(asc + ASC_ATTRSETS + 8) or 0
        for i in range(min(n, 32)):
            zestaw = p.u64(tab + i * 8) if tab else 0
            if not zestaw:
                continue
            for nz in ATRYBUTY:
                if nz in g.atrybuty:
                    continue
                a = _adres_atrybutu(p, refl, zestaw, nz)
                if a:
                    g.atrybuty[nz] = a

    # Pozycja — z komponentu, ktory ruch faktycznie przesuwa. Offset
    # `RelativeLocation` tez z refleksji, bo zgadniety bylby wartoscia losowa.
    g.pozycja = 0
    kapsula = p.wskaznik(g.komp + COMP_AKTUALIZ)
    if kapsula:
        klasa = p.wskaznik(kapsula + UOBJ_CLASS_OFF)
        pole = refl.znajdz_pole(klasa, "RelativeLocation") if klasa else None
        if pole:
            off = p.i32(pole + FP_OFFSET)
            if off and 0 < off < 0x4000:
                g.pozycja = kapsula + off

    g.ekwipunek = p.wskaznik(g.pionek + CHAR_EKWIPUNEK) or 0
    przygotuj_bronie(p, g, refl)


def przygotuj_bronie(p, g, refl):
    """Bronie NALEZACE do tego pionka (`bron+0x998 == pionek`), stale gniazda."""
    g.bronie = []
    nazwy = {}
    for _i, obj, klasa, _n, _o in p.naglowki():
        if not klasa or len(g.bronie) >= ILE_BRONI:
            continue
        nk = nazwy.get(klasa)
        if nk is None:
            nk = p.nazwa_obiektu(klasa)
            nazwy[klasa] = nk
        if "Weapon" not in nk and "HandCannon" not in nk and "Rifle" not in nk:
            continue
        if p.wskaznik(obj + BRON_PIONEK) != g.pionek:
            continue
        asc = p.wskaznik(obj + BRON_ASC)
        if not asc:
            continue
        pola = {}
        tab = p.wskaznik(asc + ASC_ATTRSETS)
        n = p.u32(asc + ASC_ATTRSETS + 8) or 0
        for i in range(min(n, 32)):
            zestaw = p.u64(tab + i * 8) if tab else 0
            if not zestaw:
                continue
            for nz in ATR_BRONI:
                if nz in pola:
                    continue
                a = _adres_atrybutu(p, refl, zestaw, nz)
                if a:
                    pola[nz] = a
        if pola:
            g.bronie.append((nk, pola))


def znajdz_graczy(p):
    """Jedno przejscie tablicy obiektow: pionki graczy i ich komponenty ruchu.

    `naglowki()` daje jeden odczyt 0x28 B na obiekt bez rozwiazywania nazw,
    a nazwe klasy rozwiazujemy raz na KLASE — inaczej przejscie 280 tysiecy
    obiektow trwa minuty zamiast sekund.
    """
    pionki, komponenty, nazwy = set(), [], {}
    for _idx, obj, klasa, _idn, _outer in p.naglowki():
        if not klasa:
            continue
        n = nazwy.get(klasa)
        if n is None:
            n = p.nazwa_obiektu(klasa)
            nazwy[klasa] = n
        if n == KLASA_POSTACI:
            pionki.add(obj)
        elif n == KLASA_KOMP:
            komponenty.append(obj)

    gracze = []
    for k in komponenty:
        wl = p.wskaznik(k + COMP_POSTAC)
        if wl in pionki and not p.nazwa_obiektu(wl).startswith("Default__"):
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


def przygotuj(p, g, refl=None):
    try:
        przygotuj_atrybuty(p, g, refl or _refleksja(p))
    except Exception:
        pass                        # brak atrybutow nie moze przerwac nagrywania
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


def _f(p, adres, fmt="{:.2f}"):
    if not adres:
        return "-"
    b = p.czytaj(adres, 4)
    return fmt.format(struct.unpack("<f", b)[0]) if b else "-"


def naglowek_kolumn(warunki):
    kol = ["czas", "kto", "tryb", "przysp", "predk", "x", "y", "z",
           "znacznik", "zegar", "wiek", "stan", "bron_idx"]
    kol += list(warunki)
    kol += ATRYBUTY
    for i in range(ILE_BRONI):
        kol += [f"b{i+1}_{a}" for a in ATR_BRONI]
    return kol


def wiersz(p, g, t):
    """Jeden wiersz o STALEJ liczbie kolumn. Brakujaca wartosc to `-`, nigdy
    zniknieta kolumna — plik ma sie dac czytac po godzinach grania."""
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
    idx = p.i32(g.ekwipunek + INV_BIEZACA) if g.ekwipunek else -1

    poz = ["-", "-", "-"]
    if g.pozycja:
        b = p.czytaj(g.pozycja, 12)
        if b:
            poz = [f"{v:.0f}" for v in struct.unpack("<fff", b)]

    kol = [f"{t:.1f}", g.kto, str(tryb[0]),
           f"{dlugosc3(p, g.komp + COMP_PRZYSP):.0f}",
           f"{dlugosc3(p, g.komp + COMP_PREDKOSC):.0f}"] + poz + \
          [f"{znacznik:.3f}", f"{zegar:.1f}", f"{zegar - znacznik:.2f}",
           str(stan if stan is not None else -1), str(idx if idx is not None else -1)]
    for _n, off in g.warunki:
        v = p.u32(off)
        kol.append(str(v if v is not None else -1))
    for nz in ATRYBUTY:
        kol.append(_f(p, g.atrybuty.get(nz, 0)))
    for i in range(ILE_BRONI):
        pola = g.bronie[i][1] if i < len(g.bronie) else {}
        for a in ATR_BRONI:
            kol.append(_f(p, pola.get(a, 0), "{:.0f}"))
    return "\t".join(kol)


def podsumuj(sciezka):
    """Rozklady zamiast tysiecy wierszy. Kolumny rozpoznawane po NAZWIE —
    pozycyjnie bylo krucho, bo schemat rosl."""
    naglowek, stat = None, {}
    for l in open(sciezka):
        l = l.rstrip("\n")
        if l.startswith("#"):
            continue
        if naglowek is None:
            if l.startswith("czas\t"):
                naglowek = l.split("\t")
            continue
        c = l.split("\t")
        if len(c) != len(naglowek):
            continue
        d = dict(zip(naglowek, c))
        s_ = stat.setdefault(d["kto"], {"n": 0, "tryby": {}, "stany": {}, "war": {},
                                        "licz": {}, "maxv": 0.0, "maxa": 0.0})
        s_["n"] += 1
        s_["tryby"][d["tryb"]] = s_["tryby"].get(d["tryb"], 0) + 1
        s_["stany"][d["stan"]] = s_["stany"].get(d["stan"], 0) + 1
        try:
            s_["maxa"] = max(s_["maxa"], float(d["przysp"]))
            s_["maxv"] = max(s_["maxv"], float(d["predk"]))
        except ValueError:
            pass
        for k, v in d.items():
            if k.startswith("State."):
                if v == "1":
                    s_["war"][k] = s_["war"].get(k, 0) + 1
            elif k in ATRYBUTY or k.split("_", 1)[-1] in ATR_BRONI:
                if v == "-":
                    continue
                try:
                    f = float(v)
                except ValueError:
                    continue
                w = s_["licz"].setdefault(k, [1e30, -1e30, None])
                w[0] = min(w[0], f); w[1] = max(w[1], f); w[2] = f

    TRYBY = {"0": "None", "1": "Walking", "2": "NavWalking", "3": "Falling",
             "4": "Swimming", "5": "Flying", "6": "Custom"}
    print(f"probek: {sum(v['n'] for v in stat.values())}\n")
    for kto, s_ in sorted(stat.items()):
        n = max(s_["n"], 1)
        print(f"══ {kto}   ({s_['n']} probek, maks |przysp| {s_['maxa']:.0f}, "
              f"maks |predk| {s_['maxv']:.0f})")
        print("   tryb ruchu:   " + "  ".join(
            f"{TRYBY.get(k,k)}={100*v/n:.0f}%" for k, v in sorted(s_["tryby"].items(), key=lambda x: -x[1])))
        print("   stan maszyny: " + "  ".join(
            f"{k}={100*v/n:.0f}%" for k, v in sorted(s_["stany"].items(), key=lambda x: -x[1])))
        print("   warunki prawdziwe (% czasu):")
        for nz, v in sorted(s_["war"].items(), key=lambda x: -x[1]):
            print(f"      {nz:<48} {100*v/n:5.1f}%")
        if not s_["war"]:
            print("      (zaden ani razu)")
        if s_["licz"]:
            print("   wartosci (min / maks / ostatnia):")
            for nz, (lo, hi, ost) in sorted(s_["licz"].items()):
                print(f"      {nz:<48} {lo:9.2f} {hi:9.2f} {ost:9.2f}")
        print()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("pid", nargs="?", help="PID gry albo `auto` / `wzorzec`")
    a.add_argument("plik", nargs="?")
    a.add_argument("minuty", nargs="?", type=float, default=120.0)
    a.add_argument("--hz", type=float, default=5.0)
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

    refl = None
    try:
        refl = _refleksja(p)
    except Exception:
        pass
    gracze = znajdz_graczy(p)
    for g in gracze:
        przygotuj(p, g, refl)
    if not gracze:
        print("nie znalazlem zadnego pionka gracza — czy host jest na wyprawie?",
              file=sys.stderr)
        return 1

    wzor = max(gracze, key=lambda g: len(g.warunki))
    WARUNKI = [n for n, _ in wzor.warunki]
    naglowek = naglowek_kolumn(WARUNKI)

    f = open(x.plik, "w", buffering=1)
    # Dziennik ZDARZEN obok szeregu: przy 5 Hz zmiana trybu albo stanu ginie
    # w tysiacach wierszy, a to wlasnie ona jest interesujaca.
    zd = open(x.plik.rsplit(".", 1)[0] + "-zdarzenia.tsv", "w", buffering=1)
    zd.write("czas\tkto\tco\tz\tna\n")
    poprzednie = {}
    f.write(f"# rejestrator, pid={pid}, {len(gracze)} graczy, {x.hz} Hz\n")
    for g in gracze:
        f.write(f"# {g.kto}: pionek 0x{g.pionek:X} komponent 0x{g.komp:X} "
                f"maszyna 0x{g.maszyna:X} atrybutow={len(g.atrybuty)} "
                f"broni={len(g.bronie)} pozycja={'tak' if g.pozycja else 'NIE'}\n")
        for i, (nk, _pola) in enumerate(g.bronie):
            f.write(f"#   b{i+1} = {nk}\n")
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
            try:
                w = wiersz(p, g, czas)
            except Exception:
                w = None
            if w is None:
                zle += 1
            else:
                f.write(w + "\n")
                # zmiany, ktore chce widziec bez przekopywania szeregu
                pola = dict(zip(naglowek, w.split("\t")))
                for co in ("tryb", "stan", "bron_idx"):
                    klucz = (g.kto, co)
                    stara = poprzednie.get(klucz)
                    if stara is not None and stara != pola[co]:
                        zd.write(f"{czas:.1f}\t{g.kto}\t{co}\t{stara}\t{pola[co]}\n")
                    poprzednie[klucz] = pola[co]
        if zle == len(gracze):
            # Wszyscy znikneli: respawn albo koniec gry. Szukamy od nowa, ale
            # rzadko — przejscie tablicy obiektow kosztuje.
            puste += 1
            if puste >= 10:
                f.write(f"# {czas:.1f} szukam graczy od nowa\n")
                try:
                    gracze = znajdz_graczy(p)
                    for g in gracze:
                        przygotuj(p, g, refl)
                    zd.write(f"{czas:.1f}\t-\trespawn\t-\t{len(gracze)} graczy\n")
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
    f.close(); zd.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
