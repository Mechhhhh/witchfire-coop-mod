#!/usr/bin/env python3
"""Wyciąga z minidumpa UE4SS to, co da się ustalić bez symboli:
kod i adres wyjątku, moduł, w którym padło, oraz kandydatów na ramki stosu.

Po co własny parser: na tej maszynie nie ma ani Ghidry, ani breakpada, a okno
błędu UE4SS pokazuje wyłącznie ścieżkę do pliku .dmp. Kluczowe pytanie brzmi
"czy padła gra, czy nasze narzędzia" — a na to wystarczy moduł i offset.

Użycie: read-dump.py <plik.dmp> [...]
"""
import os
import struct
import sys

STREAM_THREAD_LIST = 3
STREAM_MODULE_LIST = 4
STREAM_EXCEPTION = 6

# Najczęstsze kody wyjątków Windows, żeby nie sprawdzać ich ręcznie za każdym razem.
EXC = {
    0xC0000005: "ACCESS_VIOLATION (odwolanie do zlej pamieci)",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000025: "NONCONTINUABLE_EXCEPTION",
    0xC0000026: "INVALID_DISPOSITION",
    0xC000008C: "ARRAY_BOUNDS_EXCEEDED",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC0000096: "PRIV_INSTRUCTION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000409: "STACK_BUFFER_OVERRUN / __fastfail",
    0xC0000602: "FAIL_FAST_EXCEPTION",
    0xE06D7363: "C++ EXCEPTION (throw)",
    0x80000003: "BREAKPOINT (int3 — czesto assert UE)",
}


def read_string(buf, rva):
    if rva == 0 or rva + 4 > len(buf):
        return "?"
    (nbytes,) = struct.unpack_from("<I", buf, rva)
    raw = buf[rva + 4: rva + 4 + nbytes]
    try:
        return raw.decode("utf-16-le", errors="replace")
    except Exception:
        return "?"


