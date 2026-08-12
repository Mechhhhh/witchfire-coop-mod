# Zacznij tutaj — stan i następny krok

Stan na 2026-08-12, 03:40. **Kierunek projektu zmieniony tej nocy — przeczytaj
sekcję „ZWROT", zanim cokolwiek zrobisz.**

## Co czytać

**Ten plik, potem `PRZEGLAD.md` §0–§0c, potem `DZIENNIK.md`. Nic więcej na starcie.**

`WIEDZA.md` (2300 linii) to zapis, JAK doszliśmy do wniosków — nie czytaj go
w całości. Wyszukuj punktowo:

```
tools/szukaj.py 0x1418002E0        # co wiemy o adresie
tools/szukaj.py "mapa atrybutow"   # z nagłówkiem sekcji
```

Nagłówek sekcji w wynikach mówi, czy trafienie pochodzi z ustalenia
POTWIERDZONEGO, czy z OBALONEGO. **Zanim ruszysz z hipotezą — wyszukaj ją.**

`ADRESY.md` — czysta referencja adresów i offsetów. `PRZEGLAD.md` — co
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

## NASTĘPNY KROK — próba kontrolna, która czeka gotowa

**Zrób ją PIERWSZĄ. Nie buduj niczego przed nią.**

W nocy 12.08 host zaczął **zamarzać w chwili dołączania klienta** (czarny ekran,
4 FPS, zegar stoi). Gracz potwierdził: **wcześniej tego nie było**. Tego samego
wieczoru doszły dwie nowe trampoliny bajtowe — `fix_lista` i `fix_ekwipunek` —
obie w pętlach wykonujących się dokładnie przy dołączaniu.

Oba markery są **ZDJĘTE** (host i klient). Przebieg do wykonania:

1. host → CONTINUE → **zostań w hubie**, nie wchodź na wyprawę,
2. dołącz klienta (`echo 127.0.0.1 > <Saved compat2>/WFCoop_join_ip.txt`, potem
   `tools/launch-instance2.sh` na compat2),
3. obserwuj, czy host zamarza w sekundzie, w której powstaje połączenie.

| wynik | znaczenie |
|---|---|
| **nie zamarza** | regresja jest moja — wycofać albo poprawić obie ściany |
| **zamarza tak samo** | ściany niewinne, szukać dalej (patrz `PRZEGLAD.md` §0c) |

Marker to pusty plik, więc przywrócenie to `touch WFCoop_fix_lista.txt`.

**Do pomiaru bez zgadywania:** `ClientConnections` sterownika sieciowego hosta
leży pod `netdriver+0x90` (TArray, licznik `+0x98`), a `ConnectionTimeout` pod
`+0x7C` i `InitialConnectTimeout` pod `+0x78`. Próbkowanie licznika co pół
sekundy pokazuje dokładną sekundę powstania i zerwania połączenia — tak
zmierzono 64 s przy `ConnectionTimeout = 60 s`.

## Stan wdrożenia

Biblioteka **wdrożona**, `md5=8ed4a803`. Zgodność ze źródłem sprawdzona
**napisami**, nie sumą: build nie jest powtarzalny (mingw wpisuje znacznik czasu
w nagłówek PE), więc dwa buildy tego samego źródła mają różne md5. We wdrożonym
pliku są wszystkie napisy z ostatniej zmiany (`OBJECIE:`, `EKWIPUNEK: straznik`,
`LISTA: straznik`, `CZAS: wywolan`), a rozmiar zgadza się co do bajta.

**Markery hosta:** `always_listen`, `auto_host`, `fix_attrs`, `fix_booster`,
`fix_dup`, `fix_input`, `late_restart`, `map`, `no_pause`, `swap_now`,
`swap_only`, `watch_pc`.
**Markery klienta:** `fix_attrs`, `fix_dup`, `fix_effects`, `fix_weapon`,
`join_delay`, `join_ip`.

**ZDJĘTE świadomie:** `fix_state` (wywalał hosta — patrz niżej), `fix_przejscia`,
`fix_czas`, `fix_lista`, `fix_ekwipunek`, `fix_ammo` oraz cała diagnostyka
tamtej linii (`log_tryb`, `log_kanal`, `log_speed`, `log_ammo`, `log_owner`,
`log_fill`, `count_move`).

W kodzie jest gotowy, ale **bez markera** hak `log_objecie` (`patchObjecieLog`):
podgląda obie połowy uścisku dłoni objęcia pionka. Powstał, zanim wyszło, że
zamarza host — więc **najpewniej mierzyłby objaw**. Nie kłaść tego markera,
dopóki próba kontrolna nie rozstrzygnie sprawy zamrożenia.

## Czego NIE powtarzać (drogo kupione 11–12.08)

| co | dlaczego |
|---|---|
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
