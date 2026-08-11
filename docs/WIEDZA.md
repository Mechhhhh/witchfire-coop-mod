# Wiedza o grze — co ustalone i czym udowodnione

Tylko rzeczy **potwierdzone pomiarem**. Hipotezy obalone są na końcu, razem
z informacją, czym zostały zamknięte — bo dwa razy w tym projekcie wracano do
tej samej ślepej uliczki.

Adresy liczone od bazy `0x140000000` (pod Wine bez ASLR; nasza DLL i tak liczy
od rzeczywistej bazy).

---

## 1. Jak gra hostuje i dlaczego to działa

`UEngine::LoadMap` zaczyna się na **`0x143BEAE56`** (nie `0x143BEAE50` — pod
tamtym adresem stoi skok przez wskaźnik poza moduł). W środku jest:

```
lea  rdx,[...]        ; literał L"Listen"
call 0x143BFC430      ; FURL::HasOption
test al,al
je   pomiń            ; 0x143BEC200: bajty 74 0F
mov  rcx,[r13+0x280]  ; UWorld*
call 0x143C3ECE0      ; UWorld::Listen
```

Zamiana `je` na dwa `NOP`-y sprawia, że gra **sama** włącza nasłuch przy każdym
ładowaniu mapy — własnym światem, własnym URL-em, we właściwym momencie
sekwencji. To cała łatka hostowania: dwa bajty.

Zmierzone własne podróże gry (hak logujący na `LoadMap`):
```
mapa="/Game/Maps/Base/Persistent_Base"        opcja[0]="Name=Player"
mapa="/Game/Maps/Prologue/Persistent_Prologue"  opcji: 0
```
Gra **nie dopisuje** `listen` do żadnej z nich — dlatego trzeba to wymusić.

## 2. Dlaczego droga A (wymuszanie mapy) była ślepa

`OpenLevel(mapa, "listen")` omija sekwencję startu misji. `BPMission_C` istnieje
wtedy **wyłącznie jako wzorzec klasy** — żaden aktor misji nie powstaje, więc
`BeginMission` nigdy nie leci. Skutki, wszystkie zmierzone jako osobne objawy,
a naprawdę jeden problem: broń nie strzela, brak celowania, „NO AMMO", klient
bez ekranu śmierci, wariująca minimapa, brak prawdziwej postaci u klienta.

Kontrola od gracza, która to zamknęła: **bez połączenia** na tej samej mapie
wszystko inne działa, a broń i tak nie. Czyli to nie był problem co-opu.

## 3. Ekwipunek gry nie ma replikacji

`DimensionInventoryComponent`: **50 funkcji, zero RPC**. `CurrentWeaponIndex`
bez flagi `CPF_Net`. Na **203 RPC w całej grze** żadne nie wyjmuje broni
(pięć dotyczy broni: strzał, koniec strzału, FOV, rzucany przedmiot, cheat).

Kontrola poprawności odczytu flagi: `Actor` ma 10 pól replikowanych (komplet
znanych), `Character` 23, `DimensionWeapon` 15 — w tym własne gry (`MyPawn`,
`BurstCounter`, `WeaponFOV`). Autorzy **umieli** replikować; ekwipunku po prostu
nie replikowali.

Skutek: host wykonuje „wyjmij broń" lokalnie, klient nigdy. Licznik amunicji
działa, bo amunicja siedzi w replikowanym **aktorze broni**.

Naprawa: wołać u klienta z wątku gry
`UDimensionInventoryComponent::SelectWeapon(ekwipunek, 0)` @ **`0x1418D7600`**,
dla komponentu, którego właściciel ma `Role == 2` (AutonomousProxy).

**Działa też na drodze B** (przebieg 16:25): `BRON: CurrentWeaponIndex -1 -> 0
(UDALO SIE)`, cztery sekundy po dołączeniu, broń widoczna na zrzucie.

Wcześniejsze „nie działa na drodze B" było **błędem pomiaru, nie łatki**.
Kryterium `Role == 2` było poprawne przez cały czas — potwierdzone sondą
`bron-lokalna.py` na żywym kliencie: komponent ekwipunku o właścicielu
`Role=2 (AutonomousProxy)` i `CurrentWeaponIndex=-1` istnieje. Zawodziły dwie
inne rzeczy:

