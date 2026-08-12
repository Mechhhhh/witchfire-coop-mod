# Rejestr zjawisk — jeden wiersz na ZJAWISKO, nie na przebieg

Powstał, bo dokumentacja rosła liniowo: każdy przebieg dostawał własną sekcję,
choć wynik często był ten sam. Przy zjawisku niedeterministycznym to zabija
diagnozę, bo najważniejsze pytanie brzmi **„czy to się powtarza"**.

**Zasada: wynik się powtórzył → dopisz znacznik czasu do istniejącego wiersza.**
Nowa sekcja tylko wtedy, gdy zjawisko jest naprawdę nowe.

Dane w tabeli awarii pochodzą z `tools/sygnatura.py --od 00:00` — **nie wpisywać
ich z pamięci**, tylko przekleić z narzędzia. Ta tabela miała już raz błąd
wpisany ręcznie.

---

## Awarie — po sygnaturze (stan: 2026-08-10 15:40)

Sygnatura = adres odczytu + wątek + skrót ze stosu. Z ekranu wszystkie wyglądają
tak samo (proces znika), więc **tylko sygnatura je odróżnia**.

| sygnatura | adres | strona | wystąpienia | stan |
|---|---|---|---|---|
| `41d65609` | `0x24` | host | 02:01, 02:11, **15:35** | boostery. Strażnik **potwierdzony dwustronnie**: z nim nie występuje, bez niego (kontrola 15:35) wraca |
| `17fc181f` | `0x0` | **klient** | 03:00, 14:54, 16:10, **12.08: 03:18, 03:25, 14:41** | **UWAGA: sygnatura zlepia RÓŻNE odczyty nulla — rozróżniać ramkami z `read-crash-xml.py`.** (a) 16:10 ROZEBRANA: `MyPawn` == null w efektach strzału, `0x141B59EAD`, strażnik `fix_effects` — od tamtej pory milczy. (b) 03:18/03:25/14:41, stos identyczny: thunk BP **`SetLeashName`** (`0x141B7DDAA`) na nullu z timera zdrowia/wskrzeszania, 4 s po travelu klienta; bliźniak `SetSpawnBehaviour` strzeżony od dawna, ten nie — strażnik `fix_smycz` w budowie (hipoteza 31) |
| `154b0601` | `0x430` | host | 02:33 | wiązanie akcji wejścia. Strażnik założony; jedno wystąpienie przed łatką, więc dowód słabszy niż przy `0x24` |
| `204026f6` | `0x3d0000000f` | host | 15:12 | śmieciowy wskaźnik (nie null). Podejrzenie o strażniki **oddalone** kontrolą 15:35 |
| `9a071e89` | `0x0C` | host | 01:13 | zapis profilu przy śmierci; **droga A**, może nie dotyczyć drogi B |
| `cc0434fc` | ? | host | 00:26 | nierozebrana |
| `632a51bd` | ? | klient | 00:57 | nierozebrana |

**Awaria `fc5c66e3` (21:01, adres `0xFFFFFFFFFFFFFFFF`) to ARTEFAKT POMIARU, nie
usterka gry.** Założyłem pułapkę sprzętową na `AActor::SetOwner` — funkcję wołaną
setki razy — i zebrała 400 zatrzymań wątku gry dokładnie w trakcie dołączania
klienta. Host zamarł, klient zobaczył kilka assetów, host padł. Nie liczyć tego
do bilansu stabilności.

Wniosek na przyszłość: **pułapka sprzętowa nadaje się do rzadkich zdarzeń**
(zapis do konkretnego pola, jedno rozgałęzienie), a **nie do gorących funkcji
w trakcie dołączania**. Do tych drugich potrzebny jest hak w procesie, który
zapisuje do bufora i nie zatrzymuje wątku.

**Padnięcie bez zrzutu** (02:56, 03:04) to **nie była awaria gry**:
`gamescopereaper` zabijał grę razem z powłoką. Naprawione przez `setsid`
w `launch-instance2.sh`.

**„Zamrożenie klienta" to była AWARIA, a nie zator** (zmierzone 16:10). Objaw
z zewnątrz jest mylący: proces żyje, wątek pulsu tyka, a obraz stoi. Pomiar od
środka rozstrzyga to jednoznacznie:

