# Dziennik roboczy — bieżąca sesja

Jeden plik na to, **nad czym się teraz pracuje**. Historia jest w `RUNS.md`,
wiedza w `KNOWLEDGE.md`, przegląd wszerz w `OVERVIEW.md`.

Zasada: **hipoteza → przewidywanie → pomiar → werdykt**, każda w jednej linii.
Gdy hipoteza jest zamknięta, przenieść ją do `KNOWLEDGE.md` i **usunąć stąd**.

Ten plik ma zostać krótki.

---

## W toku

| # | hipoteza | przewidywanie | pomiar — NASTĘPNY KROK | werdykt |
|---|---|---|---|---|
| 41 | **komponent wejścia klienta nie trafia na stos wejścia kontrolera** — wiązanie nie jest wołane ANI RAZU (§3t), a samych wiązań jest tyle samo co u hosta (12/24), więc brakuje kroku, który wstawia komponent na stos | licznik pozycji trafiających na stos pokaże u hosta ≥1 na klatkę, a u klienta zero | znaleźć funkcję budującą `CurrentInputStack` (stos jest czyszczony w tej samej klatce, więc odczyt z zewnątrz NIE rozstrzygnie — potrzebny hak) i policzyć wstawienia po obu stronach | — |
| ~~40~~ | ~~wiązanie ruchu u klienta nie odpala albo jego skutek jest odrzucany~~ — przetwarzanie wiązań CHODZI (§3p), więc pytanie zeszło o poziom niżej, do samego wiązania | licznik na funkcji stemplującej znacznik wejścia ruchu (`pionek+0xC74`) pokaże u hosta stemple, a u klienta zero — albo odwrotnie, i wtedy strata jest za znacznikiem | znaleźć zapis do `pionek+0xC74` (`tools/pole.py 0xC74 --zapis --funkcje`) i postawić tam licznik po OBU stronach | — |
| 38 | ~~wejście ginie w `UPlayerInput::InputKey`~~ — **zawężone przez 3p**: zapis i konsumpcja stanu klawiszy są identyczne — siedem ogniw wyżej zmierzonych i zdrowych (`KNOWLEDGE.md` §3m); niezmierzone zostały tylko tablica `PC+0x5b8`/`+0x5c0` (wiersz 5a) i sam `PlayerInput` jako GAŁĄŹ (6a to odczyt statyczny spoza okna) | klient i host mają tam tę samą tablicę metod `0x1450A3470`, więc wykonują ten sam kod — różnica jest w DANYCH | **najpierw dekompilacja `0x141A01390`, bez gry**, i wypisanie jej wczesnych wyjść, zanim wybierze się gniazda. Przy okazji licznik gałęzi `PlayerInput != 0` na `0x143A64920`, żeby domknąć 6a | — |
| 39 | oś myszy ginie w tym samym miejscu co klawisze — **potwierdzenie 38, nie osobna usterka** | licznik na rozdzielaczu osi pokaże u klienta 100% dojścia do kontrolera, tak jak dla klawiszy | znaleźć `UGameViewportClient::InputAxis` (wołany z `0x141A00FD0`, tak jak `InputKey` z `0x141A01190`) i powtórzyć na nim parę liczników | — |
| 32 | **awaria hosta na wiszącym słuchaczu i park wątku gry to JEDNO zjawisko** — pętla rozgłaszania trzyma zamek (`+0x360`) przez cały przebieg listy, więc awaria w środku zostawia zamek wzięty i reszta gry staje na `futex_wait` | jeśli tak, poprawny strażnik przed wywołaniem usuwa oba objawy naraz | **zmiana planu 16.08:** przepisywać nie ma czego — pseudokod potwierdził mechanizm zamka, a audyt bajt po bajcie pokazał, że kodowanie `fix_lista` jest **poprawne** (`KNOWLEDGE.md` §3k). Próba kontrolna h.28 zdjęła `fix_lista` i `fix_ekwipunek` **naraz**, więc nie wiadomo, który zamrażał. Przebieg z włączonym **tylko** `fix_lista` — sam marker, bez przebudowy | zamek POTWIERDZONY pseudokodem; park POTWIERDZONY pomiarem (0 tików/3 s, `futex_wait`) |
| 29 | wyprawy nie da się przejść razem, bo powrót do hubu nie jest podróżą sesji | po zamianie lokalnego ładowania mapy na `ServerTravel` obaj gracze przenoszą się razem, a skrypty misji ruszają po stronie serwera | **trop znaleziony:** komenda `SERVERTRAVEL` idzie przez gniazdo **`+0x440`** w tablicy metod `UWorld`. Na żywym hoście odczytać ten wpis i zdekompilować — dopiero potem projektować łatkę | — |
| 30 | magazynek klienta, niesterowana maszyna stanów i brak potwierdzenia objęcia są **skutkami** 29, a nie osobnymi usterkami | po naprawie startu misji część z nich znika bez osobnej łatki | mierzyć dopiero PO 36 i 29 | — |
| 31b | strażnik `fix_smycz` jest przyczyną przeżycia klienta, a nie zbiegiem okoliczności | po ZDJĘCIU markera awaria wraca z tym samym stosem (`SetLeashName`, `0x141B7DDAA`) | jeden przebieg z markerem zdjętym — tani, robić przy okazji innego | — |