1. **Budżet prób był zakotwiczony w złym miejscu.** Zegar 40 prób × 2 s ruszał
   przy ładowaniu biblioteki, a klient łączył się z hostem dopiero 38 s później
   (30 s „wyciszenia" + ładowanie mapy). Prawie połowa budżetu szła na
   przeszukiwanie **menu**, w którym żadnej zdalnej postaci być nie może.
   Naprawa: zegar zeruje hak `LoadMap`, gdy zobaczy mapę z niepustym adresem
   hosta.
2. **W każdym z trzech przebiegów druga strona padała w oknie pomiaru**, więc
   „poddaje się po 40 probach" mówiło tylko tyle, że sesja już nie żyła.

Lekcja ogólniejsza: **licznik prób odmierzający czas od startu procesu mierzy
coś innego niż zjawisko.** Zakotwiczać w zdarzeniu, nie w starcie.

## 3a. Klient nie dostaje pełnej inicjalizacji gracza — i to NIE jest HUD

Pierwsza wersja tego wniosku brzmiała „dane są dobre, kłamie tylko HUD". **Była
błędna** i obalił ją zwykły argument gracza: gdyby psuł się sam wyświetlacz,
strzał i tak by wychodził. Pomiar to potwierdził.

Amunicja klienta wynosi zero **także po stronie serwera**:

| | `AmmoInClip` |
|---|---|
| broń hosta (HUD pokazuje `6/84`) | **6** |
| serwerowa kopia broni klienta | **0** |
| obie bronie widziane u klienta | **0** |

Skoro serwer też ma zero, nie jest to ani replikacja, ani wyświetlanie: **nowemu
graczowi nikt nie załadował amunicji**. W tej grze ładowanie jest zdolnością
(`AbilityWeaponLoadAmmo_C` w polu `LoadAmmoAbility` broni), więc trop prowadzi do
systemu zdolności — i tam widać różnicę wprost:

| `ActivatableAbilities.Items` | ile |
|---|---|
| postać hosta | **10** |
| postać klienta (u klienta) | **8** |
| serwerowa kopia postaci klienta | **8** |

**KOREKTA 2026-08-10 22:52 — wniosek „klientowi brakuje dwóch zdolności" jest
BŁĘDNY.** Wystarczyło wypisać nazwy zamiast liczyć pozycje. Pomiar hosta przed
dołączeniem i po nim, w jednym przebiegu:

```
przed:  DashGlide_C, MeleeHealingAbility_C, BP_SensesInvisibility_Ability_C,
        PushbackAbility_C, BP_AbilityJump_C, BP_AbilityExtraJumps_C,
        BP_Spell_Light_NELE_01_Shockwave_C, MeleePunchAbility_C          (8)

po:     ...te same osiem...,
        BP_Spell_Light_NELE_01_Shockwave_C, MeleePunchAbility_C          (10)
```

Dwie dodatkowe pozycje to **DUPLIKATY** dwóch ostatnich. Czyli nie klient ma za
mało — to **host dostaje przy dołączeniu dwie zdolności drugi raz**. Ósemka
u klienta jest liczbą prawidłową.

To przenosi całą sprawę z rubryki „braki u klienta" do rubryki „host dostaje
komplet drugi raz" (§3c) — razem z zapasową bronią i amunicją 28231.

Lekcja metodyczna, ta sama co przy `CurrentWeaponIndex`: **liczba pozycji nie
jest pomiarem zawartości.** Wypisywać nazwy.

Drugi zmierzony fakt: **klient ma dwa HandCannony przypisane do własnej postaci**
(`MyPawn` obu wskazuje na nią) — jeden zreplikowany z serwera, drugi zrobiony
lokalnie. To ten sam podwójny komplet broni, który opisano w `BRON.md`, tylko
widziany od strony klienta. Wyjaśnia „mam jedną broń i nie mogę przełączać":
lokalny komplet nie jest tym, który zna serwer.

Co przy okazji **odpada**: `Health`, `Stamina`, `MaxStamina`, `StaminaRegenSpeed`
i wszystkie atrybuty ruchu są u klienta **identyczne jak u hosta**. Puste paski
to skutek, nie przyczyna.

### Pełna lista braków u klienta (stan 2026-08-10, przebieg 16:25)

Spisana, bo dwie duże sprawy zaczęły przesłaniać resztę. Kolumna „zmierzone"
mówi, czy to już wiadomo z pomiaru, czy dopiero z ekranu.

| # | objaw | zmierzone | przypisane do |
|---|---|---|---|
| 1 | nie da się strzelać, `0/0`, „NO AMMO" | `AmmoInClip = 0` **także na serwerze** (host: 6) | brak zdolności (§3a) |
| 2 | jedna broń zamiast dwóch, brak przełączania | dwa HandCannony z `MyPawn` na własną postać: jeden zreplikowany, jeden lokalny | podwójny komplet broni |
| 3 | nie da się chodzić — „milimetr i cofa" | serwerowa kopia: prędkość `0,0`, zero przesunięcia; klient: 238 | `ServerMove` (§3b) |
| 4 | pusty pasek życia | `Health = 83` po obu stronach — **dane dobre** | wypełnienie HUD |
| 5 | stamina pulsuje na czerwono bez przerwy | `Stamina = 88/88`, `RegenSpeed 50` — **dane dobre** | wypełnienie HUD |
| 6 | brak licznika mikstur leczenia obok życia | z ekranu | wypełnienie HUD |
| 7 | brak licznika waluty zarobionej w wyprawie | z ekranu | wypełnienie HUD |
| 8 | brak panelu celu wyprawy, `X` nic nie robi | z ekranu; aktor `BPDimensionHUD_C` **istnieje** u klienta | wypełnienie HUD |
| 9 | brak własnej strzałki na środku minimapy | z ekranu | wypełnienie HUD |
| 10 | **host traci widok pierwszoosobowy przy KAŻDYM dołączeniu** | zrzut 17:14: brak rąk **i** broni przy działającym `6/84`, miksturach i pasku życia | osobna sprawa, §3c |
| 11 | **host traci walutę zdobytą w wyprawie** | zrzuty gracza przed i po dołączeniu: `960` → `0` | §3c, ta sama chwila co utrata widoku |
| 12 | przeładowanie u klienta powtarza się w kółko | animacja jest **normalna** i przerywa ją sprint (zgłoszenie gracza); powtarza się, bo amunicja nie przybywa | skutek pozycji 1, nie osobna usterka |
| 13 | **host zostaje z zaciętym celowaniem**, gdy klient dołączy w chwili, gdy host celuje | zgłoszenie gracza 20:19: zostaje FOV celowania i prędkość chodzenia jak przy celowaniu; sprint działa normalnie | nowe, niezbadane |
| 14 | ekwipunek i mapa u klienta **wyglądają poprawnie** | zgłoszenie gracza (sprawdzone przy pauzie) | zawęża pozycję 2 do samych slotów broni |

Pozycje 4–9 mają wspólną cechę: **dane po stronie gry są poprawne**, więc to jest
jeden problem wypełnienia HUD, a nie sześć. Pozycje 1 i 3 to dwie osobne, twarde
sprawy i one blokują granie.

## 3b. Serwer nie rusza pionkiem klienta — ustalone liczbowo

„Klient rusza się milimetr i wraca" zostało zmierzone po obu stronach naraz,
w jednym oknie, przy 600 próbkach z pełnym wejściem ruchu:

| | prędkość | największe oddalenie |
|---|---|---|
| klient (własna symulacja) | maks. **238**, średnio 115 | **15,5** jednostki |
| serwerowa kopia tej samej postaci | **0,0** | **0,0** |

Serwerowa kopia nie drgnęła **w żadnej osi** — ani XY, ani Z. Klient symuluje
ruch u siebie, serwer trzyma swoją kopię w miejscu i koryguje klienta z powrotem.
Stąd objaw: postać rusza o ułamek jednostki i wraca (przez 40 s trzymania klawisza
przeszła w sumie **1,3 jednostki**).

Co przy tym **odpada** — wszystko sprawdzone próbką kontrolną z własnej postaci
hosta w tym samym procesie:

| co | klient / serwerowa kopia | host |
|---|---|---|
| wejście osi ruchu | wektor 1,00–1,41 | — |
| `MaxWalkSpeed` | 600, stałe | 600 |
| `MovementMode` | 1 (Walking) | 1 |
| `bIsActive` komponentu ruchu | True | True |
| `Role` / `RemoteRole` / `bExchangedRoles` | 3 / 2 / True | 3 / 2 / True |
| `Controller.Pawn` i `AcknowledgedPawn` | ustawione na tę postać | ustawione |

Cały łańcuch posiadania sieciowego jest więc poprawny, a mimo to `ServerMove` nie
skutkuje.

### Rozstrzygnięcie: RPC dochodzi, serwer ustawia przyspieszenie, prędkość zostaje zerem

Licznik na `UFunction::Func` siedmiu RPC ruchu `Character` (przebieg 17:25):

```
17:25:21  RUCH: ServerMovePacked wykonane 44 razy
17:25:30  RUCH: ServerMovePacked wykonane 496 razy
17:26:08  RUCH: ServerMovePacked wykonane 2412 razy
```

Czyli **klient wysyła, a serwer odbiera i WYKONUJE** — około 50 razy na sekundę.
Odpada więc i „klient nie wysyła", i „pakiety nie docierają".

Pomiar na serwerowej kopii postaci klienta, 600 próbek przy trzymanym `W`:

| | wartość |
|---|---|
| `Acceleration` | **4000,0** — pełne wychylenie, czyli dane z RPC są rozpakowane i zastosowane |
| `Velocity` | **0,0** |

`MoveAutonomous` ustawia `Acceleration` **przed** wywołaniem `PerformMovement`,
więc to rozdziela sprawę precyzyjnie: **dane docierają aż do komponentu ruchu,
a prędkość z nich nie powstaje.**

Sprawdzone i wykluczone po stronie serwera (każde z próbką kontrolną z postaci
hosta w tym samym procesie):

| pole | serwerowa kopia klienta | host |
|---|---|---|
| `MovementMode` | 1 (Walking) | 1 |
| `MaxWalkSpeed` | 600 | 600 |
| `GroundFriction` / `BrakingDecelerationWalking` | 8 / 2048 | — |
| kapsuła `Mobility` | 2 (Movable) | 2 (Movable) |
| ruch korzenia (`bHasRootMotion`, `SavedRootMotion`) | czysty | czysty |
| `NormalSpeed` / `MovementModifier` | 615 / 1,0 | — |

### PRZYCZYNA ZNALEZIONA: dwa limity gry zwracają zero dla pionka zdalnego

To czwarte wystąpienie wzorca z §4 i najlepiej udokumentowane.

Łańcuch, każdy krok zmierzony:

```
klient wysyła ServerMovePacked 53×/s        →  dociera (licznik: 475 tys.)
serwer: Acceleration = 2000                  →  rozpakowane poprawnie
serwer: call [rax+0x6F8] = GetMaxAcceleration() gry  →  0
        ⇒ przyspieszenie przeskalowane do ZERA (0x1436DB8EA)
serwer: GetMaxSpeed() gry                    →  0
        ⇒ prędkość przycięta do ZERA (0x1436D0BAE)
```

Obie funkcje to **nadpisania gry** w `DimensionMovementComponent`, znalezione
przez porównanie tablic metod (`tools/vtable-diff.py`, 10 nadpisań na kilkaset):

| gniazdo | adres w grze | co to |
|---|---|---|
| 223 | `0x14177DEC0` | `GetMaxAcceleration` — wywoływana z `[rax+0x6F8]` |
| 130 | `0x14177F520` | `GetMaxSpeed` — literały `Cheat.SpeedBoost`, `State.Player.Running` |

**Próbka kontrolna, która to rozstrzygnęła** (pomysł gracza: „sprawdź, jak działa
ruch hosta, skoro on może"). Host przechodzi przez **te same instrukcje**:

```
HOST            0x1436D0AD9 Velocity=20.44 → 0x1436D0BAE Velocity=20.44  zachowana
KLIENT (serwer) 0x1436D0AD9 Velocity=39.43 → 0x1436D0BAE Velocity= 0.00  wyzerowana
```

Odczyt rejestru w chwili przycinania: limit = **0.000** dla pionka klienta.

**Potwierdzenie ruchem** (przekierowanie obu nadpisań do wersji silnika):

| stan | serwer: przyspieszenie | serwer: prędkość | przebyta droga |
|---|---|---|---|
| bez łatek | 1/600 próbek | 0,0 | 0,0 |
| tylko `GetMaxAcceleration` | **600/600**, 2000 | 0,0 | 0,0 |
| obie łatki | 600/600 | **600,0** | **868,9** |

Zostaje drobne cofanie, bo silnikowe wartości (600 / 4000) nie zgadzają się
z tymi, których używa klient (`NormalSpeed 615`, `Acceleration 2000`) — różnica
prędkości powoduje korekty. Docelowa łatka ma podmieniać wynik **tylko gdy
oryginał zwróci zero**, i to na wartość z atrybutów gry, a nie z silnika.

Narzędzia, które to umożliwiły: `tools/vtable-diff.py` (które metody nadpisano)
i `tools/pulapka-zapisu.py` (pułapka sprzętowa: kto zapisuje pod dany adres).
Ta druga odpowiada na pytanie „kto", na które czytanie pamięci nie odpowiada.

### Gdzie DOKŁADNIE rozchodzą się ścieżki — i że to sprawa BRONI, nie sieci

Pułapkami wykonania (`tools/pulapka-galezi.py`) przeszedłem rozgałęzienia
`GetMaxSpeed` po kolei, porównując w **jednym procesie** komponent postaci hosta
z komponentem serwerowej kopii klienta. Cztery pierwsze warunki dają **ten sam
wynik dla obu**. Rozejście jest dopiero tutaj:

```
0x14177F8D2  call 0x141874570(postać)     ; zwraca TRZYMANĄ BROŃ
0x14177F8D7  test rax,rax
0x14177F8DA  je   0x14177F926             ; brak broni -> ścieżka domyślna
```

| komponent | wynik `0x141874570` | ścieżka | wartość |
|---|---|---|---|
| postać hosta | **NULL** | domyślna `0x14177F9F0` | poprawna prędkość |
| serwerowa kopia klienta | `BP_HandCannon_Medium_C` | zależna od broni `0x14177E610` | **0.000** |

Wartość `0.000` odczytana wprost z `xmm0` po powrocie z `0x14177E610`, osiem
próbek z rzędu, wyłącznie dla komponentu klienta. Wyjście awaryjne na początku
tej funkcji (`0x14177EC72`) **nie jest brane** — zero powstaje w jej normalnym
liczeniu.

**Wniosek z tamtego pomiaru brzmiał: „brak ruchu to skutek stanu broni".
Był PRZEDWCZESNY** — patrz następna sekcja, gdzie przyczyna została rozebrana
do końca i broń okazała się zdrowa.

### PRZYCZYNA WŁAŚCIWA: pusta podręczna mapa atrybutów ruchu (2026-08-10, 22:52)

`DimensionMovementComponent` trzyma pod **`+0xB18`** `TMap` — **nie jest to
właściwość refleksji**, tylko podręczny bufor wartości atrybutów ruchu
(19 wpisów, element 0x48 B, wartość `float` pod `+0x38` elementu). U zdrowego
gracza są tam dokładnie te liczby, których używa ruch:

```
355   615   800   800   265   2000   1.0   0.75   1.0   1.0
0.85  0.4   0.5   0.4   500   586.99   ...
```

Wypełnia ją **`DimensionMovementComponent::OnAttributeUpdate`** — nazwa wzięta
z refleksji (`UFunction` o adresie natywnym `0x141C43530`), a nie zgadnięta;
samo wstawianie do mapy robi `0x14178E1B0`, wołana tylko z tej jednej funkcji.
Czyli bufor napełnia **powiadomienie o zmianie atrybutu**.

Z tej mapy czytają **wszystkie** funkcje limitów ruchu — sprawdzone skanem
odwołań do `+0xB18` na zrzucie obrazu:

| funkcja | rola |
|---|---|
| `0x14177DEC0` | `GetMaxAcceleration` (gniazdo 223) |
| `0x14177F520` | `GetMaxSpeed` (gniazdo 130) |
| `0x14177E610` | ścieżka zależna od broni (celowanie) |
| `0x14177F9F0` | ścieżka domyślna |
| `0x141785750` | mnożnik chodzenia w bok |

Pomiar 22:52, cztery komponenty naraz:

| komponent | wpisów w mapie |
|---|---|
| postać hosta u hosta (`Role=3`) | 19 |
| postać klienta u klienta (`Role=2`) | 19 |
| kopia hosta u klienta (`Role=1`, symulowana) | 19 |
| serwerowa kopia postaci klienta (u hosta) | **0** |

**KOREKTA po powtórzeniu — tego wyniku NIE WOLNO uznać za przyczynę.**
W kolejnym przebiegu (23:06, ta sama konfiguracja) ta sama serwerowa kopia
postaci klienta miała mapę **pełną (19 wpisów) przez całe swoje życie**, aż do
zniknięcia pionka. Szereg czasowy co 2 s nie pokazał ani jednej chwili z zerem.

Różnica między przebiegami: pomiar z zerem padł na moment, gdy zamarły klient
był już rozłączany i pionek szedł do rozbiórki (kilkadziesiąt sekund później
`ASC` tej samej postaci był już `NULL`). Zero mogło więc być objawem **rozbiórki
obiektu**, a nie brakiem inicjalizacji.

Czyli: pojedynczy odczyt zera **nie jest ustaleniem**. Zapisane tu, żeby nikt
nie zaczął od niego następnym razem.

Co z tego zostaje jako **twarda wiedza**: mechanizm liczenia limitów (mapa pod
`+0xB18`, wypełniana przez `OnAttributeUpdate`, czytana przez wszystkie funkcje
limitów). To wystarczy, żeby postawić pomiar rozstrzygający — trzeba tylko
zrobić go tam, gdzie zjawisko naprawdę występuje: **na wyprawie, przy żywym
i ruszającym się kliencie**, bo tylko wtedy `GetMaxSpeed` w ogóle liczy limit
dla tego pionka. Na mapie menu klient zamarza, więc `ServerMove` nie przychodzi
i pomiar mierzy pustkę.

**Dodatkowy argument, że pusta mapa NIE jest przyczyną — z samego kodu.**
W `0x14177E610` sprawdzenie „mapa pusta" jest inlinowane jako `Num` kontra
`NumFreeIndices` (`cmp [rsi+0xB20], [rsi+0xB4C]`, bajty `3b 86 4c 0b 00 00`,
`74 75`), a gałąź „pusta" prowadzi do:

```
0x14177E766  mov   rcx, r15          ; r15 wyzerowane w 0x14177E6E3
0x14177E769  movss xmm12,[rcx+0x38]  ; odczyt spod 0x38
```

Tam samo prowadzą **wszystkie** ścieżki „nie znalazłem klucza". Czyli pusta
mapa albo brak klucza **wywaliłyby grę** (odczyt spod `0x38`), a nie zwróciły
zera. Skoro klient nie pada w tym miejscu, mapa ma klucz — więc zero musi
pochodzić z **wartości**, nie z braku wpisu.

### Jak czytać tę mapę — klucze mają nazwy

Klucz to `FGameplayAttribute`, którego pierwszym polem jest `FString
AttributeName`. Widać to na globalnych kluczach używanych przez funkcje limitów:

| adres klucza | `FString` | używa go |
|---|---|---|
| `0x14644A7D0` | `{wsk, num=12, max=16}` → nazwa 11 znaków | `0x14177E610`, wartość bazowa (`xmm12`) |
| `0x14644A950` | `{wsk, num=28, max=32}` → 27 znaków | `0x14177E610`, człon celowania |
| `0x14644AA10` | `{wsk, num=15, max=16}` → 14 znaków | `0x141785750`, chodzenie w bok |

Układ elementu mapy: klucz od `+0x00`, **wartość `float` pod `+0x38`**,
`HashNextId` pod `+0x40` (kod chodzi po łańcuchu przez `[element+0x40]`),
element `0x48`.

`tools/stan-gracza.py` wypisuje teraz tę mapę **z nazwami atrybutów**, więc
następne porównanie host↔klient będzie po nazwach, a nie po liczbie wpisów.
To ta sama lekcja co przy zdolnościach: **liczba pozycji nie jest pomiarem
zawartości**.

### Kiedy `GetMaxSpeed` zwraca zero — pełna mapa gałęzi

Rozebrane z deasemblacji całej funkcji (`0x14177F520`), z literałami:

```
sprawdz "Cheat.SpeedBoost"                      -> jesli tak, wartosc cheatu
sprawdz "State.Player.Sliding"                  -> predkosc slizgu
sprawdz "State.Player.Running" (ASC postaci)    -> 0x14177EE40 (bieg)
    |
    v  (nie biegnie)
0x14177F8C6  call 0x14178AE70    ; znacznik "Status.Movement.Blocked.Normal"
    tak -> 0x14177F926
    nie -> 0x14177F8D2  call 0x141874570(postac)  ; trzymana bron
             NULL -> 0x14177F926
             bron -> 0x14177E610 (predkosc zalezna od broni)

0x14177F926  call 0x14178B930    ; znacznik "Status.Movement.Blocked.Walk"
    tak -> 0x14177F93F  xorps xmm6,xmm6   ← ZERO, wprost ze znacznika
    nie -> 0x14177F935  call 0x14177F9F0  ; zwykla predkosc chodu
```

**OBALONE pomiarem 01:11** — wszystkie trzy znaczniki są zerem, a limit i tak
wychodzi 0.000 (log niżej). Opis gałęzi zostaje, bo jest poprawny i przydatny;
zerowa jest inna wartość. Reszta tej sekcji to zapis, jak do tego doszliśmy.

Hipoteza brzmiała: znacznik
`Status.Movement.Blocked.Walk` na serwerowej kopii postaci klienta dałby zero
**bez żadnej usterki w atrybutach**. Znaczniki blokady zakłada się zwykle na
czas animacji wejścia do misji albo ekranu ładowania — i przy dołączającym
graczu taki znacznik mógł zostać nieusunięty.

### PRZYCZYNA BRAKU RUCHU — ZNALEZIONA I ZMIERZONA (przebieg 01:11)

Pomiar zrobiony **tam, gdzie zjawisko występuje**: host na wyprawie, klient żywy
i próbujący iść, próbka kontrolna z postaci hosta w tym samym procesie.

Hak przy zerowym limicie pyta o stan **kodem gry**:

```
01:11:29  LIMIT: GetMaxSpeed = 0.000  komponent KLIENT
          mapa atrybutow ruchu: 19 wpisow, wolnych 0   MaxWalkSpeed=600.0
          Blocked.Normal=0  Blocked.Walk=0  Blocked.Running=0
          trzymana bron: NULL (sciezka domyslna)
01:11:31  ...to samo, tylko trzymana bron: BP_HandCannon_Medium_C
```

Zero pada **na obu ścieżkach naraz** — i bez broni, i z bronią — więc przyczyna
jest wspólna dla obu. Wszystkie znaczniki blokady są zerowe, mapa niepusta.

**Rozstrzygnięcie: podręczna mapa ma poprawne KLUCZE, ale wyzerowane WARTOŚCI.**
Trzynaście z dziewiętnastu wpisów:

| atrybut | host | serwerowa kopia klienta |
|---|---|---|
| `Acceleration` | 2000 | **0** |
| `MovementModifier` | 1,0 | **0** |
| `MovementModifierOnTargeting` | 0,75 | **0** |
| `SprintSpeed` | 800 | **0** |
| `SlideSpeed` | 800 | **0** |
| `ForwardMovementModifier` | 1,0 | **0** |
| `BackwardMovementModifier` | 1,0 | **0** |
| `StrafeModifier` | 0,85 | **0** |
| `DashLength` | 500 | **0** |
| `SlowedModifier` / `SnaredModifier` | 0,5 / 0,4 | **0** |
| `OnHitMovementPenalty` | 0,4 | **0** |
| `WaterMovementMultiplier` | 0,5 | **0** |
| `NormalSpeed` | 615 | 615 |
| `WalkSpeed` | 355 | 355 |
| `CrouchSpeed` | 265 | 265 |
| `JumpVelocity` | 586,99 | 586,99 |
| `AirControl` | 0,35 | 0,35 |
| `StaminaMovementModifier` | 0,83 | 0,83 |

`MovementModifier` **mnoży** wynik — i to jedną liczbą tłumaczy, czemu zero
wychodzi na obu ścieżkach naraz.

**A same atrybuty są DOBRE.** W `ASC` klienta: `SprintSpeed = 800`,
`Acceleration = 2000` — tak samo jak u hosta. Zepsuta jest wyłącznie **podręczna
kopia**.

Lista atrybutów do buforowania (`komponent+0xB88`) jest u obu graczy
**identyczna, 19 pozycji** — więc nie chodzi o to, że klient ma inną
konfigurację.

### Kto tę mapę napełnia — i dlaczego u klienta za wcześnie

`DimensionMovementComponent::OnOwnerAbilitySystemLoad` (`0x141C43740`, nazwa
z refleksji) woła `0x14178E6E0`, a ta robi dokładnie trzy rzeczy:

1. dla każdego atrybutu z `komponent+0xB88` (19 poz., element `0x38`) wpisuje do
   mapy wynik `GetNumericAttribute` z ASC (`ASC_vtable+0x5B0`),
2. dla każdego znacznika z `komponent+0xB98` (12 poz.) sprawdza, czy ASC go ma,
   i dopisuje do listy aktywnych (`komponent+0xB68`),
3. rejestruje delegata `&UDimensionMovementComponent::OnAttributeUpdate`
   (literał w jej ogonie, `0x14178E8E2`).

Czyli mapa powstaje **z wartości, jakie ASC ma w tamtej chwili**. U dołączającego
gracza ta chwila wypada, zanim trzynaście atrybutów dostanie wartości — i już
nic tego nie poprawia, bo późniejsze powiadomienia nie przychodzą.

To znowu wzorzec §4, tylko w wersji czasowej: **kolejność, która zawsze wychodzi
dla jedynego gracza, nie wychodzi dla drugiego.**

### Naprawa: ponowne wywołanie własnej synchronizacji gry

Marker `WFCoop_fix_attrs.txt`. Przy zerowym limicie wołamy `0x14178E6E0`
dla tego komponentu — **funkcję gry, po jej własnej liście atrybutów, z jej
własnym `GetNumericAttribute`**. Nie podstawiamy żadnej liczby; wykonujemy pracę,
którą gra i tak wykonuje, tylko wtedy, gdy dane już są.

Bezpieczeństwo powtórki sprawdzone deasemblacją: pętla wypełniająca to
„znajdź-albo-dodaj, potem nadpisz" (idempotentna), a ponowna rejestracja
delegata najwyżej zapisze go drugi raz — procedura obsługi tylko przepisuje
wartość. Wyzwalaczem jest sam objaw, najwyżej **pięć razy na komponent**, z
licznikiem i logiem `przed=/po=`, więc skutek widać wprost.

### KANAŁ DZIAŁA OD KOŃCA DO KOŃCA, ale AKCJA NIE SKUTKUJE (przebieg 16:45)

Pierwszy pełny test `fix_state`. Transport i zastosowanie działają, efektu brak.

```
KLIENT  KANAL: wyslany stan [2] DimensionPlayerRunningState -> Run=1 Crouch=0
KLIENT  KANAL: wyslany stan [5] DimensionPlayerSlidingState -> Run=1 Crouch=1
HOST    KANAL: odebrany stan [5] DimensionPlayerSlidingState -> Run=1 Crouch=1
HOST    KANAL: wyslanych 0, odebranych 8, podanych akcji 8
KLIENT  KANAL: wyslanych 6, odebranych 0, podanych akcji 0
```

**Próba kontrolna przeszła:** zera po przekątnej — host nie wysyła, klient nie
odbiera. Kierunek zaadresowany poprawnie.

**Ale skutku nie ma.** W tym samym oknie limity hosta dla pionka klienta:
`599,8`, `522,8`, `591,0`, `614,9` — **ani razu 800**. Gracz potwierdza:
„bieganie i ślizganie się nie zmieniło".

### Dlaczego — trzy bajty, których nie wypełniamy

Rozbiór `ProcessExternalInputAction` (natywna **`0x1418002E0`**, gniazdo 147)
pokazał, że funkcja czyta ze struktury **pięć** bajtów, nie dwa:

```
0x141800344  movzx eax, byte ptr [rsi+0x38]   ; KeyEvent          — ustawiamy
0x141800351  movzx eax, byte ptr [rsi+0x39]   ; bCustomTriggered  — ustawiamy
0x141800359  movzx eax, byte ptr [rsi+0x3a]   ; ← zostaje zerem
0x141800361  movzx eax, byte ptr [rsi+0x3b]   ; ← zostaje zerem
0x141800369  movzx eax, byte ptr [rsi+0x3c]   ; ← zostaje zerem
```

Refleksja pokazuje tylko dwa pierwsze, bo reszta to zwykłe składowe C++ bez
`UPROPERTY`. Dalej funkcja bierze stan bieżący (`+0x178` → `States`) i oddaje
mu akcję do oceny — czyli o przejściu decyduje stan, a my prawdopodobnie
podajemy mu akcję wyglądającą na „nieaktywną".

### Narzędzie do rozstrzygnięcia — podsłuch prawdziwego wejścia

Zamiast zgadywać trzy bajty: podglądamy, co niesie **prawdziwe** wejście gracza.

`ProcessInputAction` (`0x1418005E0`) nie jest w tablicy metod, więc wyglądało to
na robotę dla trampoliny. Ale całe jej ciało to przekazanie dalej:

```
0x1418005E6  mov  rax,[rcx]
0x1418005EC  call qword ptr [rax+0x4B0]     ; 0x4B0/8 = gniazdo 150
```

Czyli wystarczy podmienić **gniazdo 150** — tak samo tanio jak resztę haków.
Hak (`patchPodsluchWejscia`, marker `log_kanal`) loguje nazwę akcji i bajty
`+0x38..+0x3F`. Napisany i **zbudowany, jeszcze nie uruchomiony**.

### ROZBIÓR OBRAZU 11.08 — trzy bajty PRZESTAJĄ być pytaniem, a pojawia się inne

Zrobione **bez uruchamiania gry** (zasada 16), na zrzucie `obraz/obraz.bin`.
Wynik zmienia plan przebiegu, więc jest tu w całości.

**a) Maszyna stanów ma TRZY tablice metod, nie jedną.** Adres `0x1418002E0`
leży jako dana dokładnie dwa razy, a trzecia klasa **nadpisuje** gniazdo 147:

| tablica | gniazdo 147 (`ProcessExternalInputAction`) | gniazdo 150 (wejście) |
|---|---|---|
| bazowa | `0x1418002E0` | `0x141800F20` |
| pośrednia | `0x1418002E0` | `0x141800D30` |
| **najbardziej pochodna** | **`0x14183CB00`** (woła bazową) | **`0x14183D720`** |

**b) Prawdziwe wejście gracza wchodzi WYŁĄCZNIE gniazdem 150.** `0x14183D720`
nie ma w całym module ani jednego bezpośredniego wołającego (`xref`: 0)
i występuje w obrazie **dokładnie raz jako dana** — jako wpis w tablicy metod
pod `0x14507EF00`. Skoro adres nie pada nigdzie indziej, każde jej wywołanie
musi być wywołaniem wirtualnym przez to gniazdo. To zamyka wątpliwość
z zasady 18: hak na gnieździe 150 **może się odpalić**, a cisza w logu będzie
znaczyła jedno.

