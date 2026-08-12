# Broń — przyczyna ustalona, naprawa działa TYLKO na drodze A

**Stan (2026-08-10): NIEROZWIĄZANE na obowiązującej drodze B.**

Przyczyna jest ustalona i pewna (brak replikacji ekwipunku — patrz niżej).
Naprawa zadziałała **raz**, na porzuconej drodze A: dwa przebiegi różniące się
wyłącznie markerem `WFCoop_fix_weapon.txt` — `logs/bron-pomiar3` (bez, brak
broni) i `logs/bron-naprawa2` (z, broń i celownik na ekranie).

**Na drodze B ta sama łatka nie zadziałała ani razu.** Log klienta w obu
przebiegach (15:11, 15:34): `BRON: poddaje sie po 40 probach` — funkcja
`znajdzEkwipunekLokalny` nigdy nie znalazła postaci o `Role == 2`. To jest
pozycja numer 0 na liście do zrobienia (`START-HERE.md`).

Szczegóły dochodzenia niżej — zostawiam też ślepe uliczki, bo dwie z nich
kosztowały po przebiegu i łatwo w nie wdepnąć drugi raz.

(Odnośniki do `README.md` w tym pliku dotyczą starszej wersji tego dokumentu,
z czasów drogi A.)

---

# Jak do tego doszło

Do tej pory jedyny z trzech problemów **nietknięty pomiarem**. Ten plik opisuje,
co zmierzyłem i czego z tego jeszcze NIE wolno wyciągnąć.

Przebieg: `logs/bron-pomiar1`, scenariusz **A** (mapa misji `Persistent_Town`,
host wchodzi przez `OpenLevel(...listen)`, wszystko automatyczne).
Markery `fix_hands` i `show_bodies` **wyłączone celowo** — przestawiają dokładnie
te flagi, które są przedmiotem pomiaru.

Narzędzia: `tools/bron-stan.py` (sonda), `tools/ue-props.py` (refleksja),
`tools/ue-snapshot.py` (migawka + różnica). Układ struktur przeszedł
`ue-props.py --sprawdz`: pozycja odczytana z pamięci zgadza się **co do
jednostki** z tą, którą mod loguje przez `K2_GetActorLocation`.

---

## Co gra robi z bronią normalnie (próbka kontrolna, host sam)

Gra rozróżnia broń **wyjętą** od **schowanej**, i schowana wygląda identycznie
jak „broni nie ma". To trzeba było zmierzyć, zanim cokolwiek się orzeknie:

| | HandCannon — wyjęta | BoltActionRifle — schowana |
|---|---|---|
| `Owner` | postać gracza | **kontroler**, nie postać |
| `WeaponMesh1Pb` rodzic | `Mesh1P` @ `VB b_Hips_b_RightWeapon` | **odczepiony** |
| `bHiddenInGame` | `False` | `True` |
| `CurrentWeaponIndex` | `0` | — |

Broń ma **dwie** siatki: `WeaponMesh1Pb` (FPP, wisi na `Mesh1P`) i
`WeaponMesh3Pb` (TPP, wisi na `CharacterMesh0`, w pojedynczym graczu ukryta).

## Wynik 1 — broń hosta jest NIETKNIĘTA przez dołączenie

Prognozę „przy `Login` gra rozbraja hosta" **obaliłem własnym pomiarem**.
W pięciu próbkach (przed dołączeniem, w chwili `conn=1`, +5 s, +20 s, +35 s):

- ten sam adres aktora `0x7F995580`,
- `Owner` = postać gracza, `Instigator` = postać gracza,
- `WeaponMesh1Pb` wciąż przyczepiony do `Mesh1P`, to samo gniazdo,
- `bVisible=True`, `bHiddenInGame=False`,
- `CurrentWeaponIndex = 0` przez cały czas.

**Nic się nie zmienia.** Odpada więc „aktor zniszczony" i odpada „odczepiony".

## Wynik 2 — przy `Login` powstaje PODWÓJNY komplet broni

Liczba broni w świecie skacze **2 → 6** dokładnie przy dołączeniu. Powstają:

- komplet dla gracza zdalnego (`Owner` = jego kontroler),
- **drugi komplet dla kontrolera HOSTA** — mimo że host już swoją broń ma.

