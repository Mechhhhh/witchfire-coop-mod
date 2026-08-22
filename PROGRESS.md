# Dziennik postępu — mod co-op do Witchfire

Witchfire (UE 4.27) to gra dla jednego gracza; mod to proxy DLL wołająca kod
sieciowy, który w grze już jest. Stan na 11 sierpnia 2026, wieczorem. W tabeli
tylko rzeczy potwierdzone pomiarem — obalone też, bo obalenie zawęża pole.

| data | co ustalono | dowód |
|---|---|---|
| 08-08 | OBALONE: „gra ma wyciętą replikację" | zrzut CDO: komplet pól replikowanych |
| 08-10 | OBALONE: wymuszanie mapy (droga A) | bez połączenia broń i tak nie strzela |
| 08-10 | Hostowanie to dwa bajty: `je`→`NOP` w `LoadMap` | port 7777 i `IpNetDriver`, 5+ przebiegów |
| 08-10 | Ekwipunek bez replikacji: 50 funkcji, zero RPC | klient wyjmuje broń po `SelectWeapon`: `-1 → 0` |
| 08-10 | Awarie hosta: obiekt jedynego gracza użyty bez sprawdzenia (4×) | bez strażnika awaria `0x24` wraca |
| 08-10 | Ponad dwie godziny wspólnej gry bez awarii | przebiegi 16:25 i 17:25 |
| 08-11 | OBALONE: „pusta mapa atrybutów", „znacznik `Blocked.Walk`" | mapa pełna w powtórce; znaczniki = 0 przy limicie `0.000` |
| 08-11 | PRZYCZYNA braku chodzenia: 13 z 19 wartości mapy `+0xB18` wyzerowanych | porównanie host↔serwer po nazwach atrybutów |
| 08-11 | NAPRAWIONE: klient chodzi — powtórzone wywołanie synchronizacji gry, bez podstawianych liczb | `przed=0.000 po=355.000` |
| 08-11 | NAPRAWIONE: duplikat ekwipunku hosta (dołączenie napełniało go drugi raz) | `pominietych powtorek: 1` w sześciu przebiegach |
| 08-11 | Serwer nie zna sprintu ani ślizgu | 74 próbki: 615 / 522,8 / 265, ani razu 800; dash 2500=2500 |
| 08-11 | DOWÓD RUCHEM: serwerowa kopia nie opuszcza `Idle` | klient przechodzi pięć stanów, serwer jeden |
| 08-11 | OBALONE: „wystarczy podać maszynie akcję" — z `Idle` nie ma przejścia do `Running` | 8/8 akcji, oba gniazda, stan bez zmian; graf przejść z danych maszyny |
| 08-11 | Amunicja: kod napełniania działa u klienta i liczy zero | host `=6`, klient `=0`, ten sam wołający |
| 08-12 | ZWROT: spotkanie w hubie i wspólna podróż — dołączanie do trwającej misji było najtrudniejszym możliwym przypadkiem, wybranym przypadkiem | gracz: wyprawy nie da się skończyć razem; hub jest środkiem wszystkiego |
| 08-12 | Zamrożenie hosta przy dołączaniu było NASZĄ regresją (dwie nowe trampoliny) | przebieg kontrolny bez nich: zegar gry 1:1, GameThread 47–70 tik/s przez całe dołączanie |
| 08-12 | Klient ginie ~4 s po travelu: zdarzenie Blueprintu `SetLeashName` wołane na nullu przez timer zdrowia | ten sam stos w trzech zrzutach; bliźniacze zdarzenie obok ma strażnika od dni |
| 08-12 | Strażnik nulla wdrożony (`fix_smycz`), trampolina sprawdzona kontrolną deasemblacją | przebieg we dwoje potwierdził: 453 s zamiast śmierci po 64 s |
| 08-12 | NOWE: po zerwaniu połączenia host ~50 s później parkuje wątek gry — nieskończony `futex_wait`, obraz dalej się rysuje | trafia dokładnie w pierwszy 30-sekundowy tik napełniania po utracie `Player` |
| 08-16 | OBALONE: „do gry klienta nie docierają zdarzenia wejścia" — docierają, setkami na sekundę | dwa piętra liczników; klient ~2950 zdarzeń w oknie, w którym host ma czyste zero, i potwierdzenie gracza w tej samej chwili |
| 08-16 | Wejście klienta dochodzi aż do `PlayerController::InputKey` — 100% dojść, jak u hosta | 417/417 u klienta, 328/328 u hosta, obie instancje w tym samym świecie |
| 08-16 | Wiązanie ruchu u klienta NIE JEST wołane ani razu, a u hosta ~200 razy na sekundę | licznik klatkowy: host bije bez żadnego wejścia, klient stoi na zerze |
| 08-17 | PRZYCZYNA nr 1: gra gasi globalne wejście na czas ładowania mapy i sama je przywraca — klient robi tylko pierwsze | host wyłącza 00:19:37 i włącza 00:19:52; klient wyłącza 00:20:54 i nie włącza nigdy |
| 08-17 | NAPRAWIONE (częściowo): łatka woła własny setter gry i wiązanie ruchu rusza z zera | trzeba PRZEŁĄCZAĆ, nie ustawiać — setter rozgłasza tylko przy zmianie |
| 08-17 | Naprawa nie wystarcza: po dołączeniu wiązanie zamiera mimo zapalonej flagi | druga przyczyna nieustalona; trop to komponent wejścia pionka |