**c) Pięć bajtów jest ZMIERZONYCH, nie zgadniętych.** Gra buduje tę strukturę
u siebie w `0x141806FDB`:

```
0x141806FDB  mov dword ptr [rbp+0x1F], 1   ; +0x38=1 (KeyEvent), +0x39..+0x3B = 0
0x141806FE2  mov byte  ptr [rbp+0x23], r15b ; +0x3C = 0   (r15 wyzerowane)
```

Czyli **`bCustomTriggered` jest ZEREM w kodzie samej gry**, a my ustawialiśmy
jedynkę. To była jedyna zgadnięta wartość w całym modzie i **zgadliśmy ją źle**.
Trzy bajty `+0x3A..+0x3C` faktycznie są zerami — ta część hipotezy była dobra.

**d) `memcpy` definicji był BŁĘDEM — podbierał grze licznik odwołań.**
Pod `+0x18`/`+0x20` definicji siedzi `TSharedPtr` (wskaźnik + kontroler
licznika). Widać to w operatorze przypisania `0x1417A3E50`, który dla pola
`+0x10` woła `0x1417A4B30`, a ta robi `inc dword ptr [rbx+8]` (podbicie)
i zwalnia starą wartość. Tymczasem `ProcessExternalInputAction` **zwalnia**
`[param+0x20]` na końcu (`0x14180041B`). Nasz `memcpy` kopiował referencję
bez podbicia, a gra ją oddawała — **każde podanie akcji zabierało definicji
gry jedno odwołanie**. Osiem podanych akcji z przebiegu 16:45 to osiem
zabranych odwołań. Nie wywaliło gry, ale to była mina.

Własność referencji **różni się między gniazdami**, co też trzeba było
sprawdzić, a nie założyć:

| gniazdo | kto zwalnia `[param+0x20]` | skąd wiadomo |
|---|---|---|
| 147 | **funkcja sama** | `0x14180041B` w `ProcessExternalInputAction` |
| 150 | **wołający** | `ProcessInputAction` robi to po powrocie, `0x1418005F2` |

**e) Znaleziona RÓŻNICA, która najlepiej tłumaczy brak przejścia.** Pełna
ścieżka wejścia (`0x141800F20`) robi przed oddaniem akcji stanowi dwie rzeczy,
których `ProcessExternalInputAction` **nie robi**:

```
0x141801001  call 0x1417B8210(this+0x2F8, klucz)   ; BRAMKA: czy to nasza akcja
0x1418010C3  call 0x1417A8A20(this+0x2F8, akcja)   ; ZAPIS stanu wejscia
```

`this+0x2F8` to `TArray` o elemencie **64 B** — tablica stanów wejścia
(co jest w tej chwili trzymane). Jeśli warunek przejścia pyta „czy `Run` jest
**trzymany**", to czyta właśnie ją — a `ProcessExternalInputAction` jej nigdy
nie dotyka. Jedyny wyjątek: pochodne nadpisanie `0x14183CB00` aktualizuje
`+0x2F8`, ale **tylko dla jednej akcji** (`0x14183CCB2`, gałąź porównania
z globalnym `FName` spod `0x14507AE18`, obsługa celowania) — nie dla `Run`.

Bramka porównuje **wartości, nie tożsamość wskaźników** (`0x1417A9740` robi
kopię i woła porównanie `0x1422289A0`), więc kopia wpisu z `InputsToCapture`
ma prawo przejść.

**Co z tego wynika dla łatki** — i to jest zapisane w kodzie:
kopiujemy definicję **operatorem przypisania gry** (`0x1417A3E50`, poprawny
licznik odwołań), bajty bierzemy z **podsłuchu prawdziwego wejścia**
(nie z niczyjego domysłu), a podanie akcji jest **dwustopniowe**: najpierw
gniazdo 147, a jeśli stan się nie zmienił — gniazdo 150, czyli ta sama droga,
którą chodzi człowiek przy klawiaturze. Log mówi wprost, który stopień
zadziałał, więc **jeden przebieg rozstrzyga pytanie, na które inaczej trzeba by
dwóch**.

| nowy adres | co to |
|---|---|
| `0x14183D720` | gniazdo 150 najbardziej pochodnej maszyny stanów — **prawdziwe wejście gracza** |
| `0x14183CB00` | gniazdo 147 tejże — woła bazową `0x1418002E0`, potem obsługa celowania |
| `0x141800F20` | bazowa obsługa wejścia: bramka, zapis `+0x2F8`, oddanie akcji stanowi |
| `0x1417A3E50` | `operator=` definicji akcji (kopia z poprawnym licznikiem odwołań) |
| `0x1417A4B30` | przypisanie `TSharedPtr` pod `+0x18`/`+0x20` definicji |
| `0x1417B8210` | szukanie akcji w tablicy stanów wejścia `+0x2F8` (bramka) |
| `0x1417A8A20` | zapis stanu wejścia do `+0x2F8` (z czasem świata) |
| `+0x2F8` | `TArray` stanów wejścia maszyny stanów, element 64 B |

### ZMIERZONE 18:29 — bajty akcji, i KOREKTA dwóch moich wniosków

Podsłuch odpalił się od razu i złapał wzorzec z wejścia człowieka grającego
na hoście. **To jest odpowiedź na pytanie, które wisiało od poprzedniej sesji:**

```
akcja=Run   KeyEvent=0  bajty +0x38..+0x3F:  00 00 00 01 01 00 00 00
akcja=Run   KeyEvent=1  bajty +0x38..+0x3F:  01 00 00 01 01 00 00 00
akcja=Jump  KeyEvent=0  ...to samo...        00 00 00 01 01 00 00 00
akcja=Dash  KeyEvent=0  ...to samo...        00 00 00 01 01 00 00 00
```

| bajt | wartość | co z tego wynika |
|---|---|---|
| `+0x38` | 0 / 1 | `KeyEvent` — wciśnięcie / puszczenie, zgodnie z oczekiwaniem |
| `+0x39` | **0** | `bCustomTriggered`. Ustawialiśmy **1**. Zgadnięte źle |
| `+0x3A` | 0 | zero, zgodnie z oczekiwaniem |
| `+0x3B` | **1** | **NIE jest zerem** |
| `+0x3C` | **1** | **NIE jest zerem** |

**KOREKTA nr 1.** Poprzednia sesja zapisała, że trzy bajty `+0x3A..+0x3C`
„zostają zerami" i że to jest problem. Połowicznie trafnie: zerem jest tylko
`+0x3A`. Dwa pozostałe niosą jedynki, a my wysyłaliśmy zera — czyli podawana
akcja różniła się od prawdziwej na **trzech** pozycjach naraz
(`+0x39` za dużo, `+0x3B` i `+0x3C` za mało).

**KOREKTA nr 2 — mojego własnego wniosku z deasemblacji, sprzed godziny.**
Wyczytałem z `0x141806FDB` (`mov dword ptr [rbp+0x1F],1`), że gra wpisuje
`KeyEvent=1` i trzy zera, i zapisałem to jako „wartości zmierzone w kodzie gry".
**Pomiar to obala.** Tamto miejsce buduje akcję **syntetyczną** (ścieżka
`State.Lock.Internal` → sztuczne puszczenie `Fire`), a nie akcję z klawiatury —
więc jego wartości nie są wzorcem dla prawdziwego wejścia. Gdyby nie to, że
kod bierze wzorzec z podsłuchu, a zer używa tylko awaryjnie, wdrożyłbym
niepoprawne bajty **z przekonaniem, że są zmierzone**.

Lekcja, ta sama co przy `0x141B242F0`: **deasemblacja mówi, co robi JEDNO
miejsce; nie mówi, czy to miejsce jest reprezentatywne.** Wzorzec bierze się
z zaobserwowanego zachowania, nie z pierwszego znalezionego konstruktora.

**KOREKTA nr 3.** Napisałem wyżej, że prawdziwe wejście gracza obsługuje
najbardziej pochodna tablica metod (`0x14183D720`). Log mówi co innego:

```
WEJSCIE-PODSLUCH: hak na gniazdo 150 zalozony (oryginal 0x141800D30)
```

Maszyna stanów gracza używa tablicy **pośredniej** (gniazdo 150 =
`0x141800D30`), a mimo to prawdziwe wejście przez nią przechodzi — widać je
w logu. Czyli `0x14183D720` należy do innej klasy maszyny stanów (broni albo
przeciwnika), a nie do gracza. Rozumowanie „adres występuje raz jako dana,
więc jest wołany wirtualnie" było poprawne; **przypisanie go do klasy gracza
było zgadnięte** i okazało się nietrafione. Dla łatki to bez znaczenia,
bo `podajAkcje` czyta tablicę metod **z samego obiektu**, a nie z założenia.

**Wzorzec zdrowego gracza** (to, do czego porównamy pionek zdalny):

```
WZORZEC — maszyna 0x7C6785D0 ma InputStates=10, InputsToCapture=10, stan=1
```

Dziesięć pozycji w tablicy stanów wejścia `+0x2F8`, tyle samo co akcji do
przechwycenia. Jeśli serwerowa kopia pionka klienta pokaże tu **0**, to znaczy,
że serwer nie ma czym ocenić wejścia i bramka z `0x1417B8210` odrzuci wszystko,
co podamy.

### ZMIERZONE 18:32 — ścieżka napełniania magazynka u ZDROWEGO gracza

Hak `log_ammo` ze spisem stosu, host solo, start wyprawy:

```
AMUNICJA: CurrentAmmoInClip = 6  dla BP_BoltActionRifle_Light_C  (wolajacy 0x141B243C1)
     stos: ... 0x141B243C1 < 0x1418CACEA < 0x141908730
AMUNICJA: CurrentAmmo = 0        dla BP_BoltActionRifle_Light_C  (wolajacy 0x141B3ACA2)
     stos: 0x141B3ACA2 < 0x1418CACC1 < 0x141908730 < 0x141908106 < 0x1418E72F6 < 0x1418CE928
```

Czyli łańcuch, który wpisuje szóstkę, wygląda tak:

```
0x1418CE928 -> 0x1418E72F6 -> 0x141908106 -> 0x141908730
            -> 0x1418CAAC0 (w niej 0x1418CACEA) -> 0x141B242F0 -> CurrentAmmoInClip = 6
```

Potwierdza to rozbiór z obrazu: `0x141B242F0` ma **dokładnie dwóch**
wołających — `0x1418CACE5` (w `0x1418CAAC0`, droga rozgrywki) i `0x1418D332E`
(w `0x1418D3290`, droga komendy cheatu `RefillAmmo`, wołana z `0x141D583ED`).
Zdrowy gracz idzie **drogą rozgrywki**. To jest wzorzec do porównania: jeśli
u dołączającego gracza tego łańcucha w logu nie będzie, usterka leży
**powyżej** `0x141908730`, a nie w samym zapisie amunicji.

## 3e. DLACZEGO podanie akcji nie mogło zadziałać — z grafu przejść

Przebieg 18:34, dwaj gracze, kanał działa od końca do końca, bajty poprawne
(z podsłuchu), `InputStates=10` **także po stronie serwera**. A mimo to:

```
KANAL: akcja[2] KeyEvent=0  stan 0 -> po147=0 -> gniazdo150 tez nic  (InputStates=10, wzorzec=jest)
KANAL: odebrany stan [2] DimensionPlayerRunningState -> Run=1 Crouch=0
KANAL: wyslanych 0, odebranych 8, podanych akcji 8
```

Czyli **oba** stopnie zawiodły: i `ProcessExternalInputAction`, i pełna ścieżka
wejścia gry. Zera po przekątnej na miejscu (host nie wysyła, klient nie odbiera).

**Powód znaleziony — i nie jest nim ani transport, ani bajty.** Nowe narzędzie
`tools/przejscia.py` wypisuje graf przejść wprost z danych maszyny
(`StateEntries` → `AvailableTransitionsFrom`, nazwy z pola `Name`, czyli
dokładnie to, czego chce `AddTransitionToQueue`):

```
[0] State.Player.Idle       przejsc wychodzacych: 3
      IdleToWalking       Idle -> Walking     warunki: wejscia=0  wlasne=2
      IdleToCrouching     Idle -> Crouching   warunki: wejscia=1  wlasne=2
      IdleToAirborne      Idle -> Airborne    warunki: wejscia=0  wlasne=1

[1] State.Player.Walking    przejsc wychodzacych: 7
      WalkingToRunning.RunPressed   Walking -> Running  warunki: wejscia=1 wlasne=5
      WalkingToSliding              Walking -> Sliding  warunki: wejscia=1 wlasne=3
      ...
```

**Ze stanu `Idle` NIE MA przejścia do `Running`.** Żadnego. Do biegu można
wejść wyłącznie z `Walking`, `Crouching` albo `Airborne`. Serwerowa kopia
pionka klienta siedzi w `Idle` — więc akcja `Run` nie miała tam czego uruchomić
**nawet gdyby dotarła idealnie**. I dotarła idealnie.

To przesuwa usterkę **o jeden krok wcześniej**: serwer nie wchodzi nawet
w `Walking`. A `IdleToWalking` ma `wejscia=0` — **nie zależy od wejścia
w ogóle**, tylko od dwóch warunków własnych (`CustomConditions`). Czyli to nie
jest ściana #2 („serwer nie ma komponentu wejścia"), tylko coś, co te dwa
warunki własne wylicza.

**Co przez to upada:** hipoteza 15 w wersji „wystarczy podać akcję" —
obalona pomiarem, dwustopniowo (147 i 150). Zapisane, bo dwa razy w tym
projekcie wracano do tej samej ślepej uliczki.

**Co z tego wynika dla naprawy.** Gra daje własne API do sterowania maszyną
z zewnątrz: `AddTransitionToQueue(Name TransitionName)` (natywna
**`0x141CB0BD0`**, `BlueprintCallable`). Nazwy przejść są **danymi klasy**,
więc identyczne u obu graczy — nie trzeba ich przesyłać. Serwer zna swój stan
bieżący i dostaje kanałem stan docelowy, więc może sam wyznaczyć **najkrótszą
ścieżkę w grafie przejść** i zakolejkować kolejne kroki po nazwie:

```
klient melduje Running, serwer stoi w Idle
  -> IdleToWalking              (Idle -> Walking)
  -> WalkingToRunning.RunPressed (Walking -> Running)
```

Nadal nie podstawiamy żadnej wartości: podajemy grze **jej własne nazwy przejść
jej własną funkcją**, a o tym, czy przejście dojdzie do skutku, decyduje jej
maszyna.

Adresy i offsety z tego rozbioru:

| co | wartość |
|---|---|
| `AddTransitionToQueue(Name)` | natywna `0x141CB0BD0`, `BlueprintCallable` |
| `IsInStateByTag(Tag)` | natywna `0x141CB2440` — gotowa próba kontrolna |
| `GetCurrentStateTag()` | natywna `0x141CB15A0` |
| maszyna `+0x158` | `StateEntries`, `TArray<DimensionStateEntry>`, element **48 B** |
| wpis `+0x00` / `+0x10` / `+0x20` | `StateTag` / `AvailableTransitionsFrom` / `...To` |
| `DimensionStateTransition` | element **64 B**: `Name +0x00`, `SourceStateTag +0x08`, `TargetStateTag +0x10`, `InputActionConditions +0x18`, `CustomConditions +0x28` |
| `0x1417F3F30` | „czy maszyna ma znacznik X" = **czy `States[+0x178]` JEST stanem o tym znaczniku** |

