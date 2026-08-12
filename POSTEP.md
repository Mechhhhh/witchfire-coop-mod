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

## Co dalej

**1. Sprint i ślizg u klienta nadal nie działają.** Serwer trzyma pionek w `Idle`,
a `IdleToWalking` wymaga warunku `State.Condition.Player.HasMovementInput`, którego
serwer nie ma skąd wziąć — wejście gracza zdalnego istnieje tylko tam, gdzie siedzi
człowiek. Ustawianie go własną funkcją gry `UpdateCustomConditionBool` na razie nie
skutkuje przejściem; nie wiadomo, czy warunek zostaje zapisany i kiedy maszyna go
czyta.

**2. Amunicja klienta — w trakcie naprawy, trzecia wersja wyzwalacza.** Napełnianie
magazynka wykonuje się u klienta i liczy zero, bo zapasu jeszcze wtedy nie ma. Dwa
poprzednie wyzwalacze czekały na zapis zapasu, który przez hakowane gniazdo nigdy
nie przechodzi. Trzecia wyzwala się samym objawem — nie sprawdzona w grze we dwóch.

**3. Czego nie potwierdzono.** Łatki nie mają próby kontrolnej przez usunięcie
markera, nie mierzono serii dołączeń w jednej sesji, a część HUD klienta jest
pusta mimo poprawnych danych po obu stronach.

---

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

## What's next

The 08-12 course change reordered everything. The old flow — host starts an
expedition alone, client joins the running mission — turned out to be the
hardest networking case Unreal has, picked by accident. The new milestone:
**a session that lives in the hub and survives the travel there and back.**

**1. The client must survive joining in the hub.** It currently dies ~4 s after
travel in a Blueprint timer event invoked on a destroyed object. A null guard
for that event (`fix_smycz`) is deployed and awaiting a two-player control run,
including a run with the guard removed to confirm the crash returns.

**2. The host must survive the client leaving.** ~50 s after a dropped
connection the host's game thread parks on an endless `futex_wait`, right on
the first 30-second inventory-refill tick after the client controller loses its
`Player`. The host keeps rendering, so it looks alive and is not.

**3. `ServerTravel` instead of local map loads.** Find what the game calls to
start an expedition and to return to the hub, and turn it into a session
travel so both players move together and mission-start scripts run server-side.

**Parked until the session flow works:** client sprint/slide (server-side state
machine never leaves `Idle`), client ammo, HUD gaps. Part of these may be
symptoms of the session never being properly started for two players.
