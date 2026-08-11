#!/usr/bin/env python3
"""Odsiewa prawdziwe ramki stosu od smieci i nazywa poczatki funkcji.

Po co: read-dump.py wypisuje ze stosu KANDYDATOW — kazda wartosc, ktora trafia
w zakres modulu. Czesc z nich to pozostalosci po wczesniejszych wywolaniach.
Prawdziwy adres powrotu ma jedna ceche nie do podrobienia: tuz przed nim konczy
sie instrukcja `call`.

Kod czytamy z pamieci ZYWEGO procesu przez /proc/PID/mem — tak, jak wykonywal
sie w chwili awarii.

Uzycie: verify-frames.py <pid> <adres_hex> [adres_hex ...]
"""
import subprocess
import sys


def read_mem(pid, addr, size):
    try:
        with open(f"/proc/{pid}/mem", "rb", 0) as f:
            f.seek(addr)
            return f.read(size)
    except Exception as e:
        print(f"  blad odczytu 0x{addr:X}: {e}")
        return None


def disasm(data, vma):
    """Zwraca liste (adres, dlugosc, tekst) z objdumpa."""
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".bin")
    try:
        os.write(fd, data)
        os.close(fd)
        out = subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
             f"--adjust-vma=0x{vma:X}", path],
            capture_output=True, text=True).stdout
    finally:
        os.unlink(path)

    res = []
    for line in out.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        head, _, rest = line.partition(":")
        try:
            a = int(head.strip(), 16)
        except ValueError:
            continue
        # Wiersz objdumpa: "  ADRES:\tBAJTY\tINSTRUKCJA" — po dwukropku zostaje
        # wiodacy tabulator, wiec pierwszy element podzialu jest PUSTY. Bez
        # odsiania go bralem bajty za tekst instrukcji i zaden `call` nie pasowal.
        parts = [p for p in rest.split("\t") if p.strip()]
        if len(parts) < 2:
            continue
        nbytes = len(parts[0].split())
        res.append((a, nbytes, parts[1].strip()))
    return res


def check_return_address(pid, addr):
    """Czy tuz przed `addr` konczy sie `call`? Probujemy wielu punktow startu,
    bo liniowa deasemblacja od przypadkowego bajtu bywa przesunieta."""
    window = 32
    data = read_mem(pid, addr - window, window + 16)
    if not data:
        return None
    for back in range(2, window + 1):
        ins = disasm(data[window - back:], addr - back)
        for a, n, text in ins:
            if a + n == addr and text.startswith("call"):
                return text
    return None


def find_function_start(pid, addr, limit=0x400):
    """Szuka wstecz typowego poczatku funkcji: ciagu int3 albo prologu."""
    data = read_mem(pid, addr - limit, limit)
    if not data:
        return None, None
    # Wyrownanie funkcji w MSVC: po poprzedniej funkcji leca int3 (0xCC).
    for i in range(len(data) - 4, 0, -1):
        if data[i - 1] == 0xCC and data[i] != 0xCC:
            return addr - limit + i, "po int3"
    return None, None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    pid = int(sys.argv[1])
    for a in sys.argv[2:]:
        addr = int(a, 16)
        call = check_return_address(pid, addr)
        if call:
            start, how = find_function_start(pid, addr)
            extra = f"  funkcja od 0x{start:X} ({how})" if start else ""
            print(f"0x{addr:X}  RAMKA  <- {call}{extra}")
        else:
            print(f"0x{addr:X}  smiec  (przed nim nie ma call)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
