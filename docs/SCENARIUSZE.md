# Scenariusze — co dzieje się w której ścieżce wejścia

> **UWAGA (2026-08-10): ten plik opisuje głównie porzuconą DROGĘ A** (wymuszanie
> mapy przez `OpenLevel`). Obowiązuje **droga B**: host wchodzi normalnie, a DLL
> dokłada nasłuch — patrz `START-TUTAJ.md`.
>
> Co z tego pliku **nadal obowiązuje**:
> - `gamescope` jest wymagany (utrata fokusu pauzuje instancję),
> - `IpNetDriver` włączony przez `DefaultPlatformService=NULL` w `Engine.ini`,
> - **menu ignoruje syntetyczne kliknięcia** — CONTINUE klika człowiek,
> - klient skacze z menu, nie z wnętrza biegu.
>
> Reszta (markery `auto_host`, `swap_now`, `late_restart`, opisy objawów na
> mapie misji) dotyczy drogi A i nie stosuje się do obecnej konfiguracji.

Powstało, bo myliłem te ścieżki i przez to raz zmierzyłem instancję, która wcale
nie miała badanego objawu. **To nie są warianty tego samego testu — to różne
stany gry i dają różne wyniki.** Przed każdym przebiegiem sprawdzić w tej tabeli,
czy badany objaw w ogóle w tym scenariuszu występuje.

---

## A. Host wchodzi przez `OpenLevel(mapa_misji, "listen")` — mapa misji

Nasz mod ładuje poziom na siłę, **omijając sekwencję startu misji**.

| co | jak jest |
|---|---|
| wejście gracza | natychmiast do poziomu, **bez menu i bez CONTINUE** |
| sekwencja startu misji | **pominięta** |
| sterowanie | **zablokowane** — trzeba oddać przez `unlockInput()` (marker: brak `no_unlock`) |
| broń | jest **przed** dołączeniem klienta, ale **nie da się nią strzelać ani celować** (pominięta sekwencja startu misji) |
| przebieg (bieg/run) | gra go nigdy nie „rozpoczęła" |
| po dołączeniu klienta | w starszych przebiegach host **wypadał do menu**; w ostatnim (22:39) obie instancje chodziły po 200 FPS i mapa „działała w połowie" |
| klient | wchodzi, widzi świat, **rusza się częściowo** (jedna oś pozioma), skakanie działa, host widzi jego animacje |

**Do czego się nadaje:** przebiegi w pełni automatyczne (nikt nic nie klika),
badanie ruchu klienta i widoczności postaci.

**Uwaga — dwie RÓŻNE rzeczy z bronią, nie mylić ich:**
1. **Na mapie misji, przed dołączeniem klienta:** broń jest w ręce, ale
   **nie strzela i nie celuje**. To skutek pominiętej sekwencji startu misji —
   gra nie „uzbroiła" gracza.
2. **Po dołączeniu klienta, na KAŻDEJ mapie:** broń, ręce i celownik znikają.
   To osobne zjawisko, zależne od `Login`, a nie od mapy.
**Do czego się NIE nadaje:** badanie zamrożenia klienta — tu objaw bywa słabszy
albo go nie ma.

## B. Host wchodzi przez hub + CONTINUE (`Persistent_Base`)

Gra przechodzi **całą swoją sekwencję**: profil, bieg, loadout.

| co | jak jest |
|---|---|
| wejście gracza | menu jako nakładka nad żywym światem → **człowiek klika CONTINUE** |
| sekwencja startu | **wykonana normalnie** |
| sterowanie | działa od razu, bez naszej ingerencji |
| mod a kursor | **musi mieć marker `WFCoop_no_unlock.txt`** — inaczej `unlockInput()` chowa kursor i nie da się kliknąć CONTINUE |
| broń | jest, do czasu dołączenia klienta |
| po dołączeniu klienta | host **chodzi dalej**, ale traci broń, ręce i celownik |
| uwaga | utrata broni przy dołączeniu **NIE zależy od mapy** — dzieje się tak samo na mapie misji |
| klient | **zamarza** — to jest scenariusz, w którym badamy zamrożenie |

**Do czego się nadaje:** badanie zamrożenia klienta. Utrata broni występuje
tu tak samo jak na mapie misji, więc do jej badania nadaje się każdy scenariusz.
**Ograniczenie:** CONTINUE musi kliknąć **człowiek** — menu ignoruje syntetyczne
kliknięcia i `Enter` (brak akcji `Accept`/`Confirm` w mapowaniach).
**Ale:** do badania samego klienta host **może zostać w menu** — w przebiegu 59
klient zamarzał również wtedy. Wtedy przebieg jest w pełni automatyczny.

## C. Skąd skacze klient — to zmienia WYNIK

