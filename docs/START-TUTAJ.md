# Zacznij tutaj — przekazanie do następnej sesji

Stan na 2026-08-10, 23:10. Ten plik zastępuje czytanie całej historii.

## Co czytać i w jakiej kolejności

1. **ten plik** — stan, następny krok, zasady pracy,
2. `WIEDZA.md` — wszystko, co ustalone pomiarem: adresy, mechanizmy, offsety,
   oraz **hipotezy obalone z informacją czym** (chroni przed powtórką),
3. `PRZEBIEGI.md` — rejestr zjawisk, jeden wiersz na zjawisko,
4. `DZIENNIK.md` — co jest w toku **teraz**; ten plik prowadzisz na bieżąco,
5. `BRON.md` — dochodzenie do problemu broni jako wzór metody.

`SCENARIUSZE.md` — referencja o ścieżkach wejścia, częściowo dotyczy porzuconej
drogi A.

## Jak to teraz działa (droga B)

Host wchodzi do gry **normalnie** — klika CONTINUE, rusza na wyprawę. Nasza DLL
robi jedną rzecz: zamienia w `UEngine::LoadMap` skok `je` na dwa `NOP`-y
(`0x143BEC200`), przez co gra **sama** woła własne `UWorld::Listen` przy każdym
ładowaniu mapy. Dzięki temu jej sekwencja startu misji nie jest rozbijana.

To zdjęło: brak prawdziwej postaci u klienta (gra daje ją sama) i cały zestaw
objawów wynikających z pominiętej sekwencji startu misji **po stronie hosta**.

