#!/usr/bin/env python3
"""Pelny stan gracza: postac, ekwipunek, bronie, ATRYBUTY i ZDOLNOSCI.

Po co powstalo
--------------
Trzy pozostale usterki (brak ruchu, brak amunicji, podwojny komplet u hosta)
zeszly sie w jedno miejsce: **bron dolaczajacego gracza nie jest zainicjowana**.
Zmierzone na zdrowej instancji solo:

  bron zdrowa: wlasny `DimensionAbilitySystemComponent` (bron+0x958) z pieciu
  zestawami atrybutow i czterema-pieciu zdolnosciami, w tym
  `AbilityWeaponLoadAmmo_C`; `SpeedMultiplier`=1.0.

A predkosc maksymalna gra liczy tak (deasemblacja `0x14177E610`):

  MaxSpeed = predkosc_bazowa
           * lerp(SpeedMultiplier, SpeedMultiplierOnTargeting * X, alfa_ADS)
           * StrafeSpeedMultiplier

czyli **zerowy atrybut broni zeruje cala predkosc** — bez zadnej usterki sieci.
To narzedzie wypisuje dokladnie te wartosci po obu stronach, zeby porownanie
bylo liczbowe, a nie z wrazenia.

Uzycie
------
  stan-gracza.py <pid>            wszyscy gracze w procesie
  stan-gracza.py <pid> --zwiezle  jedna linia na bron (do `diff`)
"""
import argparse
import struct
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_common import Pamiec

# ── offsety potwierdzone na zywej grze (nie zgadniete) ──────────────────────
CHAR_CONTROLLER = 0x258      # AActor::Controller na postaci
CHAR_ASC        = 0x528      # DimensionAbilitySystemComponent postaci
CHAR_INVENTORY  = 0x960      # DimensionInventoryComponent postaci
ACTOR_ROLE      = 0xF0
INV_CURRENT_IDX = 0x148      # CurrentWeaponIndex
WEAPON_ASC      = 0x958      # wlasny ASC broni — stad ida mnozniki predkosci
WEAPON_MYPAWN   = 0x998

ASC_ATTRSETS    = 0x140      # TArray<UAttributeSet*> SpawnedAttributes
ASC_ABILITIES   = 0x4F8      # ActivatableAbilities.Items (FGameplayAbilitySpec)
ASC_OWNER       = 0x3D0      # OwnerActor  (refleksja)
ASC_AVATAR      = 0x3D8      # AvatarActor (refleksja)
SPEC_ROZMIAR    = 0xE0       # zmierzony odstepem miedzy wskaznikami zdolnosci
SPEC_ABILITY    = 0x10

CHAR_MOVEMENT   = 0x288      # ACharacter::CharacterMovement (refleksja)
# Podreczna mapa atrybutow ruchu w komponencie — NIE jest wlasciwoscia
# refleksji, wiec offsety wziete z deasemblacji `GetMaxSpeed`/`GetMaxAcceleration`.
# Wypelnia ja `DimensionMovementComponent::OnAttributeUpdate` (0x141C43530),
# czyli powiadomienie o zmianie atrybutu. Pusta mapa = wszystkie limity ruchu
# wychodza zerem.
MOVE_MAPA_DANE  = 0xB18
MOVE_MAPA_ILE   = 0xB20
MOVE_MAPA_WOLNE = 0xB4C      # NumFreeIndices — gra sprawdza `Num == Wolne` (mapa pusta)
MOVE_MAPA_EL    = 0x48       # rozmiar elementu
MOVE_MAPA_WART  = 0x38       # float — wartosc atrybutu

# Klucz to `FGameplayAttribute`, a jego PIERWSZE pole to `FString AttributeName`
# — ustalone na globalnych kluczach uzywanych przez funkcje limitow: pod
# `0x14644A7D0` leza {wskaznik, num=12, max=16}, czyli nazwa o 11 znakach.
# Rozmiar klucza wynika z ukladu elementu: wartosc pod +0x38, `HashNextId`
# pod +0x40 (kod chodzi po lancuchu przez `[element+0x40]`), calosc 0x48.
KLUCZ_FSTRING   = 0x00

ATRYB_RUCHU = ((0x350, "SpeedMultiplier"),
               (0x354, "SpeedMultiplierOnTargeting"),
               (0x358, "StrafeSpeedMultiplier"),
               (0x34C, "Mobility"))
ATRYB_AMUNICJI = ((0x308, "ClipSize"), (0x30C, "MaxAmmo"),
                  (0x314, "CurrentAmmoInClip"), (0x318, "CurrentAmmo"))

