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

**Uruchomienie (dozorca robi drugą połowę sam):**
```
tools/stop.sh
WF_GAMESCOPE=1 WF_W=1100 WF_H=620 WF_PREFIX=~/.local/share/witchfire-mp/compat1 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
setsid nohup tools/dozorca.sh /tmp/przebieg.out > /dev/null 2>&1 < /dev/null &
# gracz klika CONTINUE i wchodzi na wyprawe — KIEDY MU WYGODNIE
```
`dozorca.sh` wykrywa wejście na wyprawę po zmianie `GWorld` ze źródła
niezerowego, sam dołącza klienta i zbiera pomiar. Człowiek klika **raz**.

**Uruchomienie ręczne:**
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

## KAMIENIE MILOWE — gdzie jesteśmy i co bramkuje co

| | stan |
|---|---|
| **M0** dwaj gracze w jednym świecie, broń, ekwipunek hosta | **zrobione**, potwierdzone godzinami gry |
| **M1** sesja, która nie kończy się awarią | **wąskie gardło** — obie żywe sygnatury załatane 12.08, **niesprawdzone** |
| **M2** ruch klienta jak u hosta | połowa: `HasMovementInput` naprawione, `IsOnGround` zdiagnozowane |
| **M3** broń klienta (amunicja, przeładowanie) | mechanizm rozebrany, pomiar uzbrojony, brak odczytu |
| **M4** **reszta gry w co-opie** | **biała plama** — `docs/PRZEGLAD.md` |
| **M5** żeby ktoś inny mógł tego użyć | publiczne repo jest, instalacji od zera nikt nie przeszedł |

**M1 bramkuje wszystko**, bo bez długiej sesji nie da się niczego zmierzyć.
Dlatego kolejność jest teraz: awarie → amunicja → przegląd wszerz → ruch → stamina.

**Amunicja przed ruchem** nie dlatego, że ważniejsza, tylko dlatego, że jest
prawdopodobnie POWYŻEJ awarii `0x148`: jej stos ma ramkę w pętli po broniach
w ekwipunku, a pętla przeładowania bez końca wali w tę ścieżkę bez przerwy.

## NASTĘPNY KROK — jedna przeszkoda, zmierzona i nazwana

Stan na 12.08, 01:4x. Biblioteka wdrożona (`md5=77cddef7`), gry **zamknięte**.

Markery u hosta: `fix_czas`, `log_tryb`, `log_ammo` oraz **dwie nowe ściany**:
`fix_lista` i `fix_ekwipunek` (obie po obu stronach). `fix_ammo` dalej zdjęty.

**Cztery niesprawdzone markery naraz — następny przebieg musi być zaprojektowany
pod PRZYPISANIE, nie tylko pod pomiar.** Każdy ma własny licznik w logu, więc
da się powiedzieć, który zadziałał; ale próby kontrolne (zdjęcie markera) trzeba
wpisać do planu, a nie zostawiać na dobre chęci.

**Przebieg jest przygotowany i czeka na jedno kliknięcie.** Wystarczy wejść na
wyprawę — klienta dołączy `dozorca` (patrz „Jak to teraz działa"), a log
odpowie na pytanie hipotezy 23 bez dalszej interakcji.

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

**Zrobione statycznie — droga rozebrana do gniazd tablicy metod:**

| co | gdzie |
|---|---|
| tablica metod `DimensionMovementComponent` | `0x14506F2C0` (sprawdzona na dwóch znanych gniazdach: 130 i 223) |
| `SetMovementMode(this, tryb, własny)` | `0x1436E7210`, **gniazdo 182** (`+0x5B0`) |
| `SetPostLandedPhysics(this, hit)` | `0x1436E75B0`, **gniazdo 241** (`+0x788`), ustawia tryb z `GroundMovementMode` (`+0x387`) |
| kto ustawia `Falling` | dziewięć miejsc w `0x1436Cxxxx`–`0x1436Exxxx`, wszystkie z `mov edx, 3` |

**Do zrobienia — jeden przebieg, marker `log_tryb` już leży.** Diagnostyka
podmienia oba gniazda tą samą drogą co `GetMaxSpeed` (żadnego splice'u bajtów)
i sprawdza przed podmianą, czy w gnieździe stoi spodziewana funkcja gry.
Co znaczy który wynik:

| co w logu | znaczenie |
|---|---|
| `TRYB: ladowanie` dla HOSTA, **brak** dla KLIENTA | `ProcessLanded` nie dochodzi — fizyka spadania nie znajduje podłogi pod pionkiem zdalnym |
| `ladowanie` jest, ale zaraz potem `-> 3` | coś wypycha pionek z powrotem w spadanie; **adres powrotu w logu powie co** |
| `gniazdo … ma 0x…, a spodziewalem sie 0x…` | numer gniazda nie ten — nic nie podmieniono, gra bezpieczna |

### 2. Amunicja — gracz dał mocny dowód

Zgłoszenie z tego przebiegu: **broń klienta przeładowywała się w kółko i nie
dodawało amunicji**. To dowód, że ścieżka przeładowania GRY działa dla broni
klienta i mimo to kończy zerem — magazynek pusty ⇒ `ShouldReload` prawdziwe ⇒
przeładowanie ⇒ dalej zero ⇒ pętla.

Analiza statyczna (`WIEDZA.md` §3g) mówi, gdzie szukać: `0x141B242F0` to
**zacisk w dół** (`min(magazynek, ClipSize, zapas)` — pierwszy operand jest
polem docelowym, więc nigdy nie podniesie), a napełnia `0x141B39940` przez
atrybut `PendingClipRefill`. To hipoteza 24.

**Zmierzy się w tym samym przebiegu, bez nowego haka.** Zapis `PendingClipRefill`
idzie tym samym gniazdem 180 ASC, na którym od tygodnia siedzi `log_ammo` —
odrzucał go tylko filtr nazwy. Filtr rozszerzony. Co znaczy który wynik:

| co w logu | znaczenie |
|---|---|
| `AMUNICJA: PendingClipRefill = N` dla broni klienta, `N > 0` | gra policzyła doładowanie — winny jest **konsument** tego atrybutu |
| brak takiego wiersza dla klienta, a jest dla hosta | `0x141B39940` nie dochodzi dla broni klienta — szukać wyżej |
| `PendingClipRefill = 0` | różnica `ClipSize − magazynek` wyszła zerem, czyli `ClipSize` też jest zerem ⇒ ASC broni klienta **nie ma zestawu atrybutów** |

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