#!/usr/bin/env python3
"""Funkcje gry (UFunction) — sygnatury, flagi sieciowe i ADRESY natywne.

Po co powstalo
--------------
Trzecie z narzedzi, ktorych brakowalo. `ue-props.py` mowi, JAKI jest stan
obiektu; to narzedzie mowi, KTO moze go zmienic — i daje adres, pod ktorym ta
zmiana siedzi w kodzie.

Trzy rzeczy, ktore z tego wynikaja i ktorych inaczej nie ma skad wziac:

1. **Co w ogole da sie zahaczyc po nazwie.** `RegisterHook` w UE4SS przyjmuje
   `/Script/Pakiet.Klasa:Funkcja`. Dotad te nazwy zgadywalem ze stringow
   w binarce i polowa hakow konczyla sie "hak NIEUDANY". Tu widac pelna liste
   tego, co NAPRAWDE istnieje w tym buildzie.
2. **Jakie funkcja bierze argumenty.** Hak bez znajomosci sygnatury loguje samo
   "wszedlem", a to za malo, zeby cokolwiek rozstrzygnac. Parametry siedza
   w `ChildProperties` samej `UFunction` — z flagami, ktore mowia, ktory jest
   wejsciowy, ktory wyjsciowy, a ktory to wartosc zwracana.
3. **Ktore funkcje sa RPC.** Flagi `FUNC_Net*` rozstrzygaja, czy funkcja leci
   przez siec i w ktora strone. Przy diagnozie co-opa to pierwsza rzecz, ktorej
   sie szuka, a nie da sie jej zobaczyc z zewnatrz.

Adres natywny (`Func`) przydaje sie osobno: mozna go podac `find-callers.py`,
zeby znalezc, kto ja wola, albo zahaczyc wprost z proxy DLL — a to jedyna droga
na KLIENCIE, gdzie UE4SS zabija gre.

Uwaga na pulapke UE 4.25+: funkcje wisza na `UStruct::Children` (UField*),
a wlasciwosci na osobnej liscie `ChildProperties` (FField*). Kto pomyli te dwie
listy, dostanie pusto i uzna, ze klasa nie ma metod.

Uzycie
------
  ue-funcs.py <pid> --klasa DimensionInventoryComponent
  ue-funcs.py <pid> --szukaj Weapon --rpc        tylko RPC z 'Weapon' w nazwie
  ue-funcs.py <pid> --szukaj Equip --sygnatury   z pelnymi argumentami
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "ue_props", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue-props.py"))
_props = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_props)
Refleksja = _props.Refleksja
FP_OFFSET, FP_FLAGS = _props.FP_OFFSET, _props.FP_FLAGS
FF_NEXT = _props.FF_NEXT

# UField::Next — po tym chodzi sie po liscie Children
UFIELD_NEXT = 0x28

# UFunction lezy zaraz za UStruct. Rozmiar UStruct zalezy od tego, gdzie
# wypadl SuperStruct (patrz ue_common.wykryj_superstruct), wiec liczymy
# wzglednie od niego, a nie na sztywno.
UFUNC_FLAGS_OD_SUPER  = 0x70   # EFunctionFlags (4)
UFUNC_NUMPARMS_OD_SUP = 0x74   # uint8
UFUNC_PARMSIZE_OD_SUP = 0x76   # uint16
UFUNC_NATIVE_OD_SUPER = 0x98   # wskaznik na kod natywny

FLAGI_FUNKCJI = [
    (0x00000040, "Net"),          (0x00000080, "NetReliable"),
    (0x00000100, "NetRequest"),   (0x00000200, "Exec"),
    (0x00000400, "Native"),       (0x00000800, "Event"),
    (0x00001000, "NetResponse"),  (0x00002000, "Static"),
    (0x00004000, "NetMulticast"), (0x00200000, "NetServer"),
    (0x01000000, "NetClient"),    (0x04000000, "BlueprintCallable"),
    (0x08000000, "BlueprintEvent"),
]
# CPF_* — flagi pojedynczego parametru
CPF_PARM, CPF_OUT, CPF_RETURN, CPF_REF = 0x80, 0x100, 0x400, 0x08000000


class Funkcje:
    def __init__(self, m):
        self.m = m
        self.r = Refleksja(m)
        self.so = self.r.super_off

    def funkcje_klasy(self, klasa, z_dziedziczeniem=False):
        """UFunction z listy Children. Zwraca [(klasa_deklarujaca, funkcja)]."""
        wynik = []
        klasy = self.m.lancuch_klas(klasa) if z_dziedziczeniem else [klasa]
        for k in klasy:
            p = self.m.wskaznik(k + self.so + 0x08)   # Children
            g = 0
            while p and g < 4000:
                if self.m.nazwa_klasy(p) == "Function":
                    wynik.append((k, p))
                p = self.m.wskaznik(p + UFIELD_NEXT)
                g += 1
        return wynik

    def flagi(self, f):
        v = self.m.u32(f + self.so + UFUNC_FLAGS_OD_SUPER) or 0
        return [n for bit, n in FLAGI_FUNKCJI if v & bit]

    def jest_rpc(self, f):
        v = self.m.u32(f + self.so + UFUNC_FLAGS_OD_SUPER) or 0
        return bool(v & (0x40 | 0x4000 | 0x200000 | 0x01000000))

    def natywna(self, f):
        return self.m.u64(f + self.so + UFUNC_NATIVE_OD_SUPER)

    def sygnatura(self, f):
        """Parametry z ChildProperties samej funkcji, w kolejnosci deklaracji."""
        wej, wyj, zwrot = [], [], None
        for p in self.r.wlasciwosci_klasy(f):
            fl = self.m.u64(p + FP_FLAGS) or 0
            if not (fl & CPF_PARM):
                continue
            opis = f"{self.r.typ(p)[:-8]} {self.r.nazwa_pola(p)}"
            if fl & CPF_RETURN:
                zwrot = opis
            elif fl & CPF_OUT and not (fl & CPF_REF):
                wyj.append(opis)
            else:
                wej.append(opis)
        s = "(" + ", ".join(wej) + ")"
        if wyj:
            s += " out:[" + ", ".join(wyj) + "]"
        if zwrot:
            s += " -> " + zwrot
        return s

    def wypisz(self, klasa_obj, f, sygnatury=False, sciezka_klasy=None):
        m = self.m
        nazwa = m.nazwa_obiektu(f)
        fl = self.flagi(f)
        nat = self.natywna(f)
        znacznik = "RPC " if self.jest_rpc(f) else "    "
        print(f"  {znacznik}{nazwa:46s} {','.join(fl)}")
        if sygnatury:
            print(f"        {self.sygnatura(f)}")
        if nat:
            print(f"        natywna 0x{nat:X}   hak: "
                  f"{sciezka_klasy or m.sciezka(klasa_obj)}:{nazwa}")


def main():
    ap = argparse.ArgumentParser(description="funkcje UE: sygnatury, RPC, adresy")
    ap.add_argument("pid", type=int)
    ap.add_argument("--klasa", help="wszystkie funkcje tej klasy")
    ap.add_argument("--dziedziczone", action="store_true",
                    help="przy --klasa: takze funkcje klas nadrzednych")
    ap.add_argument("--szukaj", help="funkcje, ktorych nazwa zawiera ten tekst (cala gra)")
    ap.add_argument("--rpc", action="store_true", help="tylko funkcje sieciowe")
    ap.add_argument("--sygnatury", action="store_true", help="pokaz argumenty")
    ap.add_argument("--limit", type=int, default=80)
    a = ap.parse_args()

    m = Pamiec(a.pid)
    fn = Funkcje(m)
    if fn.so is None:
        print("NIE WYKRYTO ukladu UStruct — przerywam (ue-props.py --sprawdz)")
        return 2

    if a.klasa:
        cel = None
        for _idx, o in m.obiekty():
            if m.nazwa_klasy(o) in ("Class", "BlueprintGeneratedClass") and \
                    m.nazwa_obiektu(o).lower() == a.klasa.lower():
                cel = o
                break
        if not cel:
            print(f"nie znalazlem klasy {a.klasa}")
            return 1
        sc = m.sciezka(cel)
        print(f"klasa {sc}")
        lista = fn.funkcje_klasy(cel, a.dziedziczone)
        biezaca = None
        for k, f in lista:
            if a.rpc and not fn.jest_rpc(f):
                continue
            if k != biezaca:
                biezaca = k
                print(f"\n── z {m.nazwa_obiektu(k)} " + "─" * 40)
            fn.wypisz(k, f, a.sygnatury, m.sciezka(k))
        print(f"\nrazem funkcji: {len(lista)}")
        return 0

    if a.szukaj:
        igla = a.szukaj.lower()
        ile = 0
        for _idx, o in m.obiekty():
            if m.nazwa_klasy(o) != "Function":
                continue
            if igla not in m.nazwa_obiektu(o).lower():
                continue
            if a.rpc and not fn.jest_rpc(o):
                continue
            wl = m.wskaznik(o + 0x20)      # Outer = klasa deklarujaca
            fn.wypisz(wl, o, a.sygnatury, m.sciezka(wl) if wl else None)
            ile += 1
            if ile >= a.limit:
                print(f"... (przerwano na {a.limit}, uzyj --limit)")
                break
        if ile == 0:
            print("nic nie znaleziono")
        return 0

    print("podaj --klasa albo --szukaj")
    return 1


if __name__ == "__main__":
    sys.exit(main())