def parse(path):
    with open(path, "rb") as f:
        buf = f.read()

    if buf[:4] != b"MDMP":
        print(f"{path}: to nie jest minidump")
        return

    _, _, nstreams, dir_rva = struct.unpack_from("<4sIII", buf, 0)[0:4]
    sig, ver, nstreams, dir_rva = struct.unpack_from("<4sIII", buf, 0)

    streams = {}
    for i in range(nstreams):
        stype, dsize, rva = struct.unpack_from("<III", buf, dir_rva + i * 12)
        streams[stype] = (dsize, rva)

    # ── moduły ──────────────────────────────────────────────────────────────
    modules = []
    if STREAM_MODULE_LIST in streams:
        _, rva = streams[STREAM_MODULE_LIST]
        (nmods,) = struct.unpack_from("<I", buf, rva)
        off = rva + 4
        for _ in range(nmods):
            base, size = struct.unpack_from("<QI", buf, off)
            (name_rva,) = struct.unpack_from("<I", buf, off + 20)
            name = read_string(buf, name_rva)
            modules.append((base, size, name.split("\\")[-1]))
            off += 108
    modules.sort()

    def locate(addr):
        for base, size, name in modules:
            if base <= addr < base + size:
                return f"{name}+0x{addr - base:X}"
        return None

    print(f"\n=== {path.split('/')[-1]} ===")

    # ── wyjątek ─────────────────────────────────────────────────────────────
    exc_addr = None
    if STREAM_EXCEPTION in streams:
        _, rva = streams[STREAM_EXCEPTION]
        tid = struct.unpack_from("<I", buf, rva)[0]
        code, flags, _rec, addr = struct.unpack_from("<IIQQ", buf, rva + 8)
        exc_addr = addr
        nparams = struct.unpack_from("<I", buf, rva + 8 + 24)[0]
        params = struct.unpack_from("<15Q", buf, rva + 8 + 32)
        print(f"  watek        : {tid}")
        print(f"  kod wyjatku  : 0x{code:08X}  {EXC.get(code, '(nieznany)')}")
        print(f"  adres        : 0x{addr:X}  -> {locate(addr) or 'poza znanymi modulami'}")
        if code == 0xC0000005 and nparams >= 2:
            kind = {0: "odczyt", 1: "zapis", 8: "wykonanie"}.get(params[0], f"op={params[0]}")
            print(f"  szczegol     : {kind} spod 0x{params[1]:X}")
    else:
        print("  brak strumienia wyjatku")

    # ── rejestry i obchód stosu ─────────────────────────────────────────────
    # Poprzednia wersja czytala deskryptor stosu spod offsetu 16, a tam w
    # MINIDUMP_THREAD siedzi Teb. Stos zaczyna sie na 24, kontekst watku na 40.
    # Przez ten blad skanowany byl przypadkowy kawalek PLIKU zamiast pamieci
    # stosu — stad dawne "stosy" pelne ntdll, VCRUNTIME i libmono.
    #
    #   MINIDUMP_THREAD: ThreadId 0, SuspendCount 4, PriorityClass 8,
    #   Priority 12, Teb 16, Stack 24 (Start 8B + DataSize 4B + Rva 4B),
    #   ThreadContext 40 (DataSize 4B + Rva 4B); calosc 48 bajtow.
    if STREAM_THREAD_LIST in streams and STREAM_EXCEPTION in streams:
        _, rva = streams[STREAM_THREAD_LIST]
        (nthreads,) = struct.unpack_from("<I", buf, rva)
        exc_tid = struct.unpack_from("<I", buf, streams[STREAM_EXCEPTION][1])[0]
        off = rva + 4
        for _ in range(nthreads):
            tid = struct.unpack_from("<I", buf, off)[0]
            stack_start, stack_size, stack_rva = struct.unpack_from("<QII", buf, off + 24)
            ctx_size, ctx_rva = struct.unpack_from("<II", buf, off + 40)
            if tid != exc_tid:
                off += 48
                continue

            # CONTEXT dla AMD64: Rax 0x78, Rcx 0x80, Rdx 0x88, Rbx 0x90,
            # Rsp 0x98, Rbp 0xA0, Rsi 0xA8, Rdi 0xB0, R8..R15 0xB8..0xF0, Rip 0xF8.
            regs = {}
            if ctx_size >= 0x100 and ctx_rva + 0x100 <= len(buf):
                names = ["Rax", "Rcx", "Rdx", "Rbx", "Rsp", "Rbp", "Rsi", "Rdi",
                         "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15", "Rip"]
                for i, nm in enumerate(names):
                    (regs[nm],) = struct.unpack_from("<Q", buf, ctx_rva + 0x78 + i * 8)
                print("  rejestry:")
                for row in (("Rip", "Rsp", "Rbp"), ("Rax", "Rcx", "Rdx"),
                            ("Rbx", "Rsi", "Rdi"), ("R8", "R9", "R14")):
                    cells = []
                    for nm in row:
                        v = regs[nm]
                        loc = locate(v)
                        cells.append(f"{nm}=0x{v:X}" + (f" ({loc})" if loc else ""))
                    print("      " + "   ".join(cells))

            if not stack_size or stack_rva + stack_size > len(buf):
                print("  stos: brak pamieci stosu w zrzucie")
                break

            data = buf[stack_rva: stack_rva + stack_size]
            rsp = regs.get("Rsp", stack_start)
            # Idziemy od RSP w gore, czyli w kolejnosci ramek: od miejsca awarii
            # do wywolan nadrzednych. Dedup tylko powtorzen pod rzad — ten sam
            # adres powrotu potrafi wystapic w kilku ramkach i to jest informacja.
            begin = max(0, rsp - stack_start)
            begin -= begin % 8
            frames, last = [], None
            for i in range(begin, len(data) - 8, 8):
                (val,) = struct.unpack_from("<Q", data, i)
                loc = locate(val)
                if not loc or val == last:
                    continue
                last = val
                frames.append((stack_start + i, val, loc))
            # UWAGA przy czytaniu: zrzut powstaje w procedurze obslugi wyjatku,
            # ktora dziala na TYM SAMYM stosie, tylko glebiej. Idac od RSP w gore
            # widzi sie najpierw ramki OBSLUGI awarii (CrashReportClient,
            # CrashGUID, IsAssert...), potem dyspozytor wyjatkow ntdll, a dopiero
            # ZA NIMI prawdziwy stos sprawcy. Ucinanie listy na 30 wpisach
            # obcinalo dokladnie to, co istotne — stad domyslnie 120.
            limit = int(os.environ.get("WF_FRAMES", "120"))
            print(f"  stos od RSP ({len(frames)} kandydatow, pierwsze {limit}):")
            for addr, val, loc in frames[:limit]:
                print(f"      [rsp+0x{addr - rsp:05X}]  0x{val:X}  {loc}")
            break

    print("  moduly istotne:")
    for base, size, name in modules:
        if any(k in name.lower() for k in ("witchfire", "ue4ss", "dwmapi", "eossdk", "steam")):
            print(f"      {name:35} 0x{base:X} + 0x{size:X}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        try:
            parse(p)
        except Exception as e:
            print(f"{p}: blad parsowania: {e}")
