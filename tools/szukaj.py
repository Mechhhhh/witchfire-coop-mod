#!/usr/bin/env python3
"""Grep po dokumentacji, ale z NAGLOWKIEM SEKCJI, w ktorej lezy trafienie.

Po co to w ogole istnieje — i dlaczego jest takie male
-----------------------------------------------------
Pierwsza wersja tego narzedzia miala 473 linie: wlasny BM25, indeks w JSON-ie,
normalizacja diakrytykow, sprawdzanie swiezosci indeksu. Zostala skasowana,
bo znajomy autora zadal trafne pytanie: „przeciez do szukania po adresach jest
grep".

Ma racje. Pomiar (11.08, 20 przebiegow): caly przeszukiwany tekst — `docs/`,
`src/`, `tools/` razem z archiwum — to **1,1 MB**, a `grep -rn` po nim konczy
sie w **2,2 ms**; z narzutem startu Pythona wychodzi **~45 ms** na zapytanie.
Grep jest przy tym DOKLADNY — dla zapytania `0x1418002E0` chcesz trafien
identycznych, a nie podobnych. Indeks, ktory trzeba budowac, uniewazniac
i utrzymywac, nie kupuje tu niczego. Baza wektorowa tym bardziej:
embeddingi zaczynaja wygrywac, gdy korpus jest za duzy, zeby go przeczytac
w calosci, i gdy pytania sa opisowe („czym to sie rozni od..."), a nie gdy
korpus miesci sie w jednym pliku, a pytania sa o konkretne szesnastkowe adresy.

Zostala wiec jedna rzecz, ktorej `grep` naprawde nie robi: te dokumenty sa
zbudowane jako **naglowek -> hipoteza -> pomiar -> werdykt**, a `grep` pokazuje
linie w oderwaniu od sekcji. Czlowiek i tak potem otwiera plik, zeby sprawdzic,
czy to zdanie jest z sekcji „POTWIERDZONE", czy z „OBALONE" — a to jest cala
roznica. To narzedzie dokleja ten kontekst i nic wiecej.

Uzycie
------
    szukaj.py 0x1418002E0
    szukaj.py "mapa atrybutow" --kontekst 3
    szukaj.py "dołączenie" --wszystko      # dolacz takze katalog archiwalny
    szukaj.py "logLine\\(.*BRON" --regexp  # wzorzec ERE zamiast tekstu wprost

Domyslnie przeszukiwane sa `docs/`, `src/` i `tools/` — czyli cala biezaca
wiedza. Katalog archiwalny (`docs/historia/`, jesli u siebie taki trzymasz —
w tym repozytorium go NIE MA) jest poza tym zbiorem, bo zbiera wnioski pozniej
obalone; wchodzi dopiero na `--wszystko`. To dwie rozne rzeczy i nie moga
siedziec pod jednym przelacznikiem: kodu z `dllmain.cpp` potrzebujesz przy
kazdym pytaniu, obalonych hipotez prawie nigdy. Brak katalogu archiwalnego nie
jest bledem — po prostu nie ma z niego trafien.
"""
import argparse
import os
import re
import subprocess
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIELONY, ZOLTY, SZARY, KONIEC = "\033[32m", "\033[33m", "\033[90m", "\033[0m"
# Katalog archiwalny jest OPCJONALNY — w tym repozytorium go nie ma. Sciezka
# sluzy tylko do odsiania trafien, gdy nie podano `--wszystko`.
ARCHIWUM = os.path.join("docs", "historia")

# „l" z kreska nie ma rozkladu NFD, wiec sama normalizacja go nie zdejmuje.
BEZ_KRESKI = str.maketrans("łŁ", "lL")
# Litera lacinska -> jej polskie odmiany. Sluzy do zbudowania wzorca, ktory
# lapie obie strony naraz; szukanie „raz tak, raz tak" nie dziala, bo zapytanie
# bez ogonkow trafia czasem w jeden wklejony log i probe z ogonkami zjada.
OGONKI = {"a": "ą", "c": "ć", "e": "ę", "l": "ł", "n": "ń",
          "o": "ó", "s": "ś", "z": "źż"}
META = set(".[]{}()*+?^$|\\/")


def bez_ogonkow(s):
    """Kod jest pisany bez polskich znakow, dokumentacja z nimi — wiec
    „mapa atrybutów" i „mapa atrybutow" musza znajdowac to samo."""
    s = s.translate(BEZ_KRESKI)
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def wzorzec_grepa(w):
    """Zapytanie -> wzorzec ERE, w ktorym litera lacinska pasuje TAKZE do swojej
    polskiej odmiany, w obie strony.

    Przy okazji cytuje znaki specjalne: `[` albo `*` w zapytaniu ma byc znakiem,
    ktorego szukamy, a nie bledem skladni regexpu (grep konczyl sie wtedy kodem
    2, a narzedzie mowilo „brak trafien" — cisza znaczaca dwie rozne rzeczy).
    Prawdziwy regexp jest nadal dostepny pod `--regexp`.
    """
    out = []
    for z in bez_ogonkow(w):
        m = z.lower()
        if m in OGONKI:
            warianty = m + OGONKI[m]
            out.append("[" + warianty + warianty.upper() + "]")
        elif z in META:
            out.append("\\" + z)
        else:
            out.append(z)
    return "".join(out)