ROLA = {0: "None", 1: "SimulatedProxy", 2: "AutonomousProxy", 3: "Authority"}


def tablica(m, adres):
    """TArray -> (wskaznik, ile, pojemnosc)."""
    return m.u64(adres), m.i32(adres + 8), m.i32(adres + 12)


def zdolnosci(m, asc):
    tab, n, _ = tablica(m, asc + ASC_ABILITIES)
    wynik = []
    for i in range(min(n or 0, 64)):
        ab = m.u64(tab + i * SPEC_ROZMIAR + SPEC_ABILITY)
        wynik.append(m.nazwa_klasy(ab) if ab else "<null>")
    return wynik


def zestawy(m, asc):
    tab, n, _ = tablica(m, asc + ASC_ATTRSETS)
    wynik = {}
    for i in range(min(n or 0, 32)):
        o = m.u64(tab + i * 8)
        if o:
            wynik[m.nazwa_klasy(o)] = o
    return wynik


def fstring(m, adres):
    """FString {wskaznik, dlugosc, pojemnosc} -> tekst. `dlugosc` liczy znak
    konca, wiec odejmujemy go."""
    p = m.u64(adres)
    n = m.i32(adres + 8)
    if not p or not n or n > 256:
        return None
    d = m.czytaj(p, n * 2)
    if not d:
        return None
    return d.decode("utf-16-le", "replace").rstrip("\x00")


def mapa_ruchu(m, comp):
    """Podręczna mapa atrybutów ruchu komponentu — z NAZWAMI atrybutów.

    To ona rozstrzyga o prędkości i przyspieszeniu: `GetMaxSpeed`,
    `GetMaxAcceleration` i ścieżka celowania czytają wartości właśnie stąd
    (sprawdzone skanem odwołań do `+0xB18` na zrzucie obrazu).

    Uwaga na porównania: sama liczba wpisów nic nie mówi — trzeba porównać
    WARTOŚCI pod tymi samymi nazwami u obu graczy. Gra zakłada, że klucz
    zawsze jest: przy jego braku czyta spod `NULL+0x38`, czyli by padła.
    """
    dane = m.u64(comp + MOVE_MAPA_DANE)
    ile = m.i32(comp + MOVE_MAPA_ILE)
    wolne = m.i32(comp + MOVE_MAPA_WOLNE)
    wynik = []
    if not dane or not ile or ile > 256:
        return wynik, ile, wolne
    for i in range(ile):
        el = dane + i * MOVE_MAPA_EL
        nazwa = fstring(m, el + KLUCZ_FSTRING)
        wart = m.f32(el + MOVE_MAPA_WART)
        wynik.append((nazwa or f"<wpis {i}>", wart))
    return wynik, ile, wolne


def opis_kontrolera(m, pc):
    """Ktory to gracz — po obiekcie `Player`. `DimensionLocalPlayer` = czlowiek
    przy tym procesie, `IpConnection` = gracz po drugiej stronie sieci.
    Sama nazwa klasy kontrolera nie rozroznia graczy: obaj maja ta sama."""
    if not pc:
        return "-"
    # Player siedzi w AController; szukamy po nazwie klasy w kilku offsetach
    for off in range(0x280, 0x400, 8):
        p = m.wskaznik(pc + off)
        if not p:
            continue
        kn = m.nazwa_klasy(p)
        if kn in ("DimensionLocalPlayer", "IpConnection", "NetConnection"):
            return kn
    return "?"