## Co dalej

**Kamień milowy pozostaje ten sam: sesja żyje w hubie i przeżywa podróż tam
i z powrotem.** Pierwsza połowa jest zrobiona — klient dołącza i przeżywa, ma
kamerę, świat i pełne objęcie pionka.

**1. Klient nie przyjmuje żadnego wejścia — to jedyny bloker grywalności.**
Droga dostarczania jest sprawna i to jest zmierzone, nie założone: zdarzenia
docierają do procesu, do filtra wejścia gry, do rozdzielacza widoku i do
kontrolera postaci — to ostatnie w stu procentach prób, tak jak u hosta.
Ginie wiązanie ruchu: u klienta nie odpala ani razu, u hosta chodzi co klatkę.

Pierwsza z dwóch przyczyn jest znaleziona i załatana: gra gasi globalne wejście
na czas ładowania mapy, a klient nigdy go nie zapala. Łatka przełącza flagę
własnym setterem gry i wiązanie zaczyna dispatchować. Po dołączeniu do hosta
zamiera jednak znowu, więc druga przyczyna pozostaje nieustalona. Bieżący trop:
komponent wejścia pionka ma u klienta mniej wiązań niż u hosta i nie buduje
swojej mapy klawiszy.

**2. Host pada po ~50 min na wiszącym słuchaczu** i przy ponownym dołączeniu
parkuje wątek gry. Pseudokod pokazał, że pętla rozgłaszania trzyma zamek przez
cały przebieg listy, więc oba objawy to prawdopodobnie jedno zdarzenie.

**3. `ServerTravel` — wspólne przejście na wyprawę.** Trop znaleziony, pomiar
odłożony do czasu, aż klient będzie grał.

# EN — Progress log: Witchfire co-op mod

Witchfire (UE 4.27) is a single-player game; the mod is a proxy DLL calling
networking code the game already contains. State as of 11 August 2026, evening.
Only measured facts below — disproved ones too, since disproving narrows the field.