def naglowek_dla(plik, linie, nr):
    """Najblizszy naglowek markdown NAD trafieniem (nr liczony od 1).

    Tylko dla `.md` i tylko poza blokami ```. Bez tych dwoch warunkow „sekcja"
    bywala `#endif` z `dllmain.cpp`, `!/usr/bin/env python3` z narzedzia albo
    `# gracz klika CONTINUE` — komentarz powloki w bloku kodu. Doklejanie
    kontekstu sekcji to jedyne, co to narzedzie robi ponad `grep`, wiec podpis
    z sufitu jest tu gorszy niz brak podpisu.
    """
    if not plik.endswith(".md"):
        return ""
    nag, plot = "", False
    for i in range(min(nr, len(linie))):
        if linie[i].lstrip().startswith("```"):
            plot = not plot
        elif not plot and linie[i].startswith("#"):
            nag = linie[i].lstrip("# ").rstrip()
    return nag


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("wzorzec")
    p.add_argument("--kontekst", type=int, default=1, help="linii wokol trafienia")
    p.add_argument("--wszystko", action="store_true",
                   help="dolacz katalog archiwalny, jesli istnieje "
                        "(ARCHIWUM wnioskow OBALONYCH; w tym repo go nie ma)")
    p.add_argument("--regexp", action="store_true",
                   help="wzorzec to ERE, nie tekst wprost (bez skladania ogonkow)")
    a = p.parse_args()

    if a.kontekst < 0:
        p.error("--kontekst nie moze byc ujemny")

    # Tylko katalogi, ktore naprawde sa — inaczej grep konczy sie bledem, gdy
    # ktoregos w kopii repozytorium brakuje. Pusta lista sciezek kazalaby mu
    # czytac stdin, wiec wtedy konczymy sami.
    gdzie = [os.path.join(REPO, g) for g in ("docs", "src", "tools")]
    gdzie = [g for g in gdzie if os.path.isdir(g)]
    if not gdzie:
        print("nie ma czego przeszukiwac: brak docs/, src/ i tools/", file=sys.stderr)
        return 2
    wzorzec = a.wzorzec if a.regexp else wzorzec_grepa(a.wzorzec)
    cmd = ["grep", "-rniIE", "--", wzorzec] + gdzie
    wynik = subprocess.run(cmd, capture_output=True, text=True)
    # grep: 0 = sa trafienia, 1 = nie ma, >=2 = zapytanie sie nie wykonalo.
    # Bez tego zly wzorzec wygladal dokladnie tak samo jak pusta dokumentacja.
    if wynik.returncode >= 2:
        print("grep nie wykonal zapytania: %s" % wynik.stderr.strip(), file=sys.stderr)
        return 2
    trafienia = [l for l in wynik.stdout.splitlines() if l.strip()]

    # Bez samego siebie: `szukaj.py 0x1418002E0` z przykladu uzycia to nie jest
    # wiedza o grze, a wyglada w wynikach jak zrodlo.
    trafienia = [t for t in trafienia if not t.startswith(os.path.abspath(__file__))]
    if not a.wszystko:
        odsiej = os.sep + ARCHIWUM + os.sep
        trafienia = [t for t in trafienia if odsiej not in t]

    if not trafienia:
        print(f"brak trafien dla {a.wzorzec!r}"
              f"{'' if a.wszystko else ' (sprobuj --wszystko)'}")
        return 1

    cache = {}
    ostatni_plik = None
    for t in trafienia[:60]:
        m = re.match(r"^(.*?):(\d+):(.*)$", t)
        if not m:
            continue
        plik, nr, tresc = m.group(1), int(m.group(2)), m.group(3)
        if plik not in cache:
            try:
                cache[plik] = open(plik, encoding="utf-8", errors="replace").read().splitlines()
            except OSError:
                continue
        linie = cache[plik]
        wzgl = os.path.relpath(plik, REPO)

        if plik != ostatni_plik:
            print(f"\n{ZIELONY}── {wzgl}{KONIEC}")
            ostatni_plik = plik
        nag = naglowek_dla(plik, linie, nr)
        print(f"  {ZOLTY}{wzgl}:{nr}{KONIEC}"
              f"{'   ' + SZARY + nag + KONIEC if nag else ''}")
        od, do = max(0, nr - 1 - a.kontekst), min(len(linie), nr + a.kontekst)
        for i in range(od, do):
            znak = ">" if i == nr - 1 else " "
            print(f"    {znak} {linie[i][:150]}")

    if len(trafienia) > 60:
        print(f"\n... i jeszcze {len(trafienia) - 60} trafien (zaweź wzorzec)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
