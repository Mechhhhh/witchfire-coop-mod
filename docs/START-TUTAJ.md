# Zacznij tutaj — stan i następny krok

Stan na 2026-08-12, 00:1x.

## Co czytać

**Ten plik i `DZIENNIK.md`. Nic więcej na starcie.**

`WIEDZA.md` (1600 linii) to zapis, JAK doszliśmy do wniosków — nie czytaj go
w całości, bo zjada ~30 tys. tokenów, zanim cokolwiek zrobisz. Wyszukuj
punktowo:

```
tools/szukaj.py 0x1418002E0        # co wiemy o adresie
tools/szukaj.py "mapa atrybutow"   # z nagłówkiem sekcji
```

Nagłówek sekcji w wynikach jest tam nie dla ozdoby: mówi, czy trafienie
pochodzi z ustalenia POTWIERDZONEGO, czy z OBALONEGO. **Zanim ruszysz
z hipotezą — wyszukaj ją.** W tym projekcie dwa razy wrócono do tej samej
ślepej uliczki.

`ADRESY.md` — czysta referencja adresów i offsetów, do zaglądania punktowego.
`PRZEBIEGI.md` — rejestr zjawisk.
`docs/historia/` — archiwum drogi A, NIE czytać.

## Jak to teraz działa (droga B)

Host wchodzi do gry **normalnie** — klika CONTINUE, rusza na wyprawę. Nasza DLL
robi jedną rzecz: zamienia w `UEngine::LoadMap` skok `je` na dwa `NOP`-y
(`0x143BEC200`), przez co gra **sama** woła własne `UWorld::Listen` przy każdym
ładowaniu mapy. Dzięki temu jej sekwencja startu misji nie jest rozbijana.

To zdjęło: brak prawdziwej postaci u klienta (gra daje ją sama) i cały zestaw
objawów wynikających z pominiętej sekwencji startu misji **po stronie hosta**.

