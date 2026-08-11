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

| # | hipoteza | przewidywanie (co zobaczę, jeśli prawdziwa) | pomiar | werdykt |
|---|---|---|---|---|
| 13 | podanie maszynie stanów akcji przez `ProcessExternalInputAction` (gniazdo 147) sprawi, że serwer wejdzie w `Running`/`Sliding` i szarpanie zniknie | stan serwerowej kopii zmienia się z `Idle`, a `GetMaxSpeed` zwraca 800 | po zbudowaniu kanału | — |
| 15 | podanie serwerowi akcji `Run`/`Crouch` przez `ProcessExternalInputAction` przełączy maszynę stanów i szarpanie zniknie | stan serwerowej kopii przestaje być `Idle`, `GetMaxSpeed` zwraca 800 przy sprincie, gracza przestaje cofać | przebieg 16:45: akcje dochodzą (8/8), stan **nie drgnął** | **CZĘŚCIOWO OBALONA** — samo gniazdo 147 nie wystarcza |
| 17 | maszyna nie przechodzi, bo `ProcessExternalInputAction` **nie zapisuje stanu wejścia** do `+0x2F8`, a warunek przejścia pyta „czy `Run` jest trzymany" | podanie akcji **gniazdem 150** (pełna ścieżka wejścia gry, ta sama co dla człowieka) przełączy stan; log pokaże `gniazdo150 ZADZIALALO` | wdrożone, czeka na przebieg | — |
| 18 | pięć bajtów struktury akcji nie trzeba zgadywać — wystarczy podpatrzeć własne wejście gracza w tym samym procesie | w logu `WEJSCIE-PODSLUCH` pojawią się bajty dla `Run`/`Crouch`, a licznik `zapamietanych wzorcow` urośnie | wdrożone, czeka na przebieg | — |
| 16 | magazynek klienta zostaje zerem, bo nie wykonuje się ten zapis do `CurrentAmmoInClip`, który u zdrowego gracza wpisuje 6 | hak na gniazdo 180 ASC broni (offset `0x5A0`, filtr po atrybucie `+0x314`) pokaże **solo** listę adresów powrotu; u dołączającego gracza jednego z nich zabraknie | najpierw SOLO (wzorzec), potem dwóch graczy | — |

Hipotezy z rodziny „amunicja to brak zdolności" i „napełnia ją `0x141B242F0`"
**zamknięte** — patrz `WIEDZA.md` §3d. Pierwsza: broń klienta ma komplet pięciu
zdolności. Druga: `0x141B242F0` to **zacisk** (`min(...)`), nie napełnianie.