**Kolejność: 41 → 39 → 32 → 29 → 30.** Gracz sprostował objaw: u klienta **nie
działa NIC** — ani klawisze, ani mysz, ani Esc (`KNOWLEDGE.md` §3o). Obie drogi
wejścia są więc martwe naraz, a rozchodzą się dopiero na rozdzielaczach — czyli
przyczyna leży w części WSPÓLNEJ. Dlatego 38 zostaje pierwsze, a 39 jest
potwierdzeniem, nie skrótem. 32 jest dalej, bo host pada po ~50 min i psuje każdy
dłuższy przebieg — a kosztuje teraz jeden marker, nie przebudowę. 29 to kamień
milowy, ale ma sens dopiero, gdy klient gra.

### Zamknięte 16.08 — NIE powtarzać

| co | werdykt |
|---|---|
| **hipoteza 40 — „wiązanie ruchu odpala z zerową wartością osi"** | **OBALONA 23:51.** U klienta funkcja `0x14187DFC0` nie jest wołana **ani razu** (0 przy ~200/s u hosta w tych samych sekundach, obie instancje w świecie). Wiązanie nie dispatchuje w ogóle. Szczegóły: `KNOWLEDGE.md` §3t |
| liczenie `wejscieA`/`wejscieB` jako miary wejścia | **bezwartościowe**: te liczniki są KLATKOWE (~200/s u hosta bez żadnego wejścia). Rozstrzyga `za-progiem`, a przy porównaniu host↔klient — sam fakt, że u klienta stoją na zerze |
| **hipoteza 37 — „wejście ginie w rozdzielaczu `0x143820F10`"** | **OBALONA 22:58.** U klienta **417 wejść, 417 dojść do `PlayerController::InputKey` — 100%**, dokładnie jak u hosta (328/328). Przeciwfaza wzorowa, a gracz w tym samym czasie potwierdził: „klient nie reaguje na żaden input". Rozdzielacz jest niewinny; szukać WEWNĄTRZ `+0xC18`. Szczegóły: `KNOWLEDGE.md` §3l |
| mierzenie rozdzielacza stosunkiem `wejsc/gra` | **bezwartościowe**: u zdrowego hosta 0,06, bo `0x143820F10` rozdziela klawisze, a `gra` liczy też każdy ruch osi i cztery wywołania z `0x141A3D200`. Odnosić do `klaw` |
| **hipoteza 36 — „do gry klienta nie docierają zdarzenia wejścia"** | **OBALONA 22:09 pomiarem na dwóch piętrach.** W oknie 22:09:17–41 klient zebrał `gra`≈2950, `klaw`=699, `mysz`=1415, `raw`=6690 przy **zerze u hosta w tej samej chwili**, a gracz w tym czasie potwierdził: „klient nie może nic, host gra normalnie". Warstwa dostarczania jest niewinna — szukać WEWNĄTRZ gry. Szczegóły i szereg czasowy: `KNOWLEDGE.md` §3j |
| **`0x141A020B0` jako „rozdzielacz zdarzeń"** | **KOREKTA:** to test progu (`return param_4 <= param_3`), nie rozdzielacz. Jako detektor zdarzeń jest dobry i ważny (baza spoczynkowa 54 s przy `+0`), ale nie mówi nic o dalszej drodze wejścia |
| pusta tablica odbiorców wejścia `widok+0x318` | **obalone**: **host ma ją tak samo pustą** i działa (zasada 11) |
| `LocalPlayer+0x30` puste albo stare u klienta po travelu | **obalone**: `0x690E9A00`, niezerowe i zgodne z kontrolerem, który widzi sonda; ta sama tablica metod co u hosta |
| „`fix_lista` ma błąd w kodowaniu trampoliny" | **obalone audytem bajt po bajcie** — cztery skoki lądują poprawnie, adresy powrotu i pominięcia się zgadzają, `r11` bezpieczny, żaden skok gry nie celuje w podmieniane 6 bajtów |
| dokładanie strażnika NULLA do pętli rozgłaszania | **bezcelowe**: gra **ma tam własny strażnik nulla**; awaria to `call [rax+0x10]` przy `rax=2`, czyli zwisający słuchacz — warunek dotyczy tablicy metod |

