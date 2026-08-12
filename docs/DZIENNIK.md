# Dziennik roboczy — bieżąca sesja

Jeden plik na to, **nad czym się teraz pracuje**. Historia jest w `PRZEBIEGI.md`,
wiedza w `WIEDZA.md`, przegląd wszerz w `PRZEGLAD.md`.

Zasada: **hipoteza → przewidywanie → pomiar → werdykt**, każda w jednej linii.
Gdy hipoteza jest zamknięta, przenieść ją do `WIEDZA.md` i **usunąć stąd**.

Ten plik ma zostać krótki.

---

## W toku

| # | hipoteza | przewidywanie | pomiar | werdykt |
|---|---|---|---|---|
| 28 | **zamrożenie hosta przy dołączaniu klienta jest regresją z 12.08** — powodują je nowe trampoliny `fix_lista` albo `fix_ekwipunek`, obie w pętlach wykonujących się przy dołączaniu | z oboma markerami ZDJĘTYMI host nie zamarza w chwili powstania połączenia | markery już zdjęte; wystarczy przebieg: host w hubie, dołączyć klienta, patrzeć na zegar hosta i licznik `netdriver+0x98` | — |
| 29 | wyprawy nie da się przejść razem, bo klient wchodzi na mapę bez sekwencji startu misji, a powrót do hubu nie jest podróżą sesji | po zamianie lokalnego ładowania mapy na `ServerTravel` obaj gracze przenoszą się razem, a skrypty misji ruszają po stronie serwera | znaleźć, czym gra startuje wyprawę i czym wraca do hubu — robota **statyczna**, na zrzucie obrazu | — |
| 30 | magazynek klienta, niesterowana maszyna stanów i brak potwierdzenia objęcia pionka są **skutkami** hipotezy 29, a nie osobnymi usterkami | po naprawie startu misji część z nich znika bez osobnej łatki | mierzyć dopiero PO 28 i 29 | — |

**Kolejność: 28 → 29 → 30.** Hipoteza 28 to próba kontrolna i nie kosztuje nic
poza przebiegiem; dopóki nie wiadomo, czy zamrożenie jest nasze, **każdy pomiar
przy dołączaniu jest niewiarygodny**.

### Zamknięte 12.08 — NIE powtarzać

| co | werdykt |
|---|---|
| **`fix_state`** | **WYWALAŁ HOSTA.** Awaria 03:08, sygnatura `0xffffffffffffffff`. Stos: `0x14180A225` (zapis warunku) ← `0x14180A373` (opakowanie `UpdateCustomConditionBool`) ← `0x141CB385C` (thunk `UFunction`) ← `0x142106F56` (`ProcessEvent`). Gra woła swoje warunki **bezpośrednio** — tą drogą chodzi wyłącznie nasz kod |
| kolejkowanie `IdleToWalking` w chwili prawdziwych warunków | **obalone**: 3600 prób, 0 udanych. Oba warunki prawdziwe 42% czasu, blokady `State.Lock.*` zerowe u obu graczy, wymagania przejścia to dokładnie te dwa warunki w postaci `>0`, kolejka przyjmuje wpis, stan `0` w 100% z 598 próbek co 20 ms |
| hipoteza 23 — pionek klienta trzymany w spadaniu | **obalona**: `MovementMode = 1` w 95% próbek; poprzedni wniosek stał na jednym odczycie |
| pauza hosta jako przyczyna zamrożenia klienta | **obalona przez gracza**: pauza zawiesza klienta tylko wtedy, gdy pauzuje **klient**; host może pauzować bez skutku |
| „dołączanie w hubie nie działa" | **doprecyzowane**: dołączenie przechodzi w pełni (`PostLogin`, pionek, host widzi klienta stojącego), po czym rwie się po 64 s przy `ConnectionTimeout = 60 s` — a przyczyną jest zamrożenie HOSTA (hipoteza 28), nie cisza klienta |

### Zamknięte 11.08 — NIE powtarzać

| co próbowano | werdykt |
|---|---|
| podanie akcji przez `ProcessExternalInputAction` (gniazdo 147) | **obalone**: akcje dochodzą (8/8), stan nie drgnął |
| to samo pełną ścieżką wejścia gry (gniazdo 150) | **obalone** mimo poprawnych bajtów i `InputStates=10` |
| nadpisywanie warunku `HasMovementInput` | **obalone**: 1822 zapisy co klatkę, każdy widzi `przed=0`. Powód: warunek nie jest przechowywany, gra liczy go ze znacznika `pionek+0xC74` |
| szukanie funkcji liczącej `HasMovementInput` wśród 34 wołających `0x14180A350` | **obalone założenie**: to wyłącznie warunki broni i 2× `RunToggled`; prawdziwy pracownik to `0x14180A210`, a funkcja ruchu `0x141809CC0` |
| powtarzanie napełniania magazynka wołaniem `0x141B242F0` | **obalone i szkodliwe**: ta funkcja pisze `min(magazynek, ClipSize, zapas)`, gdzie pierwszy operand jest polem docelowym — nie ma jak dać niezera; do tego **wywalała hosta** |

Starsze zamknięcia (hipotezy 1–22) i lekcje metodyczne: `WIEDZA.md`.
Zasady pracy: `PROMPT-NOWY-CZAT.md`.