| pomiar | klient | host (próbka kontrolna) |
|---|---|---|
| wątek gry | `futex_wait` | `running` |
| tiki CPU wątków silnika w 4 s | **0** (tylko mangohud) | 300 / 217 / 168 / … |
| stos uniksowy wątku gry | zawiera `0xC0000005` **dwa razy** | — |
| katalog `Crashes` | **nowy zrzut z tej minuty** | — |

Czyli klient **padł**, a zawiesiła się dopiero obsługa wyjątku — dlatego proces
nie znika i wygląda na zamrożony. Narzędzie: `tools/stos-watku.py`.

## Zamrożenia / kto padł

| przebieg | klient | host |
|---|---|---|
| 14:54 | 0 wątków silnika — ale zostawił zrzut `17fc181f`, więc **padł**, nie zamarł | żył, +317 tick `GameThread` |
| 15:12 | działał, 15–18 wątków, 706 FPS | **padł** (`204026f6`) |
| 15:35 (kontrola bez strażników) | działał | **padł** (`41d65609`) |
| 12.08 03:25 (trampoliny NA) | **padł** (`SetLeashName`, stos = 14:41) | **zamarzł** (regresja trampolin) |
| 12.08 14:41 (kontrola H28, trampoliny ZDJĘTE) | **padł** (`SetLeashName`, zrzut 42 s od startu) | żył przez całe życie połączenia: zegar gry 1:1, GameThread 47–70 tik/s; wypadł do menu i wrócił po CONTINUE. **Potem, 14:43:14 (53 s po zerwaniu), spasował wątek gry**: `futex_wait` bez limitu, 0 tik/s, render dalej 241 FPS — dokładnie w 30-s takcie napełniania, pierwszym po „bez Player" (hipoteza 32) |
| 12.08 15:16 (h31, `fix_smycz` NA) | **PRZEŻYŁ dołączenie w hubie** — pierwszy raz: `SMYCZ: 1` w 5 s po travelu, kamera i świat żywe, uścisk objęcia pełny, połączenie > 138 s; wejście martwe (hipoteza 33) | żył, gracz grał |

**Ten sam test bez żadnych zmian dał odwrotny wynik** (14:54 vs 15:12). Zjawisko
nie jest deterministyczne — pojedynczy przebieg nie dowodzi ani sukcesu, ani
porażki. Stąd wniosek dla dalszej pracy: **liczyć serie, nie pojedyncze próby**.

## Przebieg 16:25 — najdłuższe wspólne życie obu instancji

Pierwszy przebieg, w którym obaj gracze są w jednym świecie, **widzą się** i żyją
dłużej niż minutę. Klient dołączył 16:25:07, o 16:29:14 wciąż działał (218 FPS).
Wcześniej ginął w kilka sekund po dołączeniu.

| pomiar | wynik |
|---|---|
| broń klienta | `BRON: CurrentWeaponIndex -1 -> 0 (UDALO SIE)` o 16:25:11, **4 s po dołączeniu** |
| broń hosta | 48 próbek `bron-lokalna.py`, wszystkie `idx=0` — ale **to był zły wskaźnik**: host traci cały widok pierwszoosobowy, a indeks broni zostaje. Patrz `KNOWLEDGE.md` §3c |
| postacie u klienta | własna `Role=2` z `idx=0`, kopia hosta `Role=1` z `idx=-1` (poprawnie) |
| licznik strażnika efektów | **0** |

**Ostatni wiersz jest najważniejszy i psuje ładną historię:** strażnik ściany #3
**ani razu nie zadziałał**, więc przeżycia klienta nie wolno mu przypisać.
Zmieniły się dwie rzeczy naraz (strażnik + działająca łatka broni) i to
mierzalnie **druga** z nich weszła do gry. Rozstrzygnie próba kontrolna:
przebieg z `fix_weapon`, ale **bez** `fix_effects`.

Co u klienta nie działa mimo życia (zgłoszenie gracza, jedna rodzina objawów —
brak inicjalizacji gracza po stronie klienta):

