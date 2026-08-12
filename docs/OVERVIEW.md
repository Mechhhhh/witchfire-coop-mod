# Przegląd wszerz — co w co-opie działa, a czego nikt nie sprawdził

## Po co ten plik

Cała robota od kilku dni idzie w rzeczy, które **rzuciły się w oczy** — a rzuciły
się te ruchowe, bo widać je natychmiast. Skutek: wiemy bardzo dużo o `MovementMode`
pionka zdalnego, a **nie wiemy, czy da się razem ukończyć wyprawę**.

Jeśli okaże się, że nie da, to szlifowanie sprintu jest polerowaniem. Ten
przegląd kosztuje jedną sesję i może przestawić wszystkie priorytety.

Zasada wypełniania: **jedno zdanie na pozycję, bez interpretacji**. „Klient
dostał obrażenia, pasek spadł" — tak. „Chyba działa" — nie.

## Jak to zmierzyć tanio

Większość pozycji widać w danych, które i tak zbieramy:

| źródło | co z niego widać |
|---|---|
| `tools/rejestrator.py` | ruch, stan maszyny, warunki — szereg czasowy obu graczy |
| `tools/czuwak.sh` | awarie z kontekstem, zamrożenia |
| log biblioteki | amunicja, tryb ruchu, kanał stanu, właściciele |
| `tools/stan-gracza.py` | atrybuty, zdolności, bronie — migawka |
| `tools/ue-snapshot.py` | różnica obiektów — co powstało, co zniknęło |

Do reszty potrzebny jest człowiek, który po prostu **zagra**, a nie wykona
konkretną akcję „na teraz".

## Lista

### 0. ROZSTRZYGNIĘTE PRZEZ GRACZA 12.08 — pętla wyprawy JEST ZEPSUTA STRUKTURALNIE

Zgłoszenie gracza, 12.08 nad ranem:

> nie da się razem zrobić wyprawy, bo ładujesz klienta do mapy **bez skryptów,
> które uruchamiają resztę rzeczy**; a jak wrócę do hubu, kiedy są połączeni,
> to **host zamarza na ekranie ładowania**, a **klienta wyrzuca do
> singleplayerowego hubu**

To zamyka pytania B1, B2 i B5 jednym zdaniem — i to odpowiedzią „nie".

**Dlaczego to jest ważniejsze niż wszystko, czym się dotąd zajmowaliśmy.**
Klient nie wchodzi do *rozpoczętej wyprawy* — wchodzi do mapy, na której
sekwencja startu misji nie została dla niego uruchomiona. Powrót do hubu nie
jest w ogóle podróżą sesji sieciowej, tylko lokalnym ładowaniem mapy, które
rozrywa połączenie: host zostaje na ekranie ładowania, a klient spada do
własnej gry jednoosobowej.

W Unreal Engine jest do tego mechanizm pierwszej klasy — `ServerTravel`
(ewentualnie seamless travel) — który przenosi WSZYSTKICH podłączonych graczy
i wykonuje sekwencję startu poziomu po stronie serwera. Gra go nie używa, bo
jest jednoosobowa. To jest ten sam wzorzec co wszystkie dotychczasowe ściany
(`KNOWLEDGE.md` §4), tylko na poziomie **przepływu poziomów**, a nie pojedynczego
obiektu.

**Konsekwencja dla priorytetów:** część objawów, które rozbieraliśmy osobno,
może być SKUTKIEM tego, że sesja nigdy nie została poprawnie rozpoczęta dla
dwóch graczy — w tym magazynek broni klienta na zerze (ekwipunek i amunicja są
inicjowane przez sekwencję startu misji) i to, że maszyna stanów pionka
zdalnego nie jest przez nic sterowana. Nie jest to dowiedzione, ale jest na
tyle prawdopodobne, że naprawianie ich osobno przed naprawą startu misji może
być pracą nad objawami.

