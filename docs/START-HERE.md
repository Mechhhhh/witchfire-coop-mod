# Zacznij tutaj — stan i następny krok

Stan na **2026-08-17**, po sesji nocnej. Repo czyste i wypchnięte, gry
zamknięte. Przed wdrożeniem i tak sprawdź `tools/find-instance.sh compat1`
i `compat2` — `wdroz-dll.sh` wymaga zamkniętych.

## Co czytać

**Ten plik, potem `JOURNAL.md`. Nic więcej na starcie.**

`KNOWLEDGE.md` (~3400 linii) to zapis, JAK doszliśmy do wniosków — nie czytaj go
w całości. Wyszukuj punktowo:

```
tools/szukaj.py 0x1418002E0        # co wiemy o adresie
tools/szukaj.py "mapa atrybutow"   # z nagłówkiem sekcji
```

Nagłówek sekcji w wynikach mówi, czy trafienie pochodzi z ustalenia
POTWIERDZONEGO, czy z OBALONEGO. **Zanim ruszysz z hipotezą — wyszukaj ją.**

**LINIA RODOWODU — obowiązuje TAKŻE dla obserwacji gracza.** Każda nowa sekcja
w `KNOWLEDGE.md` otwiera się jedną linią: albo „pierwszy zapis: `<plik:linia>`
(`<data>`)", albo „szukane: «`<fraza>`» — brak trafień, zapis pierwszy".

Powód jest konkretny, nie kosmetyczny. 17.08 zapisano jako nowe zjawisko
opisane już 09.08 i **potwierdzone pomiarem 12.08** (§3y), bo reguła wyżej
mówiła o *hipotezach*, a to była *obserwacja gracza* — czyli dokładnie ta
klasa, w której gracz powtarza się najczęściej. `tools/szukaj.py menu`
znajdowało zapis w 45 ms; wyszukiwania po prostu nie uruchomiono.

**Szukać SŁOWEM GRACZA** („menu główne"), nie naszym („WYPADA DO MENU").
Sekcja bez linii rodowodu jest widoczna na pierwszy rzut oka, a napisanie
„brak trafień" bez uruchomienia narzędzia to już świadomy fałsz, nie
przeoczenie.

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

## PRZYCZYNA — DWIE, jedna już załatana (17.08)

**Przyczyna nr 1, ZAŁATANA.** Gra gasi globalne wejście na czas ładowania mapy
i sama je przywraca. Host robi jedno i drugie, klient **tylko pierwsze**:

| | host | klient |
|---|---|---|
| wyłączenie | 00:19:37 | 00:20:54 |
| **włączenie** | **00:19:52** | **nigdy** |

Łatka `fix_globalne` (marker u klienta, wdrożona) woła
`DimensionGameInstance:SetGlobalInputEnabled` — `Native, BlueprintCallable`,
czyli drogą, której gra sama używa. Musi **PRZEŁĄCZAĆ** (false→true), bo setter
rozgłasza powiadomienie wyłącznie przy zmianie (`cmp al,dl; je`), a pionek
powstały po travelu zastaje flagę już zapaloną i nic do niego nie dochodzi.

**Działa i to jest zmierzone:** przed dołączeniem, po przełączeniu, pionek
przyjmuje powiadomienie (`GameplayEnabled=1`), a licznik wiązania ruchu **rusza
z zera** do pełnej klatki. `KNOWLEDGE.md` §3x.

**Przyczyna nr 2, NIEZNANA — i to jest następny krok.** Po travelu do hosta
licznik zamiera mimo `flaga=1`, a podstawienie `GameplayEnabled=1` też nie
pomaga. Czyli po dołączeniu wiązanie nie odpala z powodu, który **nie ma nic
wspólnego z żadną z tych flag**. `KNOWLEDGE.md` §3z.

Adresy do tej linii: getter `0x1418785C0` (`movzx eax,[rcx+0x2a0]; ret`),
setter `0x1418953E0`, przejściówki UFunction `0x141BED210` / `0x141BEEAC0`.

---

## NASTĘPNY KROK — warunek wstawiania komponentu na stos (hipoteza 44)

**Hipoteza 41 POTWIERDZONA 17.08** i to zawęża pytanie do jednego zdania.
Cztery komponenty wejścia, obie instancje w tym samym świecie:

| | wiązań | `CachedKeyToActionInfo` |
|---|---|---|
| HOST kontroler | 12/24 | 1/4 |
| HOST pionek | 59/102 | 1/4 |
| KLIENT kontroler | 12/24 | 1/4 |
| **KLIENT pionek** | **48/56** | **0/0** |

Ta mapa powstaje dopiero przy przetwarzaniu komponentu. Trzy z czterech ją
mają. Komponent KONTROLERA klienta ją **ma** — więc przetwarzanie wejścia
u klienta żyje; pomijany jest ten jeden komponent (`KNOWLEDGE.md` §3ź).

**Pytanie brzmi teraz: dlaczego jest pomijany.** Wszystkie pola pionka, które
o tym decydują i które widzi refleksja — `bBlockInput`, `AutoReceiveInput`,
`InputPriority`, `InputComponent`, `Controller`, `Owner` — są po obu stronach
**identyczne**. Warunku trzeba więc szukać w kodzie, nie w danych: znaleźć
miejsce wstawiania komponentu pionka na stos i policzyć obie gałęzie po obu
stronach.

**Nienazwany trop na potem:** `pionek + 0x5B` bit `0x10` — zapalony u klienta,
zgaszony u hosta, stabilny w dwóch przebiegach, **nieodbijany** (bool-e, które
refleksja tam nazywa, są po obu stronach takie same).

---

## Poprzedni krok (zrobiony) — komponent wejścia PIONKA (hipoteza 41)

