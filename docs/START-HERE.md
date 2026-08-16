# Zacznij tutaj — stan i następny krok

Stan na **2026-08-16**. Gry są **zamknięte**, nic nie chodzi w tle, repo czyste.
Ostatnia sesja robocza: 12.08 (od nocy do wieczora).

## Co czytać

**Ten plik, potem `JOURNAL.md`. Nic więcej na starcie.**

`KNOWLEDGE.md` (2500 linii) to zapis, JAK doszliśmy do wniosków — nie czytaj go
w całości. Wyszukuj punktowo:

```
tools/szukaj.py 0x1418002E0        # co wiemy o adresie
tools/szukaj.py "mapa atrybutow"   # z nagłówkiem sekcji
```

Nagłówek sekcji w wynikach mówi, czy trafienie pochodzi z ustalenia
POTWIERDZONEGO, czy z OBALONEGO. **Zanim ruszysz z hipotezą — wyszukaj ją.**

`ADDRESSES.md` — czysta referencja adresów i offsetów. `OVERVIEW.md` — co
w co-opie działa, a czego nikt nie sprawdził. `docs/historia/` — NIE czytać.

---

## STAN W SKRÓCIE

**Co działa:** obaj gracze są w jednym świecie i widzą się; host nasłuchuje
także w hubie; klient **przeżywa dołączenie w hubie** (`fix_smycz`, 12.08:
połączenie 453 s zamiast śmierci po 64 s), ma kamerę, świat i pełne objęcie
pionka; host nie dostaje duplikatu ekwipunku (`fix_dup`); klient chodzi
(`fix_attrs`) i wyjmuje broń.

**Co blokuje grywalność — jedna rzecz:** po dołączeniu **klient nie przyjmuje
żadnego wejścia** (ani WSAD, ani myszy, ani Esc). Zmierzone: kierunek patrzenia
klienta stoi (0 zmian na 1499 próbek), gdy host w tym samym oknie ma 121 zmian.
Przed dołączeniem to samo okno przyjmuje wejście bez zarzutu (250 próbek gry
gracza, sprint 800, unik 1502) — więc psuje je dopiero dołączenie.