**Kanał POPRAWIONY i WDROŻONY (11.08, 18:25).** Biblioteka zbudowana bez
ostrzeżeń i skopiowana do katalogu gry (`md5=33e5aa5b`). Trzy zmiany, wszystkie
z rozbioru obrazu, nie z domysłu (`WIEDZA.md`, „ROZBIÓR OBRAZU 11.08"):

1. definicję akcji kopiujemy **operatorem przypisania gry** `0x1417A3E50` —
   poprzedni `memcpy` zabierał grze odwołanie do `TSharedPtr` przy każdym
   podaniu akcji,
2. bajty `+0x38..+0x3F` bierzemy z **podsłuchu prawdziwego wejścia**;
   `bCustomTriggered` = **0**, bo tyle wpisuje sama gra (`0x141806FDB`) —
   nasza jedynka była zgadnięta i zgadnięta źle,
3. podanie akcji jest **dwustopniowe**: gniazdo 147, a gdy stan nie drgnie —
   gniazdo 150, czyli pełna ścieżka wejścia gry (bramka + zapis `+0x2F8`).

Jeden przebieg rozstrzyga więc trzy pytania naraz.

**Budowa kanału — ODBLOKOWANA, wszystkie elementy zmierzone (02:22).**
Gracz zdecydował: robimy kanał (11.08). Nic już nie jest zgadywane:

| element | wartość |
|---|---|
| wysyłka z klienta | `ProcessEvent` — **gniazdo wirtualne 68** |
| parametry w ramce | `FFrame::Locals` = **`+0x28`** |
| transport | `ServerSetInversedScreenRatio(float)`, wartość ≥ 1000 = nasza |
| zastosowanie | `ProcessExternalInputAction` — **gniazdo 147** maszyny stanów |
| treść | kopia 56-bajtowej definicji z `InputsToCapture` + `KeyEvent` (+0x38) |

Hipoteza 14 potwierdzona (pomiar na odbiorze RPC ruchu u hosta). Zostaje sama
implementacja — mechaniczna.

Hipotezy 11 i 12 zamknięte: **12 potwierdzona**. Gra nie nadpisuje
`UpdateFromCompressedFlags` (jedenaście nadpisań w komponencie ruchu, żadne to
nie jest), a cały `DimensionStateMachineComponent` ma 47 funkcji i **zero RPC**.
Dowód ruchem: serwerowa kopia klienta nie opuszcza `Idle`, gdy klient przechodzi
u siebie przez pięć stanów.

Hipotezy 7–10 zamknięte 11.08 — wyniki w `WIEDZA.md`:
**7 i 8 potwierdzone** (naprawa mapy atrybutów działa, klient chodzi; strażnik
duplikatu drugi raz z rzędu), **9 potwierdzona** (serwer ani razu nie policzył
prędkości sprintu ani ślizgu — przy ślizgu widzi samo kucanie, 265),
**10 obalona** (dash zgadza się co do dziesiętnych, więc symulacja i tor ruchu
są zgodne — rozjeżdża się wyłącznie prędkość maksymalna wynikająca ze stanu).

Hipotezy 4, 5 i 6 zamknięte w przebiegu 01:11 — wyniki w `WIEDZA.md`:
**4 obalona** (wszystkie trzy znaczniki blokady zerowe, a limit i tak 0.000),
**5 potwierdzona i doprecyzowana** (13 z 19 wartości w mapie wyzerowanych, przy
poprawnych atrybutach w ASC — psuje się wyłącznie podręczna kopia),
**6 potwierdzona** (dokładnie jedno pominięcie, host działa jak w singleplayerze).

Hipoteza 5 z poprzedniej wersji („brak startowego `GameplayEffect`") **odpadła
przed pomiarem**: postać klienta ma na serwerze komplet 11 zestawów atrybutów
i `DimensionMovementAttribSet` z poprawnymi `SprintSpeed=800`, `Acceleration=2000`,
`NormalSpeed=615` — identycznie jak host.

Hipotezy 1–3 zamknięte 10.08 wieczorem — wyniki w `WIEDZA.md`:
**1 obalona** (broń klienta jest zdrowa, przyczyną braku ruchu jest pusta mapa
atrybutów ruchu), **2 obalona** (to host ma dwa duplikaty, nie klient dwa braki),
**3 rozstrzygnięta** (`0x141923AA0` = gniazdo 99 `DimensionItemStorage`;
podwójne napełnianie potwierdzone hakiem).

Wszystko, co dziś rozstrzygnięte, jest w `WIEDZA.md`. Poniżej zostają tylko
lekcje metodyczne, bo dotyczą sposobu pracy, a nie samej gry.

### KOREKTA własnego wniosku: „kłamie tylko HUD" było błędne

Napisałem, że dane są dobre, a psuje się samo wyświetlanie — bo `Stamina` wynosi
`88/88`, a `Health = 83`. Gracz zbił to jednym zdaniem: gdyby psuł się sam HUD,
broń dałoby się wystrzelić. Pomiar przyznał mu rację i **`AmmoInClip = 0` także
w serwerowej kopii broni klienta**, przy `6` u hosta. Zero po stronie serwera nie
może być usterką wyświetlania.

Wniosek poprawiony i przeniesiony do `WIEDZA.md` §3a: klient nie dostaje pełnej
inicjalizacji gracza. Twardy ślad liczbowy: `ActivatableAbilities` ma **10**
pozycji u hosta i **8** u klienta — tak samo po stronie serwera, więc to brak
nadania, nie zgubiona replikacja. Ładowanie amunicji jest w tej grze zdolnością
(`AbilityWeaponLoadAmmo_C`), co spina to w jedną całość.

Lekcja metodyczna: **zgodność atrybutów nie dowodzi, że stan jest zdrowy.**
Sprawdzałem wartości, które akurat się replikują, i wziąłem ich zgodność za dowód
sprawności całej postaci. Sprawdzać to, czego objaw dotyczy wprost — tu amunicję
w broni, nie życie w atrybucie.

### ZASADA: pułapka sprzętowa NIE w trakcie dołączania klienta

Sprawdzone dwa razy tego samego wieczoru, oba razy z tym samym skutkiem: host
zamarza, klient widzi kilka assetów, przebieg do wyrzucenia.

| próba | co | skutek |
|---|---|---|
| 21:01 | pułapka na `AActor::SetOwner`, 400 zatrzymań | host padł (`fc5c66e3`, adres `0xFFFFFFFFFFFFFFFF`) |
| 21:13 | pułapka na `0x14190306C`, 20 zatrzymań | host zamarł, klient bez świata |

Liczba zatrzymań nie ma znaczenia — **samo zatrzymywanie wątku gry w trakcie
nawiązywania połączenia rozbija sesję**. Sieć w UE ma limity czasu i sekwencję
otwierania kanałów; zatrzymany wątek gry ją łamie.

Wolno używać pułapek sprzętowych **po** ustabilizowaniu sesji i tylko na rzadkich
zdarzeniach (zapis do konkretnego pola, jedno rozgałęzienie) — tak powstały
dobre pomiary prędkości i przyspieszenia. Do wszystkiego, co dzieje się
**w chwili dołączania**, jedynym bezpiecznym narzędziem jest **hak w procesie**,
który zapisuje do logu i wraca.

Dodatkowo: pomiar z 21:13 (dwadzieścia identycznych trafień, rejestry niebędące
wskaźnikami na obiekty) jest **odrzucony** — trafiłem w to miejsce w innym
kontekście, niż zakładałem, i nie wolno z niego nic wnioskować.

## Następny przebieg — co ustawić

- markery **hosta**: `always_listen`, `fix_booster`, `fix_input`, `log_owner`,
  `log_fill`; `fix_move` **zdjęte** (łatka diagnostyczna, odrzucona),
- markery **klienta**: `join_ip`, `fix_weapon`, `fix_effects`, `log_fill`,
- **pytania o hosta rozstrzygać na mapie MENU, bez kliknięć gracza.** Sprawdzone
  22:50: podwójne napełnianie, duplikaty zdolności i podwójny komplet broni
  odtwarzają się z hostem w menu. Klient wtedy zamarza (ta sama mapa), więc do
  pomiarów po stronie klienta nadal trzeba wyprawy,
- **najpierw sprawdzić, czy pytania nie da się rozstrzygnąć na zrzucie obrazu** —
  deasemblacja, odwołania, literały i granice funkcji nie wymagają już gry
  (`tools/obraz.py`),
- czego pilnować: gracz **nie może zginąć** w trakcie dołączania (skaża pomiar),
  a instancja po awarii drugiej strony jest **popsuta** i nie nadaje się na wzorzec.