Ostatni wiersz jest ważny osobno: `GetMaxSpeed` nie czyta żadnej flagi ani
efektu — porównuje **obiekt stanu bieżącego** z obiektem znalezionym po
znaczniku. Dlatego podanie `GameplayEffect` do ASC nic by nie dało, a jedyną
drogą jest prawdziwe przejście maszyny.

### DZIAŁA — potwierdzone w przebiegu 01:24

```
01:24:53  ATRYBUTY: odswiezone (1/5) dla komponentu KLIENT — GetMaxSpeed przed=0.000 po=355.000
01:24:54  ATRYBUTY: odswiezen mapy razem: 1
```

Trzy niezależne potwierdzenia:

| dowód | wynik |
|---|---|
| log `przed=/po=` | `0.000` → `355.000` po **jednym** wywołaniu funkcji gry |
| liczba zerowych limitów w całym przebiegu | **1** (przed naprawą: kilkanaście tysięcy) |
| mapa atrybutów serwer↔klient, po nazwach | **wszystkie 19 wartości identyczne** |
| ruch | serwerowa kopia klienta **przemieszcza się** (przed naprawą `0,0` w każdej osi) |

Jedno wywołanie wystarcza na stałe — licznik zatrzymał się na 1 z 5 dozwolonych,
czyli po odświeżeniu delegat już nadąża i mapa nie psuje się ponownie.

### Co zostało: rozbieżność prędkości w SPRINCIE i ŚLIZGU

Zgłoszenie gracza po naprawie: chodzenie działa, ale **ślizg cofa mocno, sprint
lekko, dash lekko, a zwykły chód przycina ledwo zauważalnie**. Ważne, że korekta
występuje **w każdym stanie** — tylko z różną siłą. To wyklucza wyjaśnienie „psuje
się jedna konkretna zdolność" i wskazuje na coś wspólnego dla całego ruchu.

Pomiar prędkości po obu stronach w tej samej chwili:

| stan | serwer | klient |
|---|---|---|
| zwykły bieg | **510,2** | **332,1** |
| dash | **2500,0** | **2500,0** |

Dash zgadza się co do dziesiętnych — dlatego szarpie najmniej. `510,2` to
dokładnie `NormalSpeed 615 × StaminaMovementModifier 0,83`, czyli serwer liczy
**zwykły bieg**.

Skoro atrybuty są już identyczne po obu stronach, różnica musi siedzieć
w **stanie postaci**. `GetMaxSpeed` wybiera gałąź po znacznikach:

```
"Cheat.SpeedBoost" -> wartosc cheatu
"State.Player.Sliding" -> predkosc slizgu
"State.Player.Running" -> 0x14177EE40 (bieg)
w przeciwnym razie -> sciezka broni albo domyslna
```

### ROZSTRZYGNIĘTE (przebieg 01:35): serwer nie zna stanu sprintu ani ślizgu

Próbkowanie limitu **niezerowego** zwracanego przez serwer dla pionka klienta,
74 próbki, w oknie, w którym gracz **potwierdza sprint i serię ślizgów**:

| wartość | co to znaczy | ile |
|---|---|---|
| `615,0` | `NormalSpeed` — zwykły bieg | 24 (+9 wartości tuż poniżej) |
| `522,8` | `615 × StrafeModifier 0,85` — chód w bok | 26 |
| **`265,0`** | **`CrouchSpeed` — kucanie** | 10 |
| `800` | sprint albo ślizg | **0** |

Serwer **ani razu** nie policzył prędkości sprintu ani ślizgu. Przy ślizgu widzi
samo **kucanie** — kapsuła się replikuje, stan ślizgu nie.

To wprost tłumaczy zgłoszoną kolejność nasilenia korekt:

| stan | klient liczy | serwer liczy | różnica |
|---|---|---|---|
| ślizg | ~800 | **265** | **3×** — cofa najmocniej |
| sprint | 800 | 615 | 23% — cofa lekko |
| dash | 2500 | 2500 | **zgodne** — cofa jak zwykły chód, tylko widoczniej przez prędkość |
| chód | 615 | 615 | ledwo zauważalne |

**Hipoteza A potwierdzona, B odpada** jako główna przyczyna: dash zgadza się co
do dziesiętnych, więc sama symulacja i tor ruchu są zgodne — rozjeżdża się
wyłącznie **prędkość maksymalna wynikająca ze stanu**.

Dlaczego akurat dash działa: **dash jest zdolnością** (`DashGlide_C` na liście
ośmiu zdolności postaci), więc jego aktywacja idzie przez system zdolności i
dociera do serwera. Sprintu i ślizgu **nie ma na tej liście** — to stany
komponentu ruchu, ustawiane z wejścia gracza.

I tu domyka się to z **ścianą #2** (§4b): **serwer nie ma komponentu wejścia
gracza zdalnego** — wejście żyje tam, gdzie siedzi człowiek. Cokolwiek gra
ustawia w obsłudze wejścia, dla pionka zdalnego nie zajdzie po stronie serwera.
Stąd brak znaczników `State.Player.Running` i `State.Player.Sliding`.

### Gdzie te stany mieszkają — ustalone na zrzucie i refleksją

Sprint i ślizg **nie są zdolnościami** i **nie są flagami silnika**. To stany
osobnej maszyny stanów gracza:

```
postac +0x968 = StateMachine  ->  DimensionPlayerStateMachineComponent
```

To dokładnie pole, które `GetMaxSpeed` odpytuje o znaczniki
(`mov rcx,[rsi+0x968]` w `0x14177F8A3`). Maszyna ma sześć stanów, **identycznie
u obu graczy**, i po stronie serwera też jest kompletnie zbudowana:

```
Idle · Walking · Running · Crouching · Airborne · Sliding
```

Obok, w postaci, stoi `RunningGameplayEffectClass` (+0xC28 →
`RunningGameplayEffect_C`) — czyli bieg jest w tej grze osobnym efektem.

**Dlaczego serwer nigdy nie wchodzi w te stany — trzy fakty:**

| fakt | jak ustalony |
|---|---|
| maszyna ma `InputsToCapture` (**10 pozycji**) — napędza ją WEJŚCIE gracza | refleksja, `+0x130` |
| `DimensionStateMachineComponent` ma **47 funkcji i ZERO RPC** | `ue-funcs.py`; ani jednej flagi `Net*` |
| serwer **nie ma komponentu wejścia gracza zdalnego** | ściana #2, §4b — zmierzone wcześniej |

