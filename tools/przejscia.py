#!/usr/bin/env python3
"""Wypisuje PRZEJSCIA maszyny stanow gracza — nazwy i warunki.

Po co
-----
`GetMaxSpeed` nie pyta o zadna liczbe ani o ASC. Pyta maszyne stanow, czy jej
BIEZACY stan jest stanem biegu (`0x1417F3F30`: porownuje `States[+0x178]`
z wynikiem wyszukania po znaczniku). Czyli zeby serwer policzyl predkosc
sprintu dla pionka zdalnego, maszyna musi NAPRAWDE przejsc do stanu biegu.

Podanie akcji wejscia tego nie zrobilo — ani gniazdem 147, ani pelna sciezka
wejscia (gniazdo 150), mimo poprawnych bajtow i `InputStates=10`. Zostaje
wlasne API maszyny: `AddTransitionToQueue(Name TransitionName)`
(natywna `0x141CB0BD0`, `BlueprintCallable`), ktore bierze NAZWE przejscia.

Nazwy przejsc leza w danych samej maszyny, wiec sa identyczne u obu graczy:

    maszyna +0x158  StateEntries        TArray<DimensionStateEntry>, element 48 B
      entry +0x00   StateTag            FGameplayTag (8 B)
      entry +0x10   AvailableTransitionsFrom  TArray<DimensionStateTransition>
      entry +0x20   AvailableTransitionsTo    TArray<...>

    DimensionStateTransition, element 64 B
      +0x00  Name                FName
      +0x08  SourceStateTag      FGameplayTag
      +0x10  TargetStateTag      FGameplayTag
      +0x18  InputActionConditions  TArray
      +0x28  CustomConditions       TArray
      +0x38  bIgnoreLocks / bInstantUpdateEnabled / bAutoUpdateEnabled

Uklad wziety z refleksji (`ue-props.py --klasa DimensionStateEntry`
i `--klasa DimensionStateTransition`), nie zgadniety.

Uzycie
------
    przejscia.py $(find-instance.sh compat1)
    przejscia.py PID --obj 0x797BF560      # konkretna maszyna
"""
import argparse
import sys

from ue_common import Pamiec

SM_STATES        = 0x148
SM_STATE_ENTRIES = 0x158
SM_CURRENT_IDX   = 0x178
ENTRY_ROZMIAR    = 48
ENTRY_TAG        = 0x00
ENTRY_TRANS_FROM = 0x10
TRANS_ROZMIAR    = 64
TRANS_NAME       = 0x00
TRANS_SRC_TAG    = 0x08
TRANS_DST_TAG    = 0x10
TRANS_WAR_WEJ    = 0x18
TRANS_WAR_WLASNE = 0x28
# Rozmiary z refleksji (`sygnatura-funkcji.py CheckCondition` i
# `CheckInputActionCondition`), nie zgadniete:
#   CountableGameplayTagCondition   20 B
#   InputActionConditionDefinition  64 B, z `InputCondition` (enum) pod +0x38
WARUNEK_ROZMIAR     = 20
WARUNEK_WEJ_ROZMIAR = 64
WARUNEK_WEJ_STAN    = 0x38


def tablica(m, adres):
    """TArray -> (wskaznik danych, liczba elementow)."""
    dane = m.u64(adres)
    ile = m.i32(adres + 8)
    if not dane or ile < 0 or ile > 4096:
        return 0, 0
    return dane, ile


def nazwa_znacznika(m, adres):
    """FGameplayTag to pojedynczy FName."""
    idx = m.u32(adres)
    if not idx:
        return "(brak)"
    return m.nazwa(idx) or f"?{idx}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pid", type=int)
    p.add_argument("--obj", help="adres maszyny stanow; bez tego szuka wszystkich")
    a = p.parse_args()

    m = Pamiec(a.pid)

    if a.obj:
        maszyny = [(int(a.obj, 16), "(podana)")]
    else:
        maszyny = []
        for _, obj, klasa, _, _ in m.naglowki():
            if not klasa:
                continue
            if m.nazwa_klasy(obj) != "DimensionPlayerStateMachineComponent":
                continue
            sciezka = m.sciezka(obj) or ""
            if "Default__" in sciezka:
                continue
            maszyny.append((obj, sciezka))

    if not maszyny:
        print("nie znalazlem zadnej maszyny stanow gracza", file=sys.stderr)
        return 1

    for obj, nazwa in maszyny:
        biezacy = m.i32(obj + SM_CURRENT_IDX)
        st_dane, st_ile = tablica(m, obj + SM_STATES)
        print(f"\n=== maszyna 0x{obj:X}  {nazwa} ===")
        print(f"    stan biezacy: indeks {biezacy}")

        # nazwy stanow, zeby dalo sie czytac przejscia
        for i in range(st_ile):
            so = m.u64(st_dane + i * 8)
            nazwa_st = m.nazwa_klasy(so) if so else "?"
            print(f"      [{i}] {nazwa_st}{' <-- BIEZACY' if i == biezacy else ''}")

        e_dane, e_ile = tablica(m, obj + SM_STATE_ENTRIES)
        print(f"    wpisow stanow: {e_ile}")
        for i in range(e_ile):
            e = e_dane + i * ENTRY_ROZMIAR
            tag = nazwa_znacznika(m, e + ENTRY_TAG)
            t_dane, t_ile = tablica(m, e + ENTRY_TRANS_FROM)
            print(f"\n    [{i}] {tag}   przejsc wychodzacych: {t_ile}")
            for j in range(t_ile):
                t = t_dane + j * TRANS_ROZMIAR
                imie = m.nazwa(m.u32(t + TRANS_NAME)) or "?"
                zrod = nazwa_znacznika(m, t + TRANS_SRC_TAG)
                cel = nazwa_znacznika(m, t + TRANS_DST_TAG)
                wej_d, war_wej = tablica(m, t + TRANS_WAR_WEJ)
                wl_d, war_wl = tablica(m, t + TRANS_WAR_WLASNE)
                print(f"         {imie:34s} {zrod} -> {cel}"
                      f"   warunki: wejscia={war_wej} wlasne={war_wl}")
                # Warunki wlasne to `CountableGameplayTagCondition` (20 B):
                # znacznik, liczba, relacja. To one blokuja przejscie u pionka
                # zdalnego, wiec wypisujemy je z nazwami.
                for k in range(min(war_wl, 8)):
                    w = wl_d + k * WARUNEK_ROZMIAR
                    print(f"              warunek[{k}] znacznik={nazwa_znacznika(m, w)}"
                          f"  liczba={m.i32(w + 0x0C)}  relacja={m.u8(w + 0x10)}")
                for k in range(min(war_wej, 8)):
                    w = wej_d + k * WARUNEK_WEJ_ROZMIAR
                    print(f"              wejscie[{k}] akcja={m.nazwa(m.u32(w)) or '?'}"
                          f"  warunek={m.u8(w + WARUNEK_WEJ_STAN)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
