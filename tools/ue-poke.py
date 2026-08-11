#!/usr/bin/env python3
"""Kontrolowana ZMIANA właściwości obiektu gry — po nazwie, z odczytem przed i po.

Po co powstalo
--------------
Wszystkie dotychczasowe narzedzia sa bierne i to byla ich zaleta. Ale samo
czytanie nie potrafi rozstrzygnac hipotezy: „bron u klienta jest ukryta, bo
nikt nie wykonal kroku wyjmowania" brzmi tak samo wiarygodnie jak trzy inne
wyjasnienia. Rozstrzyga to dopiero KONTROLOWANA ZMIANA — zdejmij flage, zobacz,
czy bron sie pojawi. Jesli tak, mechanizm jest udowodniony ruchem, a nie
interpretacja zrzutu.

Zasada dzialania: to nie jest „edytor pamieci" z adresami na sztywno. Pole
wskazuje sie NAZWA, a offset i typ biora sie z refleksji gry — dokladnie tej
samej, ktora przeszla weryfikacje w `ue-props.py --sprawdz`. Dzieki temu zapis
trafia tam, gdzie ma trafic, takze po restarcie gry i pod innym adresem.

Bezpieczniki, ktore tu sa i po co
---------------------------------
* **Odczyt przed i po, zawsze.** Zapis, ktory sie nie udal, wyglada identycznie
  jak udany — dopoki nie sprawdzi sie wartosci po fakcie.
* **`--kopia`** zapisuje stan wyjsciowy do pliku, zeby dalo sie cofnac.
* **Typ musi sie zgadzac.** Nie pozwalam wpisac liczby w pole obiektowe.
* **Zapis pojedynczego bitu dla Bool.** Wartosci logiczne w UE dziela bajt
  z sasiadami; wpisanie calego bajtu skasowaloby kilka innych flag naraz.

UWAGA — czego ten sposob NIE zrobi
----------------------------------
UE trzyma widocznosc takze po stronie renderera. Zmiana `bVisible` w pamieci
NIE wola `MarkRenderStateDirty()`, wiec jesli komponent nie ma w ogole
reprezentacji renderujacej (bo w chwili rejestracji byl ukryty), sam zapis moze
nie wystarczyc. Brak efektu NIE obala wtedy hipotezy — znaczy tylko, ze trzeba
wywolac funkcje gry, a nie przestawic pole. To rozroznienie jest wazne, zeby
nie skreslic dobrego tropu z powodu ograniczenia narzedzia.

Uzycie
------
  ue-poke.py <pid> --obj 0x27615580 --pole bHiddenInGame --wartosc 0
  ue-poke.py <pid> --obj 0x27615580 --pole bVisible --wartosc 1 --kopia stan.json
  ue-poke.py <pid> --przywroc stan.json
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "ue_props", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue-props.py"))
_props = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_props)
Refleksja = _props.Refleksja
FP_OFFSET, FP_ELEMSIZE = _props.FP_OFFSET, _props.FP_ELEMSIZE
FBOOL_BYTEOFFSET, FBOOL_FIELDMASK = _props.FBOOL_BYTEOFFSET, _props.FBOOL_FIELDMASK

CALKOWITE = {
    "Int8Property": ("<b", 1), "ByteProperty": ("<B", 1),
    "Int16Property": ("<h", 2), "UInt16Property": ("<H", 2),
    "IntProperty": ("<i", 4), "UInt32Property": ("<I", 4),
    "Int64Property": ("<q", 8), "UInt64Property": ("<Q", 8),
}


class Zapis:
    def __init__(self, pid):
        self.pid = pid
        self.m = Pamiec(pid)
        self.r = Refleksja(self.m)
        self.fd = os.open(f"/proc/{pid}/mem", os.O_RDWR)

    def close(self):
        os.close(self.fd)
        self.m.close()

    def _pisz(self, adres, dane):
        return os.pwrite(self.fd, dane, adres) == len(dane)

    def ustaw(self, obj, nazwa_pola, wartosc):
        """Zwraca (typ, przed, po, czy_sie_udalo, opis_do_kopii)."""
        m, r = self.m, self.r
        p = r.znajdz_pole(m.wsk_klasy(obj), nazwa_pola)
        if not p:
            return None, None, None, False, f"brak pola {nazwa_pola}"
        t = r.typ(p)
        off = m.i32(p + FP_OFFSET)
        adres = obj + off

        przed = r.wartosc(p, obj)

        if t == "BoolProperty":
            bo = m.u8(p + FBOOL_BYTEOFFSET) or 0
            maska = m.u8(p + FBOOL_FIELDMASK) or 0xFF
            adres += bo
            m.odswiez()
            bajt = m.u8(adres)
            if bajt is None:
                return t, przed, None, False, "nie moge odczytac bajtu"
            nowy = (bajt | maska) if int(wartosc) else (bajt & ~maska & 0xFF)
            ok = self._pisz(adres, bytes([nowy]))
            kopia = {"typ": t, "adres": adres, "bajt_przed": bajt, "maska": maska}
        elif t in CALKOWITE:
            fmt, n = CALKOWITE[t]
            stare = m.czytaj(adres, n)
            ok = self._pisz(adres, struct.pack(fmt, int(wartosc)))
            kopia = {"typ": t, "adres": adres, "bajty_przed": stare.hex()}
        elif t == "FloatProperty":
            stare = m.czytaj(adres, 4)
            ok = self._pisz(adres, struct.pack("<f", float(wartosc)))
            kopia = {"typ": t, "adres": adres, "bajty_przed": stare.hex()}
        else:
            return t, przed, None, False, f"typ {t} — nie ruszam"

        m.odswiez()
        po = r.wartosc(p, obj)
        return t, przed, po, ok, kopia


def main():
    ap = argparse.ArgumentParser(description="kontrolowana zmiana wlasciwosci obiektu UE")
    ap.add_argument("pid", type=int, nargs="?")
    ap.add_argument("--obj", help="adres obiektu (hex)")
    ap.add_argument("--pole", action="append", default=[],
                    help="nazwa=wartosc; mozna podac wiele razy")
    ap.add_argument("--kopia", help="zapisz stan wyjsciowy do tego pliku")
    ap.add_argument("--przywroc", help="cofnij zmiany z pliku kopii")
    a = ap.parse_args()

    if a.przywroc:
        with open(a.przywroc) as f:
            dane = json.load(f)
        fd = os.open(f"/proc/{dane['pid']}/mem", os.O_RDWR)
        ile = 0
        for w in dane["zmiany"]:
            k = w["kopia"]
            if k["typ"] == "BoolProperty":
                os.pwrite(fd, bytes([k["bajt_przed"]]), k["adres"])
            else:
                os.pwrite(fd, bytes.fromhex(k["bajty_przed"]), k["adres"])
            ile += 1
        os.close(fd)
        print(f"przywrocono {ile} wartosci")
        return 0

    if not a.pid or not a.obj or not a.pole:
        print("podaj: <pid> --obj 0xADDR --pole nazwa=wartosc [...]  albo --przywroc plik")
        return 1

    z = Zapis(a.pid)
    obj = int(a.obj, 16)
    print(f"obiekt 0x{obj:X}  {z.m.nazwa_obiektu(obj)} [{z.m.nazwa_klasy(obj)}]")
    zmiany = []
    for para in a.pole:
        if "=" not in para:
            print(f"  {para}: brak '=' — pomijam")
            continue
        nazwa, wart = para.split("=", 1)
        t, przed, po, ok, kopia = z.ustaw(obj, nazwa, wart)
        stan = "OK" if ok and str(po) != str(przed) else \
               ("bez zmiany (juz taka wartosc)" if ok and str(po) == str(przed) else "NIEUDANE")
        print(f"  {nazwa:22s} [{t}]  {przed}  ->  {po}   {stan}")
        if ok and isinstance(kopia, dict):
            zmiany.append({"pole": nazwa, "kopia": kopia})
    if a.kopia and zmiany:
        with open(a.kopia, "w") as f:
            json.dump({"pid": a.pid, "obiekt": obj, "zmiany": zmiany}, f, indent=1)
        print(f"kopia stanu wyjsciowego: {a.kopia}")
    z.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