Wszystkie cztery nowe są w stanie „schowana": odczepione, `bHiddenInGame=True`.
Nie wiem jeszcze, czy to skutek uboczny, czy przyczyna czegokolwiek — ale
to fakt, którego nie dało się zobaczyć z zewnątrz.

## Wynik 3 — SKREŚLONY: to był zgon, nie błąd co-opa

Zmierzyłem u hosta `Owner=null`, `Controller=BRAK`, `RemoteRole` 2→1 i zbudowałem
na tym hipotezę, że dołączenie klienta zrywa posiadanie postaci. **Nieprawda.**
Zrzut ekranu pokazał **„Expedition FAILED"** — hosta zabili przeciwnicy, a to,
co mierzyłem, było **zwłokami**. `Owner=null` to normalny stan martwej postaci.

Zostawiam to zapisane, bo lekcja jest ogólniejsza niż sama pomyłka:

- **Na mapie misji przeciwnicy zabijają hosta w trakcie pomiaru.** To skażenie
  dotyczy KAŻDEGO przebiegu w scenariuszu A i wcześniej nie było nigdzie
  zapisane. Każdy pomiar dłuższy niż minuta jest na tej mapie zagrożony.
- **Bez obrazu z ekranu nie da się odróżnić błędu co-opa od zwykłego zgonu.**
  Dlatego `tools/zrzut.sh` idzie teraz do KAŻDEJ próbki, a skrypt pomiarowy sam
  ostrzega, gdy zobaczy `Owner=null` razem z `Controller=BRAK`.

## Wynik 4 — objaw ZOBACZONY u klienta

Zrzut z okna klienta pokazuje objaw wprost: licznik amunicji **16/180** w rogu,
a w kadrze **ani broni, ani rąk, ani celownika**. Klient renderuje przy tym
**143 FPS** — w scenariuszu A nie zamarza, co zgadza się z `SCENARIOS.md`.

Zmierzony stan tej instancji w tej samej chwili: jedyna postać gracza u klienta
to `Role=1` (SimulatedProxy) kopia postaci HOSTA, `Owner=null`, bez kontrolera.
Jej `Mesh1P` ma `bVisible=False`, a przyczepiona do niej broń — `bVisible=False`,
`bHiddenInGame=True`. Czyli cały zestaw pierwszoosobowy jest wygaszony.

**Ale to jeszcze nie dowód na błąd co-opa**: dla zdalnej postaci ukrycie widoku
pierwszoosobowego jest zachowaniem POPRAWNYM. W tym przebiegu klient nie dostał
własnej postaci (patrz zastrzeżenie niżej), więc nie ma z czym tego porównać.

## Wynik 5 — system ekwipunku NIE MA replikacji. Żadnej.

To najmocniejszy wynik, bo **nie zależy od przebiegu** — jest własnością klas
w tym buildzie, odczytaną refleksją (`tools/ue-funcs.py`). Można go sprawdzić
w dowolnej chwili, także w pojedynczym graczu:

- `DimensionInventoryComponent` ma **50 funkcji i ZERO RPC**. Ani jednej flagi
  `Net`, `NetServer`, `NetClient`, `NetMulticast`.
- Z jego pól replikują się **dwa**, oba odziedziczone z silnika: `bReplicates`
  i `bIsActive`. **`CurrentWeaponIndex` — pole mówiące, którą broń gracz trzyma
  w ręku — nie ma flagi `CPF_Net`.**
- **Przeszukanie wyczerpujące, nie próbka.** W grze jest **203 RPC ogółem**.
  Broni, ekwipunku i amunicji dotyczy **pięć** — i żadne nie wyjmuje broni:

  | klasa | RPC | do czego |
  |---|---|---|
  | `DimensionWeapon` | `Multicast_SimulateWeaponFire` | efekt strzału |
  | `DimensionWeapon` | `Multicast_StopSimulatingWeaponFire` | koniec efektu |
  | `DimensionWeapon` | `ServerSetWeaponFOV` | pole widzenia |
  | `DimensionCharacter` | `ServerSpawnThrowableItem` | rzucany przedmiot |
  | `BPDimensionPlayerCharacter_C` | `Server_ToggleInfiniteAmmo` | cheat |

  Sprawdziłem też osobno klasy, na których RPC w UE zwykle wiszą, bo szukanie
  wyłącznie w komponencie ekwipunku byłoby błędem metody: `DimensionPlayerCharacter`
  i `DimensionPlayerControllerBase`, **z całym dziedziczeniem**. Gra dodała tam
  własne RPC (`ServerSetTargeting`, `Revive`, `ServerSpawnThrowableItem`,
  `MulticastClientPlayCameraShake`, `OnInstigatedDamage`) — czyli znów: **umiała
  i używała**. Wyjmowania broni wśród nich nie ma.