Broń u klienta **jest już wyjmowana poprawnie** (patrz „Co jest zrobione").

**Uruchomienie:**
```
tools/stop.sh
WF_GAMESCOPE=1 WF_W=1100 WF_H=620 WF_PREFIX=${WF_PREFIX_ROOT:-$HOME/.local/share/witchfire-mp}/compat1 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
# gracz klika CONTINUE i wchodzi na wyprawę
echo 127.0.0.1 > <Saved compat2>/WFCoop_join_ip.txt
WF_GAMESCOPE=1 WF_PREFIX=${WF_PREFIX_ROOT:-$HOME/.local/share/witchfire-mp}/compat2 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
```

Markery **hosta**: `always_listen`, `fix_booster`, `fix_input`, `fix_dup`,
`fix_attrs`, **`fix_state`**; diagnostyczne: `count_move`, `log_owner`,
`log_fill`, `log_speed`, `log_kanal`. `fix_move` **zdjęty** — patrz niżej.
Markery **klienta**: `join_ip`, `fix_weapon`, `fix_effects`, `fix_dup`,
**`fix_state`**; diagnostyczne: `count_move`, `log_fill`, `log_speed`.

`fix_state` to **kanał stanu ruchu** — jedyna łatka w całym modzie, która dokłada
własny przekaz danych zamiast wołać kod gry. Powód: `DimensionStateMachineComponent`
ma 47 funkcji i **zero RPC**, więc gra nie ma czym przesłać tego stanu. Ten sam
marker po obu stronach; kod sam rozpoznaje rolę.

`log_speed` loguje **pierwsze zero** każdej z funkcji limitu ruchu razem
z rozmiarem mapy atrybutów odczytanym **w tej samej chwili** — to zamyka pytanie
z punktu 1 bez zgadywania, w którą sekundę trafić odczytem z zewnątrz.
Przejściowka melduje też pierwsze wywołanie, więc cisza w logu znaczy
jednoznacznie „zera nie było".

Przebudowa i wdrożenie biblioteki: `tools/wdroz-dll.sh` (buduje, kopiuje do
katalogu gry i porównuje sumy — gra musi być zamknięta).

## NASTĘPNY PRZEBIEG — biblioteka JUŻ WDROŻONA, wystarczy zagrać

Stan na 11.08, 18:25: zbudowana bez ostrzeżeń i skopiowana do katalogu gry
(`md5=33e5aa5b`). Markery ustawione po obu stronach. **Nic nie trzeba
przebudowywać** — trzeba zagrać i zajrzeć do logów.

**Co zmieniono** (wszystko z rozbioru obrazu, `WIEDZA.md` → „ROZBIÓR OBRAZU
11.08"; żadna wartość nie jest zgadnięta):

1. definicja akcji kopiowana **operatorem przypisania gry** — poprzedni
   `memcpy` przy każdym podaniu akcji zabierał grze jedno odwołanie
   `TSharedPtr`,
2. bajty struktury brane z **podsłuchu prawdziwego wejścia gracza**;
   `bCustomTriggered` = 0, bo tyle wpisuje sama gra,
3. podanie akcji **dwustopniowe**: gniazdo 147, a gdy stan nie drgnie —
   gniazdo 150, czyli pełna ścieżka wejścia gry (z bramką i zapisem do tablicy
   stanów wejścia `+0x2F8`, których gniazdo 147 nie robi).

**Czego szukać w logach** (`grep -E 'WEJSCIE-PODSLUCH|KANAL: akcja' log`):

```
WEJSCIE-PODSLUCH: hak na gniazdo 150 zalozony (oryginal 0x14183D720)
      ^ musi byc 0x14183D720. Inny adres = hak siedzi w zlej tablicy metod
        i cisza w logu znaczy co innego niz „gracz nic nie nacisnal"

WEJSCIE-PODSLUCH: akcja=Run  KeyEvent=0  bajty +0x38..+0x3F: 00 00 ...
      ^ wzorzec zlapany; bez tego kanal podaje same zera

KANAL: akcja[2] KeyEvent=0  stan 0 -> po147=2  (InputStates=10, wzorzec=jest)
      ^ ZADZIALALO na gnieździe 147
KANAL: akcja[2] KeyEvent=0  stan 0 -> po147=0 -> gniazdo150 ZADZIALALO
      ^ ZADZIALALO dopiero na pelnej sciezce wejscia
KANAL: ... -> gniazdo150 tez nic   (InputStates=0)
      ^ NIE zadzialalo, a `InputStates=0` mowi dlaczego: serwer nie ma
        czym ocenic wejscia dla pionka zdalnego
```

**Sprawdzian właściwy:** `log_speed` u hosta ma pokazać `GetMaxSpeed = 800`
zamiast `615`/`265`, a gracza ma przestać cofać przy sprincie i ślizgu.

Przy okazji tego samego przebiegu leci pomiar amunicji: hak `log_ammo` ma teraz
**spis stosu**, więc log rozróżni dwie ścieżki prowadzące do `0x141B242F0`
(`0x1418CAAC0` oraz `0x1418D3290`). Szukać `AMUNICJA:` i porównać listę stosów
u hosta z listą u dołączającego gracza — brakujący wpis to miejsce usterki.

## Co jest zrobione

| | dowód |
|---|---|
| **broń u klienta działa na drodze B** | przebieg 16:25: `CurrentWeaponIndex -1 -> 0 (UDALO SIE)` 4 s po dołączeniu, broń na zrzucie. Wcześniejsze „nie działa" było błędem pomiaru: budżet prób liczył się od startu procesu, nie od połączenia |
| **obaj gracze żyją w jednym świecie i widzą się** | klient dołączył 16:25:07 i działał o 16:29:14 (218 FPS); łącznie z kolejnym przebiegiem **ponad dwie godziny wspólnej gry bez awarii**. UWAGA: host **traci** widok pierwszoosobowy i walutę przy dołączeniu — `CurrentWeaponIndex` tego nie łapie i nie wolno go używać jako wskaźnika (`WIEDZA.md` §3c) |
| hostowanie bez wymuszania mapy | port 7777 + `IpNetDriver` w refleksji |
| klient dostaje własną postać `Role=2` | kanały aktorów + kontroler z pawnem |
| późny respawn | `UnPossess`+`K2_DestroyActor` przed `RestartPlayer` |
| ściana #1 (`0x24`, boostery) | **próba kontrolna**: bez strażnika awaria wraca |
| ściana #2 (`0x430`, wiązanie wejścia) | licznik pokazuje przechwycenia; jedno wystąpienie przed łatką |

## Co zostało — w kolejności do zrobienia

Wszystkie trzy sprawy mają **znalezioną przyczynę**; brakuje naprawy.

### 1. Klient nie może chodzić — PRZYCZYNA ROZEBRANA DO KOŃCA, naprawa NIE

`DimensionMovementComponent` trzyma pod `+0xB18` **podręczną mapę atrybutów
ruchu** (19 wpisów: 355, 615, 800, 2000, mnożniki…). Czytają z niej **wszystkie**
funkcje limitów — `GetMaxAcceleration`, `GetMaxSpeed`, ścieżka celowania
i domyślna. Wypełnia ją `DimensionMovementComponent::OnAttributeUpdate`, czyli
powiadomienie o zmianie atrybutu.

**PRZYCZYNA ZNALEZIONA (przebieg 01:11, 11.08).** Podręczna mapa ma poprawne
klucze, ale **13 z 19 wartości wyzerowanych** — przy poprawnych atrybutach
w samym `ASC` klienta (`SprintSpeed=800`, `Acceleration=2000`):

| atrybut | host | kopia klienta |
|---|---|---|
| `Acceleration` | 2000 | **0** |
| `MovementModifier` | 1,0 | **0** |
| `SprintSpeed` | 800 | **0** |
| `NormalSpeed` | 615 | 615 |

`MovementModifier` mnoży wynik, więc jedną liczbą tłumaczy zero **na obu
ścieżkach naraz** (i bez broni, i z bronią — tak było w logu).

Mapę buduje `OnOwnerAbilitySystemLoad` → `0x14178E6E0`, z wartości, jakie `ASC`
ma **w tamtej chwili**. U dołączającego gracza ta chwila wypada za wcześnie.
Wzorzec §4 w wersji czasowej: kolejność, która zawsze wychodzi dla jedynego
gracza, nie wychodzi dla drugiego.

Obalone po drodze: „znacznik `Status.Movement.Blocked.Walk`" (wszystkie trzy
znaczniki zerowe przy limicie 0.000) i „pusta mapa" (pusta mapa dałaby awarię
odczytem spod `NULL+0x38`, nie zero).

