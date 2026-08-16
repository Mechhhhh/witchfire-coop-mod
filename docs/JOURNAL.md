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
| 36 | **do gry klienta po dołączeniu nie docierają zdarzenia wejścia** — nie jest to ani tryb wejścia, ani stan kontrolera (oba wykluczone pomiarem), tylko warstwa dostarczania: Slate/okno albo coś, co travel robi z widokiem | licznik zdarzeń wejścia w grze klienta pokaże **zero** po dołączeniu, przy niezerowym u hosta w tym samym oknie czasu | **gotowe do zrobienia:** hak zliczający na `0x141A020B0` (wspólny filtr wejścia gry, wołany RAZ NA ZDARZENIE — `ADDRESSES.md`), marker `log_wejscie`, licznik w logu **po obu stronach**. Host jest próbą kontrolną: zero u obu = brak pomiaru, nie wynik | — |
| 32 | **awaria hosta na wiszącym słuchaczu i park wątku gry to JEDNO zjawisko** — pętla rozgłaszania trzyma zamek (`+0x360`) przez cały przebieg listy, więc awaria w środku zostawia zamek wzięty i reszta gry staje na `futex_wait` | jeśli tak, poprawny strażnik przed wywołaniem usuwa oba objawy naraz | przepisać `fix_lista` **z pseudokodu** (`tools/dekompiluj.sh 0x1419E7B40`), nie z asemblera — poprzednia wersja celowała dobrze, ale zamrażała hosta przy dołączaniu | park POTWIERDZONY pomiarem (0 tików/3 s, `futex_wait`, 3 wątki ze 130); związek z awarią to hipoteza |
| 29 | wyprawy nie da się przejść razem, bo powrót do hubu nie jest podróżą sesji | po zamianie lokalnego ładowania mapy na `ServerTravel` obaj gracze przenoszą się razem, a skrypty misji ruszają po stronie serwera | **trop znaleziony:** komenda `SERVERTRAVEL` idzie przez gniazdo **`+0x440`** w tablicy metod `UWorld`. Na żywym hoście odczytać ten wpis i zdekompilować — dopiero potem projektować łatkę | — |
| 30 | magazynek klienta, niesterowana maszyna stanów i brak potwierdzenia objęcia są **skutkami** 29, a nie osobnymi usterkami | po naprawie startu misji część z nich znika bez osobnej łatki | mierzyć dopiero PO 36 i 29 | — |
| 31b | strażnik `fix_smycz` jest przyczyną przeżycia klienta, a nie zbiegiem okoliczności | po ZDJĘCIU markera awaria wraca z tym samym stosem (`SetLeashName`, `0x141B7DDAA`) | jeden przebieg z markerem zdjętym — tani, robić przy okazji innego | — |

**Kolejność: 36 → 32 → 29 → 30.** Bez wejścia u klienta co-op jest niegrywalny,
więc 36 jest pierwsze. 32 jest drugie, bo host pada po ~50 min i psuje każdy
dłuższy przebieg. 29 to kamień milowy, ale ma sens dopiero, gdy klient gra.

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