| date | finding | evidence |
|---|---|---|
| 08-08 | DISPROVED: "replication was stripped out" | CDO dump: full replicated property sets |
| 08-10 | DISPROVED: forcing the map (path A) | with no connection the gun still does not fire |
| 08-10 | Hosting is two bytes: `je`→`NOP` in `LoadMap` | port 7777 and `IpNetDriver`, 5+ runs |
| 08-10 | Inventory has no replication: 50 functions, zero RPCs | client draws a weapon after `SelectWeapon`: `-1 → 0` |
| 08-10 | Host crashes: an object of the only player used unchecked (4×) | remove the guard and crash `0x24` returns |
| 08-10 | Over two hours of joint play with no crash | runs 16:25 and 17:25 |
| 08-11 | DISPROVED: "empty attribute map", "the `Blocked.Walk` tag" | map full on the repeat; tags = 0 at limit `0.000` |
| 08-11 | CAUSE of not walking: 13 of 19 values in the `+0xB18` map are zeroed | host↔server compared by attribute name |
| 08-11 | FIXED: the client walks — the game's own sync re-run, no substituted numbers | `before=0.000 after=355.000` |
| 08-11 | FIXED: the host's duplicate inventory (a join filled it twice) | `skipped repeats: 1` across six runs |
| 08-11 | The server does not know sprint or slide | 74 samples: 615 / 522.8 / 265, never 800; dash 2500=2500 |
| 08-11 | PROOF BY MOVEMENT: the server copy never leaves `Idle` | client passes five states, server one |
| 08-11 | DISPROVED: "just feed the machine an action" — there is no `Idle` → `Running` transition | 8/8 actions, both slots, state unchanged; graph from the machine's data |
| 08-11 | Ammo: the fill code runs on the client and computes zero | host `=6`, client `=0`, same caller |
| 08-12 | COURSE CHANGE: meet in the hub and travel together — joining a running mission was the hardest possible case, chosen by accident | player: an expedition cannot be finished together; the hub is the center of everything |
| 08-12 | Host freezing at join was OUR regression (two new join-time trampolines) | control run without them: game clock 1:1, GameThread 47–70 ticks/s through the whole join |
| 08-12 | The client dies ~4 s after travel: Blueprint event `SetLeashName` invoked on a null object by a health/revive timer | identical stack in three crash dumps; the twin event next door has been null-guarded for days |
| 08-12 | Null guard for the twin thunk deployed (`fix_smycz`), trampoline verified by control disassembly | live two-player run pending |
| 08-12 | NEW: after a dropped connection the host parks its game thread ~50 s later — an endless `futex_wait`, render keeps drawing | lands exactly on the first 30-second refill tick after the client controller loses its `Player` |
| 08-16 | DISPROVED: "input events do not reach the client's game" — they do, hundreds per second | counters on two floors; ~2950 client events in a window where the host sits at zero, with the player confirming in the same moment |
| 08-16 | Client input reaches `PlayerController::InputKey` — 100% of attempts, same as the host | 417/417 on the client, 328/328 on the host, both instances in the same world |
| 08-16 | The movement binding is never invoked on the client, while the host runs it ~200 times a second | frame-driven counter: the host climbs with no input at all, the client stays at zero |
| 08-17 | CAUSE #1: the game turns global input off while a map loads and back on afterwards — the client only ever does the first half | host off 00:19:37, on 00:19:52; client off 00:20:54, never on |
| 08-17 | PARTLY FIXED: a patch calls the game's own setter and the movement binding starts dispatching from zero | it must TOGGLE, not set — the setter broadcasts only on change |
| 08-17 | Not sufficient: after joining, the binding stops again with the flag on | second cause unidentified; the lead is the pawn's input component |

## What's next

**The milestone is unchanged: a session that lives in the hub and survives the
travel there and back.** The first half is done — the client joins and survives,
with camera, world and a fully acknowledged pawn.

**1. The client accepts no input — the only thing blocking playability.**
The delivery path is healthy and that is measured, not assumed: events reach the
process, the game's input filter, the viewport dispatcher and the player
controller — the last at a hundred percent of attempts, matching the host. What
dies is the movement binding: never invoked on the client, running every frame
on the host.

The first of two causes is found and patched: the game turns global input off
while a map loads and the client never turns it back on. A patch toggles the
flag through the game's own setter and the binding starts dispatching. After the
client joins the host it stops again, so a second cause remains unidentified.
The current lead is the pawn's input component, which carries fewer bindings on
the client and never builds its cached key map.

**2. The host crashes after ~50 min on a dangling listener** and parks its game
thread on a re-join. Pseudocode showed the broadcast loop holds a lock across
the whole list, so both symptoms are probably one event.

**3. `ServerTravel` — going on an expedition together.** The lead is found; the
measurement waits until the client can play.