### Zamknięte 12.08 — NIE powtarzać

| co | werdykt |
|---|---|
| **hipoteza 31 — strażnik `fix_smycz` na `SetLeashName`** | **DZIAŁA.** `SMYCZ: 1` dokładnie 5 s po travelu, zero nowych zrzutów, połączenie **453 s** bez zerwania (stary punkt śmierci: 64 s), uścisk objęcia PEŁNY, klient ma kamerę i świat, host widzi jego pionka. Zostaje kontrola przez zdjęcie markera (31b) |
| **hipoteza 33 — „to okno nie potrafi przyjmować wejścia"** | **OBALONA 15:57:** przed dołączeniem gracz gra w tym samym oknie normalnie — 250 próbek ruchu, prędkości 600–800 i 1502 (unik), `HasMovementInput=1` w 232/250. Uwaga: to NIE obala twierdzenia „travel psuje dostarczanie wejścia do tego okna" (hipoteza 36) |
| **hipoteza 35 — travel z menu zostawia tryb wejścia UI** | **OBALONA 17:01 dwoma pomiarami.** (a) Gracz wszedł u klienta przez CONTINUE (tryb gry zmierzony: przechwyt myszy `3→2`) i po travelu i tak stracił wejście. (b) Łatka `fix_wejscie` wołała własną funkcję gry `SetInputModeGameOnly(bool)` **60 razy z wątku gry**; wywołanie DZIAŁAŁO (przechwyt myszy `2→1`), a wejścia dalej nie było. **Nie budować kolejnych wariantów `SetInputMode`** — dekompilacja tłumaczy czemu: fokus jest tylko ODKŁADANY do `FReply`, a silnik realizuje go przy przetworzeniu zdarzenia wejścia, którego nie ma |
| **hipoteza 28 — zamrożenie hosta przy dołączaniu to regresja `fix_lista`/`fix_ekwipunek`** | **POTWIERDZONA próbą kontrolną 14:39–14:49.** Bez obu markerów host NIE zamarł (zegar gry 1:1, GameThread 47–70 tik/s). Markery ZOSTAJĄ zdjęte, dopóki pętle nie będą przepisane (zasada 7) |
| „64 s timeout dołączenia = skutek zamrożenia hosta" | **SKORYGOWANE:** host był zdrowy, a rozłączenie i tak przyszło. Przyczyną była ŚMIERĆ KLIENTA 4 s po travelu; host tylko odliczał `ConnectionTimeout` po trupie |
| „czarny ekran klienta = czeka na objęcie pionka" | **SKORYGOWANE:** klient nie czekał — klient NIE ŻYŁ (GameThread martwy, `PULS` proxy dalej bił). Brak `AcknowledgePossession` był skutkiem awarii |
| **`fix_state`** | **WYWALAŁ HOSTA.** Gra woła swoje warunki **bezpośrednio**, bez `UFunction` i bez `ProcessEvent` — tą drogą chodzi wyłącznie nasz kod |
| kolejkowanie `IdleToWalking` w chwili prawdziwych warunków | **obalone**: 3600 prób, 0 udanych, przy potwierdzonym ruchu gracza |
| hipoteza 23 — pionek klienta trzymany w spadaniu | **obalona**: `MovementMode = 1` w 95% próbek |
| pauza hosta jako przyczyna zamrożenia klienta | **obalona przez gracza**: pauza szkodzi tylko wtedy, gdy pauzuje **klient** |

### Zamknięte 11.08 — NIE powtarzać

| co próbowano | werdykt |
|---|---|
| podanie akcji przez `ProcessExternalInputAction` (gniazdo 147) | **obalone**: akcje dochodzą (8/8), stan nie drgnął |
| to samo pełną ścieżką wejścia gry (gniazdo 150) | **obalone** mimo poprawnych bajtów i `InputStates=10` |
| nadpisywanie warunku `HasMovementInput` | **obalone**: 1822 zapisy co klatkę, każdy widzi `przed=0`. Gra liczy go ze znacznika `pionek+0xC74` |
| szukanie funkcji liczącej `HasMovementInput` wśród 34 wołających `0x14180A350` | **obalone założenie**: to warunki broni i 2× `RunToggled`; prawdziwy pracownik to `0x14180A210` |
| powtarzanie napełniania magazynka wołaniem `0x141B242F0` | **obalone i szkodliwe**: funkcja pisze `min(magazynek, ClipSize, zapas)` z polem docelowym jako pierwszym operandem — nie ma jak dać niezera; do tego **wywalała hosta** |

Starsze zamknięcia (hipotezy 1–22) i lekcje metodyczne: `KNOWLEDGE.md`.
Zasady pracy: `PROMPT-NOWY-CZAT.md`.