**NAPRAWIONE — marker `WFCoop_fix_attrs.txt` działa (przebieg 01:24).**
Przy zerowym limicie wołamy `0x14178E6E0`, czyli **własną synchronizację gry**,
po jej własnej liście atrybutów. Żadnej podstawionej liczby. Wynik:
`przed=0.000 po=355.000`, zerowy limit wystąpił **raz w całym przebiegu**,
mapa serwer↔klient identyczna w 19 z 19 wpisów, a klient **chodzi**.

### 1a. Zostało: serwer nie zna stanu sprintu ani ślizgu — PRZYCZYNA ZNALEZIONA

74 próbki limitu zwracanego przez serwer dla pionka klienta, w oknie
z potwierdzonym sprintem i serią ślizgów: `615,0` (zwykły bieg), `522,8`
(chód w bok), **`265,0` (kucanie)** — i **ani razu `800`**.

| stan | klient | serwer | skutek |
|---|---|---|---|
| ślizg | ~800 | **265** | cofa najmocniej (3×) |
| sprint | 800 | 615 | cofa lekko |
| dash | 2500 | **2500** | zgodne |
| chód | 615 | 615 | ledwo zauważalne |

Dash działa, bo **jest zdolnością** (`DashGlide_C`) i jego aktywacja idzie przez
system zdolności. Sprintu i ślizgu na liście zdolności **nie ma** — to stany
komponentu ruchu ustawiane z wejścia gracza, a **serwer nie ma komponentu
wejścia gracza zdalnego** (ściana #2, `WIEDZA.md` §4b). Stąd brak znaczników
`State.Player.Running` i `State.Player.Sliding` po stronie serwera.

**Ustalone, gdzie te stany mieszkają:** to maszyna stanów gracza
(`postać+0x968` → `DimensionPlayerStateMachineComponent`, sześć stanów: Idle,
Walking, Running, Crouching, Airborne, Sliding). Po stronie serwera jest
zbudowana kompletnie — tylko nigdy nie przechodzi, bo:

- napędza ją **wejście** (`InputsToCapture`, 10 pozycji),
- cały podsystem ma **47 funkcji i ZERO RPC**,
- serwer **nie ma komponentu wejścia gracza zdalnego** (ściana #2).

Siódme wystąpienie wzorca §4, najczystsze z dotychczasowych.

Gra daje gotowy punkt zaczepienia: **`ProcessExternalInputAction`** (gniazdo 147),
w całym module **nie wołana ani razu**. Brakuje tylko **transportu** — i to
pierwsza sprawa, w której nie da się po prostu ponownie uruchomić kodu gry.
Decyzja o dołożeniu kanału należy do gracza.

**Potwierdzone ruchem** (pomiar 01:57): pionek klienta przechodzi u siebie przez
`Walking → Running → Sliding → Airborne`, a **serwerowa kopia nie opuszcza
`Idle` ani razu**. Stan bieżący czytać z `maszyna+0x178` (indeks do `States`
pod `+0x148`).

**Obalone przy okazji:** broń klienta jest zdrowa (mnożniki 1.0, komplet
atrybutów i zdolności), więc wcześniejsze „brak ruchu to sprawa broni" nie
utrzymało się. **Łatka `fix_move` pozostaje odrzucona** — podstawia sufit,
czego gracz słusznie nie chce.

Następny krok: hak licznikowy na `OnAttributeUpdate` (`0x141C43530`) —
przewidywanie: dla postaci hosta ≥19 wywołań, dla postaci klienta **zero**.
Da się zmierzyć **na mapie menu, bez kliknięć gracza**.

### 2. Amunicja klienta — trop przesunięty

Trzymana broń klienta ma `CurrentAmmoInClip = 0` **także po stronie serwera**,
przy zapasie 90. Ale hipoteza „brakuje zdolności ładowania" **odpadła**: broń
klienta ma na własnym ASC komplet pięciu zdolności, w tym `AbilityWeaponLoadAmmo_C`,
i komplet pięciu zestawów atrybutów.

Różnica 10 kontra 8 zdolności **postaci** też odpadła — to host dostaje przy
dołączeniu **dwa duplikaty**, a ósemka u klienta jest liczbą prawidłową
(`WIEDZA.md` §3a, wypisane nazwy).

Ustalone (`WIEDZA.md` §3d):

- **`0x141B242F0` NAPEŁNIA magazynek** — zmierzone hakiem `log_ammo`:
  `CurrentAmmoInClip = 6 (wolajacy 0x141B243C1)`. Przeszło przez dwa błędne
  odczyty statyczne w obie strony; rozstrzygnął dopiero pomiar.
- **`"RefillAmmo Invalid Player."` to komenda CHEATU**, nie kod rozgrywki.
- „brak zdolności" **odpada** — broń klienta ma komplet pięciu.

Następny krok: **hak na gniazdo 180 ASC broni** (offset `0x5A0`, ustawianie
atrybutu), filtrowany po `+0x314`, logujący adres powrotu. **Najpierw SOLO** —
lista adresów z instancji zdrowej jest wzorcem i pokazuje, kto naprawdę wpisuje
6. Potem to samo u dołączającego gracza i porównanie, którego adresu brakuje.
Ta sama metoda, która zadziałała przy ruchu.

### 3. Host dostaje duplikat ekwipunku przy każdym dołączeniu — MECHANIZM ZNALEZIONY

`0x141923AA0` to **gniazdo 99 tablicy metod `DimensionItemStorage`** (ustalone
przez wyszukanie adresu jako danej w zrzucie obrazu i sprawdzenie, który żywy
obiekt ma tę tablicę). Hak na to gniazdo (`WFCoop_log_fill.txt`) pokazał wprost:

```
zdrowy start:   JEDNO napelnianie (flaga=1)
dolaczenie:     DWA w tej samej sekundzie — najpierw magazyn HOSTA, potem klienta
```

Wołający to pętla `0x1418D2C30` **rozgłaszająca po liście magazynów**, wołana
z zadania `LoadGameDataForTags` (`0x1419EE860`). Nowy gracz przeładowuje więc
ekwipunek **wszystkim**, w tym hostowi.

**NAPRAWIONE — strażnik `WFCoop_fix_dup.txt` działa (przebieg 01:11).**
Pomija przebieg z `flaga=1` dla magazynu, którego `ItemContainers` nie jest pusta
(napełnianie samo czyści tę tablicę na starcie, więc niepusta = już napełniony).
Wynik: `pominietych powtorek: 1`, magazyn klienta napełniony normalnie, podróż
hosta na wyprawę nietknięta, a gracz zgłasza: **„host działa tak jak na
singleplayer"**.

Zostało do domknięcia: **próba kontrolna przez usunięcie markera** i sprawdzenie
serii (drugie i trzecie dołączenie w jednej sesji).

### Do potwierdzenia

- **Strażnik ściany #3** (`fix_effects`) zadziałał wreszcie w przebiegu 21:xx
  (`pominiete efekty strzalu bez pawna: 1`), ale nie ma jeszcze próby kontrolnej
  przez **usunięcie** łatki.
- **Stabilność**: ponad dwie godziny wspólnej gry bez awarii. Liczyć serie.

## Narzędzia (wszystkie sprawne, `tools/`)

| narzędzie | do czego |
|---|---|
| `sygnatura.py` | grupuje zrzuty po sygnaturze — **uruchamiać jako pierwsze** |
| `nazwij-ramke.py` | nazywa ramki po adresach natywnych `UFunction` |
| `ue-props.py` | właściwości obiektów przez refleksję, `--sprawdz`, `--drzewo` |
| `ue-funcs.py` | sygnatury `UFunction`, flagi RPC, adresy natywne |
| `ue-objects.py` | wyszukiwanie obiektów, `--isa` po dziedziczeniu |
| `ue-snapshot.py` | migawka 280 tys. obiektów w 0,4 s + różnica |
| `ue-disasm.py`, `find-xref.py`, `find-callers.py` | deasemblacja żywej pamięci |
| `ue-poke.py` | kontrolowana zmiana pola (z kopią do cofnięcia) |
| `bron-stan.py` | sonda broni, stały format do `diff` |
| `zrzut.sh` | zrzut ekranu (Wayland/gamescope) |
| `bron-lokalna.py` | ekwipunek + rola właściciela + stan `Mesh1P`, `--zwiezle` do szeregu czasowego |
| `pomiar-broni.sh` | szereg czasowy obu instancji w jednym pliku |
| `stos-watku.py` | stos żywego wątku Win32 (do zamrożeń, nie awarii) |
| `sygnatura-funkcji.py` | **parametry `UFunction`** — typy, offsety, rozwinięte struktury; bez tego nie da się wywołać kodu gry |
| `obraz.py` | **deasemblacja i szukanie odwołań BEZ działającej gry** — `fun`, `xref`, `dane`, `gdzie`, `napis` |
| `stan-gracza.py` | pełny stan gracza: mapa atrybutów ruchu, zestawy, zdolności, bronie z amunicją i mnożnikami |
| `vtable-diff.py` | **które metody wirtualne gra nadpisała** — 10 zamiast kilkuset |
| `pulapka-zapisu.py` | pułapka sprzętowa: **kto** zapisuje pod dany adres |
| `pulapka-galezi.py` | pułapka wykonania + rejestry: **którą gałąź bierze który obiekt** |
| `wdroz-dll.sh` | build + kopia do gry z porównaniem sum |

## Zasady, które kosztowały przebiegi

1. Nazywać funkcje po adresach natywnych, **nie po sąsiednich literałach**.
2. Instancja pomiarowa musi być **zdrowa i na wyprawie** — hub ma postać, broń
   i kontroler mimo braku wyprawy; sprawdzać liczbę podróży `LOADMAP` (>1).
3. Instancja po awarii drugiej strony jest **popsuta** — nie mierzyć na niej.
4. Offsety kodu maszynowego weryfikować deasemblacją **przed** wdrożeniem.
5. Każda łatka potrzebuje **licznika** — objaw z ekranu wygląda tak samo.
6. **Porównywać sygnatury, nie wrażenia** (`sygnatura.py`).
7. Padnięcie **bez zrzutu** to podejrzenie o własne stanowisko (naprawione
   `setsid`, ale sprawdzać).
8. Hak wstawiany w kod **nie tworzy ramki stosu** — jego brak w stosie niczego
   nie dowodzi.
9. **Menu klika człowiek.** Gra ignoruje syntetyczne kliknięcia i `Enter`.
10. Dopisywać do **istniejącego wiersza** w `PRZEBIEGI.md`, gdy wynik się
    powtórzył.
11. **Pomiar wejścia potrzebuje własnej próbki kontrolnej.** Fokus idzie za
    myszą, a gracz pisze w terminalu — więc pomiar „na zawołanie" mierzy okno
    terminala. Uznawać wynik tylko wtedy, gdy w tej samej serii zmienia się
    `ControlRotation`; inaczej zero znaczy „gra nic nie dostała".
12. **Instancja solo to WZORZEC, nie skrót.** Na niej ustalać adresy, offsety, układ tablic metod oraz **jak gra zachowuje się
    poprawnie** — co dana funkcja zwraca normalnie, jak wygląda zdrowy ekwipunek,
    broń, prędkość. Dopiero znając stan prawidłowy wiadomo, która wartość
    u drugiego gracza jest „dziwna" i co trzeba odtworzyć. Tryb dwóch graczy
    zostawić wyłącznie na to, co bez niego nie istnieje: replikację,
    `ServerMove`, przydział przy `Login`. Sporo pomiarów z 10.08 przepadło, bo
    robiłem je od razu w trybie dwóch graczy, na instancjach już skażonych.
    Nie chodzi o to, żeby instancja solo stale chodziła — ale jeśli akurat stoi
    i jest zdrowa, nie ubijać jej bez potrzeby, bo restart kosztuje kliknięcie
    CONTINUE przez gracza.
13. **Jedna przebudowa na przebieg, nie jedna linia logu na przebieg.** 10.08
    przebudowałem bibliotekę i restartowałem parę instancji osiem razy, zwykle
    po to, żeby dołożyć jeden log. Każdy cykl to ~3 minuty plus kliknięcia
    gracza. Przed restartem wypisać sobie **wszystko**, co ten przebieg ma
    zmierzyć, i dołożyć naraz.
14. **Każdy hak musi udowodnić, że się odpalił.** Hak na `SetOwner` milczał
    i przez chwilę nie dało się odróżnić „zjawisko nie zaszło" od „hak siedzi
    w złej tablicy metod" (bo bronie nie mają wspólnej). Logować pierwsze
    wywołanie — wtedy cisza znaczy coś jednoznacznego.
15. **Pułapka sprzętowa NIGDY w trakcie dołączania klienta.** Sprawdzone
    dwukrotnie: 400 zatrzymań i 20 zatrzymań dały ten sam skutek — host zamarza,
    klient bez świata, przebieg do wyrzucenia. Zatrzymany wątek gry łamie
    sekwencję otwierania kanałów sieciowych. W tej fazie wolno używać wyłącznie
    **haka w procesie**, który zapisuje do logu i wraca.
16. **Pytanie o kod nie wymaga uruchomionej gry.** Deasemblację, odwołania
    i literały daje analiza obrazu pliku wykonywalnego — `obraz.py` (obraz
    wskazuje `WF_OBRAZ_DIR`, nie ma go w repozytorium). Przed uruchomieniem
    instancji „żeby coś zdeasemblować" — sprawdzić `obraz.py`.
17. **Liczba pozycji to nie pomiar zawartości.** „Host ma 10 zdolności, klient 8"
    czytałem przez pół dnia jako brak u klienta. Po wypisaniu NAZW okazało się,
    że host ma dwa duplikaty. To ten sam błąd co `CurrentWeaponIndex`: wskaźnik
    obok objawu zamiast objawu.
18. **`UFunction` istnieje ≠ gra woła ją przez `UFunction`.** Hak na
    `ProcessInputAction` milczał, bo gra woła prawdziwą metodę **bezpośrednio
    z C++**, a przejściówka skryptowa jest tylko drugim wejściem. Przed hakiem
    na `Func` sprawdzić na zrzucie, czy metoda nie ma drugiego wołającego —
    inaczej cisza w logu jest dwuznaczna i łamie zasadę 14.
19. **Przy przechodzeniu tablicy obiektów czytaj tylko nagłówek `UObject`**
    (`+0x00`–`+0x28`), dopóki klasa nie jest potwierdzona. Odczyt roli spod
    `+0xF0` dla każdego obiektu wywalił obie instancje (11.08, sygnatury
    `57b9e83f` i `dfd46a05`) — większość `UObject` jest mniejsza niż 0xF1 B.
20. **Skan tablicy metod widzi NASZE łatki, nie kod gry.** `vtable-diff.py`
    pokazał 3 nadpisania zamiast 10, bo gniazda 130 i 223 trzymały już nasze
    przejściowki (adresy `0x6FFFF…`, poza modułem) i skan urwał się na 130.
    Uruchamiać na instancji **bez markerów** albo przed założeniem łatek.
21. **Mapa menu odtwarza TYLKO zjawiska ekwipunkowe po stronie hosta.** Dołączenie klienta do hosta
    stojącego w menu odtwarza podwójne napełnianie ekwipunku, duplikaty
    zdolności i podwójny komplet broni — **bez ani jednego kliknięcia gracza**.
    Do **wszystkiego innego ta droga jest bezużyteczna**: klient na tej samej
    mapie zamarza, a ruchu, wejścia i stanu postaci nie zmierzy się bez gracza,
    który naprawdę chodzi, sprintuje i strzela. Wtedy trzeba normalnej wyprawy.
22. **Nie proś gracza o akcję „na teraz".** Jest przy klawiaturze, ale bywa
    zajęty czym innym — trzy pomiary jednego dnia przepadły, bo mierzyłem
    piętnastosekundowe okno i trafiałem w pustkę, a log przez cały czas
    zapisywał wszystko poprawnie. Loguj asynchronicznie i pozwól grać normalnie;
    jeśli okno czasowe jest naprawdę konieczne, daj **co najmniej minutę**.


## Jak organizować pracę (cztery pliki, każdy o czym innym)

| plik | co tam trafia | kiedy pisać |
|---|---|---|
| `DZIENNIK.md` | hipotezy w toku, plan najbliższego przebiegu | na bieżąco, przed i po każdym przebiegu |
| `PRZEBIEGI.md` | zjawiska i awarie — **jeden wiersz na zjawisko** | gdy coś wystąpi; przy powtórce dopisać znacznik czasu do istniejącego wiersza |
| `WIEDZA.md` | rzeczy **zamknięte**: potwierdzone albo obalone | gdy hipoteza z dziennika się rozstrzygnie |
| `START-TUTAJ.md` | stan ogólny i następny krok | gdy zmieni się priorytet albo coś dużego się domknie |

Cykl jednej hipotezy: wpisz ją do `DZIENNIK.md` **razem z przewidywaniem**
(„co zobaczę, jeśli jest prawdziwa") → zmierz → wpisz werdykt → przenieś do
`WIEDZA.md` i **usuń z dziennika**. Dziennik ma zostać krótki; jeśli rośnie,
znaczy że coś wisi nierozstrzygnięte.

Do tego prowadź listę zadań w narzędziu (`TaskCreate`/`TaskUpdate`) — ale tylko
na czynności („zmierz X", „napisz łatkę Y"), nie na hipotezy. Hipotezy żyją
w dzienniku, bo mają przewidywanie i werdykt, czego lista zadań nie zapisze.