To jest **siódme wystąpienie wzorca §4** i najczystsze: cały podsystem stanu
gracza jest napisany bez sieci, dokładnie tak jak ekwipunek (§3, „50 funkcji,
zero RPC"). Autorzy umieli replikować — po prostu tego podsystemu nie
replikowali, bo w grze jednoosobowej nie było po co.

### Punkt zaczepienia, który gra sama daje

Wśród 47 funkcji jest **`ProcessExternalInputAction`** (przejściowka
`0x141CB2ED0`, metoda wirtualna w gnieździe **147**) — wejście podające
maszynie akcję **spoza komponentu wejścia**. W całym module **nikt jej nie
woła** (skan `call rel32`: zero wołających), czyli to gotowy, nieużywany punkt
zaczepienia.

Obok są `AddTransitionToQueue`, `IgnoreNextInputActionProcessing`
i `GetCurrentState` — komplet do sterowania maszyną z zewnątrz.

Czego brakuje do naprawy: **transportu**. Gra nie ma czym przesłać stanu
z klienta na serwer, bo nie ma tu ani jednego RPC. To pierwsza z trzech spraw,
w której nie da się „ponownie uruchomić kodu gry" — trzeba dołożyć kanał.
Gracz na to przystał (11.08).

### Projekt kanału — strona STOSOWANIA jest już rozwiązana

Nie trzeba niczego podrabiać, bo `ProcessExternalInputAction` bierze strukturę,
której gotowe egzemplarze gra trzyma u siebie:

| co | ustalone |
|---|---|
| `FInputActionStateDefinition` | **64 B** = 56-bajtowa definicja akcji + `KeyEvent` (+0x38) + `bCustomTriggered` (+0x39) |
| skąd wziąć definicję | `maszyna+0x130` `InputsToCapture`, **10 pozycji po 56 B**, pierwsze 8 bajtów to `FName` |
| co tam jest | `Crouch`, `RunToggle`, **`Run`**, `Jump`, `Targeting`, `Reload`, `Fire`, `LightSpell`, `Melee`, `Healing` |

Czyli: bierzemy **własną definicję gry** (np. `[2] Run`), ustawiamy `KeyEvent`
na wciśnięcie albo puszczenie i oddajemy przez `ProcessExternalInputAction`.
Czy z tego wyjdzie `Running`, czy `Sliding`, rozstrzyga **maszyna stanów gry** —
my podajemy tylko brakujące wejście.

Layout struktury wzięty z refleksji (`tools/sygnatura-funkcji.py`, napisane
w tym celu — pokazuje parametry `UFunction` i rozwija struktury).

### Czego jeszcze brakuje: dwa adresy, i jest na nie pomiar

1. **`UObject::ProcessEvent`** — bez niego klient nie wyśle RPC. Szukanie po
   wzorcach kodu **zawiodło**: przesunięcia `+0xD8` (`UFunction::Func`),
   `+0xB6` (`ParmsSize`) i `+0x58` (`PropertiesSize`) są zbyt pospolite —
   128 kandydatów, żaden rozstrzygający. Szukanie po wspólnym gnieździe
   tablicy metod też nie trafiło.
2. **układ `FFrame`** — gdzie w nim leży bufor parametrów.

**Pierwsze podejście do tego pomiaru było BŁĘDNE — i to jest wynik wart
zapisania.** Założyłem hak na przejściówkę skryptową `ProcessInputAction`
i milczał. Powód ustalony na zrzucie, nie zgadnięty: ta funkcja ma **dwóch
wołających** — przejściówkę (`0x141CB3174`) i **bezpośrednie wywołanie C++**
z kodu wejścia (`0x141807041`). Gra używa tego drugiego, więc przez
`UFunction::Func` nic nie przechodzi.

Lekcja, szersza niż ten przypadek: **`UFunction` istnieje ≠ gra woła ją przez
`UFunction`.** Zanim założysz hak na `Func`, sprawdź na zrzucie, czy prawdziwa
metoda nie ma drugiego, bezpośredniego wołającego. Inaczej cisza w logu jest
dwuznaczna — a to łamie zasadę 14.

Poprawny pomiar (marker `WFCoop_log_kanal.txt`) siedzi na **odbiorze RPC ruchu
u hosta**, bo tu wątpliwości nie ma: odbiór RPC zawsze idzie
`ProcessRemoteFunction` → `ProcessEvent` → `Func`.

- adres powrotu z thunku `ServerMovePacked` → **wnętrze `ProcessEvent`**,
- pole `Locals` w `FFrame` rozpoznajemy **po położeniu, nie po offsecie**:
  `ProcessEvent` alokuje bufor parametrów na własnym stosie, więc `Locals` to
  jedyne pole ramki celujące tuż obok naszego `rsp`.

Kanałem transportowym ma być istniejące RPC klient→serwer. W grze jest ich
**86**; najlepszy kandydat to `DimensionPlayerCharacter::ServerSetInversedScreenRatio`
(**pewne**, jeden parametr `float`) — prawdziwy stosunek ekranu to ~0,5–2,0,
więc wartości powyżej tysiąca są jednoznacznie nasze i da się je odróżnić od
wywołań gry, zamiast je psuć.

### ZMIERZONE (przebieg 02:22) — komplet do zbudowania kanału

```
02:22:13  KANAL: RPC ruchu wykonane z 0x142106F56 — to wnetrze ProcessEvent
02:22:13  KANAL:    pola FFrame celujace w poblize stosu: +0x28 (rsp+544), +0x48 (rsp+944)
```

| co | wartość | jak ustalone |
|---|---|---|
| **`FFrame::Locals`** | **`+0x28`** | jedyne sensowne pole ramki celujące tuż obok `rsp`; **zgadza się z układem `FFrame` w UE 4.27** — dwie niezależne drogi |
| `UFunction::Invoke` | `0x142106ED0` (168 B) | adres powrotu z naszego thunku leży w środku |
| **`UObject::ProcessEvent`** | **gniazdo wirtualne 68** | bazowa wersja `0x1420D38D0` znaleziona w tablicach klas, które jej nie nadpisują (`Texture2D`, `DataTable`) |

Wersja bazowa `0x1420D38D0` rozpoznana po ciele, nie po nazwie: czyta
`PropertiesSize` (`+0x58`), `ParmsSize` (`+0xB6`) dwa razy, testuje
`FUNC_Native` (`+0xB0 & 0x400`) i woła `UFunction::Invoke`.

**`AActor` i `APlayerController` mają WŁASNE nadpisania `ProcessEvent`** (gniazdo
68 wskazuje u nich gdzie indziej), więc wołać trzeba **przez gniazdo**, a nie pod
stały adres — inaczej ominęłoby się logikę aktora.

**Dlaczego wcześniejsze szukanie po wzorcach nie mogło się udać** — warto
zapamiętać: `ProcessEvent` **nie woła `Func` bezpośrednio**. Robi to
`UFunction::Invoke`, o poziom niżej. Szukanie „kto woła `[reg+0xD8]`" z definicji
znajdowało więc co innego. A ponieważ `ProcessEvent` jest wirtualna, ma
**jednego** bezpośredniego wołającego w całym module — po liczbie wywołań też
nie dało się jej znaleźć.

### Komplet elementów kanału — wszystkie zmierzone

| element | wartość |
|---|---|
| wysyłka z klienta | `ProcessEvent` (gniazdo **68**) na postaci, funkcja `ServerSetInversedScreenRatio`, bufor 4 B `float` |
| odbiór na serwerze | hak na `UFunction::Func` tego RPC; parametr pod `FFrame+0x28` |
| rozpoznanie „nasze / gry" | wartość ≥ 1000 (prawdziwy stosunek ekranu to ~0,5–2,0) |
| zastosowanie | `ProcessExternalInputAction`, gniazdo **147** maszyny stanów |
| treść | kopia 56-bajtowej definicji z `InputsToCapture` + `KeyEvent` (+0x38) |

### Kanał NAPISANY — marker `WFCoop_fix_state.txt` (czeka na przebieg)

Jeden marker po **obu** stronach; kod sam rozpoznaje rolę.

**Klient** (z wątku gry, nie z pulsu — wysyłka to `ProcessEvent`, czyli kod gry):
znajduje własną postać (`Role == 2`), czyta stan (`maszyna+0x178`) i wysyła
`1000 + indeks`. Wysyła **tylko wtedy, gdy zmienia się para (Run, Crouch)** —
bez tego filtra przejścia `Idle↔Walking` przy każdym kroku zalałyby pewny kanał
RPC kilkudziesięcioma pakietami na sekundę.

**Serwer**: przechwytuje RPC, bierze parametr spod `FFrame+0x28`. Wartość ≥ 999
zjada (nie oddaje grze, więc prawdziwa funkcja RPC zostaje nietknięta),
wyprowadza z niej parę (Run, Crouch) i podaje różnicę względem poprzedniego
stanu przez `ProcessExternalInputAction`.

Odwzorowanie stanu na akcje jest **jedno, wspólne dla obu stron** (żeby nie
mogły się rozjechać) i celowo malutkie — nie odtwarzamy logiki przejść, tylko
mówimy, co gracz trzyma:

| stan | Run | Crouch |
|---|---|---|
| `DimensionPlayerRunningState` | tak | nie |
| `DimensionPlayerSlidingState` | tak | tak |
| `DimensionPlayerCrouchingState` | nie | tak |
| pozostałe | nie | nie |

Zabezpieczenia wbudowane, każde z powodu wcześniejszej wpadki w tym projekcie:

| zabezpieczenie | dlaczego |
|---|---|
| kierunek: sterujemy **tylko pionkiem zdalnym** (kontroler bez `DimensionLocalPlayer`) | u hosta obie postacie mają `Role == 3`, więc rola tego nie rozstrzyga |
| oba gniazda wirtualne sprawdzane, czy wskazują **kod gry** | zasada 4 — offsety weryfikować przed użyciem; skok w nieznane nie zostawiłby śladu w logu |
| wysyłka wyłącznie z **wątku gry** | wołanie kodu gry z obcego wątku kosztowało już raz dzień diagnozy przy travelu |
| liczniki `wyslanych / odebranych / podanych` | zasada 14 — cisza ma znaczyć jedno |

**Próba kontrolna wbudowana:** u hosta licznik `wyslanych` ma zostać **na zerze**
(jego własna postać ma `Role == 3`), a `odebranych` rosnąć. U klienta odwrotnie.

### DOWÓD RUCHEM: serwerowa kopia klienta nie opuszcza `Idle`

Pomiar 01:57, klient zdrowy (po restarcie), gracz aktywnie chodzi, sprintuje
i robi serię ślizgów. Wypisywane tylko zmiany stanu:

| czas | klient u siebie | serwerowa kopia klienta |
|---|---|---|
| 4,1 s | `Running` (v=264) | **`Idle`** (v=231) |
| 5,1 s | `Sliding` (v=**800,0**) | **`Idle`** (v=393) |
| 6,5 s | `Sliding` (v=794) | **`Idle`** (v=615) |
| 9,4 s | `Sliding` (v=774) | **`Idle`** (v=**265,0**) |
| 13,5 s | `Airborne` (v=2500) | **`Idle`** (v=**2500,0**) |
| 22,5 s | `Running` (v=332) | **`Idle`** (v=325) |

```
klient u siebie widzial: Airborne, Idle, Running, Sliding, Walking
serwer widzial pionek klienta w stanach: Idle
```

**Serwerowa kopia nie opuściła `Idle` ani razu w całym pomiarze**, podczas gdy
pionek klienta przeszedł przez pięć stanów. To jest przyczyna szarpania,
potwierdzona ruchem, a nie wywnioskowana z prędkości.

Zwróć uwagę na wiersz `Airborne`: **2500 kontra 2500**. Dash zgadza się nawet
przy zamrożonej maszynie stanów — bo idzie przez system zdolności, nie przez nią.
To osobne, niezależne potwierdzenie, że mechanizmy oparte na zdolnościach
replikują się poprawnie, a nie replikuje się **ten jeden podsystem**.

### Stan bieżący maszyny — offset POTWIERDZONY ruchem

`GetCurrentState` (natywna `0x141CB1480` → prawdziwa metoda `0x1417EDC60`):

```
0x1417EDC60  movsxd rax,[rcx+0x178]     ; indeks stanu biezacego
0x1417EDC67  test / js  -> null
0x1417EDC6B  cmp eax,[rcx+0x150]        ; kontrola zakresu wzgledem States.Num
0x1417EDC76  mov rax,[rcx+0x148]        ; States.Data
0x1417EDC7D  mov rax,[rax+rdx*8]
```

Czyli stan bieżący to **indeks `int32` pod `+0x178`**, a nie wskaźnik — dlatego
skan po wskaźnikach nic nie znalazł.

**Potwierdzone ruchem** (pomiar wyżej): pionek klienta przechodzi przez pięć
różnych stanów, więc pole żyje i wskazuje to, co trzeba.

Dwa wcześniejsze przebiegi pokazywały `Idle` wszędzie i **nie były pomiarem** —
w jednym gracza nie było przy klawiaturze, w drugim klient był **zapauzowany
i przez to zawieszony**. Lekcja: przy pomiarze stanu upewnić się, że druga
strona naprawdę działa; „wszędzie ta sama wartość" to typowy objaw martwego
pomiaru, nie wynik.

Pomiar do następnego przebiegu jest już w bibliotece: `log_speed` próbkuje teraz
także limity **niezerowe** dla pionka zdalnego (co 600. wywołanie). Odczyt
rozstrzyga wprost — `355` chód, `615` normalna, `800` sprint, ×0,83 przy
nadwątlonej staminie.

---

Rodzina znaczników blokady jest zarejestrowana w jednym miejscu (`0x141788E20`,
596 B) — komponent ruchu zapisuje się tam na powiadomienia o zmianie:

```
Status.Water.Active
Status.Movement.Blocked.Running
Status.Movement.Blocked.Normal
Status.Movement.Blocked.Walk
Status.Movement.Blocked.Crouch
Status.Movement.Blocked.Targeting
```

Stąd biorą się pojemniki `komponent+0xB68` i `+0xB78`, które czytają predykaty.

**Kto znacznik zakłada — nie da się znaleźć w kodzie:** literał
`Status.Movement.Blocked.Walk` ma w całym module tylko **dwa** odwołania
(rejestrację powyżej i predykat), więc zakładanie idzie przez dane
(`GameplayEffect` w zasobach), a nie przez kod. Dlatego to musi zmierzyć hak
w procesie, nie analiza obrazu.

### Co przy tym OBALONE: „broń klienta ma zerowe mnożniki prędkości"

Przewidywanie z rozbioru `0x14177E610` brzmiało: skoro prędkość jest mnożona
przez atrybuty broni (`SpeedMultiplier`, `SpeedMultiplierOnTargeting`,
`StrafeSpeedMultiplier` — literały w `0x141b2a150`, `0x141b2a230`,
`0x141b2a500`), to u klienta któryś z nich będzie zerem. **Pomiar to obalił.**
Serwerowa kopia trzymanej broni klienta:

| pole | wartość |
|---|---|
| `SpeedMultiplier` / `OnTargeting` / `Strafe` | **1.0 / 1.0 / 1.0** (jak u hosta) |
| zestawy atrybutów broni | **5**, komplet |
| zdolności broni | **5**, w tym `AbilityWeaponLoadAmmo_C` |

Czyli broń klienta jest **zainicjowana poprawnie**. Wcześniejsze „brak ruchu to
sprawa broni" było wnioskiem z tego, że ścieżka prędkości akurat przechodzi
przez broń — a przechodzi przez nią u obu graczy. Mnożenie przez 1.0 niczego
nie psuje; zerem jest wartość **bazowa** z pustej mapy.

### Stan broni klienta po stronie serwera — zmierzony

| broń | czyja | `Owner` | `AmmoInClip` |
|---|---|---|---|
| HandCannon `_2147479736` | **host, trzymana** (`MyPawn`) | postać | **6** |
| BoltActionRifle `_2147479716` | host, schowana | kontroler | 0 |
| HandCannon `_2147472739` | **klient, trzymana** (`MyPawn`) | postać | **0** |
| HandCannon `_2147472791` | klient, schowana | kontroler | **6** |
| BoltActionRifle `_2147472717` | klient | kontroler | 94 |
| BoltActionRifle `_2147472769` | klient | kontroler | 244 |

Host ma **dwie** bronie, klient **cztery** — i to jest ten sam podwójny komplet,
który opisano w `BRON.md` (wynik 2), tylko widziany po stronie serwera.
Najważniejsze: **klient trzyma pusty duplikat**, a poprawnie napełniona broń
z sześcioma nabojami leży schowana. To wprost tłumaczy „NO AMMO" i zapętlone
przeładowanie: gracz przeładowuje broń, która nie jest tą z amunicją.

Różnice trzymanych broni (poza tożsamością obiektów), z porównania 152 pól:

| pole | host | klient |
|---|---|---|
| `AttachmentReplication` | `AttachParent` = postać, gniazdo `VB b_Hips_b_RightWeapon`, `AttachComponent` = `Mesh1P` | **`AttachParent = null`, gniazdo `None`** |
| `WeaponFOV` | 110 | **120** |

Czyli broń klienta jest u serwera **nieprzyczepiona do postaci**, choć ma
ustawione `MyPawn` i `Owner`.

### Skąd bierze się podwójny komplet — zmierzone migawką przed/po

`ue-snapshot.py`, różnica obiektów u hosta przed dołączeniem klienta i po nim.
Powstaje **jedna** postać, **jeden** kontroler, **jeden** komponent ekwipunku —
ale **sześć broni**. Duplikacja jest więc w napełnianiu ekwipunku, nie
w tworzeniu postaci.

Rozkład właścicieli tych sześciu (kontroler hosta = `_2147480521`,
kontroler klienta = `_2147460396`):

| broń | `Owner` | amunicja |
|---|---|---|
| HandCannon `_2147460227` | **postać klienta** (trzymana, `MyPawn`) | **0** |
| BoltRifle `_2147460205` | kontroler klienta | 65 |
| HandCannon `_2147460323` | **kontroler HOSTA** | **6** |
| BoltRifle `_2147460301` | **kontroler HOSTA** | 67 |
| HandCannon `_2147460271` | **NULL** | 0 |
| BoltRifle `_2147460249` | **NULL** | 42 |

**Bronie dołączającego gracza trafiają do kontrolera HOSTA**, a jego własna
postać zostaje z pustym egzemplarzem. To dokładnie ten sam wzorzec co §4:
„daj graczowi broń startową" rozwiązuje się na gracza **lokalnego**, bo gra zna
tylko jednego. Dwie bronie zostają w ogóle bez właściciela.

Widać też, że komplety z **poprzedniej** sesji klienta (`_21474727xx`) nie
zostały posprzątane po jego rozłączeniu i również wiszą na kontrolerze hosta —
przy kolejnych dołączeniach będzie ich przybywać.

To spina brak amunicji, „jedną broń zamiast dwóch" i zapętlone przeładowanie
w jedną przyczynę. Naprawa: doprowadzić do tego, żeby broń startowa
dołączającego gracza trafiała do **jego** kontrolera i żeby trzymał ten
egzemplarz, w którym jest amunicja.

### Mechanizm zmierzony co do wywołania: ekwipunek napełniany DWA RAZY

Hak na `SetOwner` (gniazdo 139 w **15** tablicach metod broni — bronie nie mają
wspólnej), logujący wskaźniki i numery instancji. Przebieg 21:18:29, dołączenie
klienta:

```
HandCannon_2147465574 (0x97560040) -> kontroler 0x680F9A00   ← HOSTA
BoltRifle_2147465552  (0x71100040) -> kontroler 0x680F9A00   ← HOSTA
HandCannon_2147465522 (0x91CE0040) -> kontroler 0x8D4CCD00   ← KLIENTA
BoltRifle_2147465500  (0x8D265580) -> kontroler 0x8D4CCD00   ← KLIENTA
HandCannon_2147465522 (0x91CE0040) -> postać klienta 0x9635E390   (wyjęcie)
```

Który kontroler jest czyj — sprawdzone, nie wywnioskowane z kolejności:

| kontroler | `Player` |
|---|---|
| `0x680F9A00` (`_2147480500`) | `DimensionLocalPlayer` → **host** |
| `0x8D4CCD00` (`_2147465648`) | `IpConnection` → **klient** |

**KOREKTA.** Napisałem najpierw, że „pierwszy przebieg oddaje broń kontrolerowi
HOSTA", czyli że gra myli graczy. **To było błędne.** Log łańcucha obiektów
nadrzędnych pokazał, że kod wybiera właściciela **poprawnie** — bierze kontroler,
do którego należy magazyn przedmiotów użyty w danym przebiegu:

```
przebieg 1: wejscie = DimensionItemStorage < DimensionPlayerController_C_2147480517
przebieg 2: wejscie = DimensionItemStorage < DimensionPlayerController_C_2147442211
```

a przynależność sprawdzona osobno: `_2147480517` ma `DimensionLocalPlayer`
(**host**), `_2147442211` ma `IpConnection` (**klient**).

Prawdziwy mechanizm jest inny i prostszy: **dołączenie klienta uruchamia
napełnianie ekwipunku DWA RAZY — raz dla klienta i raz dla HOSTA.** Host dostaje
przez to zbędny, drugi komplet broni.

Stan po dołączeniu (zmierzony):

| broń | właściciel | trzymana | `AmmoInClip` |
|---|---|---|---|
| HandCannon `_2147479732` | postać hosta | **tak** | 6 |
| BoltRifle `_2147479712` | kontroler hosta | nie | 0 |
| **HandCannon `_2147442137`** | **kontroler hosta** | nie | **6** ← nowy duplikat |
| **BoltRifle `_2147442115`** | **kontroler hosta** | nie | **28231** ← nowy duplikat |
| HandCannon `_2147442085` | postać klienta | **tak** | **0** |
| BoltRifle `_2147442063` | kontroler klienta | nie | 219 |

To rozdziela sprawę na **dwie osobne usterki**:

**A. Host dostaje drugi komplet przy każdym dołączeniu.** Jedna z nowych broni
ma amunicję `28231` — wartość bezsensowna, więc napełnianie nie tylko się
powtarza, ale i liczy źle. To jest najlepszy kandydat na przyczynę znikającej
waluty i zaciętego celowania u hosta.

**B. Trzymana broń klienta ma pusty magazynek** (`0`) przy działającym zapasie
(karabin `219`). Stąd pętla przeładowania: próba napełnienia magazynka nie
dochodzi do skutku. Wiąże się to z brakiem dwóch zdolności u dołączającego
gracza (§3a) — ładowanie amunicji jest w tej grze zdolnością.

### Łańcuch wywołań napełniania — prześledzony

Spis stosu w haku `SetOwner`, z filtrem „prawdziwy adres powrotu ma przed sobą
instrukcję `call`" (bez filtra spis wskazywał adres leżący **za** `ret` i wyszedł
z tego fałszywy wniosek):

```
0x14394A86D < 0x141903078 < 0x141903078 < 0x141932583 < 0x14192523B
```

Rozwinięte w nazwy i role:

| adres | co to |
|---|---|
| `0x141923AA0` | funkcja nadrzędna, literał `Type.Item` — obsługa przedmiotów |
| `0x141925236` | wywołuje `0x141932310` jako **trzeci** krok sekwencji (`0x1419326C0`, `0x1419435F0`, `0x141932310`) |
| `0x141932310` | napełnianie ekwipunku; **trzech wołających**, jeden z nich przy napisie **`SaveLoadItemDataContainers`** |
| `0x141903078` | tworzy broń i przypisuje właściciela (kontroler właściciela magazynu) |

Czyli napełnianie ekwipunku jest częścią **wczytywania danych przedmiotów
z zapisu**, a przy dołączeniu klienta cała ta sekwencja leci **dwa razy** — raz
dla magazynu klienta, raz dla magazynu hosta.

### Brakujące ogniwo ZNALEZIONE: `0x141923AA0` to metoda wirtualna magazynu

Skan `call rel32` dawał **zero** wołających i na tym poprzednie dochodzenie
utknęło. Odpowiedź dał zrzut obrazu (`tools/obraz.py`) i pytanie postawione
inaczej — nie „kto ją woła", tylko **„gdzie ten adres leży jako dana"**:

```
0x141923AA0 jako wartosc 8-bajtowa: dokladnie JEDNO wystapienie, 0x145097118
```

Czyli wpis w tablicy metod. Który to obiekt — sprawdzone na żywej grze
przeglądem tablicy obiektów (`*(void**)obj == tablica`): **`DimensionItemStorage`**.

| co | wartość |
|---|---|
| tablica metod | `0x145096E00` (główna) |
| wpis | `0x145097118`, offset **`0x318`** = gniazdo 99 |
| `this` w metodzie | **obiekt + 0x38** — druga tablica metod (dziedziczenie po interfejsie) |
| sygnatura | `void(UDimensionItemStorage*, bool)` — z prologu: `mov r14,rcx`, `movzx ebx,dl`, `cmp bl,1 / jne koniec` |

Przy `flaga != 1` funkcja **nic nie robi** i wraca — to ważne, bo takie
wywołania lecą co 30 s i nie są objawem.

### Podwójne napełnianie POTWIERDZONE hakiem (przebieg 22:50)

Hak na gniazdo 99 (marker `WFCoop_log_fill.txt`, logujący też pierwsze
wywołanie, więc cisza znaczyłaby coś jednoznacznego):

```
22:50:43  #1 magazyn=0x4E3A6D60  flaga=1     ← zdrowy start: JEDNO napelnianie
22:51:13  #2 ten sam magazyn     flaga=2     ← co 30 s, funkcja nic nie robi
22:51:43  #3 ten sam magazyn     flaga=2
22:52:13  #4 ten sam magazyn     flaga=2
--- dolaczenie klienta ---
22:52:38  #5 magazyn=0x4E3A6D60  flaga=1     ← magazyn HOSTA, DRUGI RAZ
22:52:38  #6 magazyn=0x8671CD00  flaga=1     ← magazyn klienta, pierwszy raz
```

Obie sprawy w tej samej sekundzie, obie z tego samego miejsca
(`wolajacy 0x1418D2CC3`), **magazyn hosta jako pierwszy**.

Wołający `0x1418D2CC3` leży w `0x1418D2C30` — pętli, która przechodzi po
**tablicy obiektów** i na każdym woła metody wirtualne z gniazd `8`, `0x20`
i `0x30`. To rozgłoszenie do listy uczestników, a nie wywołanie skierowane do
jednego magazynu. Dlatego dołączenie nowego gracza przeładowuje **wszystkie**
magazyny, w tym magazyn hosta, który był już napełniony.

Rozróżnienie startu od dołączenia widać też w spisie stosu: przy #5 i #6
pojawia się `0x1417EEA2F` (funkcja `0x1417EE8F0`), której **nie ma** przy
zdrowym #1.

### Co to za rozgłoszenie — nazwane z literałów

Pętla `0x1418D2C30` jest wołana z dwóch miejsc, obu w funkcji `0x1419EE860`,
która obsługuje **zadanie zapisu/wczytania z etykietami**:

