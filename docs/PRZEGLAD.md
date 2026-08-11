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
| C1 | magazynek klienta zostaje zerem, broń przeładowuje się w pętli | hipoteza 24, mechanizm rozebrany (`WIEDZA.md` §3g) |
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
