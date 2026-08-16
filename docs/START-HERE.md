# Zacznij tutaj — stan i następny krok

Stan na **2026-08-16**, po sesji wieczornej. Repo czyste i wypchnięte.
**Gry mogą jeszcze chodzić** — sprawdź `tools/find-instance.sh compat1`
i `compat2`, zanim cokolwiek wdrożysz (`wdroz-dll.sh` wymaga zamkniętych).

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
żadnego wejścia** — ani WSAD, ani myszy, ani Esc. Gracz 16.08: „klient nie może
robić absolutnie nic". Nie zawężać tego do kamery: obie drogi wejścia są martwe
naraz, więc przyczyna jest w ich części WSPÓLNEJ. Zmierzone: kierunek patrzenia
klienta stoi (0 zmian na 1499 próbek), gdy host w tym samym oknie ma 121 zmian.
Przed dołączeniem to samo okno przyjmuje wejście bez zarzutu (250 próbek gry
gracza, sprint 800, unik 1502) — więc psuje je dopiero dołączenie.

**16.08 zawężone dwoma przebiegami do jednego wywołania.** Wejście u klienta
przechodzi CAŁĄ drogę i ginie dopiero w kontrolerze postaci:

| piętro | klient | host (wzorzec) |
|---|---|---|
| komunikaty Win32 | 504 klawisze | 457 |
| wspólny filtr gry `0x141A020B0` | 1595 | 5910 |
| wejścia do `UGameViewportClient::InputKey` | 417 | 328 |
| dojścia do **`PlayerController::InputKey`** | **417 — 100%** | **328 — 100%** |
| reakcja gracza w grze | **żadna** | normalna gra |

Oba przebiegi miały wzorową przeciwfazę (aktywny dokładnie jeden proces,
drugi na czystym zerze) i potwierdzenie gracza w tym samym oknie czasu.
**Strata jest WEWNĄTRZ `PlayerController::InputKey` (vtable `+0xC18`) albo
poniżej** — `KNOWLEDGE.md` §3j i §3l.

