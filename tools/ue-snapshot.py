#!/usr/bin/env python3
"""Migawka WSZYSTKICH obiektow gry + porownywarka dwoch migawek.

Po co powstalo
--------------
Do tej pory kazde pytanie o stan gry brzmialo "czy X istnieje?" i wymagalo, zeby
wczesniej wpasc na pomysl, ze warto zapytac akurat o X. Migawka odwraca kolejnosc:
zapisuje wszystko, a roznica miedzy dwoma migawkami sama pokazuje, CO sie
zmienilo w chwili zdarzenia. Przy dolaczeniu klienta znikaja bron, rece i
celownik — ale nie wiadomo, czy tylko one. Roznica odpowie.

Sluzy wszystkim trzem problemom, nie tylko broni:
  * bron    — czy aktor znika z tablicy obiektow, czy zostaje,
  * zamrozenie klienta — co przybywa u klienta w sekundzie, w ktorej staje,
  * awaria hosta — co znika tuz przed zrzutem.

Dwie rzeczy, ktore trzeba bylo zrobic inaczej niz "po prostu wypisac liste"
------------------------------------------------------------------------
1. **Szybkosc jest czescia poprawnosci.** Migawka robiona minute to nie migawka,
   tylko smuga: jej poczatek i koniec pochodza z dwoch roznych chwil gry. Przy
   zjawisku trwajacym sekunde to unieważnia pomiar. Dlatego przemial tablicy
   czyta surowe naglowki (jeden odczyt na obiekt) i NIE rozwiazuje nazw —
   nazwy rozwiazuja sie po zakonczeniu przemialu, juz poza pomiarem.
2. **Roznica kluczowana SCIEZKA, nie adresem.** Bron zniszczona i utworzona na
   nowo pod innym adresem to zupelnie inny wynik niz bron nietknieta — i wlasnie
   ten wynik chcemy zobaczyc, a nie ukryc. Adres sluzy do wykrycia odtworzenia.

Uzycie
------
  ue-snapshot.py <pid> --out logs/bron/host-przed.tsv
  ue-snapshot.py --diff logs/bron/host-przed.tsv logs/bron/host-po.tsv
  ue-snapshot.py --diff a.tsv b.tsv --only Weapon      # zawez do interesujacych
"""
import argparse
import os
import struct
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec, UOBJ_HEADER, UOBJ_CLASS_OFF, UOBJ_NAME_OFF, UOBJ_OUTER_OFF


def zrob_migawke(pid):
    """Zwraca (lista_wierszy, czas_przemialu, czas_nazw).

    Wiersz: (idx, adres, nazwa_klasy, sciezka).
    """
    m = Pamiec(pid)

    # ── faza 1: surowy przemial. Tylko to musi trafic w moment objawu. ──────
    t0 = time.time()
    surowe = []
    for idx, obj in m.obiekty():
        d = m.czytaj(obj, UOBJ_HEADER)
        if not d:
            continue
        klasa = struct.unpack_from("<Q", d, UOBJ_CLASS_OFF)[0]
        nazwa_id, nazwa_nr = struct.unpack_from("<II", d, UOBJ_NAME_OFF)
        outer = struct.unpack_from("<Q", d, UOBJ_OUTER_OFF)[0]
        surowe.append((idx, obj, klasa, (nazwa_id, nazwa_nr), outer))
    t_przemial = time.time() - t0

    # ── faza 2: rozwiazywanie nazw, juz na zebranych danych ────────────────
    t0 = time.time()
    # Lancuch Outer budujemy z wlasnej tablicy, bez wracania do pamieci procesu:
    # kazdy Outer jest obiektem, wiec i tak go mamy.
    po_adresie = {obj: (para, outer) for _, obj, _, para, outer in surowe}

    def sciezka(obj):
        czesci, o, g = [], obj, 0
        while o and g < 8:
            wpis = po_adresie.get(o)
            if wpis is None:
                # Outer spoza tablicy zdarza sie przy obiektach w trakcie
                # niszczenia — czytamy go wtedy wprost.
                n = m.nazwa_obiektu(o)
                if not n:
                    break
                czesci.append(n)
                o = m.wskaznik(o + UOBJ_OUTER_OFF)
            else:
                para, outer = wpis
                czesci.append(m.nazwa_z_para(*para))
                o = outer
            g += 1
        return ".".join(reversed(czesci))

    # Nazwe klasy rozwiazujemy po WSKAZNIKU klasy: klas jest kilka tysiecy,
    # obiektow dwiescie tysiecy — bez tego bufora robimy te sama prace 40 razy.
    nazwy_klas = {}

    def nazwa_klasy(k):
        if not k:
            return "?"
        s = nazwy_klas.get(k)
        if s is None:
            wpis = po_adresie.get(k)
            s = m.nazwa_z_para(*wpis[0]) if wpis else m.nazwa_obiektu(k)
            nazwy_klas[k] = s
        return s

    wiersze = []
    for idx, obj, klasa, _para, _outer in surowe:
        wiersze.append((idx, obj, nazwa_klasy(klasa), sciezka(obj)))
    t_nazwy = time.time() - t0
    m.close()
    return wiersze, t_przemial, t_nazwy