| klient skacze… | efekt |
|---|---|
| **z menu** (nie kliknął CONTINUE) | **łączy się** — host pokazuje `conn=1` |
| **z wnętrza biegu** (po CONTINUE) | **nie łączy się wcale** — `conn=0` przez cały czas, a jego `GWorld` i tak się zmienia, bo to jego własna gra przeładowuje mapę po nieudanym połączeniu |

Wygląda na to, że gra w trakcie biegu przechwytuje albo unieważnia travel.
**Domyślnie testować skok z menu.**

## D. Pauza i ekwipunek — psują wejście TRWALE

Dotyczy **każdego** scenariusza, także w gamescope (czyli bez utraty fokusu).

- naciśnięcie Escape / wejście w ekwipunek → po powrocie **nie da się już nic
  zrobić poza pauzowaniem**,
- nie pomaga ręczne kliknięcie RESUME,
- historycznie brało się z tego wrażenie „host traci sterowanie, gdy klient się
  łączy" — bo dołączenie klienta wyrzucało go do menu, a **menu działa jak pauza**.

**Na czas testów: nie dotykać pauzy ani ekwipunku.**

## E. Środowisko

| rzecz | stan |
|---|---|
| gamescope | **wymagany** — bez niego utrata fokusu pauzuje instancję i psuje wejście |
| `IpNetDriver` | włączony przez `DefaultPlatformService=NULL` w `Engine.ini` obu prefiksów |
| Steam Cloud | wyłączony (nie miało wpływu, ale zostawione) |
| ustawienia grafiki | minimalne (nie miało wpływu — problem nie jest graficzny) |

---

## Co mierzyć w którym scenariuszu

| pytanie | scenariusz | miernik |
|---|---|---|
| czy klient zamarza | **B** (hub), host może zostać w menu | stan wątków: zdrowa instancja ma `wchan` pusty, zaklinowana — wszystkie w oczekiwaniu |
| czy klient wchodzi | dowolny | PULS w `WFCoopProxy.log`: zmiana `GWorld` |
| czy klient się porusza | **A** (mapa misji) | pozycja jego pawna w `RUCH:` u hosta |
| czy host traci broń | **B** | wzrok — HUD pokazuje amunicję, ale broni nie widać |
| czy host pada | dowolny, po ~1–4 min | nowy katalog w `Saved/Crashes` + `read-crash-xml.py` |

**Zasada:** nigdy nie mierzyć bez próbki kontrolnej z instancji, która działa.
Bez tego `ntsync_char_ioctl` u klienta wygląda groźnie, a dopiero porównanie
z hostem (gdzie `wchan` jest pusty) pokazuje, że to naprawdę zator.

---

## Planowane narzędzie: podsłuch ruchu sieciowego

Pomysł kolegi — i dobry, bo to **pierwsze narzędzie, które zmierzy
sam kanał**, a nie oba końce osobno. `tcpdump`/Wireshark na UDP 7777 odpowie na
pytania, których dotąd nie umieliśmy postawić:

1. **Ile host wysyła w chwili dołączenia?** Jeśli to lawina, hipoteza
   o streamingu poziomów dostaje twardą liczbę zamiast domysłu.
2. **Czy klient odpowiada w trakcie zamrożenia?** Jeśli tak — jego sieć żyje,
   a stoi tylko reszta. Jeśli nie — zator obejmuje też odbiór pakietów.
3. **Czy to serwer przestaje wysyłać, czy klient przestaje odbierać?**

Do zrobienia: `tcpdump -i lo -n udp port 7777` z zapisem do pliku i policzeniem
bajtów w oknach czasowych wokół `conn=1`.


---

## KOREKTY (uwagi użytkownika, 2026-08-09 późny wieczór)

Trzy rzeczy zapisałem wcześniej źle:

**1. Utrata broni przy dołączeniu nie zależy od mapy.** Wpisałem ją jako cechę
huba — nieprawda, na mapie misji dzieje się to samo. Jest związana z `Login`
drugiego gracza, nie ze scenariuszem wejścia.

**2. Na mapie misji host ma broń przed połączeniem, ale nie może strzelać ani
celować.** To osobny problem od znikania broni: skutek pominiętej sekwencji
startu misji. Dwa różne objawy, które wrzucałem do jednego worka.

**3. Ręce, które host widzi po `fixHands()`, są PUSTE** — wiszą w powietrzu i nie
trzymają broni.

Punkt 3 obala moje wcześniejsze „jedna flaga tłumaczy ręce, broń i celownik
naraz". Zdjęcie `bOnlyOwnerSee` przywraca **sam komponent rąk** i nic więcej —
broń nie jest do nich przyczepiona albo jej model nie istnieje. Czyli:

- **ręce** = komponent `Mesh1P`, ukryty przez flagę → to potwierdzone,
- **broń** = osobny obiekt, którego przy dołączeniu **nie ma albo nie jest
  przyczepiony** → osobna przyczyna, jeszcze niezbadana,
- **celownik** = najpewniej idzie za bronią, ale to też domysł.

Nie łączyć tych trzech, dopóki każdego nie zmierzy się osobno.
