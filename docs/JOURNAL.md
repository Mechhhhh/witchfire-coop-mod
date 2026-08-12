# Dziennik roboczy — bieżąca sesja

Jeden plik na to, **nad czym się teraz pracuje**. Historia jest w `RUNS.md`,
wiedza w `KNOWLEDGE.md`, przegląd wszerz w `OVERVIEW.md`.

Zasada: **hipoteza → przewidywanie → pomiar → werdykt**, każda w jednej linii.
Gdy hipoteza jest zamknięta, przenieść ją do `KNOWLEDGE.md` i **usunąć stąd**.

Ten plik ma zostać krótki.

---

## W toku

| # | hipoteza | przewidywanie | pomiar | werdykt |
|---|---|---|---|---|
| 31 | **klient ginie 4 s po travelu do hosta przez zdarzenie BP `SetLeashName` wołane na nullu z timera** (PC `0x141B7DDAA`, stos identyczny 03:18/03:25/14:41); strażnik nulla na bliźniaczym thunku `SetSpawnBehaviour` już działa, więc ten sam strażnik na `0x141B7DDA0` pozwoli klientowi przeżyć | z markerem `fix_smycz`: licznik `SMYCZ` > 0, klient żyje > 120 s po połączeniu, brak nowego zrzutu; bez markera awaria wraca z tym samym stosem | **POŁOWA POZYTYWNA POTWIERDZONA 15:16:** `SMYCZ: 1` dokładnie 5 s po travelu, zero nowych zrzutów, połączenie > 138 s (stary punkt śmierci 64 s), uścisk objęcia PEŁNY (`ServerAcknowledgePossession [2 raz]` u hosta), klient ma kamerę i świat, host widzi jego pionka. Obie mapy atrybutów pełne (19 wpisów) po obu stronach | kontrola przez ZDJĘCIE markera — do zrobienia |
| 33 | **wejście klienta po dołączeniu w hubie jest martwe** (gracz: „oboje żyją, ale nie mogę nic robić"), mimo pełnego objęcia i kamery. Trop: klient podróżuje z otwartego menu do mapy o TEJ SAMEJ nazwie (`Persistent_Base` → `Persistent_Base`), więc warstwa menu mogła przeżyć travel i trzymać fokus wejścia; przy wyprawach 11.08 mapa się zmieniała, menu ginęło i wejście działało | jeśli fokus trzyma UI: Esc/klik przywróci wejście albo pokaże widżet; odczyt refleksją pokaże tryb wejścia/widżety. Kandydat „4 pominięte wiązania z nullem" ODPADA: występują przy każdym dołączeniu, także 11.08, gdy wejście działało | relacja gracza (mysz? WSAD? Esc?) + refleksja po widżetach `UserWidget` na kliencie | — |
| 29 | wyprawy nie da się przejść razem, bo klient wchodzi na mapę bez sekwencji startu misji, a powrót do hubu nie jest podróżą sesji | po zamianie lokalnego ładowania mapy na `ServerTravel` obaj gracze przenoszą się razem, a skrypty misji ruszają po stronie serwera | znaleźć, czym gra startuje wyprawę i czym wraca do hubu — robota **statyczna**, na zrzucie obrazu | — |
| 30 | magazynek klienta, niesterowana maszyna stanów i brak potwierdzenia objęcia pionka są **skutkami** hipotezy 29, a nie osobnymi usterkami | po naprawie startu misji część z nich znika bez osobnej łatki | mierzyć dopiero PO 31 i 29 | — |
| 32 | **host paruje wątek gry ~50 s po zerwaniu połączenia** (14:43:14: `futex_wait` bez limitu na `0x7f08d4565144`, wątek 0 tik/s, render żyje — „241 FPS a stoi"). Trafia dokładnie w 30-sekundowy takt cyklu napełniania (14:41:14/44 → 14:42:14/44 → **14:43:14**), pierwszy takt po tym, jak kontroler klienta został „bez Player"; na hoście zostają sieroty (4 bronie, kontroler bez pionka). Gracz: „to się zawsze działo" | jeśli park siedzi w takcie napełniania na zombie, to log wejścia/WYJŚCIA taktu urwie się na wejściu w chwili parku; przy kliencie, który przeżywa (`fix_smycz`), park nie wystąpi wcale | hak logujący wejście/wyjście taktu napełniania dla kontrolerów bez Player + pytanie do gracza: czy zamrożenie „po czasie" zdarzało się też w czystym singleplayerze bez dołączeń? | — |

**Kolejność: 31 → 29 → 30.** Dopóki klient umiera 4 sekundy po travelu,
żaden pomiar sesji w hubie nie ma szans trwać dłużej niż `ConnectionTimeout`.
Przy przebiegu 31 jedyną zmianą kodu jest strażnik `fix_smycz`; `log_objecie`
to czysty pomiar (zasada 8: wszystko, co przebieg ma zmierzyć, naraz).

### Zamknięte 12.08 — NIE powtarzać

| co | werdykt |
|---|---|
| **hipoteza 28 — zamrożenie hosta przy dołączaniu to regresja trampolin `fix_lista`/`fix_ekwipunek`** | **POTWIERDZONA próbą kontrolną 14:39–14:49.** Bez obu markerów host NIE zamarł w chwili połączenia (zegar gry 1:1 przez całe okno, GameThread 47–70 tik/s, gracz grał — zrzuty). Markery ZOSTAJĄ zdjęte; przed powrotem ich pętle wymagają przepisania (zasada 7). Szczegóły: `KNOWLEDGE.md` „Próba kontrolna hipotezy 28" |
| „64 s timeout dołączenia w hubie = skutek zamrożenia hosta" | **SKORYGOWANE 14:41:** host był zdrowy, a rozłączenie po 63,8 s i tak przyszło. Przyczyną jest ŚMIERĆ KLIENTA 4 s po travelu (`SetLeashName` na nullu → hipoteza 31); host tylko odlicza `ConnectionTimeout` po trupie |
| „czarny ekran klienta = czeka na objęcie pionka" (łańcuch §0c) | **SKORYGOWANE:** klient nie czeka — klient NIE ŻYJE (zrzut 14:41, GameThread martwy, proces ~6 tik/s, PULS proxy dalej bije). Brak `AcknowledgePossession` jest skutkiem awarii |
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

Starsze zamknięcia (hipotezy 1–22) i lekcje metodyczne: `KNOWLEDGE.md`.
Zasady pracy: `PROMPT-NOWY-CZAT.md`.