### 0a. ARCHITEKTURA, KTÓREJ NIE ZNALIŚMY — hub jest centrum wszystkiego

Zgłoszenie gracza, 12.08:

> menu główne jest na tej samej mapie co hub, i z hubu robi się wszystko —
> ascendy, rozpoczynanie ekspedycji, wszystko tak naprawdę; klient **nie może
> dołączyć do hosta, kiedy ten jest w hubie**

To ustawia właściwy przepływ co-opu i pokazuje, że dotychczasowy jest
**najtrudniejszym możliwym wariantem, wybranym przypadkiem**:

| co robimy dziś | co powinno być |
|---|---|
| host wchodzi **sam** na wyprawę | host stoi w hubie i nasłuchuje |
| klient dołącza **do trwającej misji** (późne wejście na żywy poziom) | klient dołącza w hubie, gdzie nic jeszcze nie trwa |
| wyprawy nie da się skończyć, powrót rozrywa sesję | `ServerTravel` przenosi OBU na wyprawę i z powrotem |

Późne wejście do działającego poziomu jest w Unrealu najtrudniejszym
przypadkiem sieciowym, jaki istnieje — trzeba dosłać stan wszystkiego, co już
się zdarzyło. Dołączenie w lobby i wspólna podróż to przypadek **podstawowy**,
ten, pod który silnik jest napisany.

**Czyli cały czas rozwiązywaliśmy trudniejszy problem, niż trzeba.**

Nowy kamień milowy, zastępujący dotychczasowe M2/M3 w kolejności:

**M1′ — sesja żyje w hubie i przeżywa podróż tam i z powrotem.**

Dwa kroki, w tej kolejności:
1. **Dołączenie w hubie.** Częściowo zmierzone 12.08: host **nasłuchuje także
   w hubie** (żywy `IpNetDriver`), klient **dochodzi w pełni** (`PostLogin`,
   własny pionek `Role=2`, widzi pionek hosta `Role=1`). Zostaje jedna rzecz:
   **host zamarza w chwili połączenia** — hipoteza 28, próba kontrolna czeka.
2. **`ServerTravel` zamiast lokalnego ładowania.** Znaleźć, czym gra startuje
   wyprawę i czym wraca do hubu, i podmienić na podróż sesyjną.

Dopiero po tym ma sens wracać do amunicji i ruchu — bo oba mogą być skutkami
tego, że sesja nigdy nie została poprawnie rozpoczęta dla dwóch graczy.

### 0b. ZMIERZONE 12.08 03:24 — dołączenie w hubie to TIMEOUT, nie odrzucenie

> **KOREKTA z 03:32, przeczytaj PRZED resztą tej sekcji.** Poniższy wywód kończy
> się wnioskiem „klient milknie". **Ten wniosek jest BŁĘDNY.** Zrzut ekranu od
> gracza pokazał, że to **HOST zamarza** (czarny ekran, 4 FPS, zegar stanął na
> `03:25:05`) — dokładnie w sekundzie, w której powstało połączenie (`03:25:04`).
> Klient milczał, bo nie miał do kogo mówić, a po wyrzuceniu wrócił do własnego
> singleplayera i działał normalnie (247 FPS). Same LICZBY poniżej są dobre;
> błędna jest tylko przypisana im przyczyna. Otwarta hipoteza: **28**.

Śledzenie `ClientConnections` sterownika sieciowego hosta (offset `+0x90`,
znaleziony refleksją) co pół sekundy, w trakcie dołączania klienta w hubie:

```
 46,0 s   połączeń klienckich: 0 -> 1     klient dołącza
110,0 s   połączeń klienckich: 1 -> 0     host go wyrzuca
          połączenie żyło 64 s;  ConnectionTimeout = 60,0 s
```

`InitialConnectTimeout = 120 s`, `ConnectionTimeout = 60 s` (odczytane z tego
samego sterownika). 64 s to **timeout utrzymania**, z dokładnością do
półsekundowego próbkowania.

