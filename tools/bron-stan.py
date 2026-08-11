#!/usr/bin/env python3
"""Sonda stanu BRONI — jedna strona tekstu, ktora rozstrzyga miedzy trzema
mozliwosciami. Do porownywania przed/po dolaczeniu klienta.

Po co osobne narzedzie, skoro jest ue-props.py
----------------------------------------------
Bo pytanie o bron ma dokladnie jedna poprawna forme, a odpowiedz musi byc
porownywalna z inna odpowiedzia sprzed minuty. `ue-props.py --obj` wypisuje
dwiescie pol i za kazdym razem inne, wiec dwa jego wydruki roznia sie w
miejscach, ktore nic nie znacza. Ta sonda wypisuje ZAWSZE to samo, w tej samej
kolejnosci, wiec `diff` dwoch przebiegow pokazuje wylacznie realna zmiane.

Trzy mozliwosci, ktore trzeba rozroznic (kazda prowadzi gdzie indziej):
  A) NIE MA aktora broni            -> zniszczony przy `Login`, szukac w GameMode
  B) jest, ale odczepiony/bez wlasciciela -> psuje sie przyczepienie przy possession
  C) jest i przyczepiony, ale niewidoczny  -> problem jest w samych flagach

Skad wzialy sie akurat te pola
------------------------------
Ze zmierzonego stanu KONTROLNEGO hosta przed dolaczeniem klienta:
  WeaponMesh1Pb (bron FPP) -> przyczepiona do Mesh1P postaci, gniazdo
     `VB b_Hips_b_RightWeapon`, bVisible=1 bHiddenInGame=0 bOnlyOwnerSee=1
  WeaponMesh3Pb (bron TPP) -> przyczepiona do CharacterMesh0, calkiem ukryta
Kazde odstepstwo od tego obrazu po dolaczeniu klienta jest tropem.

Uwaga na `fixHands()`: on zdejmuje `bOnlyOwnerSee` i wola `SetVisibility`, ale
NIE dotyka `bHiddenInGame` — i chodzi tylko po komponentach SZKIELETOWYCH,
wiec celowniki (`RearSight_*`, `FixedSight`) i naboje, ktore sa komponentami
STATYCZNYMI, zostaja ukryte niezaleznie od niego. Dlatego sonda pokazuje oba
rodzaje komponentow.

Uzycie
------
  bron-stan.py <pid>                     > logs/bron/T0.txt
  bron-stan.py <pid>                     > logs/bron/T1.txt
  diff logs/bron/T0.txt logs/bron/T1.txt
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec, UOBJ_OUTER_OFF

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "ue_props", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ue-props.py"))
_props = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_props)
Refleksja, FP_OFFSET = _props.Refleksja, _props.FP_OFFSET

FLAGI = ("bVisible", "bHiddenInGame", "bOnlyOwnerSee", "bOwnerNoSee")


def pole(m, r, obj, nazwa):
    p = r.znajdz_pole(m.wsk_klasy(obj), nazwa)
    return r.wartosc(p, obj) if p else "<brak pola>"


def wskaznik_pola(m, r, obj, nazwa):
    p = r.znajdz_pole(m.wsk_klasy(obj), nazwa)
    return m.wskaznik(obj + (m.i32(p + FP_OFFSET) or 0)) if p else None


def opis_komponentu(m, r, c):
    """Jedna linia na komponent — zawsze te same pola, zawsze w tej kolejnosci."""
    rodzic = wskaznik_pola(m, r, c, "AttachParent")
    gniazdo = pole(m, r, c, "AttachSocketName")
    flagi = " ".join(f"{n}={pole(m, r, c, n)[:5]}" for n in FLAGI)
    # Komponent bez przypisanego modelu nie narysuje sie nawet z dobrymi flagami
    # — to trzecia mozliwa przyczyna i trzeba ja widziec osobno.
    model = "-"
    for nazwa_pola_modelu in ("SkeletalMesh", "StaticMesh"):
        p = r.znajdz_pole(m.wsk_klasy(c), nazwa_pola_modelu)
        if p:
            cel = m.wskaznik(c + (m.i32(p + FP_OFFSET) or 0))
            model = m.nazwa_obiektu(cel) if cel else "BRAK MODELU"
            break
    return (f"    {m.nazwa_obiektu(c):26s} [{m.nazwa_klasy(c):22s}]\n"
            f"        rodzic={m.nazwa_obiektu(rodzic) if rodzic else 'ODCZEPIONY'}"
            f"  gniazdo={gniazdo}\n"
            f"        {flagi}\n"
            f"        model={model}")


def komponenty_aktora(m, aktor):
    """Komponenty aktora rozpoznajemy po Outer — nie po liscie w aktorze,
    bo ta bywa niespojna w trakcie niszczenia obiektu, a wlasnie wtedy patrzymy."""
    wynik = []
    for _idx, o in m.obiekty():
        if m.wskaznik(o + UOBJ_OUTER_OFF) == aktor and \
                m.nazwa_klasy(o).endswith("Component"):
            wynik.append(o)
    return wynik


def main():
    ap = argparse.ArgumentParser(description="sonda stanu broni")
    ap.add_argument("pid", type=int)
    ap.add_argument("--etykieta", default="", help="dopisek do naglowka, np. 'po dolaczeniu'")
    a = ap.parse_args()

    m = Pamiec(a.pid)
    r = Refleksja(m)
    if r.super_off is None:
        print("NIE WYKRYTO ukladu UStruct — przerywam")
        return 2

    # Jedno przejscie tablicy, zeby zebrac wszystko naraz: sonda ma byc szybka,
    # bo bywa uruchamiana w trakcie zjawiska.
    bronie, postacie, ekwipunki = [], [], []
    for _idx, o in m.obiekty():
        n = m.nazwa_obiektu(o)
        if n.startswith("Default__"):
            continue
        if m.dziedziczy_po(o, "DimensionWeapon"):
            bronie.append(o)
        elif m.dziedziczy_po(o, "Pawn"):
            postacie.append(o)
        elif "Inventory" in m.nazwa_klasy(o) and m.dziedziczy_po(o, "ActorComponent"):
            ekwipunki.append(o)

    print(f"=== SONDA BRONI  pid={a.pid}  {a.etykieta} ===")
    print(f"broni w swiecie: {len(bronie)}   postaci: {len(postacie)}   "
          f"komponentow ekwipunku: {len(ekwipunki)}")

    print("\n########## POSTACIE ##########")
    for p in sorted(postacie, key=lambda x: m.nazwa_obiektu(x)):
        print(f"\n  {m.nazwa_obiektu(p)} [{m.nazwa_klasy(p)}]  0x{p:X}")
        print(f"      Role={pole(m, r, p, 'Role')}  RemoteRole={pole(m, r, p, 'RemoteRole')}"
              f"  Owner={pole(m, r, p, 'Owner').split()[-1] if pole(m, r, p, 'Owner') != 'null' else 'null'}")
        print(f"      Controller={pole(m, r, p, 'Controller').split()[-1] if pole(m, r, p, 'Controller') != 'null' else 'BRAK'}")
        for nazwa_komp in ("Mesh1P", "Mesh"):
            c = wskaznik_pola(m, r, p, nazwa_komp)
            if c:
                print(opis_komponentu(m, r, c))

    print("\n########## BRONIE ##########")
    for b in sorted(bronie, key=lambda x: m.nazwa_obiektu(x)):
        wl = wskaznik_pola(m, r, b, "Owner")
        inst = wskaznik_pola(m, r, b, "Instigator")
        print(f"\n  {m.nazwa_obiektu(b)} [{m.nazwa_klasy(b)}]  0x{b:X}")
        print(f"      Owner={m.nazwa_obiektu(wl) if wl else 'BRAK WLASCICIELA'}"
              f"  Instigator={m.nazwa_obiektu(inst) if inst else 'brak'}")
        print(f"      Role={pole(m, r, b, 'Role')}  RemoteRole={pole(m, r, b, 'RemoteRole')}"
              f"  bHidden={pole(m, r, b, 'bHidden')}"
              f"  bActorIsBeingDestroyed={pole(m, r, b, 'bActorIsBeingDestroyed')}")
        for c in sorted(komponenty_aktora(m, b), key=lambda x: m.nazwa_obiektu(x)):
            if m.dziedziczy_po(c, "SceneComponent"):
                print(opis_komponentu(m, r, c))

    print("\n########## EKWIPUNEK ##########")
    for e in sorted(ekwipunki, key=lambda x: m.sciezka(x)):
        wl = m.wskaznik(e + UOBJ_OUTER_OFF)
        print(f"\n  {m.nazwa_obiektu(e)} [{m.nazwa_klasy(e)}]  wlasciciel={m.nazwa_obiektu(wl)}")
        # Nazwy pol sa nieznane z gory, wiec pokazujemy wszystkie, ktore
        # wskazuja na bron albo licza sztuki — reszta to szum.
        for _k, p in r.wszystkie_wlasciwosci(m.wsk_klasy(e)):
            nazwa = r.nazwa_pola(p)
            t = r.typ(p)
            if t in ("ObjectProperty", "ArrayProperty", "IntProperty") and \
                    any(s in nazwa.lower() for s in
                        ("weapon", "item", "slot", "current", "active", "equip")):
                print(f"      {nazwa:34s} = {r.wartosc(p, e)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