- amunicja `0/0`, napis „NO AMMO",
- paski życia i staminy puste, choć `CachedHealth = 83` u obu **tak samo**,
- brak licznika waluty i mikstur leczenia,
- brak panelu celu wyprawy, klawisz `X` nic nie robi,
- brak własnej strzałki na środku minimapy,
- brak ruchu w poziomie (komponent ruchu jest sprawny: `MovementMode=1`,
  `MaxWalkSpeed=600`, więc blokada jest wyżej).

Odczyty, które zawężają to dalej:

| pomiar | klient | host |
|---|---|---|
| `CachedHealth` | 83 | 83 |
| `HealthAndStaminaSFXEnabled` | **False** | **True** |
| `bBlockInput` | True | True (**nie jest to różnica** — sprawdzone) |
| aktor `BPDimensionHUD_C` | jest | jest |
| aktor `BPMission_C` | tylko wzorzec klasy | tylko wzorzec klasy |

## Przebieg 17:25 — stabilność potwierdzona długością, nie pojedynczym testem

Obie instancje przeżyły **ponad dwie godziny wspólnej gry** bez awarii (łącznie
z poprzednim przebiegiem od 16:25). Gracz potwierdza: „gra nie scrashowała
i dalej działa tak samo jak dwie godziny temu". Przy zjawisku, które wcześniej
zabijało klienta w kilka sekund, to jest wynik mocniejszy niż seria krótkich prób.

Strażniki pracują i mają na to liczby — obie łatki zadziałały w **pierwszej
sekundzie** po dołączeniu klienta:

```
17:25:18  WEJSCIE: pominiete wiazania z nullem: 4
17:25:18  BOOSTER: pominiete wywolania z nullem: 1
```

## Przebieg 22:50 — dołączenie odtworzone BEZ wyprawy (host w menu)

Sprawdzenie, czy zjawiska da się badać bez kliknięć gracza. **Częściowo tak.**

| co | wynik |
|---|---|
| podwójne napełnianie ekwipunku u hosta | **odtworzone** — hak `log_fill` pokazał dwa wywołania z `flaga=1` w tej samej sekundzie, magazyn hosta jako pierwszy |
| dwie duplikaty zdolności u hosta | **odtworzone** — 8 przed dołączeniem, 10 po (dwie ostatnie powtórzone) |
| podwójny komplet broni u hosta | **odtworzone** — 2 bronie przed, 6 po |
| pusta mapa atrybutów ruchu u serwerowej kopii klienta | **zmierzona**, z trzema próbkami kontrolnymi |
| **klient** | **ZAMARZA** — zgłoszenie gracza: dzieje się tak zawsze, gdy host jest na mapie huba/menu, bo to ta sama mapa |

Wniosek roboczy: **mapa menu wystarczy do wszystkiego, co mierzy się po stronie
HOSTA** (napełnianie, duplikaty, serwerowe kopie obiektów klienta — one na
hoście istnieją i są kompletne). Do czegokolwiek po stronie klienta trzeba
wyprawy, czyli kliknięć gracza.

To jest znaczące dla tempa pracy: pytania o hosta można teraz zadawać seriami
bez angażowania człowieka.

## Przebieg 01:11 (11.08) — dwie sprawy rozstrzygnięte jednym przebiegiem

Pierwszy przebieg z markerami `fix_dup` i `log_speed`. Host **na wyprawie**,
klient dołącza normalnie.

| co | wynik |
|---|---|
| strażnik duplikatu | `pominietych powtorek: 1` — dokładnie magazyn hosta; magazyn klienta napełniony normalnie |
| **host** | zgłoszenie gracza: **„działa tak jak na singleplayer"** |
| podróż na wyprawę | nowy magazyn, napełnianie przechodzi — strażnik nie psuje podróży |
| znaczniki blokady ruchu | `Blocked.Normal=0  Blocked.Walk=0  Blocked.Running=0` przy limicie `0.000` → hipoteza **obalona** |
| mapa atrybutów ruchu klienta | 19 wpisów, **13 wartości wyzerowanych**, przy poprawnym `ASC` → **przyczyna braku ruchu** |
| klient | nadal nie chodzi i zapętla przeładowanie (`0/90` na zrzucie) — zgodnie z pomiarem |

Zrzuty: `logs/t-blocked/zrzuty/`. Pełne porównanie map:
`logs/t-blocked/porownanie-map-atrybutow.txt`.

