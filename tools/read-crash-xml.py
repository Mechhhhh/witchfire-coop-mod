#!/usr/bin/env python3
"""Czyta raport awarii UE (`CrashContext.runtime-xml`) i nazywa ramki stosu.

Po co, skoro jest `read-dump.py`: okazalo sie, ze UE zapisuje obok minidumpa
plik XML, a w nim GOTOWY stos wywolan (`PCallStack`) — offsety wzgledem bazy
modulu, juz odsiane, w prawidlowej kolejnosci. To jest lepsze zrodlo niz recznie
chodzenie po stosie z minidumpa: obchod z RSP w gore lapie najpierw ramki
PROCEDURY OBSLUGI awarii i dwa razy doprowadzil w tym projekcie do blednej
diagnozy. XML podaje od razu watek, ktory padl, i komunikat.

Czego XML NIE ma: nazw funkcji (shipping bez symboli). Dlatego przy podanym
PID zywego procesu dokladamy nazywanie po literalach — ten sam pomysl, co
w `name-function.py`: czytamy kod spod adresu ramki i wypisujemy napisy,
do ktorych siega. Dziala, bo baza jest stala (0x140000000, brak ASLR), wiec
adresy z martwego procesu pasuja do zywego.

Uzycie:
  read-crash-xml.py                      # najnowszy raport z obu prefiksow
  read-crash-xml.py <katalog-lub-xml>
  read-crash-xml.py <katalog-lub-xml> <pid-zywego-procesu>
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

# WF_PREFIX_ROOT — katalog, w ktorym leza prefiksy Proton obu instancji
# (ten sam, ktorego uzywa tools/launch-instance2.sh).
KORZEN_PREFIKSOW = os.environ.get(
    "WF_PREFIX_ROOT", os.path.expanduser("~/.local/share/witchfire-mp"))

PREFIXES = [
    os.path.join(KORZEN_PREFIKSOW, p,
                 "pfx/drive_c/users/steamuser/"
                 "AppData/Local/Witchfire/Saved/Crashes")
    for p in ("compat1", "compat2")
]

LEA_RIP = re.compile(r"lea\s+\w+,\[rip\+0x([0-9a-f]+)\]")
MOV_RIP = re.compile(r"mov\s+\w+,QWORD PTR \[rip\+0x([0-9a-f]+)\]")


def newest_report():
    best, best_t = None, -1
    for root in PREFIXES:
        for d in glob.glob(os.path.join(root, "*", "CrashContext.runtime-xml")):
            t = os.path.getmtime(d)
            if t > best_t:
                best, best_t = d, t
    return best


def tag(text, name):
    m = re.search(r"<%s>(.*?)</%s>" % (name, name), text, re.S)
    return m.group(1).strip() if m else ""


def read_mem(pid, addr, size):
    try:
        with open("/proc/%d/mem" % pid, "rb", 0) as f:
            f.seek(addr)
            return f.read(size)
    except Exception:
        return None


def read_text(pid, addr, maxlen=120):
    raw = read_mem(pid, addr, maxlen * 2)
    if not raw or not raw[0:1]:
        return None
    if len(raw) >= 6 and raw[1] == 0 and raw[3] == 0 and 0x20 <= raw[0] < 0x7F:
        out = []
        for i in range(0, len(raw) - 1, 2):
            ch = raw[i] | (raw[i + 1] << 8)
            if ch == 0:
                break
            if ch < 0x20 or ch > 0x7E:
                return None
            out.append(chr(ch))
        if len(out) >= 4:
            return "".join(out)
    if 0x20 <= raw[0] < 0x7F:
        out = []
        for b in raw:
            if b == 0:
                break
            if b < 0x20 or b > 0x7E:
                return None
            out.append(chr(b))
        if len(out) >= 5:
            return "".join(out)
    return None


def literals_near(pid, addr, back=0x700, fwd=0x180):
    """Napisy, do ktorych siega kod wokol adresu powrotu.

    Adres z PCallStack to adres POWROTU, czyli srodek funkcji wolajacej.
    Nie znamy jej poczatku, wiec bierzemy okno w obie strony — to wystarcza,
    zeby zlapac charakterystyczne literaly (nazwy klas, komunikaty).
    """
    start = addr - back
    data = read_mem(pid, start, back + fwd)
    if not data:
        return []
    fd, path = tempfile.mkstemp(suffix=".bin")
    try:
        os.write(fd, data)
        os.close(fd)
        out = subprocess.run(
            ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
             "--adjust-vma=0x%X" % start, path],
            capture_output=True, text=True).stdout
    finally:
        os.unlink(path)

    found, seen = [], set()
    for line in out.splitlines():
        if not (LEA_RIP.search(line) or MOV_RIP.search(line)):
            continue
        t = re.search(r"#\s*0x([0-9a-f]+)", line)
        if not t:
            continue
        target = int(t.group(1), 16)
        if target in seen:
            continue
        seen.add(target)
        s = read_text(pid, target)
        if s and len(s) >= 5:
            found.append(s)
    return found[:6]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else newest_report()
    if path and os.path.isdir(path):
        path = os.path.join(path, "CrashContext.runtime-xml")
    if not path or not os.path.exists(path):
        print("nie znalazlem CrashContext.runtime-xml")
        return 1
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else None

    text = open(path, encoding="utf-8", errors="replace").read()
    print("raport: %s" % path)
    for name in ("ErrorMessage", "CrashType", "IsAssert", "IsEnsure",
                 "SecondsSinceStart", "EngineVersion"):
        v = tag(text, name)
        if v:
            print("  %-18s %s" % (name, v.replace("\n", " ")[:200]))

    crashed = re.search(
        r"<Thread>(?:(?!</Thread>).)*?<IsCrashed>true</IsCrashed>.*?</Thread>",
        text, re.S)
    if crashed:
        tn = tag(crashed.group(0), "ThreadName")
        ti = tag(crashed.group(0), "ThreadID")
        print("  watek, ktory padl: %s (ID %s)" % (tn, ti))

    frames = re.findall(r"\+\s*([0-9a-f]+)\s*$", tag(text, "PCallStack"), re.M)
    if not frames:
        frames = re.findall(r"0x0000000140000000\s*\+\s*([0-9a-f]+)", text)
    print("\nstos (%d ramek, baza 0x140000000):" % len(frames))
    if pid:
        print("  (nazywanie po literalach z procesu %d)" % pid)
    for i, off in enumerate(frames):
        addr = 0x140000000 + int(off, 16)
        line = "  #%-2d  +0x%-8s  = 0x%X" % (i, off, addr)
        if pid:
            lits = literals_near(pid, addr)
            if lits:
                line += "\n        napisy: " + " | ".join(lits)
        print(line)
    if not pid:
        print("\nPodaj PID zywej instancji jako drugi argument, zeby nazwac ramki.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