| literał w `0x1419EE860` | co robi |
|---|---|
| `SaveGameDataForTags` | ścieżka zapisu — woła pętlę z **flagą 2** |
| `LoadGameDataForTags` | ścieżka wczytania — woła pętlę z **flagą 1** |
| `OnObjectSaveLoadTaskFinish` | zakończenie zadania |

To domyka odczyt flagi z haka: **`flaga=1` to wczytanie** (wykonuje pracę),
**`flaga=2` to zapis** (nasza funkcja od razu wraca, `cmp bl,1 / jne`). Wpisy
„co 30 s, flaga=2" w logu to zwykłe autozapisy i nie są objawem.

Wniosek: dołączenie gracza uruchamia zadanie **wczytania**, a to rozgłasza się
po **liście wszystkich zarejestrowanych magazynów**. Magazyn hosta jest w tej
liście, bo zarejestrował się przy własnym wczytaniu i nikt go nie wyrejestrował.
To wzorzec §4 w wersji „za dużo, nie za mało": kod pisany dla jednego gracza
traktuje wczytanie jako zdarzenie **całej gry**, a nie jednego gracza.

### Gdzie dokładnie powstaje duplikat — i dlaczego strażnik ma taki warunek

Napełnianie **zaczyna od wyczyszczenia** `ItemContainers`: `0x141930cc0` na
`this+0x220` (= `magazyn+0x258`, element `0x2a8`, licznik zerowany na końcu).
Czyli **sam magazyn się nie dubluje**. Dublują się **zespawnowane aktory broni**:
stare nie są niszczone, a napełnianie tworzy nowy komplet (`0x141903078`
przypisuje mu właściciela — to widać w logu `WLASCICIEL`).

Stąd warunek strażnika (`WFCoop_fix_dup.txt`): pomijamy przebieg z `flaga=1`
dla magazynu, którego `ItemContainers` **nie jest pusta**. Przy pierwszym
wczytaniu (start solo, dołączający gracz) tablica jest pusta, więc gra działa
jak dotąd; powtórka dla już napełnionego magazynu odpada. Nie podstawiamy
żadnej wartości — pomijamy przebieg, który z definicji jest powtórką.

**POTWIERDZONE w przebiegu 01:11.** Przewidywanie sprawdziło się co do liczby:

```
01:11:29  NAPELNIANIE: POMINIETE powtorne napelnianie #1
          — magazyn 0x50DC3400 (HOST) ma juz 11 przedmiotow
01:11:29  NAPELNIANIE: #4 magazyn=0x57FA93A0 ... KLIENT (IpConnection) flaga=1
01:11:29  NAPELNIANIE: pominietych powtorek: 1
```

Dokładnie **jedno** pominięcie (magazyn hosta), a magazyn klienta napełnił się
normalnie. Zgłoszenie gracza: **„host działa tak jak na singleplayer"** — czyli
znika też utrata widoku pierwszoosobowego i waluty, które przypisywaliśmy tej
samej przyczynie (§3c).

Dwie kontrole, które przy okazji przeszły:

- **podróż między mapami działa.** Wejście hosta na wyprawę tworzy **nowy**
  magazyn (nowy kontroler) i napełnianie przechodzi normalnie — strażnik nie
  blokuje niczego poza powtórką dla tego samego magazynu,
- **autozapisy nietknięte** — lecą z `flaga=2` i nasza funkcja i tak od razu
  wraca.

Czego jeszcze brakuje: **próby kontrolnej przez usunięcie markera** oraz dłuższej
serii (czy przy drugim i trzecim dołączeniu też jest po jednym pominięciu).

Wołający, wszystkie trzy z logu:

| adres | co robi |
|---|---|
| `0x1435B5053` | kod silnika — właścicielem kontroler |
| `0x141903078` | **kod gry** — właścicielem kontroler (to tutaj rozstrzyga się, który) |
| `0x141B32920` | kod gry — właścicielem postać (moment wyjęcia broni) |

Wybór kontrolera robi `0x1418718E0`, wołana z `0x141903067` z argumentem w `rsi`;
funkcja idzie po łańcuchu obiektów nadrzędnych, więc zwraca kontroler wynikający
z tego, **co dostała na wejściu**. Ustalenie, czym jest to wejście w pierwszym
przebiegu, jest ostatnim brakującym ogniwem — i musi to zmierzyć **hak
w procesie**, nie pułapka sprzętowa (patrz zasada 12 w `START-TUTAJ.md`).

**Wynik negatywny, wart zapisania:** `+0xD8` w komponencie maszyny stanów **nie
jest** polem stanu bieżącego — dla broni hosta, broni klienta i broni schowanej
daje ten sam `DimensionWeaponUnequippingState`, a `+0x148` to dane tablicy
`States`. Wcześniejszy odczyt „stan maszyny gracza = RunningState u obu" był tym
samym błędem i **nie dowodzi**, że obie postacie biegły.

## 3d. Amunicja — dwa ślepe tropy zamknięte, zanim kosztowały przebieg

Sprawa amunicji klienta (`CurrentAmmoInClip = 0` przy zapasie 90, „NO AMMO",
zapętlone przeładowanie). Rozbiór na zrzucie obrazu, bez uruchamiania gry.

**Punkt wyjścia — co już wiadomo i czego nie trzeba sprawdzać ponownie:**
broń klienta ma **komplet pięciu zdolności** na własnym ASC, w tym
`AbilityWeaponLoadAmmo_C`, `AbilityWeaponReload_C` i `AbilityWeaponClipRefill_C`.
Hipoteza „brak zdolności" jest więc **zamknięta**.

### `0x141B242F0` NAPEŁNIA magazynek — i historia dwóch pomyłek

Ta pozycja przeszła przez dwa błędne odczyty, oba warte zapisania, bo pokazują
granicę analizy statycznej.

**Odczyt 1 (mój, błędny w drugą stronę):** „kandydat na napełnienie magazynka",
bo funkcja czyta `ClipSize` i pisze do `CurrentAmmoInClip`. Uzasadnienie było
za słabe — sam zapis do pola niczego nie przesądza.

**Odczyt 2 (z rozbioru równoległego, też błędny):** „to ZACISK, nie napełnianie",
bo przed zapisem stoją dwa `minss`:

```
0x141B2435E  minss xmm7, xmm6      ; min(wynik 0x141B25D10, ClipSize)
0x141B2436A  minss xmm6, xmm7      ; min(wynik 0x141B25AA0, powyzsze)
0x141B243BB  call [rdi+0x5a0]      ; zapis do CurrentAmmoInClip
```

Instrukcje odczytane poprawnie — ale **przypisanie, co wchodzi do tych minimów,
było zgadnięte z nazw literałów**, których te funkcje dotykają. Stąd wniosek
„przy magazynku 0 wpisuje z powrotem 0".

**ROZSTRZYGNIĘCIE — POMIAREM** (przebieg 16:32, hak `log_ammo` na gnieździe 180):

```
16:32:00  AMUNICJA: CurrentAmmoInClip = 6  dla BP_BoltActionRifle_Light_C  (wolajacy 0x141B243C1)
```

`0x141B243C1` to instrukcja **tuż za** wywołaniem settera w `0x141B242F0`.
Czyli ta funkcja **wpisała szóstkę** — a więc napełnia magazynek, nie zaciska go.

Dlaczego statyczny odczyt zmylił: `0x141B25AA0` i `0x141B25D10` **nie są
getterami** `CurrentAmmoInClip`. Obie dotykają trzech rzeczy naraz —
`CurrentAmmoInClip`, `CurrentAmmo` **oraz `Cheat.InfiniteClip`** — czyli liczą
„ile brakuje w magazynku" i „ile jest dostępne", a nie zwracają surowego pola.
Nazwa literału mówi, czego funkcja **dotyka**, a nie co **zwraca**.

**Lekcja, ogólniejsza niż ten przypadek:** przy funkcji, która czyta kilka
atrybutów i zwraca jedną liczbę, deasemblacja mówi, JAK liczy, ale nie CO
oznacza wynik. Rozstrzyga dopiero hak na zapis — bo pokazuje wartość i miejsce
naraz.

### ŚLEPY TRÓP 2: „RefillAmmo Invalid Player." to komenda CHEATU

Literał wyglądał na strażnik w stylu §4 i był najlepszym tropem. Okazał się
ciałem **`UDimensionCheatManager::RefillAmmo`** — komendy konsolowej, a nie
kodu rozgrywki. Rozpoznane po tablicy rejestracji funkcji natywnych
(`0x14528DDC0`: para nazwa `0x14527EC18` = `"RefillAmmo"` → funkcja
`0x141DA0C20`, klasa `"UDimensionCheatManager"` pod `0x14528D670`).

Komunikat wybiera jeden warunek: **Pawn kontrolera jest nullem albo nie jest
`ADimensionPlayerCharacter`** (krawędzie `0x141D583AF`, `0x141D583C5`,
`0x141D583CF`). Awaria wcześniejszego ogniwa ma osobny komunikat i osobny blok
(`0x14527DD10`, `0x141D58516`), więc oba człony da się rozróżnić — przydatne,
gdyby kiedyś ta komenda była potrzebna.

Rozpoznanie `RefillAmmo` jako cheatu **potwierdzone niezależnie** (audyt
11.08): `0x14528DDC0` trzyma parę {nazwa `0x14527EC18`, funkcja `0x141DA0C20`},
pod nazwą leży ascii `"RefillAmmo"`, pod `0x14528D670` utf-16
`"UDimensionCheatManager"`, a thunk kończy się `jmp 0x141d58350`. Cały łańcuch
się zamyka.

### Narzędzie: hak `log_ammo` na gnieździe 180

Marker `WFCoop_log_ammo.txt`. Wszystkie zapisy atrybutów idą przez jedno gniazdo
tablicy metod ASC (**180**, offset `0x5A0` — ustalone z `0x141B243BB`), więc
jeden hak łapie wszystkie. Nazwa atrybutu nie jest zgadywana: pierwszym polem
`FGameplayAttribute` jest `FString AttributeName`.

Każdy **adres powrotu logowany RAZ** — chodzi o listę MIEJSC, nie o strumień
wywołań. Tani filtr po samej długości napisu (18 dla `CurrentAmmoInClip`,
12 dla `CurrentAmmo`) idzie przed czytaniem znaków, bo przez to gniazdo
przechodzą też zdrowie, stamina i cała reszta.

Wynik funkcji można pominąć — sprawdzone: na **38** miejsc wywołania żadne nie
używa `xmm0` po powrocie.

**Wzorzec ze zdrowej gry (start wyprawy solo):**

| atrybut | wartość | wołający |
|---|---|---|
| `CurrentAmmo` | 0 | `0x141B3ACA2` |
| `CurrentAmmoInClip` | **6** | `0x141B243C1` (w `0x141B242F0`) |

Metoda dalej: zebrać pełną listę z gry solo (strzał, przeładowanie), potem tę
samą dla broni dołączającego gracza i zobaczyć, **którego adresu brakuje**. To ta
sama droga, która zadziałała przy ruchu: nie zgadywać, gdzie coś powinno się
stać, tylko zobaczyć, gdzie dzieje się u zdrowego gracza.

### POTWIERDZONE POMIAREM 11.08, 23:57 — `fix_czas` działa, blokuje następny warunek

Pierwszy przebieg z markerem `fix_czas`. Odczyt **mapy warunków obu maszyn
w tej samej chwili** (`maszyna+0x110`, 14 pozycji, wpis 16 B: znacznik + `int32`):

| warunek | KLIENT | HOST |
|---|---|---|
| `State.Condition.Player.IsMoving` | **1** | 0 |
| **`State.Condition.Player.HasMovementInput`** | **1** | 0 |
| **`State.Condition.Player.IsOnGround`** | **0** | **1** |
| pozostałe 11 | 0 | 0 |

**To jest rzecz, której nie dało się osiągnąć przez cały projekt.** Warunek,
który przy nadpisywaniu zawsze wracał do zera (1822 zapisy, każdy `przed=0`),
jest teraz liczony przez samą grę jako prawdziwy — bo dostała daną wejściową,
a nie podstawiony wynik.

Liczby z przebiegu: **8093 stempli**, `znacznik 318.438 -> 318.438`,
`|przysp|` do **1660**, próg wieku znacznika **`0.100 s`** (odczytany z
`maszyna+0x494` — stąd stempel MUSI iść co klatkę). `GetMaxSpeed` klienta
przestał być wyłącznie `522,8`/`265`: pojawiły się próbki `615,0`.

**Nowa ściana, konkretna i zmierzona: `IsOnGround = 0`.** Przejście
`IdleToWalking` wymaga OBU warunków, więc maszyna dalej stoi w `Idle`.

`IsOnGround` gra liczy tak (`0x141809E44`–`0x141809E65`):

```
mov  rcx,[maszyna+0x488]   ; pionek
mov  rdx,[rcx]             ; tablica metod pionka
call [rdx+0x638]           ; -> komponent ruchu
mov  rcx,[rax]
mov  rdx,[rcx+0x570]
call rdx                   ; IsMovingOnGround() -> al
movzx esi, al              ; to jest IsOnGround
```

A `IsMovingOnGround()` w UE to po prostu `MovementMode ∈ {Walking, NavWalking}`.
Odczyt refleksją potwierdza wprost:

| pole | KLIENT | HOST |
|---|---|---|
| `MovementMode` (`komponent+0x168`) | **3** (spadanie) | **1** (chodzenie) |
| `GroundMovementMode` | 1 | 1 |
| `MaxWalkSpeed` | 600 | 600 |

**Serwer trzyma pionek klienta w trybie SPADANIA.** To jest następne pytanie:
czemu `MovementMode` nie schodzi do `Walking`. Podejrzenie do sprawdzenia, nie
ustalenie: pionek zdalny nie ma po stronie serwera wyniku sprawdzenia podłoża
albo `UpdatedComponent` nie robi sweepu — obie rzeczy dałyby stałe `Falling`.

### Zgłoszenie gracza z tego przebiegu — trzy objawy, wszystkie spójne z pomiarem

Gracz zgłosił po przebiegu: **broń klienta przeładowywała się w kółko i nie
dodawało amunicji do magazynka**, oraz **ruch dalej cofało**. Oba pasują do
tego, co zmierzono, i jedno z nich jest nowym, mocnym dowodem.

**Przeładowanie w pętli to dowód, że ścieżka przeładowania GRY DZIAŁA dla broni
klienta i mimo to kończy się zerem.** Warunki broni (`ShouldReload`,
`AutoReloadEnabled`) liczy `0x1418480E0` z tego samego ASC broni, z którego
czyta `0x141B242F0`. Magazynek pusty ⇒ `ShouldReload` prawdziwe ⇒ auto-przeładowanie
startuje ⇒ magazynek dalej zero ⇒ warunek znów prawdziwy. Pętla domyka się sama.

To wyklucza „zdolność przeładowania nie dochodzi" i przenosi całe pytanie tam,
gdzie wskazała analiza statyczna: **czy `0x141B39940` w ogóle ustawia
`PendingClipRefill` dla broni klienta, i czy coś ten atrybut konsumuje** (§3g).

**Cofanie ruchu mimo działającego `fix_czas`** jest dokładnie tym, czego należało
oczekiwać po `IsOnGround = 0`: maszyna stoi w `Idle`, sufit prędkości zostaje
przy `522,8`, więc korekty pozycji trwają. `fix_czas` zdjął jedną z dwóch
przeszkód, nie obie — i pomiar mówi to samo co gracz.

### Awaria hosta 23:58 — nowa sygnatura, przyczyny NIE ustalono

`EXCEPTION_ACCESS_VIOLATION reading address 0x148`, `SecondsSinceStart 616`,
sygnatura `abeaa893` — **pierwsze wystąpienie w całym archiwum**. Stos w całości
w kodzie gry, **ani jednej ramki z naszej biblioteki**:

```
0x141A01C6B < 0x1417A938D < 0x1417C04F5 < 0x1418DA5D5 < 0x1418D3279 < 0x1418B3EC6 < ...
```

Ramka `0x1418D3279` leży w **pętli po broniach w ekwipunku** — tej samej, która
pod `0x1418D332E` woła `0x141B242F0` (§3g).

Hipoteza do sprawdzenia, NIE ustalenie: pętla przeładowania bez końca dobija
ścieżkę ekwipunku, aż trafia na nullu `+0x148`. Za tym przemawia zbieżność
miejsca (ta sama funkcja) i objawu (przeładowanie w kółko). Przeciw — nic
jeszcze nie sprawdzono.

**Czego ta awaria NIE obciąża:** `fix_czas` pisze jednego floata pod
`pionek+0xC74` i czyta cztery wskaźniki; z ekwipunkiem nie ma styku, a poprawność
offsetu potwierdza to, że gra policzyła z niego warunek. Rozstrzygnie próba
kontrolna: przebieg **bez** `fix_czas`. Jeśli awaria wróci, marker jest niewinny.

### Lekcja metodyczna z tego samego przebiegu