Broń u klienta **jest już wyjmowana poprawnie** (patrz „Co jest zrobione").

**Uruchomienie:**
```
tools/stop.sh
WF_GAMESCOPE=1 WF_W=1100 WF_H=620 WF_PREFIX=~/.local/share/witchfire-mp/compat1 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
# gracz klika CONTINUE i wchodzi na wyprawę
echo 127.0.0.1 > <Saved compat2>/WFCoop_join_ip.txt
WF_GAMESCOPE=1 WF_PREFIX=~/.local/share/witchfire-mp/compat2 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
```

Markery **hosta**: `always_listen`, `fix_booster`, `fix_input`, `fix_dup`,
`fix_attrs`, `fix_state`, **`fix_czas`**; diagnostyczne: `count_move`, `log_owner`,
`log_fill`, `log_speed`, `log_kanal`, `log_ammo`.
Markery **klienta**: `join_ip`, `fix_weapon`, `fix_effects`, `fix_dup`,
`fix_attrs`, `fix_state`; diagnostyczne: `count_move`, `log_fill`, `log_speed`.

`fix_czas` ma sens **tylko u hosta** — stempluje znacznik czasu wejścia ruchu
pionka ZDALNEGO, a taki istnieje wyłącznie po stronie serwera. U klienta marker
niczego nie zmieni (własny pionek stempluje się sam), ale nie zaszkodzi.

**`fix_ammo` jest ZDJĘTY po obu stronach i ma taki zostać** — powód w sekcji
„NASTĘPNY KROK". `fix_move` usunięty z kodu (podstawiał sufit prędkości).

`fix_state` to **kanał stanu ruchu** — jedyna łatka w całym modzie, która dokłada
własny przekaz danych zamiast wołać kod gry. Powód: `DimensionStateMachineComponent`
ma 47 funkcji i **zero RPC**, więc gra nie ma czym przesłać tego stanu. Ten sam
marker po obu stronach; kod sam rozpoznaje rolę.

`log_speed` loguje **pierwsze zero** każdej z funkcji limitu ruchu razem
z rozmiarem mapy atrybutów odczytanym **w tej samej chwili** — to zamyka pytanie
z punktu 1 bez zgadywania, w którą sekundę trafić odczytem z zewnątrz.
Przejściowka melduje też pierwsze wywołanie, więc cisza w logu znaczy
jednoznacznie „zera nie było".

Przebudowa i wdrożenie biblioteki: `tools/wdroz-dll.sh` (buduje, kopiuje do
katalogu gry i porównuje sumy — gra musi być zamknięta).

## NASTĘPNY KROK — jedna przeszkoda, zmierzona i nazwana

Stan na 12.08, 00:1x. Biblioteka wdrożona (`md5=4287a6ae`), gry **zamknięte**
(host padł 23:58, patrz niżej). Marker `fix_czas` **leży u hosta**;
`fix_ammo` dalej zdjęty po obu stronach.

### 1. Sprint — `fix_czas` DZIAŁA; blokuje następny warunek

Przebieg 23:53–23:58 z markerem `fix_czas`. Odczyt mapy warunków **obu**
maszyn w tej samej chwili:

| warunek | KLIENT | HOST |
|---|---|---|
| `IsMoving` | **1** | 0 |
| **`HasMovementInput`** | **1** | 0 |
| **`IsOnGround`** | **0** | **1** |

`HasMovementInput` u klienta jest prawdziwe **pierwszy raz w tym projekcie**.
8093 stempli, próg wieku znacznika `0.100 s`. Ale `IdleToWalking` wymaga OBU
warunków, więc maszyna dalej stoi w `Idle` — i gracz dalej jest cofany.

**Przyczyna drugiej przeszkody, zmierzona:**

| pole komponentu ruchu | KLIENT | HOST |
|---|---|---|
| `MovementMode` (`+0x168`) | **3** = spadanie | **1** = chodzenie |

`IsOnGround` gra liczy jako `pionek->KomponentRuchu()->IsMovingOnGround()`
(`[vt+0x638]` → `[vt+0x570]`, `0x141809E44`–`0x141809E65`), a to w UE znaczy
po prostu `MovementMode ∈ {Walking, NavWalking}`.

**Do zrobienia:** znaleźć, co po stronie serwera trzyma pionek zdalny
w `Falling`. To hipoteza 23 w `DZIENNIK.md`. Robota jest **statyczna** —
`tools/pole.py 0x168` pokaże wszystkich zapisujących `MovementMode`,
a `tools/warunki.py` i `obraz.py` resztę. Gra do tego niepotrzebna.

### 2. Amunicja — gracz dał mocny dowód

Zgłoszenie z tego przebiegu: **broń klienta przeładowywała się w kółko i nie
dodawało amunicji**. To dowód, że ścieżka przeładowania GRY działa dla broni
klienta i mimo to kończy zerem — magazynek pusty ⇒ `ShouldReload` prawdziwe ⇒
przeładowanie ⇒ dalej zero ⇒ pętla.

Analiza statyczna (`WIEDZA.md` §3g) mówi, gdzie szukać: `0x141B242F0` to
**zacisk w dół** (`min(magazynek, ClipSize, zapas)` — pierwszy operand jest
polem docelowym, więc nigdy nie podniesie), a napełnia `0x141B39940` przez
atrybut `PendingClipRefill`. To hipoteza 24.

### 3. Awaria hosta 23:58 — próba kontrolna do dołożenia za darmo

Nowa sygnatura (`abeaa893`, `0x148`), stos **w całości w kodzie gry**, ramka
`0x1418D3279` = pętla po broniach w ekwipunku. Podejrzenie: to pętla
przeładowania dobija ekwipunek. Rozstrzyga przebieg **bez** `fix_czas` — jeśli
awaria wróci, marker jest niewinny. To hipoteza 25; kosztuje tylko zdjęcie pliku.

### 4. Stamina — zeszła na koniec

`522,8` to `615 × 0,85` (chód w bok), a **nie** `615 × 0,83` (mnożnik staminy).
Czyli nie ma dowodu, że stamina uczestniczy w sprawie prędkości. Ścieżka
regeneracji rozebrana statycznie w `WIEDZA.md` §3h, razem z następnym pomiarem.

## Co jest zrobione

| | dowód |
|---|---|
| **broń u klienta działa na drodze B** | przebieg 16:25: `CurrentWeaponIndex -1 -> 0 (UDALO SIE)` 4 s po dołączeniu, broń na zrzucie. Wcześniejsze „nie działa" było błędem pomiaru: budżet prób liczył się od startu procesu, nie od połączenia |
| **obaj gracze żyją w jednym świecie i widzą się** | klient dołączył 16:25:07 i działał o 16:29:14 (218 FPS); łącznie z kolejnym przebiegiem **ponad dwie godziny wspólnej gry bez awarii**. Utrata widoku pierwszoosobowego i waluty u hosta **naprawiona przez `fix_dup`** (gracz: „host działa jak na singleplayer") |
| hostowanie bez wymuszania mapy | port 7777 + `IpNetDriver` w refleksji |
| klient dostaje własną postać `Role=2` | kanały aktorów + kontroler z pawnem |
| późny respawn | `UnPossess`+`K2_DestroyActor` przed `RestartPlayer` |
| ściana #1 (`0x24`, boostery) | **próba kontrolna**: bez strażnika awaria wraca |
| ściana #2 (`0x430`, wiązanie wejścia) | licznik pokazuje przechwycenia; jedno wystąpienie przed łatką |

## Narzędzia (wszystkie sprawne, `tools/`)

| narzędzie | do czego |
|---|---|
| `sygnatura.py` | grupuje zrzuty po sygnaturze — **uruchamiać jako pierwsze** |
| `nazwij-ramke.py` | nazywa ramki po adresach natywnych `UFunction` |
| `ue-props.py` | właściwości obiektów przez refleksję, `--sprawdz`, `--drzewo` |
| `ue-funcs.py` | sygnatury `UFunction`, flagi RPC, adresy natywne |
| `ue-objects.py` | wyszukiwanie obiektów, `--isa` po dziedziczeniu |
| `ue-snapshot.py` | migawka 280 tys. obiektów w 0,4 s + różnica |
| `ue-disasm.py`, `find-xref.py`, `find-callers.py` | deasemblacja żywej pamięci |
| `ue-poke.py` | kontrolowana zmiana pola (z kopią do cofnięcia) |
| `bron-stan.py` | sonda broni, stały format do `diff` |
| `zrzut.sh` | zrzut ekranu (Wayland/gamescope) |
| `bron-lokalna.py` | ekwipunek + rola właściciela + stan `Mesh1P`, `--zwiezle` do szeregu czasowego |
| `pomiar-broni.sh` | szereg czasowy obu instancji w jednym pliku |
| `stos-watku.py` | stos żywego wątku Win32 (do zamrożeń, nie awarii) |
| `zrzut-kodu.py` | zrzut **odszyfrowanego** obrazu exe do pliku (raz na build) |
| `sygnatura-funkcji.py` | **parametry `UFunction`** — typy, offsety, rozwinięte struktury; bez tego nie da się wywołać kodu gry |
| `obraz.py` | **deasemblacja i szukanie odwołań BEZ działającej gry** — `fun`, `xref`, `dane`, `gdzie`, `napis` |
| `stan-gracza.py` | pełny stan gracza: mapa atrybutów ruchu, zestawy, zdolności, bronie z amunicją i mnożnikami |
| `vtable-diff.py` | **które metody wirtualne gra nadpisała** — 10 zamiast kilkuset |
| `pulapka-zapisu.py` | pułapka sprzętowa: **kto** zapisuje pod dany adres |
| `pulapka-galezi.py` | pułapka wykonania + rejestry: **którą gałąź bierze który obiekt** |
| `wdroz-dll.sh` | build + kopia do gry z porównaniem sum |
| `szukaj.py` | **wyszukiwanie w dokumentacji z nagłówkiem sekcji** — mówi, czy trafienie jest z POTWIERDZONE czy z OBALONE |
| `przejscia.py` | graf przejść maszyny stanów z jej własnych danych, z warunkami |

## Zasady pracy

**Są w `PROMPT-NOWY-CZAT.md` i tylko tam.** Jedna kopia, bo dwie rozjeżdżają
się w godzinę — tak właśnie zdezaktualizowało się publiczne README 11.08.

Cztery najdroższe, żeby nie trzeba było przełączać pliku:
nie wołaj funkcji gry bez potwierdzonej sygnatury (trzy awarie jednego
wieczoru); wyzwalacz opieraj na zmierzonym, nie na oczywistym; zanim powiesz
„nie działa", sprawdź, czy okno pomiaru w ogóle zawiera zjawisko; wrażenie
gracza to pomiar, nie anegdota.
## Jak organizować pracę (cztery pliki, każdy o czym innym)

| plik | co tam trafia | kiedy pisać |
|---|---|---|
| `DZIENNIK.md` | hipotezy w toku, plan najbliższego przebiegu | na bieżąco, przed i po każdym przebiegu |
| `PRZEBIEGI.md` | zjawiska i awarie — **jeden wiersz na zjawisko** | gdy coś wystąpi; przy powtórce dopisać znacznik czasu do istniejącego wiersza |
| `WIEDZA.md` | rzeczy **zamknięte**: potwierdzone albo obalone | gdy hipoteza z dziennika się rozstrzygnie |
| `START-TUTAJ.md` | stan ogólny i następny krok | gdy zmieni się priorytet albo coś dużego się domknie |

Cykl jednej hipotezy: wpisz ją do `DZIENNIK.md` **razem z przewidywaniem**
(„co zobaczę, jeśli jest prawdziwa") → zmierz → wpisz werdykt → przenieś do
`WIEDZA.md` i **usuń z dziennika**. Dziennik ma zostać krótki; jeśli rośnie,
znaczy że coś wisi nierozstrzygnięte.

Do tego prowadź listę zadań w narzędziu (`TaskCreate`/`TaskUpdate`) — ale tylko
na czynności („zmierz X", „napisz łatkę Y"), nie na hipotezy. Hipotezy żyją
w dzienniku, bo mają przewidywanie i werdykt, czego lista zadań nie zapisze.