def bronie_gracza(m):
    """Wszystkie aktory broni w procesie, z ich wlascicielami."""
    wynik = []
    for _, obj, klasa, _, _ in m.naglowki():
        if not m.dziedziczy_po(obj, "DimensionWeapon"):
            continue
        if m.nazwa_obiektu(obj).startswith("Default__"):
            continue
        wynik.append(obj)
    return wynik


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int, nargs="?")
    ap.add_argument("--zwiezle", action="store_true")
    a = ap.parse_args()

    pid = a.pid
    if not pid:
        pid = int(subprocess.run(["pgrep", "-x", "Witchfire-Win64"],
                                 capture_output=True, text=True).stdout.split()[0])
    m = Pamiec(pid)

    postacie, bronie = [], []
    for _, obj, klasa, _, _ in m.naglowki():
        kn = m.nazwa_obiektu(klasa)
        if m.nazwa_obiektu(obj).startswith("Default__"):
            continue
        # Sama nazwa klasy nie wystarcza: komponenty postaci tez zaczynaja sie
        # od `BPDimensionPlayerCharacter...`. Rozstrzyga dziedziczenie po Pawn.
        if kn.startswith("BPDimensionPlayerCharacter") and m.dziedziczy_po(obj, "Pawn"):
            postacie.append(obj)
        elif m.dziedziczy_po(obj, "DimensionWeapon"):
            bronie.append(obj)

    print(f"# proces {pid}: {len(postacie)} postaci, {len(bronie)} broni")

    for p in postacie:
        pc = m.wskaznik(p + CHAR_CONTROLLER)
        inv = m.wskaznik(p + CHAR_INVENTORY)
        asc = m.wskaznik(p + CHAR_ASC)
        rola = m.u8(p + ACTOR_ROLE)
        print(f"\n=== POSTAC {m.nazwa_obiektu(p)} 0x{p:X}")
        print(f"    Role={rola} ({ROLA.get(rola, '?')})  kontroler={m.nazwa_obiektu(pc) if pc else '-'}"
              f"  [{opis_kontrolera(m, pc)}]")
        print(f"    CurrentWeaponIndex = {m.i32(inv + INV_CURRENT_IDX) if inv else '-'}")

        # Mapa atrybutow ruchu — to ona rozstrzyga o predkosci i przyspieszeniu.
        # Zmierzone: u obu graczy LOKALNIE ma 19 wpisow, a serwerowa kopia
        # dolaczajacego gracza ma ZERO. Stad zerowe limity ruchu.
        comp = m.wskaznik(p + CHAR_MOVEMENT)
        if comp:
            wpisy, ile, wolne = mapa_ruchu(m, comp)
            pusta = " <-- PUSTA wg testu gry (Num == NumFreeIndices)" if ile == wolne else ""
            print(f"    mapa atrybutow ruchu: {ile} wpisow, wolnych {wolne}{pusta}")
            for nazwa, wart in sorted(wpisy):
                print(f"        {nazwa:34s} = {wart}")
        if asc:
            print(f"    ASC: OwnerActor={m.nazwa_obiektu(m.wskaznik(asc + ASC_OWNER)) or 'NULL'}"
                  f"  AvatarActor={m.nazwa_obiektu(m.wskaznik(asc + ASC_AVATAR)) or 'NULL'}")
            zs = zestawy(m, asc)
            ruch = zs.get("DimensionMovementAttribSet")
            print(f"    zestawy atrybutow postaci ({len(zs)})"
                  + (f"  SprintSpeed={m.f32(ruch + 0x310)} Acceleration={m.f32(ruch + 0x31C)}"
                     if ruch else "  BRAK DimensionMovementAttribSet"))
            lst = zdolnosci(m, asc)
            print(f"    zdolnosci postaci ({len(lst)}): {', '.join(lst)}")

    for b in bronie:
        wl = m.wskaznik(b + 0x198) or 0        # AActor::Owner szukany nizej
        mypawn = m.wskaznik(b + WEAPON_MYPAWN)
        asc = m.wskaznik(b + WEAPON_ASC)
        print(f"\n--- BRON {m.nazwa_obiektu(b)} 0x{b:X}")
        print(f"    MyPawn = {m.nazwa_obiektu(mypawn) if mypawn else 'NULL'}"
              f"   Role={m.u8(b + ACTOR_ROLE)}")
        if not asc:
            print("    ASC broni: BRAK  <-- bron niezainicjowana")
            continue
        print(f"    ASC broni: OwnerActor={m.nazwa_obiektu(m.wskaznik(asc + ASC_OWNER)) or 'NULL'}"
              f"  AvatarActor={m.nazwa_obiektu(m.wskaznik(asc + ASC_AVATAR)) or 'NULL'}")
        zs = zestawy(m, asc)
        print(f"    zestawy atrybutow ({len(zs)}): {', '.join(sorted(zs)) or 'BRAK'}")
        w = zs.get("DimensionWeaponAttribSet")
        if w:
            czesci = [f"{n}={m.f32(w + o):.3f}" for o, n in ATRYB_RUCHU]
            print("    RUCH:  " + "  ".join(czesci))
        else:
            print("    RUCH:  brak DimensionWeaponAttribSet  <-- predkosc wyjdzie ZEREM")
        am = zs.get("DimensionAmmoAttribSet")
        if am:
            czesci = [f"{n}={m.f32(am + o):.0f}" for o, n in ATRYB_AMUNICJI]
            print("    AMUNICJA: " + "  ".join(czesci))
        else:
            print("    AMUNICJA: brak DimensionAmmoAttribSet")
        lst = zdolnosci(m, asc)
        print(f"    zdolnosci broni ({len(lst)}): {', '.join(lst) or 'BRAK'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
