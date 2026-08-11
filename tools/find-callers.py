#!/usr/bin/env python3
"""Znajduje, KTO wola dana funkcje — skanem kodu zywego procesu.

Po co: raport awarii podaje adres funkcji, ktora padla, ale nie mowi, w jakim
podsystemie gry to jest. Gdy funkcja jest malutkim akcesorem (a tak bylo
z `Cast<T>(obiekt->pole)` pod 0x1418721A0), sama w sobie nic nie znaczy —
znaczenie ma dopiero to, kto ja wola i po co.

Jak: instrukcja `call rel32` ma opcode 0xE8, a cel liczy sie wzgledem adresu
NASTEPNEJ instrukcji. Skanujemy caly obszar kodu i liczymy cel dla kazdego E8.
Kod czytamy z pamieci zywego procesu. Odpowiednik bez uruchomionej gry to
`obraz.py xref`.

Uzycie: find-callers.py <pid> <adres_hex_funkcji> [ile_pokazac]
"""
import struct
import subprocess
import sys
import os
import re
import tempfile

BASE = 0x140000000
LEA_RIP = re.compile(r"lea\s+\w+,\[rip\+0x([0-9a-f]+)\]")
MOV_RIP = re.compile(r"mov\s+\w+,QWORD PTR \[rip\+0x([0-9a-f]+)\]")


def code_range(pid):
    """Zakres wykonywalnego odwzorowania exe — z /proc/PID/maps."""
    lo, hi = None, None
    for line in open("/proc/%d/maps" % pid):
        if "Witchfire-Win64-Shipping.exe" not in line and "x" not in line.split()[1]:
            continue
        a, b = line.split()[0].split("-")
        a, b = int(a, 16), int(b, 16)
        if a < BASE or a > BASE + 0x10000000:
            continue
        if "x" not in line.split()[1]:
            continue
        lo = a if lo is None else min(lo, a)
        hi = b if hi is None else max(hi, b)
    return lo, hi


def read(pid, addr, size):
    with open("/proc/%d/mem" % pid, "rb", 0) as f:
        f.seek(addr)
        return f.read(size)


def literals(pid, addr, back=0x500, fwd=0x120, limit=5):
    start = addr - back
    try:
        data = read(pid, start, back + fwd)
    except Exception:
        return []
    fd, p = tempfile.mkstemp(suffix=".bin")
    try:
        os.write(fd, data)
        os.close(fd)
        out = subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
             "--adjust-vma=0x%X" % start, p], capture_output=True, text=True).stdout
    finally:
        os.unlink(p)
    found, seen = [], set()
    for line in out.splitlines():
        if not (LEA_RIP.search(line) or MOV_RIP.search(line)):
            continue
        m = re.search(r"#\s*0x([0-9a-f]+)", line)
        if not m:
            continue
        t = int(m.group(1), 16)
        if t in seen:
            continue
        seen.add(t)
        try:
            raw = read(pid, t, 200)
        except Exception:
            continue
        if not raw:
            continue
        s = None
        if len(raw) > 6 and raw[1] == 0 and raw[3] == 0 and 0x20 <= raw[0] < 0x7F:
            chars = []
            for i in range(0, len(raw) - 1, 2):
                ch = raw[i] | (raw[i + 1] << 8)
                if ch == 0:
                    break
                if ch < 0x20 or ch > 0x7E:
                    chars = []
                    break
                chars.append(chr(ch))
            if len(chars) >= 5:
                s = "".join(chars)
        elif 0x20 <= raw[0] < 0x7F:
            chars = []
            for b in raw:
                if b == 0:
                    break
                if b < 0x20 or b > 0x7E:
                    chars = []
                    break
                chars.append(chr(b))
            if len(chars) >= 6:
                s = "".join(chars)
        if s:
            found.append(s)
        if len(found) >= limit:
            break
    return found


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    pid = int(sys.argv[1])
    target = int(sys.argv[2], 16)
    show = int(sys.argv[3]) if len(sys.argv) > 3 else 12

    lo, hi = code_range(pid)
    if lo is None:
        print("nie znalazlem wykonywalnego obszaru exe")
        return 1
    print("skanuje 0x%X-0x%X (%.1f MB) w poszukiwaniu call 0x%X"
          % (lo, hi, (hi - lo) / 1048576, target))

    hits = []
    CH = 1 << 22
    addr = lo
    while addr < hi:
        n = min(CH, hi - addr)
        try:
            buf = read(pid, addr, n)
        except Exception:
            addr += n
            continue
        if not buf:
            addr += n
            continue
        i = buf.find(b"\xe8")
        while i != -1 and i + 5 <= len(buf):
            rel = struct.unpack("<i", buf[i + 1:i + 5])[0]
            if addr + i + 5 + rel == target:
                hits.append(addr + i)
            i = buf.find(b"\xe8", i + 1)
        addr += n

    print("znaleziono %d wywolan\n" % len(hits))
    for a in hits[:show]:
        lits = literals(pid, a)
        print("  0x%X  (+0x%X)" % (a, a - BASE))
        if lits:
            print("      napisy w poblizu: " + " | ".join(lits))
    if len(hits) > show:
        print("  ... i %d dalszych" % (len(hits) - show))
    return 0


if __name__ == "__main__":
    sys.exit(main())