## Przebieg 01:24 (11.08) — KLIENT ZACZĄŁ CHODZIĆ

Pierwszy przebieg z markerem `fix_attrs`. Naprawa polega na ponownym wywołaniu
**własnej funkcji gry** (`0x14178E6E0`), nie na podstawianiu wartości.

| pomiar | wynik |
|---|---|
| log naprawy | `ATRYBUTY: odswiezone (1/5) ... GetMaxSpeed przed=0.000 po=355.000` |
| zerowych limitów w całym przebiegu | **1** (poprzednio kilkanaście tysięcy) |
| mapa atrybutów serwer↔klient | **19 z 19 wartości identycznych** |
| ruch serwerowej kopii klienta | **przemieszcza się** (poprzednio `0,0` w każdej osi) |
| strażnik duplikatu (drugie potwierdzenie) | `pominietych powtorek: 1` |
| zgłoszenie gracza | klient chodzi; korekta pozycji **w każdym stanie**, najsilniejsza przy ślizgu |

Prędkości w tej samej chwili: zwykły bieg **serwer 510,2 / klient 332,1**,
dash **2500,0 / 2500,0**.

Zrzuty i dane: `logs/t-fix-attrs/`.

## Przebieg 01:35 (11.08) — szarpanie rozebrane

Marker `log_speed` próbkuje teraz także limity **niezerowe**. Gracz potwierdza,
że w oknie pomiaru sprintował i robił serię ślizgów.

| co serwer liczy dla pionka klienta | ile z 74 próbek |
|---|---|
| `615,0` zwykły bieg | 24 (+9 tuż poniżej) |
| `522,8` = `615 × 0,85` chód w bok | 26 |
| **`265,0` kucanie** | 10 |
| `800` sprint / ślizg | **0** |

Trzecie z rzędu potwierdzenie obu naprawek: `ATRYBUTY: odswiezone (1/5) …
przed=0.000 po=355.000` oraz `NAPELNIANIE: pominietych powtorek: 1`.

**Pułapka narzędziowa wykryta przy okazji:** `vtable-diff.py` pokazał 3
nadpisania zamiast 10, bo gniazda 130 i 223 trzymały już **nasze** przejściowki
(adresy poza modułem) i skan urwał się na 130. Uruchamiać na instancji bez
markerów.

## Przebieg 02:22 (11.08) — kanał odblokowany, dwa adresy zmierzone

Pomiar odpalił się **sam**, przy pierwszym pakiecie ruchu — bez udziału gracza.

```
KANAL: RPC ruchu wykonane z 0x142106F56 — to wnetrze ProcessEvent
KANAL:    pola FFrame celujace w poblize stosu: +0x28 (rsp+544), +0x48 (rsp+944)
```

Wynik: `FFrame::Locals` = **`+0x28`** (zgodne z układem UE 4.27 — dwie niezależne
drogi), `UFunction::Invoke` = `0x142106ED0`, **`UObject::ProcessEvent` = gniazdo
wirtualne 68**.

Poprzednie podejście (hak na przejściówkę `ProcessInputAction`) **milczało**, bo
gra woła tę metodę bezpośrednio z C++ — zapisane jako zasada 18.

Obie naprawy (`fix_attrs`, `fix_dup`) potwierdzone po raz **piąty i szósty**.

## Przebieg 01:57 (11.08) — DOWÓD RUCHEM: serwer trzyma klienta w `Idle`

Klient zrestartowany sam (host został na wyprawie, gracz nic nie klikał).
Naprawa atrybutów odpaliła **czwarty raz z rzędu**, strażnik duplikatu również
— licznik poszedł z 1 na **3**, bo przy powtórnym dołączeniu pomijane są dwa
magazyny: hosta i **nieposprzątany magazyn poprzedniej sesji klienta**.

Pomiar stanu maszyny podczas aktywnej gry:

```
klient u siebie widzial: Airborne, Idle, Running, Sliding, Walking
serwer widzial pionek klienta w stanach: Idle
```

Serwerowa kopia **nie opuściła `Idle` ani razu** w 25 s. Osobne potwierdzenie
przy okazji: przy dashu obie strony pokazały **2500,0** — bo dash idzie przez
system zdolności, nie przez maszynę stanów.

