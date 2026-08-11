#!/usr/bin/env python3
"""Kto zapisuje pod ten adres — pulapka sprzetowa (debug registers).

Po co powstalo
--------------
Doszlismy do pytania, na ktore czytanie pamieci juz nie odpowiada: predkosc
serwerowej kopii postaci klienta jest **ustawiana na zero**, skokowo, a nie
hamowana. Zadne z nadpisan `DimensionMovementComponent` nie zapisuje do tego
pola, wiec robi to kod, ktorego nie znamy z nazwy.

Zamiast zgadywac, uzywamy tego, co procesor daje wprost: rejestrow debugowych.
Ustawiamy pulapke na ZAPIS pod konkretny adres, czekamy na przerwanie i czytamy
`RIP` — czyli adres instrukcji tuz PO tej, ktora zapisala. To jedyny sposob, ktory
odpowiada „kto", a nie „co tam teraz jest".

Ostrzezenie: to zatrzymuje watek na czas obslugi. Skrypt zawsze sie odpina,
takze przy bledzie — inaczej zostawilby zamrozona gre.

Uzycie:
    tools/pulapka-zapisu.py <pid> <tid> <adres> [--ile 5] [--czas 20]
"""
import argparse
import ctypes
import os
import signal
import struct
import sys

libc = ctypes.CDLL("libc.so.6", use_errno=True)

PTRACE_PEEKUSER = 3
PTRACE_POKEUSER = 6
PTRACE_CONT = 7
PTRACE_ATTACH = 16
PTRACE_DETACH = 17
PTRACE_GETREGS = 12

# offsetof(struct user, u_debugreg) na x86-64
OFF_DEBUGREG = 848


class Regs(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8",
        "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags",
        "rsp", "ss", "fs_base", "gs_base", "ds", "es", "fs", "gs")]


def ptrace(req, pid, addr, data):
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
    ap.add_argument("tid", type=int, help="watek do obserwacji (zwykle watek gry)")
    ap.add_argument("adres", type=lambda s: int(s, 0))
    ap.add_argument("--ile", type=int, default=5, help="ile trafien zebrac")
    ap.add_argument("--dlugosc", type=int, default=4, choices=(1, 2, 4, 8))
    a = ap.parse_args()

    print(f"pulapka na ZAPIS pod 0x{a.adres:X}, watek {a.tid}")
    ptrace(PTRACE_ATTACH, a.tid, 0, 0)
    os.waitpid(a.tid, 0)
    try:
        # DR0 = adres
        ptrace(PTRACE_POKEUSER, a.tid, OFF_DEBUGREG + 0 * 8, a.adres)
        # DR7: L0=1 (bit0), RW0=01 (zapis, bity 16-17), LEN0 (bity 18-19)
        dlug = {1: 0b00, 2: 0b01, 8: 0b10, 4: 0b11}[a.dlugosc]
        dr7 = (1 << 0) | (0b01 << 16) | (dlug << 18)
        ptrace(PTRACE_POKEUSER, a.tid, OFF_DEBUGREG + 7 * 8, dr7)

        trafienia = []
        for _ in range(a.ile):
            ptrace(PTRACE_CONT, a.tid, 0, 0)
            _, status = os.waitpid(a.tid, 0)
            if not os.WIFSTOPPED(status):
                print("watek przestal istniec")
                break
            regs = Regs()
            libc.ptrace(PTRACE_GETREGS, a.tid, None, ctypes.byref(regs))
            trafienia.append(regs.rip)
            print(f"  zapis z okolicy RIP = 0x{regs.rip:X}")
            # skasowanie DR6, inaczej kolejne trafienie nie przyjdzie czysto
            ptrace(PTRACE_POKEUSER, a.tid, OFF_DEBUGREG + 6 * 8, 0)

        print("\npodsumowanie — adresy instrukcji zapisujacych:")
        for r in sorted(set(trafienia)):
            print(f"  0x{r:X}  (wystapien: {trafienia.count(r)})")
    finally:
        try:
            ptrace(PTRACE_POKEUSER, a.tid, OFF_DEBUGREG + 7 * 8, 0)
        except OSError:
            pass
        try:
            ptrace(PTRACE_DETACH, a.tid, 0, 0)
            print("odpiete")
        except OSError as e:
            print(f"UWAGA: nie udalo sie odpiac: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