def zapisz(wiersze, sciezka_pliku, pid, t_przemial, t_nazwy):
    os.makedirs(os.path.dirname(os.path.abspath(sciezka_pliku)), exist_ok=True)
    with open(sciezka_pliku, "w") as f:
        f.write(f"# migawka pid={pid} czas={time.strftime('%H:%M:%S')} "
                f"obiektow={len(wiersze)} przemial={t_przemial:.2f}s nazwy={t_nazwy:.2f}s\n")
        f.write("# idx\tadres\tklasa\tsciezka\n")
        for idx, obj, klasa, sc in wiersze:
            f.write(f"{idx}\t{obj:X}\t{klasa}\t{sc}\n")


def wczytaj(sciezka_pliku):
    wiersze = []
    naglowek = ""
    with open(sciezka_pliku) as f:
        for linia in f:
            if linia.startswith("#"):
                if not naglowek:
                    naglowek = linia.strip()
                continue
            cz = linia.rstrip("\n").split("\t")
            if len(cz) == 4:
                wiersze.append((int(cz[0]), int(cz[1], 16), cz[2], cz[3]))
    return wiersze, naglowek


def roznica(a_plik, b_plik, tylko=None, limit=60):
    a, na = wczytaj(a_plik)
    b, nb = wczytaj(b_plik)
    print(f"A: {os.path.basename(a_plik)}  {na}")
    print(f"B: {os.path.basename(b_plik)}  {nb}")
    print(f"   obiektow: A={len(a)}  B={len(b)}  roznica={len(b) - len(a):+d}\n")

    def klucz(w):
        return (w[2], w[3])          # (klasa, sciezka)

    ka, kb = Counter(map(klucz, a)), Counter(map(klucz, b))
    adr_a, adr_b = defaultdict(list), defaultdict(list)
    for w in a:
        adr_a[klucz(w)].append(w[1])
    for w in b:
        adr_b[klucz(w)].append(w[1])

    def pasuje(k):
        return tylko is None or tylko.lower() in (k[0] + " " + k[1]).lower()

    zniknely = [(k, ka[k] - kb.get(k, 0)) for k in ka if ka[k] > kb.get(k, 0) and pasuje(k)]
    powstaly = [(k, kb[k] - ka.get(k, 0)) for k in kb if kb[k] > ka.get(k, 0) and pasuje(k)]
    # Ten sam klucz, inny adres = obiekt zniszczony i utworzony na nowo.
    # Bez tego wygladalby na "nietkniety".
    odtworzone = [k for k in ka
                  if k in kb and pasuje(k) and set(adr_a[k]).isdisjoint(adr_b[k])]

    def wypisz(tytul, pozycje, znak):
        print(f"── {tytul}: {len(pozycje)} ─────────────────────────────")
        for k, ile in sorted(pozycje, key=lambda x: (-x[1], x[0][0]))[:limit]:
            print(f"  {znak} {ile:3d}x  {k[0]:34s} {k[1]}")
        if len(pozycje) > limit:
            print(f"  ... (jeszcze {len(pozycje) - limit}, uzyj --limit)")
        print()

    wypisz("ZNIKNELO (bylo w A, nie ma w B)", zniknely, "-")
    wypisz("POJAWILO SIE (nie bylo w A, jest w B)", powstaly, "+")

    print(f"── ODTWORZONE (ta sama sciezka, INNY adres): {len(odtworzone)} ──────")
    for k in sorted(odtworzone)[:limit]:
        print(f"  ~ {k[0]:34s} {k[1]}")
    if len(odtworzone) > limit:
        print(f"  ... (jeszcze {len(odtworzone) - limit})")
    print()

    # Podsumowanie po klasach — pokazuje kierunek zmiany, gdy pozycji sa setki.
    zbiorczo = Counter()
    for k, ile in zniknely:
        zbiorczo[k[0]] -= ile
    for k, ile in powstaly:
        zbiorczo[k[0]] += ile
    istotne = [(kl, d) for kl, d in zbiorczo.items() if d]
    if istotne:
        print("── bilans po klasach (tylko niezerowe) ─────────────────")
        for kl, d in sorted(istotne, key=lambda x: -abs(x[1]))[:40]:
            print(f"  {d:+5d}  {kl}")


def main():
    ap = argparse.ArgumentParser(description="migawka obiektow UE i porownywarka")
    ap.add_argument("pid", nargs="?", type=int)
    ap.add_argument("--out", help="zapisz migawke do pliku")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"), help="porownaj dwie migawki")
    ap.add_argument("--only", help="w roznicy pokaz tylko pozycje zawierajace ten tekst")
    ap.add_argument("--limit", type=int, default=60)
    a = ap.parse_args()

    if a.diff:
        roznica(a.diff[0], a.diff[1], a.only, a.limit)
        return 0

    if not a.pid:
        print("podaj pid (migawka) albo --diff A B")
        return 1

    wiersze, tp, tn = zrob_migawke(a.pid)
    print(f"obiektow: {len(wiersze)}  przemial: {tp:.2f}s  nazwy: {tn:.2f}s")
    if a.out:
        zapisz(wiersze, a.out, a.pid, tp, tn)
        print(f"zapisano: {a.out}")
    else:
        for idx, obj, kl, sc in wiersze[:a.limit]:
            print(f"[{idx:6d}] 0x{obj:X}  {kl:30s} {sc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