**Uwaga na podmiot, bo to już raz pomyliło:** chodzi o komponent wejścia
**PIONKA**, nie kontrolera. Komponent KONTROLERA jest u klienta **identyczny**
z hostem (12 wiązań z 24, §3o) — i to właśnie ta liczba trafiła wcześniej
w tekst jako argument, że „wiązań jest tyle samo". Komponent PIONKA wygląda
inaczej:

| | host | klient |
|---|---|---|
| wiązania (`+0x110`) | **59** | **48** |
| `CachedKeyToActionInfo` | jest | **brak** |
| dwie dalsze tablice | są | **brak** |

**Przepis:**

1. **Najpierw potwierdzić same liczby 48/59.** Mają dziś jedno źródło i brak
   surowego odczytu w repo — a cała hipoteza na nich stoi.
2. Porównać **ZAWARTOŚĆ** wiązań host↔klient, nie liczbę pozycji. W tym
   projekcie „10 zdolności kontra 8" czytano pół dnia jako brak u klienta,
   a po wypisaniu NAZW okazało się, że host ma dwa duplikaty.
3. Jeśli brakuje wiązań osi — sprawdzić, czy `SetupPlayerInputComponent`
   w ogóle przebiega na replikowanym pionku klienta.

**Czego NIE robić:** nie szukać stosu wejścia odczytem z zewnątrz. Stos jest
budowany i czyszczony w tej samej klatce, więc z zewnątrz zawsze wygląda na
pusty — także u zdrowego hosta. To sprawdzone.

---

## Wcześniejsze kroki, wszystkie zrobione

Hipotezy **36, 37, 38, 40, 42, 43** są zamknięte — pełne werdykty w tabelach
`JOURNAL.md`, dowody w `KNOWLEDGE.md` §3j–§3z. W skrócie: wejście przechodzi całą
drogę dostarczania (Win32 → filtr gry → rozdzielacz widoku →
`PlayerController::InputKey`, 100% dojść po obu stronach), jest zapisywane
i konsumowane — a mimo to wiązanie ruchu u klienta nie odpala ani razu.

**Gdzie NIE szukać — sprawdzone i kosztowne.** Refleksja jest tu ślepa:
`PlayerInput` klienta i hosta mają **zero różnic** we wszystkich właściwościach,
`UInputComponent` kontrolera też, kontroler ma pionka i jest tylko jeden.
Różnica siedzi w stanie nieodbijanym — zwykłych tablicach C++, nie `UPROPERTY`
(`KNOWLEDGE.md` §3o).

---

## Stan wdrożenia

Biblioteka **wdrożona 17.08 00:36**, `md5=842efaa560946a91bdd4d91804eb7fbf` —
**zgodna** z `src/proxy-dll/build/xinput1_3.dll` (sprawdzone `md5sum` obu
plików). Zgodność ze źródłem sprawdzać **napisami**, nie sumą (build
niepowtarzalny — mingw wpisuje czas w nagłówek PE). Ta wersja ma napisy
`SMYCZ:`, `WEJSCIE:`, `WEJSCIE-LICZNIK:`, `ROZDZIELACZ:`, `RUCH-WIAZANIE:`,
`GLOBALNE:` **i `GLOBALNE-FIX:`**.

> Ten akapit rozjeżdżał się już dwa razy, bo `wdroz-dll.sh` wypisuje sumę,
> a nikt jej tu nie przepisywał. Po każdej przebudowie **poprawić go razem
> z wdrożeniem**, nie później.

**Markery hosta (compat1)** — odczytane z dysku 17.08: `always_listen`,
`auto_host`, `fix_attrs`, `fix_booster`, `fix_dup`, `fix_input`,
`late_restart`, `log_globalne`, `log_objecie`, `log_rozdzielacz`, `log_ruch`,
`log_wejscie`, `map`, `no_pause`, `swap_now`, `swap_only`, `watch_pc`.

**Markery klienta (compat2)** — odczytane z dysku 17.08: `fix_attrs`,
`fix_dup`, `fix_effects`, **`fix_globalne`**, `fix_smycz`, `fix_weapon`,
`join_delay` (= 60 s), `join_ip` (= 127.0.0.1), `log_globalne`, `log_objecie`,
`log_rozdzielacz`, `log_ruch`, `log_wejscie`.

**`fix_globalne` jest UZBROJONY i tylko u klienta** — to jedyna czynna łatka
z 17.08. U hosta go nie ma celowo: tam flaga i tak jest zapalona, więc host
pełni rolę próby kontrolnej. Sprawdzać to poleceniem, nie pamięcią:

```
ls ~/.local/share/witchfire-mp/compat{1,2}/pfx/drive_c/users/steamuser/AppData/Local/Witchfire/Saved/WFCoop_*.txt
```

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
| **zapisywanie obserwacji gracza bez wyszukania** | 17.08 zapisano jako nowe zjawisko znane od 09.08 i zmierzone 12.08. Patrz „linia rodowodu" na górze pliku |
| podstawianie bajta flagi, która ma łańcuch powiadomień | nierozstrzygające z zasady — zapis nie odtwarza powiadomień. Używać własnego settera flagi |
| `strcmp` na nazwie klasy żywego obiektu | żywe obiekty bywają blueprintowymi PODKLASAMI (`BPDimensionGameInstance_C`); dokładne porównanie trafia tylko we wzorzec klasy i łatka cicho milczy |
| liczenie `wejscieA`/`wejscieB` jako miary wejścia | te liczniki są KLATKOWE (~200/s bez żadnego wejścia). Rozstrzyga `za-progiem` |
| szukanie stosu wejścia odczytem z zewnątrz | budowany i czyszczony w tej samej klatce — zawsze wygląda na pusty, także u zdrowego hosta |

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
