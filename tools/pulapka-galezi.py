#!/usr/bin/env python3
"""Ktora galaz bierze KTORY obiekt — pulapka WYKONANIA z odczytem rejestrow.

Po co powstalo
--------------
Wiemy juz, ze `DimensionMovementComponent::GetMaxSpeed` zwraca zero dla pionka
zdalnego, a normalna wartosc dla pionka hosta — w TYM SAMYM procesie i przez te
same instrukcje. Roznica musi wiec siedziec w rozgalezieniu. Czytanie pol tego
nie pokaze: wszystkie widoczne refleksja sa po obu stronach identyczne.

Pulapka na WYKONANIE konkretnego adresu zatrzymuje watek dokladnie w tym
rozgalezieniu i pozwala odczytac rejestry — czyli i to, KTOREGO komponentu
dotyczy wywolanie (`rcx`/`rdi`), i wynik wczesniejszego wywolania (`rax`).
Dopiero to odpowiada na pytanie „ktora galaz i dla kogo".

Roznica wzgledem `pulapka-zapisu.py`: tam pulapka reaguje na ZAPIS pod adres
danych, tutaj na WYKONANIE adresu kodu (bity RW w DR7 = 00, dlugosc = 1 bajt).

Uzycie:
    tools/pulapka-galezi.py <pid> <tid> <adres> --rejestr rdi --ile 20
"""
import argparse
import ctypes
import os
import sys
import time

libc = ctypes.CDLL("libc.so.6", use_errno=True)
PTRACE = {"POKEUSER": 6, "CONT": 7, "ATTACH": 16, "DETACH": 17, "GETREGS": 12}
OFF_DEBUGREG = 848

POLA = ("r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8",
        "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags",
        "rsp", "ss", "fs_base", "gs_base", "ds", "es", "fs", "gs")


class Regs(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in POLA]


def pt(req, pid, addr, data):
    libc.ptrace.restype = ctypes.c_long
    libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_long,
                            ctypes.c_void_p, ctypes.c_void_p]
    ctypes.set_errno(0)
    r = libc.ptrace(req, pid, ctypes.c_void_p(addr), ctypes.c_void_p(data))
    if r == -1 and ctypes.get_errno() != 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pid", type=int)
    ap.add_argument("tid", type=int)
    ap.add_argument("adres", type=lambda s: int(s, 0))
    ap.add_argument("--rejestry", default="rdi,rcx,rax",
                    help="ktore rejestry wypisac, po przecinku")
    ap.add_argument("--ile", type=int, default=20)
    ap.add_argument("--czas", type=float, default=60.0)
    ap.add_argument("--opoznienie", type=float, default=0.0,
                    help="odczekaj tyle sekund przed zalozeniem pulapki")
    a = ap.parse_args()

    chce = [r.strip() for r in a.rejestry.split(",") if r.strip() in POLA]
    if a.opoznienie:
        time.sleep(a.opoznienie)

    print(f"pulapka na WYKONANIE 0x{a.adres:X}, watek {a.tid}")
    pt(PTRACE["ATTACH"], a.tid, 0, 0)
    os.waitpid(a.tid, 0)
    zebrane = []
    try:
        pt(PTRACE["POKEUSER"], a.tid, OFF_DEBUGREG + 0 * 8, a.adres)
        # DR7: L0=1, RW0=00 (wykonanie), LEN0=00 (1 bajt)
        pt(PTRACE["POKEUSER"], a.tid, OFF_DEBUGREG + 7 * 8, 1 << 0)
        t0 = time.time()
        while len(zebrane) < a.ile and time.time() - t0 < a.czas:
            pt(PTRACE["CONT"], a.tid, 0, 0)
            # WNOHANG, a nie zwykle czekanie: jesli pulapka nie trafia (bo ta
            # galaz po prostu nie jest brana), zwykle `waitpid` blokuje sie na
            # zawsze i narzedzie wisi z podpietym procesem. Zdarzylo sie —
            # i „brak wyjscia" jest tu WYNIKIEM, nie awaria.
            status = 0
            while time.time() - t0 < a.czas:
                pid_, status = os.waitpid(a.tid, os.WNOHANG)
                if pid_:
                    break
                time.sleep(0.02)
            else:
                print("czas minal — ta galaz NIE zostala wykonana ani razu")
                break
            if not os.WIFSTOPPED(status):
                print("watek zniknal")
                break
            r = Regs()
            libc.ptrace(PTRACE["GETREGS"], a.tid, None, ctypes.byref(r))
            zebrane.append({n: getattr(r, n) for n in chce})
            pt(PTRACE["POKEUSER"], a.tid, OFF_DEBUGREG + 6 * 8, 0)
    finally:
        try:
            pt(PTRACE["POKEUSER"], a.tid, OFF_DEBUGREG + 7 * 8, 0)
        except OSError:
            pass
        pt(PTRACE["DETACH"], a.tid, 0, 0)

    print(f"trafien: {len(zebrane)}")
    for w in zebrane:
        print("  " + "  ".join(f"{n}=0x{w[n]:X}" for n in chce))
    return 0


if __name__ == "__main__":
    sys.exit(main())