**Dwa problemy poboczne, oba zmierzone:** host pada po ~50 min na wiszącym
słuchaczu (ściana #3), a przy PONOWNYM dołączeniu klienta parkuje wątek gry
(`futex_wait`, 0 tików/3 s). Dekompilacja pokazała, że pętla rozgłaszania trzyma
zamek przez cały przebieg listy — więc oba objawy to prawdopodobnie jedno
zdarzenie.

---

## PRZYCZYNA ZNALEZIONA (17.08) — i co z nią zrobić

**Gra gasi globalne wejście na czas ładowania mapy i sama je przywraca. Host
robi jedno i drugie, klient tylko pierwsze.**

| | host | klient |
|---|---|---|
| wyłączenie | 00:19:37 | 00:20:54 |
| **włączenie** | **00:19:52** | **nigdy** |
| `GameInstance+0x2A0` na koniec | **1** | **0** |

To tłumaczy objaw w całości i spina wszystkie wcześniejsze ustalenia w jeden
łańcuch — szczegóły i dowody w `KNOWLEDGE.md` §3x.

**NASTĘPNY KROK (hipoteza 43):** wywołać u klienta
`DimensionGameInstance:SetGlobalInputEnabled(true)` po dołączeniu. To
`Native, BlueprintCallable`, czyli droga, której gra sama używa (zasada 1).
**Nie zapisem bajta** — sprawdzone, surowy zapis nie odtwarza powiadomień
i nie odblokowuje ruchu (§3w).

Potwierdzenie będzie tanie: liczniki ruchu są **klatkowe**, więc ruszą same,
bez naciskania czegokolwiek. Marker `fix_globalne`, licznik wywołań,
potwierdzenie przez ZDJĘCIE markera (zasada 9).

---

## Poprzedni krok (zrobiony) — globalna flaga wejścia (hipoteza 42)

**Zmierzone:** `GameInstance + 0x2A0` (`GlobalInputEnabled`) to **1 u hosta
i 0 u klienta**. Flaga jest globalna dla instancji gry, więc gasi wejście
w całej grze naraz — klawisze, mysz i Esc — i jako jedyna dotąd ma zasięg
zgodny z objawem (`KNOWLEDGE.md` §3w).

**Przepis:**

1. Hak logujący na setterze **`0x1418953E0`** (`SetGlobalInputEnabled`),
   z wartością i licznikiem, po OBU stronach. Ma pokazać, **kiedy** flaga
   spada u klienta i czy u hosta spada i wraca przy ładowaniu mapy.
2. Dopiero mając to — próba wywołania `SetGlobalInputEnabled(true)` na
   kliencie. To `BlueprintCallable`, czyli droga, której gra sama używa
   (zasada 1 spełniona). **Nie zapisem bajta**: flaga ma łańcuch powiadomień
   (`OnGlobalInputEnabledValueChanged` osobno na postaci i na broni), więc
   surowy zapis niczego nie odtwarza — sprawdzone.

**Adresy gotowe:** getter `0x1418785C0` (`movzx eax,[rcx+0x2a0]; ret`),
przejściówki UFunction `0x141BED210` / `0x141BEEAC0`.

---

## Trop poboczny — stos wejścia kontrolera (hipoteza 41)

**Zmierzone 16.08:** u klienta funkcja obsługi ruchu `0x14187DFC0` nie jest
wołana **ani razu**, gdy u hosta bije ~200 razy na sekundę — obie instancje
w świecie, w tych samych sekundach (`KNOWLEDGE.md` §3t). Wiązanie nie dispatchuje
w ogóle, a samych wiązań w `UInputComponent` klienta jest tyle samo co u hosta
(12 z 24). Brakuje więc kroku, który wstawia komponent na **stos wejścia**
kontrolera.

**Przepis:**

1. Znaleźć funkcję budującą stos (`CurrentInputStack`). **Odczyt z zewnątrz
   NIE rozstrzygnie** — stos jest budowany i czyszczony w tej samej klatce,
   więc z zewnątrz zawsze widać go pustym, także u zdrowego hosta.
2. Licznik wstawień na stos, po OBU stronach. Host ≥1 na klatkę, klient zero
   domyka sprawę.
3. Dopiero potem szukać warunku, który u klienta pomija wstawienie.

**Punkt wyjścia do szukania:** `0x1418C7810` (`PlayerController::InputKey`)
przechodzi po tablicy `PC+0x5b8`/`+0x5c0` — u obu stron pustej — więc to nie
ta. Szukać w ścieżce tickowania kontrolera, nie w obsłudze zdarzeń.

---

## Poprzedni krok (zrobiony) — `PlayerController::InputKey` (hipoteza 38)

Hipotezy 36 i 37 są **obalone**, obie pomiarem z próbą kontrolną. Zostało
jedno wywołanie, w którym wejście u klienta jeszcze jest, a po którym już go
nie widać w grze.

Droga jest już prześledzona do końca i **siedem ogniw jest zmierzonych jako
zdrowe** — pełna tabela w `KNOWLEDGE.md` §3m. Zostało jedno ogniwo.

**Przepis:**

1. **`tools/dekompiluj.sh 0x141A01390`** — `UPlayerInput::InputKey`, gniazdo
   `+0x278` w tablicy metod `0x1450A3470`. Bez uruchamiania gry. Dopiero jego
   pseudokod powie, co porównywać.
2. Klient i host wykonują tu **ten sam kod** (ta sama tablica metod, to samo
   gniazdo), więc różnica jest w DANYCH — szukać w tablicy wiązań i w stanie
   klawiszy, a nie w kolejnym wyłączniku.
3. Liczniki dopiero po dekompilacji, i zawsze z wzorcem u hosta (zasada 11).

**Gdzie NIE szukać.** Refleksja jest tu ślepa i już to sprawdzono: `PlayerInput`
klienta i hosta mają **zero różnic** we wszystkich właściwościach, `InputComponent`
też, kontroler ma pionka i jeden jest tylko jeden. Różnica siedzi w stanie
nieodbijanym — tablicach wiązań `UInputComponent` i stanie klawiszy
`UPlayerInput` (`KNOWLEDGE.md` §3o).

**Hipoteza 39 (oś myszy) jest POTWIERDZENIEM, nie skrótem.** U klienta nie
działa NIC — ani klawisze, ani mysz, ani Esc — a obie drogi rozchodzą się
dopiero na rozdzielaczach, więc przyczyna jest w części wspólnej.

**Gotowe do użycia:** marker `log_rozdzielacz` i `tools/wejscie-liczniki.py`
(przyrosty na sekundę, obie strony w jednym szeregu, cięcie po wyzerowaniu
licznika przy restarcie). Odnosić `wejsc` do `klaw`, **nigdy do `gra`**.

Dwa tanie kroki, które nie wymagają przebudowy biblioteki:

* **hipoteza 32** — przebieg z włączonym **tylko** `fix_lista` (bez
  `fix_ekwipunek`). Próba kontrolna h.28 zdjęła oba naraz i nigdy nie
  rozstrzygnęła, który zamrażał hosta; kod `fix_lista` przeszedł audyt
  (`KNOWLEDGE.md` §3k);
* **hipoteza 31b** — przebieg ze zdjętym `fix_smycz`; awaria ma wrócić.

Potem `ServerTravel` (hipoteza 29, trop: gniazdo `+0x440` w tablicy metod
`UWorld`).

---

## Stan wdrożenia

**UWAGA: w grze stoi STARSZA biblioteka niż w repo.** Wdrożone jest
`md5=834ba5e2e6312a790a2cffbb1913d4e2` (napisy `WEJSCIE-LICZNIK:` i
`ROZDZIELACZ:`). W `src/proxy-dll/build/` leży nowsza, z licznikami wiązania
ruchu (`RUCH-WIAZANIE:`, marker `log_ruch`) — **niewdrożona**, bo wdrożenie
wymaga zamknięcia gier, a te chodziły. Pierwszy krok następnej sesji:
`tools/wdroz-dll.sh` i marker `log_ruch` po obu stronach. Zgodność ze źródłem sprawdzać
**napisami**, nie sumą (build niepowtarzalny — mingw wpisuje czas w nagłówek PE).
Ta wersja ma napisy `SMYCZ:`, `WEJSCIE:`, `WEJSCIE-LICZNIK:` **i `ROZDZIELACZ:`**.

**Markery hosta (compat1):** `always_listen`, `auto_host`, `fix_attrs`,
`fix_booster`, `fix_dup`, `fix_input`, `late_restart`, `log_objecie`,
**`log_rozdzielacz`**, **`log_wejscie`**, `map`, `no_pause`, `swap_now`,
`swap_only`, `watch_pc`.

**Markery klienta (compat2):** `fix_attrs`, `fix_dup`, `fix_effects`,
`fix_smycz`, `fix_weapon`, `join_delay` (= 60 s), `join_ip` (= 127.0.0.1),
`log_objecie`, **`log_rozdzielacz`**, **`log_wejscie`**.

`log_wejscie` zostaje włączony: kosztuje jedną linię logu na sekundę, a daje
bazę spoczynkową, bez której żaden następny pomiar wejścia nie da się odczytać.

**ZDJĘTE świadomie:**

- `fix_wejscie` — kod został w bibliotece, ale marker jest zdjęty: wywołania
  działały i nic nie dały (hipoteza 35, obalona);
- `fix_lista`, `fix_ekwipunek` — zdjęte razem, bo **razem** zamrażały hosta
  przy dołączaniu; który z nich to robił, **nie wiadomo** — próba kontrolna
  zdjęła oba naraz, a `fix_lista` przeszedł audyt bajt po bajcie
  (`KNOWLEDGE.md` §3k). Rozstrzyga przebieg z samym `fix_lista`;
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

**Odczyt pomiaru wejścia:** `wejscie-liczniki.py` — zamienia linie
`WEJSCIE-LICZNIK:` z obu logów w przyrosty na sekundę, zestawia host i klienta
w jednym szeregu i sam wykrywa bazę spoczynkową (`--szereg`, `--od`, `--do`).

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
| **uruchamianie obu gier naraz** | gracz traci mysz — kursor ucieka między oknami zamiast zostać w tym, w którym gra. Klienta uruchamiać DOPIERO, gdy host jest w hubie |
| **porównywanie nazwy klasy DOKŁADNIE** | żywe obiekty bywają blueprintowymi PODKLASAMI: instancja gry to `BPDimensionGameInstance_C`, nie `DimensionGameInstance`. Dokładne porównanie trafia wtedy tylko we wzorzec klasy (`Default__`), który i tak się pomija — i łatka cicho nie robi nic. Dopasowywać po fragmencie nazwy |
| **czujnik czytający ogon `WFCoopProxy.log`** | log jest dopisywany MIĘDZY SESJAMI, więc ogon zawiera wpisy z poprzedniego przebiegu. 16.08 taki czujnik odpalił klienta w tej samej sekundzie co hosta. Liczyć linie przy uzbrajaniu i patrzeć tylko na nowsze |
| pułapka sprzętowa w trakcie dołączania | łamie sekwencję otwierania kanałów; wolno tylko hak w procesie |
| **kolejne liczniki na `0x141A020B0`** | zmierzone i zamknięte: zdarzenia DOCIERAJĄ. To test progu, nie rozdzielacz |
| **strażnik NULLA w pętli rozgłaszania** | gra ma tam własny; awaria to zwisający słuchacz (`rax=2`), nie null |
| wnioski z pomiaru, w którym host też ma zero | to brak pomiaru. 16.08 sonda `ControlRotation` dała 0/0 przez 90 s, bo gracz akurat nie grał |

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
| **zdarzenia wejścia docierają do klienta** (16.08) | dwa piętra liczników; klient `gra`≈2950 w oknie, w którym host ma 0; gracz potwierdził brak reakcji |
| **wejście klienta dochodzi do `PlayerController::InputKey`** | 417 wejść do rozdzielacza, 417 dojść — 100%, jak u hosta |
| **mapa rozdzielacza wejścia** `0x143820F10` | wszystkie ciche wyjścia powyżej `PC::InputKey` wykluczone pomiarem |

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