**Co to znaczy.** Dołączenie NIE jest odrzucane i NIE zawodzi logowanie.
Klient przechodzi pełną drogę: dostaje własny pionek (`Role=2`) i widzi pionek
hosta (`Role=1`), czyli `PostLogin` po stronie serwera się wykonał.

**Potem zamarza HOST** (patrz korekta wyżej), więc przez 60 s nie ma kto
obsługiwać połączenia i netdriver je zamyka. Klient zostaje z nieważnym
`IpConnection` i czarnym ekranem, a po wyrzuceniu wraca do własnej gry
jednoosobowej.

**Następny krok jest w `JOURNAL.md` jako hipoteza 28:** próba kontrolna bez
`fix_lista` i `fix_ekwipunek`. Gracz potwierdził, że **wcześniej host nie
zamarzał**, a obie te trampoliny doszły tego samego wieczoru i siedzą w pętlach
wykonujących się przy dołączaniu. Dopóki to nie jest rozstrzygnięte, każdy inny
pomiar przy dołączaniu jest niewiarygodny.

> **ROZSTRZYGNIĘTE 12.08 14:41 (próba kontrolna).** Bez trampolin host NIE
> zamarł — regresja potwierdzona, hipoteza 28 zamknięta. Timeout 64 s jednak
> WRÓCIŁ przy zdrowym hoście: przyczyną jest śmierć klienta 4 s po travelu
> (thunk BP `SetLeashName` na nullu, hipoteza 31). Liczby 46/110 s z tej sekcji
> pozostają dobre; „host zamarza" przestało być częścią mechanizmu.

### 0c. Klient nie potwierdza objęcia pionka — najpewniej SKUTEK, nie przyczyna

> **KOREKTA z 03:32.** Ta obserwacja jest prawdziwa jako odczyt, ale opisany
> niżej łańcuch przyczynowy jest odwrócony: host zamarza **zanim** zdąży
> dokończyć uścisk dłoni, więc brak potwierdzenia jest skutkiem zamrożenia.
> **Nie kłaść markera `log_objecie` przed rozstrzygnięciem hipotezy 28** — hak
> mierzyłby objaw.
>
> **KOREKTA 2 z 12.08 14:41.** Hipoteza 28 rozstrzygnięta (host zdrowy), więc
> embargo na `log_objecie` ZDJĘTE. Sam łańcuch wymaga jednak poprawki głębiej:
> klient nie wykonuje `AcknowledgePossession`, bo **umiera** 4 s po travelu
> (`SetLeashName` na nullu — hipoteza 31), a nie dlatego, że czeka. Mierzyć
> objęcie ma sens dopiero z żywym klientem, czyli razem ze strażnikiem
> `fix_smycz`.

Odczyt stanu klienta w chwili czarnego ekranu (po wyrzuceniu przez host):

| kontroler | rola | stan |
|---|---|---|
| `DimensionPlayerController_C` | 2 (AutonomousProxy) | `Player` ✓, `PlayerCameraManager` ✓, `Pawn` ✓, **`AcknowledgedPawn = NULL`** |
| `PlayerController` | **3 (Authority)** | wszystko `NULL` |

**`AcknowledgedPawn = NULL` przy ustawionym `Pawn`** to w Unrealu stan
jednoznaczny: klient nie wykonał `AcknowledgePossession`. Uścisk dłoni objęcia
(`ClientRestart` → `AcknowledgePossession` → `ServerAcknowledgePossession`)
jest tym, co daje klientowi WIDOK i sprawia, że zaczyna odsyłać ruch.

To spina wszystkie objawy w jeden łańcuch:

```
brak potwierdzenia objęcia
   → kamera nie ma celu           → CZARNY EKRAN u klienta
   → klient nie odsyła ruchu      → CISZA na łączu
   → serwer nie dostaje nic 60 s  → ROZŁĄCZENIE (zmierzone: 64 s)
```