## Pauza rozwala KLIENTA, hosta nie (11.08, 01:55)

Zgłoszenie gracza: zapauzował grę u klienta i „się zjebała"; u hosta pauza nie
psuje nic. Zmierzone od środka zaraz po tym:

| pomiar | wynik |
|---|---|
| proces klienta | **żyje** |
| `GWorld` | bez zmian, puls tyka |
| katalog `Crashes` | **żadnego nowego zrzutu** (najnowszy sprzed doby) |

Czyli to **nie jest awaria** — klient zawiesza się logicznie i zostaje w tym
stanie. To wyjaśnia zasadę z pierwszego dnia („nie używamy pauzy") i domyka
starą obserwację „host traci sterowanie przy `Login`" → tracił przez menu/pauzę.

**Skutek dla pomiarów:** dwa przebiegi pomiaru stanu maszyny stanów (01:5x)
pokazały `Idle` przez cały czas — mierzyły zapauzowanego klienta i są
**unieważnione**. Naprawa: klienta da się zrestartować **samego**, bez ruszania
hosta i bez klikania przez gracza — host zostaje na wyprawie.

## AWARIA Z NASZEJ WINY (11.08, 16:27 i 16:36) — odczyt poza obiektem

Pierwszy przebieg kanału stanu ruchu wywalił **obie** instancje. Gracz zgłosił
to jako „zawiesiło się", ale pomiar rozstrzygnął inaczej — tą samą metodą, co
przy kliencie 16:10:

| pomiar | wynik |
|---|---|
| katalog `Crashes` | **świeży zrzut o 16:36:50**, dokładnie gdy obraz zamarł |
| tiki CPU wątków w 4 s | **zero na wszystkich** |
| ramki w zrzucie | `0x6ffffb4a0000` — **nasza biblioteka** |

| sygnatura | adres | strona | kiedy |
|---|---|---|---|
| `57b9e83f` | `0x51df0030` | host | 16:27 |
| `dfd46a05` | `0x46f50050` | klient | 16:36 |

**Przyczyna:** skan w `kanalTick` zaczynał od odczytu roli sieciowej spod
`obj+0xF0` dla **każdego** obiektu w tablicy. Większość `UObject` jest
znacznie mniejsza niż 0xF1 bajtów — odczyt wychodził poza koniec obiektu
i przy trafieniu w koniec strony wywalał grę.

**Poprawka:** zaczynać od `obj+0x10` (wskaźnik klasy, leży w nagłówku KAŻDEGO
`UObject`), potwierdzić klasę, i dopiero wtedy sięgać głębiej.

**Zasada, która z tego wynika (19):** przy przechodzeniu tablicy obiektów wolno
czytać tylko nagłówek `UObject` (`+0x00`–`+0x28`), dopóki klasa nie jest
potwierdzona. Każdy głębszy offset jest wtedy odczytem poza obiektem.

Po drodze wyszło też, że wcześniejsze „gra od razu zfreezowała w menu" (16:27)
**też było tą awarią**, a nie samym spadkiem płynności.

## Potwierdzone wielokrotnie — nie wymaga powtórek

| ustalenie | ile razy |
|---|---|
| host nasłuchuje bez wymuszania mapy (łatka `LoadMap`) | 5+ |
| nasłuch przeżywa własną podróż gry na kolejną mapę | 3 |
| klient dostaje własną postać `Role=2` + kontroler + bronie | 2 |
| strażniki nie ruszają nic w grze solo (liczniki = 0) | 3 |
| strumieniowanie poziomów identyczne host↔klient (17/7/26) | 1 |

## Nieudane, ale ważne

| co | wynik |
|---|---|
| łatka broni na drodze B | `BRON: poddaje sie po 40 probach — **OBALONE 16:25**: zawodzil budzet prob liczony od startu procesu, nie latka` w obu przebiegach (15:11, 15:34) — nie znalazła postaci o `Role == 2` |

## Zasada porównywania

1. Sygnatura już była? → dopisz czas do wiersza, nie twórz sekcji.
2. Wynik odwrotny do poprzedniego? → **to jest wynik**, opisz osobno.
3. Zjawisko wystąpiło raz? → nie wyciągaj wniosku, powtórz.
