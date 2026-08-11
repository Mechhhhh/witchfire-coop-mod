#!/usr/bin/env python3
"""Probuje NAZWAC funkcje w binarce bez symboli, po literalach, do ktorych siega.

Pomysl: shipping UE nie ma symboli, ale kod wciaz laduje adresy napisow —
nazwy klas, nazwy property, komunikaty. Kazde `lea reg,[rip+X]` wskazuje dane;
jesli pod tym adresem lezy czytelny tekst (UE trzyma FName/FString jako
UTF-16LE, komunikaty czesto jako ASCII), to zwykle wystarcza, by rozpoznac
funkcje.

Kod czytamy z pamieci ZYWEGO procesu. Odpowiednik bez uruchomionej gry to
`obraz.py napis`.

Uzycie: name-function.py <pid> <adres_hex> [rozmiar]
"""
import os
import re
import subprocess
import sys
import tempfile

LEA_RIP = re.compile(r"lea\s+\w+,\[rip\+0x([0-9a-f]+)\]")
MOV_RIP = re.compile(r"mov\s+\w+,QWORD PTR \[rip\+0x([0-9a-f]+)\]")
CALL_ABS = re.compile(r"call\s+0x([0-9a-f]+)")


def read_mem(pid, addr, size):
    try:
        with open(f"/proc/{pid}/mem", "rb", 0) as f:
            f.seek(addr)
            return f.read(size)
    except Exception:
        return None


def read_text(pid, addr, maxlen=160):
    raw = read_mem(pid, addr, maxlen * 2)
    if not raw:
        return None
    # UTF-16LE: co drugi bajt zerowy dla ASCII-owej tresci.
    if len(raw) >= 6 and raw[1] == 0 and raw[3] == 0 and 0x20 <= raw[0] < 0x7F:
        out = []
        for i in range(0, len(raw) - 1, 2):
            ch = raw[i] | (raw[i + 1] << 8)
            if ch == 0:
                break
            if ch < 0x20 or ch > 0x7E:
                return None
            out.append(chr(ch))
        if len(out) >= 3:
            return "".join(out) + "  [UTF-16]"
    # ASCII
    if 0x20 <= raw[0] < 0x7F:
        out = []
        for b in raw:
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            out.append(chr(b))
        if len(out) >= 4:
            return "".join(out) + "  [ASCII]"
    return None


def disasm(data, vma):
    fd, path = tempfile.mkstemp(suffix=".bin")
    try:
        os.write(fd, data)
        os.close(fd)
        return subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
             f"--adjust-vma=0x{vma:X}", path],
            capture_output=True, text=True).stdout
    finally:
        os.unlink(path)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    pid = int(sys.argv[1])
    addr = int(sys.argv[2], 16)
    size = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x300

    data = read_mem(pid, addr, size)
    if not data:
        print("nie udalo sie odczytac pamieci")
        return 1

    out = disasm(data, addr)
    print(f"=== funkcja 0x{addr:X} (pierwsze {size} bajtow) ===")
    seen_str, calls = set(), []
    for line in out.splitlines():
        m = LEA_RIP.search(line) or MOV_RIP.search(line)
        if m:
            # objdump dopisuje "# 0xTARGET" — to najpewniejsze zrodlo adresu.
            t = re.search(r"#\s*0x([0-9a-f]+)", line)
            if t:
                target = int(t.group(1), 16)
                if target not in seen_str:
                    seen_str.add(target)
                    s = read_text(pid, target)
                    if s:
                        print(f"  0x{target:X}  {s}")
        c = CALL_ABS.search(line)
        if c:
            calls.append(int(c.group(1), 16))

    if calls:
        uniq = []
        for c in calls:
            if c not in uniq:
                uniq.append(c)
        print("  wola:", ", ".join(f"0x{c:X}" for c in uniq[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
