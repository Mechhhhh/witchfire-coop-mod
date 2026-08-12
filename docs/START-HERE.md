# Zacznij tutaj — stan i następny krok

Stan na 2026-08-12, 15:05. **Kierunek projektu zmieniony w nocy 12.08 —
przeczytaj sekcję „ZWROT", zanim cokolwiek zrobisz.**

## Co czytać

**Ten plik, potem `OVERVIEW.md` §0–§0c, potem `JOURNAL.md`. Nic więcej na starcie.**

`KNOWLEDGE.md` (2300 linii) to zapis, JAK doszliśmy do wniosków — nie czytaj go
w całości. Wyszukuj punktowo:

```
tools/szukaj.py 0x1418002E0        # co wiemy o adresie
tools/szukaj.py "mapa atrybutow"   # z nagłówkiem sekcji
```

Nagłówek sekcji w wynikach mówi, czy trafienie pochodzi z ustalenia
POTWIERDZONEGO, czy z OBALONEGO. **Zanim ruszysz z hipotezą — wyszukaj ją.**

`ADDRESSES.md` — czysta referencja adresów i offsetów. `OVERVIEW.md` — co
w co-opie działa, a czego nikt nie sprawdził. `docs/historia/` — NIE czytać.

---

## ZWROT 12.08 — przestajemy naprawiać gałęzie

Przez kilka dni szło wszystko w ruch pionka zdalnego (sprint, maszyna stanów,
amunicja). W nocy 12.08 gracz podał dwie informacje, które to unieważniły:

1. **Wyprawy nie da się przejść razem** — klient ląduje na mapie bez skryptów,
   które uruchamiają resztę. Powrót do hubu przy połączonych graczach zawiesza
   hosta na ekranie ładowania, a klienta wyrzuca do jego singleplayera.
2. **Hub jest centrum wszystkiego** (menu główne jest na tej samej mapie);
   stamtąd robi się ascendy i startuje wyprawy. Klient nie potrafi dołączyć,
   gdy host jest w hubie.

Wniosek: dotychczasowy przepływ — host wchodzi SAM na wyprawę, klient dołącza
do TRWAJĄCEJ misji — jest **najtrudniejszym możliwym przypadkiem sieciowym
w Unrealu**, wybranym przypadkiem. Właściwy jest odwrotny: obaj spotykają się
w hubie, a `ServerTravel` przenosi ich razem.

**Nowy kamień milowy M1′: sesja żyje w hubie i przeżywa podróż tam i z powrotem.**
Ruch, amunicja i maszyna stanów **odłożone** — mogą być skutkami tego, że sesja
nigdy nie została poprawnie rozpoczęta dla dwóch graczy.

## Próba kontrolna h. 28 — WYKONANA 12.08 14:39–14:49. Dwa rozstrzygnięcia

1. **Host bez trampolin NIE zamarł przy dołączeniu** → zamrożenie z 03:25 było
   regresją `fix_lista`/`fix_ekwipunek`. Zostają zdjęte; przed powrotem pętle
   do przepisania (zasada 7).
2. **Klient umiera ~4 s po travelu**: thunk BP `SetLeashName` (`0x141B7DDA0+0xA`)
   wołany na nullu z timera zdrowia. Stos identyczny 03:18/03:25/14:41.
   Bliźniak `SetSpawnBehaviour` jest strzeżony od dawna — awaria przeniosła
   się na niestrzeżonego bliźniaka. Stąd strażnik `fix_smycz` (wdrożony,
   patrz niżej). Pełny zapis: `KNOWLEDGE.md` „Próba kontrolna hipotezy 28".