Pierwszy odczyt logu o 23:54 pokazał **zero wierszy `CZAS:`** i o mało nie
zapisałem „wyzwalacz nie działa". Było to okno pomiaru sprzed zjawiska —
klient dopiero wstawał. Rozstrzygnęło dopiero **próbkowanie szeregu czasowego**
(`tools/probka-ruchu.py`): `Acceleration` bywa niezerowe w 31% próbek, więc
wyzwalacz miał na czym stać. To dokładnie zasada 3, tym razem złapana na czas.

Drugi wniosek: `LIMIT: GetMaxSpeed` w logu **nie jest** dowodem, że gracz się
rusza — ta funkcja liczy sufit co klatkę, także gdy postać stoi.

## 3g. Amunicja — `0x141B242F0` to ZACISK W DÓŁ, nie napełnianie (analiza statyczna)

Ustalone na zrzucie obrazu, **bez uruchomionej gry**; potwierdzone przez
niezależną próbę obalenia, która wyostrzyła sformułowanie.

```
CurrentAmmoInClip := min( CurrentAmmoInClip, ClipSize, CurrentAmmo )
```

**Pierwszy operand minimum JEST polem docelowym.** Dlatego funkcja nie może
NIGDY podnieść magazynka: przy pustym magazynku wynik jest zerem niezależnie
od zapasu 90. To domyka sprawę „powtarzanie wywołania nic nie dało" — nie
mogło dać. I domyka pytanie, czemu `fix_ammo` ma zostać zdjęty.

| adres | rola |
|---|---|
| `0x141B2431A` | literał `ClipSize`; odczyt przez `0x141651D00` (`GetNumericAttribute` na ASC broni `broń+0x958`) |
| `0x141B24351` | `call 0x141B25D10` → składnik A |
| `0x141B2435E` | `minss xmm7, xmm6` |
| `0x141B24362` | `call 0x141B25AA0`, wołana z `edx = 0` |
| `0x141B2436A` | `minss xmm6, xmm7` |
| `0x141B243BB` | zapis przez gniazdo 180 ASC (`[rdi+0x5A0]`), atrybut w `rdx`, wartość w `xmm2` |

**Semantyka obu składników** (obie mają wspólnego strażnika „magazynek == 0
**i** zapas == 0", na którym zwracają stałą `1.0f`):

```
0x141B25D10(broń)      = InfiniteClip ? 1.0f : CurrentAmmoInClip
0x141B25AA0(broń, dl)  = InfiniteClip ? 1.0f : CurrentAmmo      (dl wybiera postać wyniku; wołający daje 0)
```

Znaczniki sprawdzane przez `[ASC+0x120]` → `call [rbx+0x18]`:
`Cheat.InfiniteClip` (`0x1450498E8`), `Status.Weapon.InfiniteClip` (`0x145049910`).

**Czym więc gra naprawdę napełnia magazynek:** `0x141B39940` — wylicza różnicę
`ClipSize − CurrentAmmoInClip`, sprawdza `|różnica| > 1e-8` (czyli „już pełny —
nic nie rób") i ustawia atrybut **`PendingClipRefill`**. `0x141B242F0` jest
wołana dopiero PO niej, jako domknięcie. Dwóch wołających `0x141B242F0`:
`0x1418CACE5` (podniesienie amunicji) i `0x1418D332E` (pętla po ekwipunku).

**Test rozstrzygający dla następnego przebiegu:** wszystkie trzy odczyty idą
przez `0x14088D730`, który przy braku podobiektu zestawu w ASC zwraca `0.0f`.
Więc w logu klienta:

- `ClipSize > 0` → zestaw `DimensionAmmoAttribSet` istnieje, magazynek jest
  naprawdę pusty i szukać trzeba wyżej (czy `0x141B39940` w ogóle się wykonuje
  dla broni klienta),
- `ClipSize == 0` → ASC broni klienta **nie ma zestawu amunicji**, i naprawa
  dotyczy inicjalizacji zestawu, a nie napełniania.

**Czego tu NIE ustalono:** czy gniazdo 180 zapisuje `BaseValue` czy
`CurrentValue`. Od tego zależy, czy ta funkcja jest tylko zaciskiem, czy
zatwierdzeniem wartości bieżącej do bazy.

## 3h. Stamina — regeneracja to GameplayEffect za bramką roli (analiza statyczna)

Ustalone na zrzucie obrazu; cztery twierdzenia przeszły próbę obalenia bez
poprawek. **Pomiaru na żywej grze jeszcze nie było.**

| co | gdzie |
|---|---|
| regeneracja to **okresowy `GameplayEffect`** klasy `UDimensionStaminaRegenEffect`, nie tik komponentu | konstruktor `0x1416BC860` |
| magnituda liczy się z `ActualStaminaRegenSpeed` (atrybut **pochodny**), nie z `StaminaRegenSpeed` | `0x1416BD860`, literał pod `0x1416BDB3D` |
| efekt nakładany jest w **całym obrazie tylko raz** — w inicjalizacji ASC gracza | `0x1418799B0` (gniazdo `+0x8B8`), jedyny wołający `StaticClass` efektu: `0x141879AB5` |
| **bramka roli**: `BeginPlay` obu klas postaci woła tę inicjalizację TYLKO gdy `Role == 3` | `0x14185F12E cmp byte ptr [rsi+0xF0], 3` |
| wygaszanie tagami właściciela: `IgnoreTags = { Status.Stamina.Full.Max, Status.Stamina.Drained }` | `0x1416BCC9C`, `0x1416BCCD4`, kontener kopiowany do `[efekt+0x3F8]` |
| zużycie i opóźnienie regeneracji to osobne ścieżki efektowe | `UseStamina 0x14189FBC0`, `DepleteStamina 0x141867E10`, opóźnienie `0x14185BF90` |

**Korekta liczby, na której stała hipoteza:** `522,8` to `615 × 0,85` (chód
w bok), **a nie** `615 × 0,83` (mnożnik staminy — ten daje `510,2`). Czyli sam
ten pomiar **nie jest** dowodem, że stamina stoi na zerze. Rozróżnienie było
już w tym pliku, w sekcji o rozbieżności prędkości w sprincie.

**Następny pomiar (gdy przyjdzie kolej na staminę):** trampolina na
`0x1418799B0` logująca `rcx` (pionek), `[rcx+0xF0]` (rola), `[rcx+0x528]` (ASC)
i nazwę pionka. Trzy możliwe wyniki: haka nie widać dla drugiego pionka →
serwer nie doszedł do `BeginPlay` albo rola nie była 3 w tej chwili; hak się
odpala z zerowym ASC → inicjalizacja na pustym ASC; hak czysty → problem jest
ZA bramką i przenosi się na `0x141647990` (uchwyt efektu `-1` znaczy, że
bramka autorytetu w `0x140886971` odrzuciła nałożenie).

**Czego tu NIE ustalono:** offsetów pól wewnątrz `UDimensionStaminaAttribSet`
(kod sięga po nie przez `FindProperty` po nazwie, nie przez stały offset), oraz
czy istnieje blueprintowa podklasa efektu nakładana poza ścieżką natywną.

## 3c. Host traci widok pierwszoosobowy przy każdym dołączeniu

**Korekta wcześniejszego wpisu.** Zapisałem to jako „zdarzyło się raz, nie
powtórzyło", opierając się na 48 próbkach `CurrentWeaponIndex = 0`. **To był zły
wskaźnik.** Gracz zgłosił, że dzieje się to ZAWSZE, i zrzut ekranu przyznaje mu
rację: hostowi znika **cały zestaw pierwszoosobowy — ręce razem z bronią** —
przy działającym liczniku `6/84`, liczniku mikstur i pełnym pasku życia.
`CurrentWeaponIndex` tego nie łapie, bo broń pozostaje wybrana; nie jest
rysowana.

Lekcja: **wskaźnik musi mierzyć objaw, a nie sąsiadujący z nim stan.** To już
drugi raz w tym projekcie (poprzednio: `RestartPlayer -> nil`).

Co zmierzone na żywym hoście z bronią niewidoczną na ekranie — i co przez to
**odpada**:

| pole | host (broni nie widać) | klient (broń widać — próbka kontrolna) |
|---|---|---|
| broń `bVisible` / `bHiddenInGame` | True / False | — |
| broń `AttachParent` | `Mesh1P` postaci | — |
| broń `AttachSocketName` | `VB b_Hips_b_RightWeapon` | — |
| broń `Owner` | postać gracza | — |
| `Mesh1P` `bVisible` / `bHiddenInGame` | True / False | **True / False** |
| `Mesh1P` `bOnlyOwnerSee` / `bOwnerNoSee` | True / False | **True / False** |
| postać `Owner` | kontroler hosta | — |
| `LocalPlayers[0].PlayerController` | ten sam kontroler | — |

Czyli **wszystkie pola widoczności, przyczepienia i własności są poprawne
i identyczne z klientem, u którego broń widać**. Przyczyna nie leży w tych
polach — a to jest wynik, bo zamyka całą rodzinę tanich hipotez.

Czego brakuje do rozstrzygnięcia: **porównania „przed i po dołączeniu"**.
Wszystko powyżej to stan końcowy, a on nie mówi, co się zmieniło. `bron-lokalna.py`
zapisuje teraz w każdej próbce surowe bajty pól bitowych `Mesh1P`
(0x63 dla postaci oglądanej lokalnie, 0x43 dla zdalnej kopii) i to, czy siatka
jest przyczepiona — więc następny przebieg sam pokaże chwilę zmiany.

## 4. Wzorzec, który tłumaczy wszystkie awarie hosta

> Obiekt, który **zawsze istnieje dla jedynego gracza**, nie istnieje dla
> drugiego — i jest używany **bez sprawdzenia**.

Trzy wystąpienia, wszystkie potwierdzone deasemblacją:

**a) Boostery** (`0x24`). `DimensionBoosterManager` **nie jest aktorem** —
to `UObject` w `GameInstance`, jeden na proces, bez roli sieciowej. Ekwipunek
jest per postać i przy każdym dodaniu przedmiotu woła `OnItemAddedCallback` do
tego jednego menedżera. Dla przedmiotu drugiego gracza wyszukiwanie
(`0x141911FF0`) nie znajduje wpisu i zwraca **wskaźnik na dane pustej tablicy**,
czyli zero.

```
0x1419CA7AE  call 0x1419B3850  → test rax,rax → je    ; SPRAWDZONY
0x1419CA7CF  call 0x141911FF0  → mov rcx,rax → call   ; NIE sprawdzony
```
Strażnik: `0x1419CA7D4`, wyjście przez własny epilog gry `0x1419CA8FD`.

**b) Wiązanie akcji wejścia** (`0x430`). Łańcuch, przejście po żywych obiektach:
```
broń --[+0x998]--> postać --[+0x258]--> Controller --[+0x348]--> DimensionPlayerInput
```
Serwer **nie ma** komponentu wejścia gracza zdalnego — wejście żyje tam, gdzie
siedzi człowiek. `TWeakObjectPtr::Get` zwraca `nullptr`, wołający nie sprawdza,
a kod robi `lea r11,[rcx+0x428]; movsxd rcx,[r11+8]` → odczyt spod `0x430`.

Funkcja `0x141A1A0C0` ma **14 wołających** z literałami `Dash_Left`, `Dash_Right`,
`Input.Tap`, `LightSpell`, `HeavySpell` — to wiązanie akcji, nie stan zaklęć.
Nic nie zwraca, więc pominięcie przy `rcx == 0` jest bezpieczne.

**c) Zapis profilu przy śmierci** (`0x0C`, tylko droga A). Ramki: parser JSON,
`Init.Player.InventoryComponent.Load`, `StartingFleshLevel`, `_Backup_%d`.

**d) Efekty strzału u klienta** (`0x0`, sygnatura `17fc181f`, 3 wystąpienia).
Ramki nazwane refleksją: `SpawnInstantHitEffects+0x10C` → `SpawnTrailEffect+0x7E`
→ `0x141B59EAD`.

```
0x141B59EA6  mov  rcx,[rsi+0x998]   ; MyPawn
0x141B59EAD  mov  rax,[rcx]         ; ← rcx == 0, NIE sprawdzone
0x141B59EB0  call [rax+0x9C0]
0x141B59EB8  je   0x141B59F35       ; ← wyjście, którego gra sama używa
0x141B59EBA  mov  rcx,[rsi+0x998]   ; TA SAMA wartość...
0x141B59EC1  call 0x1418721A0
0x141B59EC9  test rax,rax / je      ; ...i TU sprawdzona
```

`+0x998` = `MyPawn` — potwierdzone `ue-props.py --klasa DimensionWeapon`, nie
odgadnięte z sąsiedztwa. Pole jest replikowane, ale gdy do klienta przychodzi
multicast efektu strzału broni **hosta**, referencja do pawna jeszcze nie jest
rozwiązana. Strażnik: `0x141B59EA6`, wyjście przez `0x141B59F35`.

To jest trzecie wystąpienie tego samego wzorca — i drugie, w którym **gra
sprawdza tę samą wartość kilka instrukcji dalej**, tylko nie w tym użyciu.

## 5. Późny respawn — dlaczego „nie działał"

`RestartPlayer` **nic nie zwraca** (sygnatura `(Object NewPlayer)`), więc
logowane „`-> nil`" nigdy nie oznaczało błędu. Prawdziwy powód: gdy kontroler
**już ma pawna**, UE tylko go teleportuje. Naprawa: `UnPossess` +
`K2_DestroyActor` przed wywołaniem, potem sprawdzać `pc.Pawn`, nie wynik.

## 5a. Zrzut odszyfrowanego obrazu — analiza kodu bez działającej gry

Sekcja `.text` na dysku jest zaszyfrowana przez SteamStub, więc **każde** pytanie
o kod wymagało dotąd działającej gry: trzy minuty startu plus kliknięcie gracza.
W pamięci kod jest już odszyfrowany, a wystarczy **jeden** zrzut — nawet z gry
stojącej w menu.

```
tools/zrzut-kodu.py          zapisuje obraz exe do obraz/obraz.bin  (109 MB)
tools/obraz.py fun   ADR     deasembluje, z LITERAŁAMI przy `lea rip`
tools/obraz.py xref  ADR     kto woła bezposrednio (call/jmp rel32)
tools/obraz.py dane  ADR     gdzie adres lezy JAKO DANA -> tablice metod
tools/obraz.py gdzie ADR     w ktorej funkcji lezy adres (z .pdata)
tools/obraz.py napis TEKST   literaly ascii i utf-16
```

Dwie rzeczy okazały się kluczowe i warto o nich pamiętać:

1. **`dane`** odpowiada na pytanie, na które `xref` nie odpowiada: „kto woła
   pośrednio". Tak znalazła się klasa i gniazdo `0x141923AA0`.
2. **`gdzie`** czyta granice funkcji z tablicy wyjątków PE (`.pdata`) i **rozwija
   fragmenty** (`UNW_FLAG_CHAININFO`). MSVC tnie funkcje na kawałki i każdy
   kawałek ma własny wpis; bez rozwijania fragment wygląda na osobną funkcję bez
   wołających. Zanim to dołożyłem, wyszło mi z tego fałszywe „docs się mylą" —
   po rozwinięciu okazało się, że łańcuch z 21:18 był opisany poprawnie.

Uwaga o zrzucie: jeśli gra działała z markerami, w obrazie są już **nasze łatki
tablic metod**. Do analizy samej gry robić zrzut z instancji bez markerów
(`WFCoop_no_patch.txt`).

## 6. Adresy potwierdzone

| adres | co to |
|---|---|
| `0x143BEAE56` | `UEngine::LoadMap` (początek funkcji) |
| `0x143BEC200` | `je` pomijające `Listen` — cel łatki |
| `0x143C3ECE0` | `UWorld::Listen` |
| `0x143BFC430` | `FURL::HasOption` |
| `0x1437E9AC0` | `GameEngineTick` — pewny punkt wejścia na wątek gry |
| `0x1418D7600` | `DimensionInventoryComponent::SelectWeapon(int32)` |
| `0x1419CA7A0` | `BoosterManager::OnItemAddedCallback` (prawdziwa metoda) |
| `0x141923AA0` | `DimensionItemStorage` gniazdo 99 (offset `0x318`) — napełnianie ekwipunku; `this` = obiekt+0x38 |
| `0x1418D2C30` | pętla rozgłaszająca po liście magazynów (wołający napełniania) |
| `0x141C43530` | `DimensionMovementComponent::OnAttributeUpdate` — jedyne miejsce, które wypełnia mapę atrybutów ruchu |
| `0x14178E1B0` | wstawianie wpisu do mapy atrybutów ruchu (`komponent+0xB18`) |
| `0x141874570` | „weź trzymaną broń": `Controller is APlayerController ? GetCurrentWeapon(postać+0x960) : null` |
| `0x1418BEFD0` | `GetCurrentWeapon(ekwipunek)` — znacznik `Type.Item.Weapon` pod `CurrentWeaponIndex` |
| `0x141b2a150` / `0x141b2a230` / `0x141b2a500` | atrybuty broni `SpeedMultiplier` / `SpeedMultiplierOnTargeting` / `StrafeSpeedMultiplier` |
| `0x141A1A0C0` | wiązanie akcji wejścia |
| `0x141B7DDE0` | thunk zdarzenia Blueprintu (stary hak; **bywa nie wołany**) |
| `0x146543810` | `GUObjectArray` · `0x1464EA8C0` `FNamePool` |