Drugi kontroler z `Role = 3` (autorytet) po stronie klienta to pozostałość po
jego własnej grze jednoosobowej — warto sprawdzić, czy nie przeszkadza.

**Czego to NIE tłumaczy:** dlaczego host przy dołączeniu wypada do menu bez
myszy i wraca do hubu sam. To osobny objaw, zgłoszony przez gracza 12.08.

**Hak jest napisany i czeka w kodzie** (`patchObjecieLog`, marker
`log_objecie`): podgląda obie połowy uścisku — `ClientRestart` po stronie
klienta i `ServerAcknowledgePossession` po stronie hosta. **Nie kłaść markera,
dopóki hipoteza 28 nie jest rozstrzygnięta.**

### A. Walka i przeżycie — NIC NIE SPRAWDZONE

| # | pytanie | wynik | jak sprawdzone |
|---|---|---|---|
| A1 | Czy przeciwnicy w ogóle **widzą** klienta (agresja, celowanie)? | — | |
| A2 | Czy klient **zadaje** obrażenia przeciwnikom? | — | |
| A3 | Czy klient **dostaje** obrażenia? | — | |
| A4 | Czy klient może **umrzeć**? Co się wtedy dzieje po obu stronach? | — | |
| A5 | Czy po śmierci klienta da się **wstać/wskrzesić**? | — | |
| A6 | Czy host widzi obrażenia i śmierć klienta, czy tylko u siebie? | — | |
| A7 | Czy zaklęcia i zdolności klienta działają (nie tylko broń)? | — | |

### B. Pętla wyprawy — NIC NIE SPRAWDZONE

| # | pytanie | wynik | jak sprawdzone |
|---|---|---|---|
| B1 | Czy da się **ukończyć** wyprawę razem? | — | |
| B2 | Czy klient wraca do hubu razem z hostem, czy zostaje? | — | |
| B3 | Czy łup i waluta klienta **zostają** po powrocie? | — | |
| B4 | Czy postęp (odblokowania, poziomy) zapisuje się u klienta? | — | |
| B5 | Czy da się wejść na **drugą** wyprawę bez restartu obu gier? | — | |
| B6 | Co się dzieje, gdy host wraca do hubu, a klient jeszcze gra? | — | |

### C. Rzeczy, o których wiemy, że są zepsute

| # | co | stan |
|---|---|---|
| C1 | magazynek klienta zostaje zerem, broń przeładowuje się w pętli | hipoteza 24, mechanizm rozebrany (`KNOWLEDGE.md` §3g) |
| C2 | ruch klienta cofa (maszyna stanów stoi w `Idle`) | hipoteza 23, połowa naprawiona (`fix_czas`), blokuje `IsOnGround` |
| C3 | stamina klienta podobno się nie odnawia | hipoteza 21, **niepotwierdzone** — liczba `522,8` okazała się `615 × 0,85`, nie mnożnikiem staminy |

### D. Odporność

| # | pytanie | wynik | jak sprawdzone |
|---|---|---|---|
| D1 | Ile minut sesji wytrzymuje host bez awarii? | — | licznik `czuwak.out` |
| D2 | Czy dołączenie klienta **w trakcie** wyprawy jest bezpieczne? | — | ściany #3 i #4, do potwierdzenia |
| D3 | Czy da się dołączyć **drugi raz** po rozłączeniu klienta? | — | |
| D4 | Czy działa na innej mapie niż prolog? | — | |

## Zasada zamykania

Pozycja przechodzi z „—" do wyniku dopiero wtedy, gdy jest **dowód**: wiersz
z logu, zrzut ekranu albo zdanie gracza opisujące, co widział. Wynik „nie
sprawdzone" jest lepszy od zgadniętego — cały ten plik istnieje dlatego, że
kilka rzeczy uznano za działające, bo nikt nie patrzył.