Do tego zjawisko trzecie, zaobserwowane po przebiegu (hipoteza 32,
`JOURNAL.md`): **host paruje wątek gry ~50 s po zerwaniu połączenia**
(`futex_wait` bez limitu, render dalej rysuje — „241 FPS a stoi"), dokładnie
w pierwszym 30-sekundowym takcie napełniania po tym, jak kontroler klienta
został „bez Player". Gracz: „to się zawsze działo".

## NASTĘPNY KROK — przebieg hipotezy 31 (może już trwać)

Host wystartowany z nową biblioteką, markery uzbrojone. Przebieg jak przy
próbie 28: gracz klika CONTINUE i zostaje w hubie, ruch pionka uruchamia
pomiar, klient dołącza sam. Kryteria:

| pomiar | oczekiwane przy sukcesie |
|---|---|
| log klienta przy starcie | `SMYCZ: straznik nulla zalozony na SetLeashName` |
| licznik | `SMYCZ: pominiete SetLeashName na nullu: N`, N ≥ 1 ok. 4 s po travelu |
| życie klienta | brak nowego zrzutu w `Crashes` compat2, proces żyje > 120 s po połączeniu |
| licznik `netdriver+0x98` | trzyma 1 dłużej niż 64 s |
| `OBJECIE` po obu stronach | czy uścisk (`ClientRestart` → `ServerAcknowledgePossession`) dochodzi dla klienta |

Potwierdzenie strażnika: ZDJĄĆ `fix_smycz` — awaria ma wrócić z tym samym
stosem. Potem hipoteza 29 (`ServerTravel`, robota statyczna).

**Do pomiaru bez zgadywania:** `ClientConnections` sterownika sieciowego hosta
leży pod `netdriver+0x90` (TArray, licznik `+0x98`), a `ConnectionTimeout` pod
`+0x7C` i `InitialConnectTimeout` pod `+0x78`. Sterownik POWSTAJE dopiero po
CONTINUE (w menu go nie ma — skan znajduje tylko klasy i `Default__`).
Próbnik z przebiegu 28: `~/.claude/jobs/*/tmp/h28-probka.py` (szuka sterownika
sam, próbkuje licznik + tiki wątków co 0,5 s, zleca zrzuty po `0→1`).

## Stan wdrożenia

Biblioteka **wdrożona 15:04**, `md5=96d866a2`. Zgodność ze źródłem sprawdzać
**napisami**, nie sumą (build niepowtarzalny — mingw wpisuje czas w nagłówek
PE). Nowość tej wersji: napisy `SMYCZ:` (6 sztuk w pliku).

**Markery hosta:** `always_listen`, `auto_host`, `fix_attrs`, `fix_booster`,
`fix_dup`, `fix_input`, `late_restart`, `log_objecie`, `map`, `no_pause`,
`swap_now`, `swap_only`, `watch_pc`.
**Markery klienta:** `fix_attrs`, `fix_dup`, `fix_effects`, `fix_smycz`,
`fix_weapon`, `join_delay`, `join_ip`, `log_objecie`.

**ZDJĘTE świadomie:** `fix_state` (wywalał hosta — patrz niżej), `fix_przejscia`,
`fix_czas`, `fix_lista`, `fix_ekwipunek` (obie trampoliny = regresja zamrażająca
hosta, potwierdzona próbą kontrolną 14:41), `fix_ammo` oraz diagnostyka tamtej
linii (`log_tryb`, `log_kanal`, `log_speed`, `log_ammo`, `log_owner`,
`log_fill`, `count_move`).

`log_objecie` UZBROJONE po obu stronach (embargo z §0c zdjęte — h. 28
rozstrzygnięta). Kontrola działania: przy starcie hosta oba haki strzeliły po
razie dla własnego kontrolera (`ClientRestart 1, ServerAcknowledgePossession 1`)
— cisza w przebiegu NIE będzie dwuznaczna.

## Czego NIE powtarzać (drogo kupione 11–12.08)

| co | dlaczego |
|---|---|
| **`fix_lista` + `fix_ekwipunek` w obecnej postaci** | **zamrażały hosta przy dołączaniu** (regresja potwierdzona próbą kontrolną 14:41: bez nich host żył). Pętle wykonują się przy dołączaniu i łamią zasadę 7 — przepisać, zanim wrócą |
| **`fix_state`** | **wywalał hosta.** Stos: zapis warunku ← opakowanie `UpdateCustomConditionBool` ← thunk `UFunction` ← `ProcessEvent`. Gra swoje warunki woła **bezpośrednio**, bez `UFunction` i bez `ProcessEvent` — tą drogą chodzi wyłącznie nasz kod |
| kolejkowanie `IdleToWalking` w dobrej chwili | 3600 prób, 0 udanych, przy potwierdzonym ruchu gracza |
| „pionek klienta trzymany w spadaniu" | obalone: `MovementMode = 1` w 95% próbek |
| pauza jako przyczyna | gracz: pauza zawiesza klienta tylko wtedy, gdy pauzuje **klient**; host może pauzować bez skutku dla klienta |
| wołanie kodu gry drogą, której gra sama nie używa | dwa razy skończyło się awarią hosta (`fix_ammo`, `fix_state`) |

## Jak to działa (droga B)

Host wchodzi normalnie — CONTINUE, potem hub. DLL zamienia w `UEngine::LoadMap`
skok `je` na dwa `NOP`-y (`0x143BEC200`), przez co gra **sama** woła
`UWorld::Listen` przy każdym ładowaniu mapy. Sprawdzone 12.08: **host nasłuchuje
także w hubie** — jest tam żywy `IpNetDriver`.

**Uruchomienie:**
```
tools/stop.sh
WF_GAMESCOPE=1 WF_W=1100 WF_H=620 WF_PREFIX=~/.local/share/witchfire-mp/compat1 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
# gracz klika CONTINUE
echo 127.0.0.1 > <Saved compat2>/WFCoop_join_ip.txt
WF_GAMESCOPE=1 WF_PREFIX=~/.local/share/witchfire-mp/compat2 \
  WF_INJECT=proxy nohup tools/launch-instance2.sh &
```

Przebudowa i wdrożenie: `tools/wdroz-dll.sh` (gry muszą być zamknięte).

## Co jest zrobione

| | dowód |
|---|---|
| obaj gracze w jednym świecie, broń klienta działa | ponad dwie godziny wspólnej gry 11.08 |
| hipoteza 28 rozstrzygnięta: host zdrowy bez trampolin, winowajca śmierci klienta wskazany co do instrukcji | próba kontrolna 14:39–14:49, `KNOWLEDGE.md` |
| host bez duplikatu ekwipunku (`fix_dup`) | gracz: „host działa jak na singleplayer" |
| mapa atrybutów ruchu klienta (`fix_attrs`) | `przed=0.000 po=355.000` |
| host nasłuchuje **także w hubie** | żywy `IpNetDriver` przy hoście w hubie, 12.08 |
| ściany #1 (`0x24`) i #2 (`0x430`) | próby kontrolne: bez strażnika awaria wraca |

## Narzędzia (`tools/`, wszystkie sprawne)

Analiza **bez uruchomionej gry**: `obraz.py` (deasemblacja, odwołania, literały
ze zrzutu), `warunki.py` (kto ustawia który warunek maszyny stanów),
`pole.py` (kto czyta/zapisuje dane pole struktury), `szukaj.py` (dokumentacja
z nagłówkiem sekcji), `przejscia.py` (graf przejść z danych gry).

Na żywej grze: `ue-props.py` (właściwości przez refleksję — **stąd bierze się
offsety pól, których nie ma w zrzucie**), `ue-objects.py`, `stan-gracza.py`,
`ue-snapshot.py`, `sygnatura.py` (grupuje awarie), `read-crash-xml.py`,
`stos-watku.py`, `zrzut.sh`.

Nagrywanie: `obserwator.sh` (wykrywa uruchomienie gry i sam zapisuje sesję),
`rejestrator.py` (szereg czasowy obu graczy; `--podsumuj` zwija do rozkładów),
`czuwak.sh` (awarie z kontekstem), `dozorca.sh`.

Niesprawdzone: `wejscie.py` — wejście przez `/dev/uinput` (urządzenie powstaje
i jądro je widzi; czy **gra** je przyjmuje, nie wiadomo).

## Zasady pracy

**Są w `PROMPT-NOWY-CZAT.md` i tylko tam.** Cztery najdroższe:
nie wołaj funkcji gry bez potwierdzonej sygnatury **i nie drogą, której gra sama
nie używa**; wyzwalacz opieraj na zmierzonym, nie na oczywistym; zanim powiesz
„nie działa", sprawdź, czy okno pomiaru zawiera zjawisko; wrażenie gracza to
pomiar, nie anegdota.

**Piąta, dopisana 12.08 po trzech wpadkach jednej nocy:** *pojedynczy odczyt
z zewnątrz nie opisuje stanu — próbkuj przebieg w czasie, zanim cokolwiek
nazwiesz.* Tej nocy trzy razy z rzędu wzięto migawkę za opis: „pionek
w spadaniu" (naprawdę `Walking` w 95% czasu), „dołączanie w hubie działa"
(naprawdę stan przejściowy między 46 a 110 sekundą), „wyzwalacz nie zadziałał"
(naprawdę okno pomiaru sprzed zjawiska).