**Dwa problemy poboczne, oba zmierzone:** host pada po ~50 min na wiszącym
słuchaczu (ściana #3), a przy PONOWNYM dołączeniu klienta parkuje wątek gry
(`futex_wait`, 0 tików/3 s). Dekompilacja pokazała, że pętla rozgłaszania trzyma
zamek przez cały przebieg listy — więc oba objawy to prawdopodobnie jedno
zdarzenie.

---

## NASTĘPNY KROK — licznik zdarzeń wejścia (hipoteza 36)

Jedyne pytanie, które blokuje wszystko inne: **czy do gry klienta docierają
zdarzenia wejścia po dołączeniu.** Wykluczone już zostało wszystko po stronie
gry (tryb wejścia, wiązania, stan kontrolera — patrz `JOURNAL.md`), więc
zostaje warstwa dostarczania. Odpowiedź daje jeden przebieg.

**Przepis, wszystko gotowe do napisania:**

1. Hak zliczający na **`0x141A020B0`** — wspólny filtr zdarzeń wejścia gry,
   wołany przez wszystkie trzy obsługi z tablicy metod `FViewportClient`
   (`ADDRESSES.md`, sekcja „punkt wejścia zdarzeń"). Wołany **raz na zdarzenie**,
   nie co klatkę, więc jest tani (zasada 7).
2. Marker `log_wejscie`, licznik wypisywany do logu co kilka sekund — po
   **obu** stronach, bo host jest próbą kontrolną.
3. Przebieg: host w hubie, klient dołącza **pierwszy raz** (ponowne dołączenie
   parkuje hosta i unieważnia pomiar — sprawdź tiki hosta przed werdyktem),
   gracz gra chwilę u hosta i próbuje u klienta.

| wynik | znaczenie |
|---|---|
| host > 0, klient = 0 | zdarzenia nie docierają do gry klienta → szukać w Slate/oknie, nie w co-opie |
| host > 0, klient > 0 | zdarzenia docierają, a gra je ignoruje → wracamy do środka gry, z nowym tropem |
| oba = 0 | **brak pomiaru**, nie wynik — gracz nie grał w tym oknie; powtórzyć |

Potem, w tej kolejności: **przepisać `fix_lista`** z pseudokodu
(`tools/dekompiluj.sh 0x1419E7B40`) i dopiero wtedy `ServerTravel` (hipoteza 29,
trop: gniazdo `+0x440` w tablicy metod `UWorld`).

---

## Stan wdrożenia

Biblioteka **wdrożona**, `md5=cff407728ca95ad1c16dd365d029680a` — zgodna
z `src/proxy-dll/build/xinput1_3.dll`. Zgodność ze źródłem sprawdzać
**napisami**, nie sumą (build niepowtarzalny — mingw wpisuje czas w nagłówek PE).
Ta wersja ma napisy `SMYCZ:` i `WEJSCIE:`.

**Markery hosta (compat1):** `always_listen`, `auto_host`, `fix_attrs`,
`fix_booster`, `fix_dup`, `fix_input`, `late_restart`, `log_objecie`, `map`,
`no_pause`, `swap_now`, `swap_only`, `watch_pc`.

**Markery klienta (compat2):** `fix_attrs`, `fix_dup`, `fix_effects`,
`fix_smycz`, `fix_weapon`, `join_delay` (= 60 s), `join_ip` (= 127.0.0.1),
`log_objecie`.

**ZDJĘTE świadomie:**

- `fix_wejscie` — kod został w bibliotece, ale marker jest zdjęty: wywołania
  działały i nic nie dały (hipoteza 35, obalona);
- `fix_lista`, `fix_ekwipunek` — **zamrażały hosta przy dołączaniu**, do
  przepisania;
- `fix_state`, `fix_ammo` — wywalały hosta;
- `fix_przejscia`, `fix_czas` oraz diagnostyka tamtej linii (`log_tryb`,
  `log_kanal`, `log_speed`, `log_ammo`, `log_owner`, `log_fill`, `count_move`).

**Opóźnienie dołączenia klienta: `WFCoop_join_delay.txt` = 60 s.** Gracz
poprosił 12.08, żeby nie dawać więcej. Wartość czyta się przy starcie klienta.

---

## Jak to uruchomić

Host wchodzi normalnie — CONTINUE, potem hub. DLL zamienia w `UEngine::LoadMap`
skok `je` na dwa `NOP`-y (`0x143BEC200`), przez co gra **sama** woła
`UWorld::Listen` przy każdym ładowaniu mapy — także w hubie.

```
tools/stop.sh
WF_GAMESCOPE=1 WF_W=1100 WF_H=620 WF_PREFIX=~/.local/share/witchfire-mp/compat1 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
# gracz klika CONTINUE i zostaje w hubie
WF_GAMESCOPE=1 WF_PREFIX=~/.local/share/witchfire-mp/compat2 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
# klient dołącza sam po 60 s
```

**Zawsze z `WF_GAMESCOPE=1`.** Bez tego gra pauzuje się przy utracie fokusu,
a to psuje drugą instancję trwale — pomiar bez kompozytora mierzy inne zjawisko.

Przebudowa i wdrożenie: `tools/wdroz-dll.sh` (gry muszą być zamknięte).

---

## Narzędzia (`tools/`)

**Bez uruchomionej gry:** `dekompiluj.sh <adres>` (**pseudokod C**, Ghidra na
zrzucie obrazu — do LOGIKI i do kodu spoza świata `UObject`), `obraz.py`
(deasemblacja, odwołania, literały), `pole.py` (kto czyta/zapisuje pole),
`wpisy.py` (gdzie leży wskaźnik na napis — tablice UHT), `warunki.py`,
`przejscia.py`, `szukaj.py`.

**Na żywej grze:** `stan-gracza.py`, `ue-props.py` (**stąd offsety pól, których
nie ma w zrzucie**), `ue-objects.py`, `ue-funcs.py --sygnatury` (**tak potwierdza
się sygnaturę przed wołaniem**), `sonda-wejscia.py` (czy wejście dochodzi —
`ControlRotation`), `wejscie-stan.py` (wyłączniki wejścia bez odbicia),
`zrzut-wejscia.py` (zrzut przed/po zdarzeniu), `sygnatura.py`,
`read-crash-xml.py`, `stos-watku.py`, `zrzut.sh`.

**Nagrywanie:** `obserwator.sh` (sam wykrywa uruchomienie gry i zapisuje sesję),
`rejestrator.py` (szereg czasowy obu graczy), `czuwak.sh`.

**Wejście i okna:** `wejscie.py` (`/dev/uinput` — **działa**, ale gra pod
gamescope go nie przyjmuje), `kursor.py` (ustawia kursor; `hyprctl movecursor`
w tej konfiguracji NIE działa), `kto-ma-wejscie.py` (kto dostaje wejście, sam
odczyt).

**Publikacja:** `sync-public.sh` — jedyna droga do publicznego repo; tłumaczy
nazwy plików na angielskie i przepisuje odsyłacze.

---

## Czego NIE powtarzać (drogo kupione 11–12.08)

| co | dlaczego |
|---|---|
| **kolejne warianty `SetInputMode`** | wywołanie DZIAŁA (przechwyt myszy `2→1`) i nie przywraca wejścia: fokus jest tylko ODKŁADANY do `FReply`, a silnik realizuje go przy zdarzeniu wejścia, którego nie ma |
| **`fix_lista` + `fix_ekwipunek` w obecnej postaci** | zamrażały hosta przy dołączaniu; przepisać z pseudokodu, nie z asemblera |
| **`fix_state`, `fix_ammo`** | wywalały hosta — wołanie kodu gry drogą, której gra sama nie używa |
| podawanie wejścia z zewnątrz przez gamescope | **nie da się**; kursor gry nie idzie za pozycją systemową, a kliknięcia nie docierają. Menu klika gracz |
| testy bez gamescope | gra pauzuje się przy utracie fokusu i psuje klienta — pomiar jest bezwartościowy |
| pomiar po PONOWNYM dołączeniu | host ma wtedy zaparkowany wątek gry; sprawdź tiki, zanim cokolwiek odczytasz |
| pułapka sprzętowa w trakcie dołączania | łamie sekwencję otwierania kanałów; wolno tylko hak w procesie |

---

## Co jest zrobione

| | dowód |
|---|---|
| obaj gracze w jednym świecie, broń klienta działa | ponad dwie godziny wspólnej gry 11.08 |
| **klient przeżywa dołączenie w hubie** (`fix_smycz`) | 12.08: `SMYCZ: 1` w 5 s po travelu, połączenie 453 s, objęcie pionka pełne |
| host bez duplikatu ekwipunku (`fix_dup`) | gracz: „host działa jak na singleplayer" |
| mapa atrybutów ruchu klienta (`fix_attrs`) | `przed=0.000 po=355.000` |
| host nasłuchuje **także w hubie** | żywy `IpNetDriver` przy hoście w hubie |
| ściany #1 (`0x24`) i #2 (`0x430`) | próby kontrolne: bez strażnika awaria wraca |
| dekompilator w warsztacie | `tools/dekompiluj.sh`, cztery ustalenia w pierwszej godzinie |

---

## ZWROT 12.08 — dlaczego celem jest hub, nie wyprawa

Dotychczasowy przepływ (host wchodzi SAM na wyprawę, klient dołącza do TRWAJĄCEJ
misji) to najtrudniejszy przypadek sieciowy w Unrealu, wybrany przypadkiem.
Właściwy jest odwrotny: obaj spotykają się w hubie, a `ServerTravel` przenosi ich
razem. Menu główne jest na tej samej mapie co hub, więc to stamtąd startuje
wszystko.

**Kamień milowy M1′: sesja żyje w hubie i przeżywa podróż tam i z powrotem.**
Pierwsza połowa jest zrobiona (klient dołącza i przeżywa). Zostaje wejście
klienta i wspólna podróż.

**Droga alternatywna** („dwie symulacje i duch", bez silnika sieciowego UE) jest
rozpisana w `PROMPT-DUCH.md`. Gracz 12.08 zdecydował: **zostajemy przy obecnej**,
bo tylko ona prowadzi do wspólnych przeciwników i łupu.