Offsety: `UStruct::SuperStruct` **`0x40`**, `CurrentWeaponIndex` **`+0x148`**,
`Actor::Role` **`+0xF0`**, `RemoteRole` **`+0x5F`**.

Offsety sprawdzone na żywej grze 10.08 wieczorem (refleksją albo pomiarem, nie
zgadnięte) — wszystkie używa `tools/stan-gracza.py`:

| gdzie | offset | co |
|---|---|---|
| postać | `+0x258` | `Controller` |
| postać | `+0x288` | `CharacterMovement` |
| postać | `+0x528` | `DimensionAbilitySystemComponent` |
| postać | `+0x960` | `DimensionInventoryComponent` |
| kontroler | `+0x298` | `Player` — **jedyne**, co odróżnia hosta (`DimensionLocalPlayer`) od klienta (`IpConnection`) |
| broń | `+0x958` | własny ASC broni |
| broń | `+0x998` | `MyPawn` |
| ASC | `+0x140` | `SpawnedAttributes` (tablica zestawów) |
| ASC | `+0x3D0` / `+0x3D8` | `OwnerActor` / `AvatarActor` |
| ASC | `+0x4F8` | `ActivatableAbilities.Items`, element **`0xE0`**, `Ability` pod `+0x10` |
| komponent ruchu | `+0xB18` | mapa atrybutów ruchu, element **`0x48`**, wartość `float` pod `+0x38` |
| `DimensionWeaponAttribSet` | `+0x350` / `+0x354` / `+0x358` | `SpeedMultiplier` / `OnTargeting` / `Strafe` |
| `DimensionAmmoAttribSet` | `+0x308` / `+0x30C` / `+0x314` / `+0x318` | `ClipSize` / `MaxAmmo` / `CurrentAmmoInClip` / `CurrentAmmo` |
| `DimensionMovementAttribSet` | `+0x310` / `+0x31C` | `SprintSpeed` / `Acceleration` |

---

## Hipotezy OBALONE — nie wracać

| hipoteza | czym obalona |
|---|---|
| Proton / vkd3d / kompilacja shaderów | kolega na Windowsie ma to samo |
| brak VRAM, problem graficzny | 10,3 z 16,3 GB; GPU 25% przy 2 FPS |
| wspólny zapis / Steam Cloud / konto Steam | `IpNetDriver` daje to samo |
| reset profilu przy `Login` | przedmioty zostają |
| nasz wyścig wątków przy `SetClientTravel` | travel starą drogą też dochodzi |
| „host traci sterowanie przy `Login`" | traci przez menu/pauzę |
| łatka na null `AbilityCachedData` | zamieniła awarię na zawieszenie |
| gra przechodzi na mapę przez `OpenLevel` | hak nie odpalił się ani razu w ~70 logach |
| ekwipunek: „broni nie ma / nie jest przyczepiona" | jest i wisi we właściwym gnieździe |
| „to strumieniowanie poziomów dławi klienta" | klient i host mają identycznie 17/7/26 |
| `PendingNetGame` blokuje klienta | ma `NetDriver=null`, nikt nań nie wskazuje |
| strażniki nulla psują pamięć (`0x3d0000000f`) | próba kontrolna: bez nich wraca stara awaria `0x24` |
| `bPauseable` blokuje pauzę w sieci | zmierzone `True` |
| „klient zamarza, bo czeka na dane" | zostawił zrzut — **padł**, nie zamarł |
| „klient ZAMARZA po dołączeniu (zator synchronizacji Wine)" | 16:10: wątek gry klienta w `futex_wait` przy hoście `running`, **zero** tików CPU wątków silnika, `0xC0000005` na stosie uniksowym, świeży zrzut w `Crashes`. Klient **pada**, a zawiesza się dopiero obsługa wyjątku. `WF_NO_FSYNC` nie ma czego naprawiać |
| „łatka broni nie działa na drodze B" | 16:25: działa (`-1 → 0`). Zawodził budżet prób liczony od startu procesu, nie kryterium `Role == 2` |
| „klient nie dostaje komponentu ekwipunku o `Role == 2`" | `bron-lokalna.py` na żywym kliencie: dostaje |
| „`bBlockInput` blokuje ruch klienta" | **próba kontrolna**: host ma tę samą wartość `True` i chodzi |
| przestawianie flag widoczności z zewnątrz | `bHiddenInGame=True` na widocznej broni nic nie dało |
| `EnableInput(broń, PC)` uzbroi broń | zero strzałów po wywołaniu |
| `BindWeaponInputActionPreProcess` uzbroi broń | zero strzałów po wywołaniu |
| „klientowi brakuje dwóch zdolności postaci" | 22:52: wypisane NAZWY — host ma 8 + **dwa duplikaty**, klient ma prawidłowe 8. To host dostaje za dużo |
| „trzymana broń klienta ma zerowe mnożniki prędkości" | 22:52, serwerowa kopia: `SpeedMultiplier`/`OnTargeting`/`Strafe` = **1.0/1.0/1.0**, 5 zestawów atrybutów, 5 zdolności z `AbilityWeaponLoadAmmo_C`. Broń klienta jest zdrowa |
| „brak ruchu klienta to skutek stanu broni" | j.w. — ścieżka prędkości przechodzi przez broń u OBU graczy; zerem jest wartość bazowa z pustej mapy atrybutów ruchu (§3b) |
| „`0x141923AA0` nie ma wołających, bo to delegat" | ma jednego: to metoda wirtualna `DimensionItemStorage`, gniazdo 99. Skan `call rel32` z definicji jej nie widział |

---

# Zamknięte 11.08 (przeniesione z dziennika)

## OBALONE 20:39 — powtorzenie napelniania NIE wystarcza

Trzecia wersja naprawy amunicji dziala mechanicznie i nie dziala skutkiem.
Piec wywolan na WLASCIWEJ broni (trzymany HandCannon pionka zdalnego,
wziety przez `0x141874570`), a magazynek dalej zero:

```
20:39:16  AMUNICJA: CurrentAmmoInClip = 0  dla BP_HandCannon_Medium_C
20:39:17..19  napelniam trzymana bron pionka zdalnego (2/5 ... 5/5)
```

**Co to obala:** hipoteze „funkcja policzyla zero, bo zapasu jeszcze nie bylo,
wiec wystarczy ja powtorzyc". Wczesniejszy pomiar pokazal `CurrentAmmo=90`
przy `CurrentAmmoInClip=0`, wiec zapas BYL — a `0x141B242F0` i tak wpisuje zero.
Czyli ta funkcja NIE liczy po prostu `min(zapas, ClipSize)`; cos jeszcze
rozstrzyga o wyniku i tego czegos brakuje u dolaczajacego gracza.

**Nastepny krok (nie zgadywac dalej):** wejsc do srodka `0x141B242F0` hakiem
i zalogowac WEJSCIA obu `minss` osobno — czyli wyniki `0x141B25D10`
i `0x141B25AA0` — dla broni hosta i dla broni klienta w jednym przebiegu.
Ktora z tych dwoch liczb jest zerem u klienta, ta wskazuje wlasciwa przyczyne.
Obie funkcje dotykaja `CurrentAmmoInClip`, `CurrentAmmo` oraz
`Cheat.InfiniteClip` (`WIEDZA.md` §3d), wiec zgadywanie po nazwach juz raz
zawiodlo.

**Sprint:** w tym przebiegu zero wystapien `GetMaxSpeed = 800` i zero udanych
przejsc, ale klient dolaczyl minute wczesniej i nie ma pewnosci, czy gracz
sprintowal w oknie pomiaru. To NIE jest wynik — to brak pomiaru.


## 21:23 — NADPISYWANIE WARUNKU TO SLEPA ULICZKA (obalone wlasnym pomiarem)

Podtrzymywanie `HasMovementInput` co klatke NIE POMAGA:

```
warunek ruchu ustawiony 1822 razy      <- piszemy w kazdej klatce
licznik przed=0                        <- i za kazdym razem jest juz wyzerowany
odczyt na zywo: HasMovementInput=0  IsMoving=0
maszyna 0 -> 0 nie doszla  droga: 0->1(nie)
```

Zapis DOCHODZI (`przed=0 po=1`), ale maszyna przelicza warunki w swoim tiku
i kasuje nasza wartosc, zanim kolejka przejsc zostanie oceniona. Wyscig
przegrywamy niezaleznie od czestotliwosci — wiec **nadpisywanie WYNIKU nie ma
szans i trzeba znalezc funkcje, ktora ten warunek WYLICZA**.

### Mechanizm kolejki przejsc — rozebrany do konca (i dziala poprawnie)

| co | gdzie |
|---|---|
| `AddTransitionToQueue` (prawdziwa) | `0x1417E1B60` |
| szuka nazwy w tablicy | `maszyna+0x208`, licznik `+0x210`, element **64 B** |
| tablica ma **42 przejscia**, w tym `IdleToWalking` | zmierzone, identyczna u obu graczy |
| po znalezieniu wola | `0x1417E19F0` |
| ta dopisuje do KOLEJKI | `maszyna+0x218`, licznik `+0x220`, element 64 B |
| kolejka jest oprozniana przez tik | zmierzone: licznik zawsze 0 przy odczycie z zewnatrz |

Czyli caly nasz lancuch dziala: nazwa jest znajdowana, przejscie kolejkowane,
kolejka przerabiana. Odrzuca je dopiero OCENA WARUNKOW w tiku — a warunek do
tego czasu jest juz z powrotem zerem.

### ROZSTRZYGNIETE 11.08 wieczorem — patrz sekcja 3f ponizej

Szukanie funkcji wsrod 34 wolajacych `0x14180A350` bylo **oparte na blednym
zalozeniu** i nie moglo sie udac. Rozstrzygniecie, komplet adresow i przyczyna
sa w sekcji **3f**. Czterej kandydaci wypisani tu wczesniej (`0x141885900`,
`0x141885B70`, `0x1418D76B0`, `0x1418DE510`) sa **sprawdzeni i odrzuceni** —
dwaj pierwsi ustawiaja `RunToggled`, dwaj pozostali warunki broni.

## 3f. HasMovementInput — warunek NIE JEST przechowywany, tylko przeliczany ze znacznika czasu

**Zalozenie, ktore kosztowalo dzien:** „funkcja liczaca warunek jest wsrod 34
wolajacych `UpdateCustomConditionBool` (`0x14180A350`)". Jest bledne.

`tools/warunki.py 0x14180A350` mapuje **kazde** z tych 34 wywolan na nazwe
ustawianego znacznika. Wynik: 32 razy warunek **broni**, 2 razy
`State.Condition.Player.RunToggled`. Zadnego warunku ruchu tam nie ma.

Powod: `0x14180A350` to tylko **opakowanie**, ktore sklada strukture parametru
i wola prawdziwego pracownika `0x14180A210`:

```
0x14180A350  sub  rsp,0x38
0x14180A354  mov  [rsp+0x20],rdx      ; znacznik
0x14180A35E  movzx eax,r8b
0x14180A362  mov  [rsp+0x28],eax      ; wartosc
0x14180A36E  call 0x14180A210
```

`tools/warunki.py 0x14180A210` pokazuje wsrod wolajacych **`0x141809CC0`**,
ktora ustawia komplet **osmiu** warunkow ruchu gracza jednym ciagiem:

| adres wywolania | warunek |
|---|---|
| `0x141809D7F` | `IsMoving` |
| **`0x141809E0F`** | **`HasMovementInput`** |
| `0x141809EE3` | `CoyoteTimeEnabled` |
| `0x141809F7A` | `IsOnGround` |
| `0x141809FC4` | `HasRunningInput` |
| `0x14180A0BA` | `HasRunningVelocity` |
| `0x14180A1A1` | `RunToggled` |
| `0x14180A1EF` | `RunToggleEnabled` |

### Z czego liczy sie ten warunek — cala arytmetyka

```
0x141809D84  mov    rcx,[maszyna+0x488]   ; pionek
0x141809D8B  call   0x141871230           ; xmm0 = [pionek+0xC74]   (dwie instrukcje)
0x141809D93  comiss xmm0,0
0x141809D96  jbe    -> ebx = 0            ; znacznik musi byc DODATNI
0x141809DB3  movss  xmm6,[swiat+0x5A0]    ; UWorld::TimeSeconds
0x141809DBB  call   0x141871230
0x141809DC0  subss  xmm6,xmm0             ; wiek znacznika
0x141809DC4  mov    ebx,1
0x141809DC9  comiss xmm6,[maszyna+0x494]  ; prog
0x141809DD0  jbe    -> zostaw ebx = 1     ; wiek <= prog  =>  PRAWDA
0x141809DD2  mov    ebx,r14d              ; inaczej FALSZ
```

Czyli **`HasMovementInput = (znacznik > 0) && (zegar - znacznik <= prog)`**,
gdzie znacznik to jeden `float` pod `pionek+0xC74`. Warunek nigdzie nie jest
przechowywany — dlatego nadpisywanie go bylo z gory przegrane (zasada
„nadpisywanie wyniku funkcji przeliczanej co klatke").

### Kto ten znacznik zapisuje — i dlaczego serwer nie

`tools/pole.py 0xC74 --funkcje` daje dwa zapisy w kodzie postaci, oba
**identycznym ciagiem**:

```
call [vt+0x738]         ; AddMovementInput — LOKALNA obsluga wejscia
call [vt+0x160]         ; AActor::GetWorld
mov  ecx,[swiat+0x5A0]  ; TimeSeconds
mov  [pionek+0xC74],ecx
```

- `0x14187E285` (w `0x14187DFC0`) i `0x14187E60C` (w `0x14187E2B0`) — dwie osie
  wejscia ruchu (przod/tyl i boki: pierwsza czyta wektor spod `[rax+0x00/04/08]`,
  druga spod `[rax+0x10/14/18]`).
- `0x141853CA3` — **konstruktor postaci** (obok literalu `InventoryComponent`)
  ustawia `[pionek+0xC74] = -1.0f`.

Serwer nie wykonuje lokalnej obslugi wejscia dla pionka **zdalnego**, wiec pole
zostaje na `-1.0f` z konstruktora i przegrywa juz na pierwszym warunku
(`znacznik > 0`). Stad maszyna serwera nigdy nie wychodzi z `Idle`, a bez
`Walking` nie ma drogi do `Running` — czyli sufit 522,8 zamiast 800.

### Latka `fix_czas` — i dlaczego wyzwalaczem NIE jest kanal stanu

Stemplujemy `pionek+0xC74` zegarem swiata gry, gdy komponent ruchu ma niezerowe
`Acceleration` (**`komponent+0x22C`**, FVector — offset z instrukcji
`0x1436DB8EA movsd [rbx+0x22c],xmm0`, ktora je zeruje). To sygnal **gry**:
`Acceleration` rozpakowuje ona sama z RPC klienta (zmierzone wczesniej: 2000
i 4000 dla pionka zdalnego).

Kanal stanu (`fix_state`) do wyzwalania **sie nie nadaje**: wysyla tylko przy
zmianie sprintu albo kucania, wiec zwykly chod nie wyzwolilby go ani razu.

Hak wisi w istniejacej przejsciowce `GetMaxSpeed` (gniazdo 130), **przed**
wyjsciem `v > 1.0f` — bo przypadek, ktory nas obchodzi, to limit niezerowy,
ale za niski.

Zabezpieczenia zapisu pod glebokim offsetem: pionek musi byc zdalny (klasa
obiektu `Player` kontrolera **nie** jest `DimensionLocalPlayer`), jego klasa
musi dziedziczyc po `DimensionPlayerCharacter`, a wartosc zastana pod `+0xC74`
musi byc `-1.0f` albo sensownym czasem. Ocena „nie umiem powiedziec" (pionek
bez kontrolera w pierwszych klatkach) **nie jest zapamietywana** — inaczej
latka wylaczylaby sie na cala sesje, a w logu wygladaloby to jak nieudany
wyzwalacz.

## POTWIERDZONE PRZEZ USUNIECIE 21:1x — awarie hosta powodowala naprawa amunicji

Zdjecie markera `fix_ammo` zatrzymalo awarie hosta przy sprincie i slizgu.
Przyczyna: `naprawMagazynekPostaci` wolala `0x141B242F0` bezposrednio,
z sygnatura wziesta z deasemblacji. Marker jest teraz ZDJETY po obu stronach,
wiec amunicja klienta jest znowu zepsuta (pistolet przeladowuje sie w kolko).

Poprawna droga do amunicji: HAK na `0x141B242F0` (trampolina), ktory podglada
wynik, gdy funkcje wola SAMA GRA — nie wolanie jej przez nas.

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

---

## Zamknięte hipotezy 1-18 (przeniesione z dziennika 11.08)

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