Z tego wynika mechanizm, który tłumaczy objaw w całości:

1. Host wykonuje `SelectWeapon` / `AutoEquipFirstValidWeapon`. Ta funkcja
   przyczepia `WeaponMesh1Pb` do `Mesh1P` i zdejmuje `bHiddenInGame`.
2. Wywołanie jest **czysto lokalne** — nie ma czym polecieć do klienta.
3. Klient nie dostaje ani wywołania, ani wartości `CurrentWeaponIndex`, więc
   **nigdy nie wykonuje kroku „wyjmij broń"**.
4. Sam aktor broni replikuje się normalnie (`bReplicates=True`) i przyczepienie
   też dochodzi — dlatego u klienta broń **jest** i **wisi we właściwym
   gnieździe**, ale z `bVisible=False` i `bHiddenInGame=True`.
5. **Licznik amunicji działa**, bo amunicja siedzi w replikowanym aktorze broni,
   a nie w komponencie ekwipunku. Stąd „HUD zna broń, ale broni nie widać" —
   objaw, który od początku wyglądał na sprzeczność, a jest wprost tego skutkiem.

To nie jest usterka, którą wprowadziliśmy. To gra jednoosobowa, w której
ekwipunku nigdy nie napisano tak, żeby się replikował.

**Kierunek naprawy, jaki z tego płynie:** nie ma sensu szukać, „co psuje broń".
Trzeba **wykonać krok wyjmowania po stronie klienta** — albo wołając u niego
`SelectWeapon`, albo (taniej, na próbę) zdejmując `bHiddenInGame` i ustawiając
`bVisible` na `WeaponMesh1Pb` jego bieżącej broni. Dokładnie tego `fixHands()`
nie robił: on rusza tylko `bOnlyOwnerSee`.

## Czego to NIE tłumaczy i co zmierzyć dalej

1. **Broń klienta w stanie docelowym.** Wynik 4 opisuje instancję, w której
   klient **nie miał własnej postaci**. Pomiar trzeba powtórzyć wtedy, gdy późny
   respawn faktycznie zadziała — dopiero wtedy porównanie „broń hosta (widoczna)
   vs broń klienta (niewidoczna)" cokolwiek znaczy.
2. **Dlaczego `fixHands()` przywracał ręce, a broń nie.** Mam na to kandydata
   z liczbami, ale jeszcze nie sprawdzony ruchem: `fixHands()` zdejmuje
   `bOnlyOwnerSee` i woła `SetVisibility`, ale **nie dotyka `bHiddenInGame`** —
   a zmierzona broń klienta ma `bHiddenInGame=True`. Do tego chodzi wyłącznie po
   komponentach **szkieletowych**, więc celowniki (`RearSight_*`, `FixedSight`)
   i naboje, będące komponentami **statycznymi**, zostają ukryte niezależnie
   od niego. To by tłumaczyło „ręce wracają puste" jednym mechanizmem.
   **Test:** zdjąć `bHiddenInGame` i `bVisible` na `WeaponMesh1Pb` klienta
   i zobaczyć na zrzucie, czy broń wraca.
3. **Po co gra tworzy drugi komplet broni dla hosta** (wynik 2) i czy ekwipunek
   przełącza się na tamten, ukryty, komplet.

## Zastrzeżenie do scenariusza

