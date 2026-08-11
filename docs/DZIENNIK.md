# Dziennik roboczy — bieżąca sesja

Jeden plik na to, **nad czym się teraz pracuje**. Nie jest to historia ani
wiedza — te są w `PRZEBIEGI.md` i `WIEDZA.md`. Tutaj jest stan „w toku",
przepisywany na bieżąco, żeby nie zgubić wątku między przebiegami.

Zasada: **hipoteza → przewidywanie → pomiar → werdykt**, każda w jednej linii.
Gdy hipoteza jest zamknięta, przenieść ją do `WIEDZA.md` (potwierdzona) albo do
tabeli obalonych na końcu `WIEDZA.md` (obalona) — i **usunąć stąd**.

Ten plik ma zostać krótki. Jeśli urósł powyżej ~80 linii, znaczy że coś, co
powinno być zamknięte, wisi tu za długo.

---

## W toku

| # | hipoteza | przewidywanie | pomiar | werdykt |
|---|---|---|---|---|
| 23 | maszyna klienta nie wychodzi z `Idle`, bo serwer trzyma jego pionek w trybie SPADANIA (`MovementMode=3`), więc `IsOnGround` jest fałszem | po doprowadzeniu `MovementMode` do `Walking` warunek `IsOnGround` zrobi się `1`, `IdleToWalking` zajdzie i `GetMaxSpeed` sięgnie 800 przy sprincie | znaleźć, co na serwerze utrzymuje `Falling` dla pionka zdalnego — czy to brak sprawdzenia podłoża, czy zerowany sweep `UpdatedComponent` | — |
| 24 | broń klienta przeładowuje się w pętli, bo `PendingClipRefill` albo nie jest ustawiane przez `0x141B39940`, albo nikt go nie konsumuje | trampolina na `0x141B39940` pokaże dla broni klienta niezerową różnicę `ClipSize − CurrentAmmoInClip` i zapis atrybutu; jeśli zapis jest, a magazynek zostaje zerem, winny jest konsument | trampolina + odczyt `PendingClipRefill` z ASC broni (§3g) | — |
| 25 | awaria hosta `0x148` (sygnatura `abeaa893`, nowa) bierze się z pętli przeładowania dobijającej ścieżkę ekwipunku, a nie z `fix_czas` | przebieg kontrolny **bez** `fix_czas`, ale z tą samą broń klienta: awaria wraca | jeden przebieg, marker zdjęty | — |
| 20 | magazynek klienta zostaje zerem, bo `0x141B242F0` liczy `min(bieżący magazynek, ClipSize, zapas)` — przy pustym magazynku wynik jest zerem **niezależnie od zapasu**, więc to ZACISK, a napełnia co innego (`0x141B39940` → atrybut `PendingClipRefill`) | trampolina pokaże dla broni klienta `A=0`, `B=90`, `ClipSize>0`; jeśli `ClipSize==0`, to ASC broni nie ma zestawu `DimensionAmmoAttribSet` i naprawa dotyczy inicjalizacji zestawu, nie napełniania | cztery trampoliny filtrowane po adresie powrotu (szczegóły w `WIEDZA.md` §3d) | — |
| 21 | stamina klienta nie odnawia się i przez `StaminaMovementModifier` (0,83) zjada prędkość niezależnie od sprintu | `Stamina` w ASC pionka klienta stoi na zerze przy niezerowym `StaminaRegenSpeed` | `stan-gracza.py` dla obu graczy w tej samej chwili | — |

**Kolejność: 23, potem 24, potem 25.** Hipoteza 23 jest ostatnią przeszkodą
między stanem obecnym a działającym sprintem — reszta łańcucha jest już
zmierzona i działa. 24 da się przygotować statycznie, bez gry. 25 to próba
kontrolna, którą warto dołożyć do najbliższego przebiegu za darmo (samo zdjęcie
markera).

Hipoteza 21 (stamina) **schodzi na koniec**: liczba `522,8` okazała się
`615 × 0,85` (chód w bok), a nie `615 × 0,83` (mnożnik staminy), więc nie ma
dowodu, że stamina w ogóle uczestniczy w tej sprawie. Ścieżka regeneracji jest
rozebrana statycznie w `WIEDZA.md` §3h.

### Zamknięte 11.08 — NIE powtarzać

| co próbowano | werdykt |
|---|---|
| podanie akcji przez `ProcessExternalInputAction` (gniazdo 147) | **obalone**: akcje dochodzą (8/8), stan nie drgnął |
| to samo pełną ścieżką wejścia gry (gniazdo 150) | **obalone**: `gniazdo150 tez nic`, mimo poprawnych bajtów i `InputStates=10` |
| zgadywanie pięciu bajtów struktury akcji | **zamknięte pomiarem**: `00 00 00 01 01 00 00 00`; `bCustomTriggered` = 0 |
| kolejkowanie przejść przez `AddTransitionToQueue` | mechanizm **działa** (nazwa znaleziona, kolejka przerobiona), odrzuca dopiero ocena warunków |
| nadpisywanie warunku `HasMovementInput` | **obalone**: 1822 zapisy co klatkę, każdy widzi `przed=0`. Powód znany od 11.08 wieczorem: warunek **nie jest przechowywany**, gra przelicza go co klatkę ze znacznika `pionek+0xC74` (`WIEDZA.md` §3f) |
| szukanie funkcji liczącej `HasMovementInput` wśród 34 wołających `0x14180A350` | **obalone założenie**: `tools/warunki.py` mapuje wszystkie 34 na nazwy — to wyłącznie warunki broni i 2× `RunToggled`. `0x14180A350` jest tylko opakowaniem; prawdziwy pracownik to `0x14180A210`, a funkcja ruchu to `0x141809CC0` |
| czterej kandydaci `0x141885900`, `0x141885B70`, `0x1418D76B0`, `0x1418DE510` | **sprawdzeni i odrzuceni**: dwaj pierwsi ustawiają `RunToggled`, dwaj pozostali warunki broni |
| powtarzanie napełniania magazynka wołaniem `0x141B242F0` | **obalone i szkodliwe**: magazynek dalej zero, a wołanie **wywalało hosta**. Powód znany: ta funkcja pisze `min(A, ClipSize, B)`, gdzie `A` to bieżący magazynek — przy zerze nie ma jak dać niezera |
| **hipoteza 22: znacznik `pionek+0xC74`** | **POTWIERDZONA POMIAREM 23:57** — `HasMovementInput` u klienta = `1` (pierwszy raz w projekcie), 8093 stempli, próg wieku `0.100 s`. Nie wystarczyło: blokuje `IsOnGround` (hipoteza 23). Szczegóły `WIEDZA.md` §3f |
| kanał stanu (`fix_state`) jako wyzwalacz stemplowania znacznika ruchu | **odrzucone przed pomiarem**: kanał wysyła tylko przy zmianie sprintu albo kucania, więc zwykły chód nie wyzwoliłby go ani razu. Wyzwalaczem jest `Acceleration` (`komponent+0x22C`) |

Starsze, zamknięte hipotezy (1–18) i lekcje metodyczne: `WIEDZA.md`, sekcja o zamknięciach z 11.08. Zasady pracy: `PROMPT-NOWY-CZAT.md`.