W tym przebiegu **późny respawn nie zadziałał**: `RestartPlayer -> nil`, drugi
gracz został na `DefaultPawn`, nie dostał prawdziwej postaci. To nie jest stan
opisany w `README.md` jako aktualny („obaj mają prawdziwą postać"). Wyniki 1 i 2
dotyczą broni **hosta** i są ważne niezależnie, ale wynik o stronie klienta
trzeba powtórzyć w przebiegu, w którym drugi gracz naprawdę dostanie postać.

## Kontrola pozytywna dla wyniku 5

Odczyt flagi replikacji sprawdzony na klasach, o których wiadomo z góry, co
mają replikować — żeby „zero replikacji" nie okazało się błędem narzędzia:

| klasa | pola z `CPF_Net` |
|---|---|
| `Actor` | 10 — `ReplicatedMovement`, `Owner`, `Instigator`, `Role`, `RemoteRole`, `bHidden`, `AttachmentReplication`, … (komplet, nic nie brakuje) |
| `Character` | 23 — m.in. `ReplicatedBasedMovement`, `RepRootMotion`, `bIsCrouched`, `PlayerState`, `Controller` |
| `DimensionWeapon` | 15 — w tym **własne** gry: `MyPawn`, `BurstCounter`, `WeaponFOV`, `Properties` |
| **`DimensionInventoryComponent`** | **2 — obie odziedziczone z silnika, gra nie dodała ani jednej** |

Ostatni wiersz zestawiony z przedostatnim jest właściwym argumentem: autorzy
**umieli** replikować i zrobili to w aktorze broni. Ekwipunku po prostu nie
replikowali. To wybór projektowy gry jednoosobowej, nie usterka do naprawienia
u nas — i dlatego nie da się tego „odblokować", trzeba to obejść.


---

# ROZWIĄZANIE

## Przyczyna

Ekwipunek gry **nie ma replikacji**: `DimensionInventoryComponent` — 50 funkcji,
zero RPC; `CurrentWeaponIndex` bez flagi `CPF_Net`; na 203 RPC w całej grze żadne
nie wyjmuje broni. Host wykonuje „wyjmij broń" **lokalnie**, więc klient nigdy
nie robi tego kroku: jego postać ma sprawne ręce, ale `CurrentWeaponIndex = -1`
i żadna broń nie jest do niej przyczepiona.

Licznik amunicji działał, bo amunicja siedzi w **replikowanym aktorze broni**,
a nie w komponencie ekwipunku — stąd pozorna sprzeczność „HUD zna broń, a broni
nie widać", od której zaczęło się całe dochodzenie.

## Naprawa

Nasza DLL po stronie klienta woła **z wątku gry**:

```
UDimensionInventoryComponent::SelectWeapon(ekwipunek_lokalnego_gracza, 0)   @ 0x1418D7600
```

Trzy rzeczy, bez których to nie działa, każda ustalona pomiarem:

1. **Musi to być kod gry, nie zapis do pamięci.** Sprawdziłem tańszy wariant:
   ustawienie `bHiddenInGame=True` na widocznej broni **nie ukryło jej**. UE trzyma
   widoczność w stanie renderera i zmiana wymaga `MarkRenderStateDirty()`.
2. **Musi to być wątek gry.** Wołanie z wątku roboczego to ten sam błąd, który
   wcześniej kosztował dzień przy travelu.
3. **Musi to być punkt, który naprawdę się wykonuje.** Pierwsza próba wisiała na
   thunku zdarzenia Blueprintu — log powiedział wprost „hak nie zostal wywolany
   przez 8 s". Dopiero hak na `GameEngineTick` (co klatkę) zadziałał.

Wybór komponentu: właściciel musi mieć `Role == 2` (AutonomousProxy), czyli być
postacią **lokalnego** gracza. Kopia postaci hosta ma `Role == 1` i jej widoku
pierwszoosobowego ruszać nie wolno — pomylenie tych dwóch sprawiło, że pierwszy
pomiar niczego nie rozstrzygał.

## Wynik zmierzony

| | przed naprawą (`bron-pomiar3`) | po naprawie (`bron-naprawa2`) |
|---|---|---|
| ekran klienta | brak broni i celownika | **broń i celownik są** |
| `CurrentWeaponIndex` | `-1` | `0` |
| `WeaponMesh1Pb` własnej postaci | brak przyczepienia | `Mesh1P @ VB b_Hips_b_RightWeapon` |
| `bVisible` / `bHiddenInGame` | `False` / `True` | `True` / `False` |

Stan po naprawie jest **identyczny ze wzorcem hosta**. Host nietknięty.

## Co ZOSTAŁO z tego wątku

Na zrzucie po naprawie widać komunikat **„NO AMMO"** przy działającym liczniku
`16/180`. Czyli broń jest wyjęta i widoczna, ale jej lokalny stan amunicji nie
jest tym, co pokazuje HUD. To osobna sprawa tej samej natury (co się replikuje,
a co nie) i osobny pomiar — **nie doklejać jej do tego wątku**.
