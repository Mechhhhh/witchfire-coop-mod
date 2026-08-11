# witchfire-coop

Nieoficjalny mod co-op dla dwóch graczy do **Witchfire** — gry, która nie ma
żadnego trybu sieciowego. To proxy DLL wstrzykiwany do procesu gry: łata pamięć, podpina
się pod vtable i wywołuje własny kod gry, żeby włączyć sieć, którą gra już w
sobie ma, ale nigdy jej nie udostępnia.

Działa na Linuksie przez Protona. Na Windowsie też — sam mod to zwykły
windowsowy DLL, tylko skrypty uruchamiające są linuksowe.

**Stan: nieskończone i szczerze mówiąc daleko do końca.** Dwie osoby grają razem
ponad dwie godziny bez awarii. Dwa z czterech znanych problemów są naprawione i
potwierdzone powtórzonymi przebiegami. Dwa dalej są otwarte — w jednym przyczyna
jest rozpracowana do końca, ale naprawa nie działa. Przeczytaj „Co nie działa",
zanim spróbujesz.

---

## Co działa

Każde twierdzenie niżej zostało zmierzone, nie założone.

- **Obaj gracze są w jednym świecie i widzą się nawzajem.** Ponad dwie godziny
 wspólnej gry bez awarii.
- **Dołączenie nie psuje hosta.** Wcześniej dołączający gracz po raz drugi
 ładował ekwipunek hosta: host dostawał drugi komplet broni, tracił walutę
 zdobytą w przebiegu i psuł mu się widok z pierwszej osoby. Naprawione
 zabezpieczeniem, które pomija powtórne wypełnienie; relacja gracza brzmiała:
 *„host zachowuje się teraz jak w singlu"*.
- **Klient chodzi.** W komponencie ruchu klienta 13 z 19 zapamiętanych atrybutów
 ruchu było wyzerowanych, więc serwerowy limit prędkości dla tego pawna
 wychodził `0.0` i cofał gracza przy każdym kroku. Naprawione przez ponowne
 uruchomienie własnej synchronizacji atrybutów gry, kiedy dane już istnieją:
 `0.000 → 355.000`.
- **Klient dobywa broni** i strzela w świecie hosta.

## Co nie działa

- **Sprint i ślizg szarpią.** Serwer nie wie, że zdalny gracz sprintuje, więc
 liczy 615 (zwykły bieg) albo 265 (kucanie) zamiast 800 i cofa klienta.
 Przyczyna jest rozpracowana do końca (niżej), naprawa jeszcze nie działa.
- **Magazynek klienta zostaje pusty**, więc przeładowanie kręci się w kółko bez
 końca. Przyczyna jest znaleziona, a naprawa w chwili pisania jest w testach.
- Kilka elementów HUD-u u klienta zostaje pustych (licznik mikstur, waluta z
 przebiegu, panel celu, własna strzałka na minimapie). Dane pod spodem są
 poprawne — to sprawa samego wyświetlania.

---

## Jak to działa

- **Hostowanie to łatka na dwa bajty.** `UEngine::LoadMap` sprawdza, czy URL mapy
 zawiera `listen`, i jeśli nie zawiera — pomija `UWorld::Listen`. Zamiana tego
 skoku warunkowego na dwa `NOP`-y sprawia, że gra sama uruchamia swój
 listen-serwer, ze swoim światem i swoim URL-em, dokładnie w tym miejscu
 własnego startu misji. Wymuszanie mapy z zewnątrz — pierwsze podejście, jakie
 próbowano — rozwala sekwencję misji i zostało porzucone.
- **Mod prawie nigdy nie podstawia wartości.** Kiedy coś jest źle, naprawą jest
 ponowne wywołanie własnej funkcji gry, gdy jej dane wejściowe są już gotowe.
 Obie działające naprawy mają taki kształt. Podstawienie liczby traktujemy jako
 *dowód przyczyny*, a nie jako naprawę.
- **Gra w ogóle nie replikuje ekwipunku.** `DimensionInventoryComponent` ma 50
 funkcji i zero RPC; z 203 RPC w całej grze żadne nie dobywa broni. Autorzy
 umieli replikować — `Actor`, `Character` i `DimensionWeapon` mają replikowane
 właściwości — po prostu nie objęli tym tego podsystemu, bo w grze dla jednego
 gracza nie było po co.
- **Tak samo jest z maszyną stanów gracza**: 47 funkcji, zero RPC. Sprint i
 ślizg to stany tej maszyny, napędzane wejściem — a serwer nie ma komponentu
 wejścia dla zdalnego gracza. Dlatego sprint się rozjeżdża, a dash nie: dash
 jest *zdolnością*, a zdolności się replikują.
- **Analiza idzie offline.** Na pytania o kod gry odpowiada analiza obrazu pliku
 wykonywalnego, bez uruchamiania gry: deasemblacja, odwołania krzyżowe, napisy
 i granice funkcji — wszystko z tego obrazu. Repozytorium nie zawiera ani takiego
 obrazu, ani narzędzia do jego pozyskania — `tools/obraz.py` czyta obraz, który
 użytkownik dostarcza sam.

---

## Wymagania

- **Każdy gracz musi mieć własny, legalnie kupiony egzemplarz Witchfire.** Ten mod
 nie służy do grania we dwoje z jednego egzemplarza i nie jest do tego
 przeznaczony.
- Linux z Protonem albo Windows.
- Dwie instancje gry, każda z własnym prefiksem i własnym zapisem.
- Kompilacja przez mingw-w64 (`x86_64-w64-mingw32-g++`).

Repozytorium nie zawiera żadnych zasobów gry ani treści niewydanej — tylko kod
źródłowy, narzędzia i notatki powstałe w tym projekcie. Jedyny wyjątek to kilka
krótkich ciągów bajtów kodu maszynowego zacytowanych z gry w
`src/proxy-dll/dllmain.cpp`; są technicznie niezbędne, żeby sprawdzić i założyć
łatki, **nie** są objęte licencją MIT tego projektu, a plik mówi o tym w każdym
miejscu, gdzie występują.

To nie jest oficjalny tryb sieciowy i nigdy nim nie będzie. Projekt nie jest
powiązany z The Astronauts ani przez nich firmowany. Licz się z awariami.

Kod, komentarze i dokumentacja są na razie po polsku; przejście na angielski jest
planowane.

---

## O autorze i o AI — ten fragment przeczytaj

Projekt prowadzi jedna osoba pracująca sama, mniej więcej dziesięć
godzin dziennie, czasem więcej, od **8 sierpnia 2026**. W chwili pisania tego
tekstu to około cztery dni. To krótki, bardzo intensywny kawałek pracy i celowo
jest tak opisany: nikt tu nie udaje, że poszły na to miesiące.

**Kod i większość inżynierii wstecznej powstały razem z modelem AI** (Claude,
przez Claude Code). To nie przypis na dole strony — to większość pisania. Model
pisze C++, czyta deasemblację, stawia hipotezy i prowadzi dokumentację.

To, co robi człowiek, też nie jest ozdobą, i repozytorium ma na to dowody:

- **To on uruchamia grę i tylko on może.** Prawie każde ustalenie stąd wymagało,
 żeby ktoś naprawdę grał — sprintował, ślizgał się, przeładowywał — a hooki w
 tym czasie zapisywały, co się dzieje. Pomiary bez żywego gracza dawały ciszę,
 która wyglądała dokładnie jak wynik, a wynikiem nie była.
- **Obalał błędne wnioski modelu, i to nie raz.** Model orzekł, że dane klienta
 są w porządku i kłamie tylko HUD. Gracz zbił to jednym zdaniem: *gdyby chodziło
 o samo wyświetlanie, broń dalej by strzelała*. Miał rację — pomiar pokazał
 potem, że amunicja jest zerowa również na serwerze.
- **Podsunął pomiar, który rozgryzł błąd ruchu**: *sprawdź, jak działa ruch u
 hosta, skoro host się rusza*. Porównanie obu graczy wewnątrz jednego procesu
 wskazało dokładnie tę instrukcję, w której ścieżki się rozchodzą.
- **Odrzucał naprawy, które były podróbkami.** Łatka zwracająca zaszyty na
 sztywno sufit prędkości wyleciała z tego powodu, że podstawia liczbę zamiast
 naprawiać mechanizm. Ta zasada ukształtowała cały mod.

I uczciwa druga połowa: **model mylił się wielokrotnie, i to tak, że bez
sprawdzenia przez człowieka te błędy poszłyby dalej.** Jedną funkcję odczytał raz
jako clamp, a raz jako wypełnianie — zmienił zdanie dwa razy, na podstawie samej
deasemblacji. Zgadł wartość bajtu, która okazała się zła; wpisał w notatkach, że
inny wzorzec bajtów jest „zmierzony w kodzie gry", choć naprawdę czytał sztuczną
ścieżkę kodu; dwa razy napisał łatki, które wywaliły obie instancje gry.
Dokumentacja w tym repozytorium notuje te sprostowania celowo, bo w tym projekcie
sprostowania bywały warte więcej niż pierwotne wnioski.

Jeśli szukasz projektu, w którym AI pracowało samodzielnie — to nie ten. To też
nie jest projekt, w którym AI było sprawdzaczem pisowni. Jest gdzieś pośrodku i
warto to powiedzieć dokładnie.

Pełna lista współtwórców: [CONTRIBUTORS.md](CONTRIBUTORS.md).

## Wsparcie

Jeśli chcesz wesprzeć tę pracę: **https://ko-fi.com/mechhhh**

## Licencja

Apache License 2.0 — patrz [LICENSE](LICENSE) i [NOTICE](NOTICE).

Licencja jest wybrana dla jednej rzeczy: **wskazania autorstwa**. Jeśli
rozpowszechniasz ten projekt albo coś na nim opartego, punkt 4 wymaga
zachowania pliku NOTICE i przekazania jego treści dalej — dzięki temu zostaje
widoczne, że praca bazuje na tym projekcie. Poza tym możesz go używać, zmieniać
i rozpowszechniać, także komercyjnie.

Kod jest otwarty i taki ma zostać.

## Zastrzeżenie

Mod zmienia pamięć gry dla jednego gracza, w twoim własnym procesie, żeby
umożliwić wspólną grę. To nie jest cheat do gier sieciowych i nie jest do niczego takiego
przeznaczony. Używasz na własne ryzyko; odpowiadasz za to, jak z tego korzystasz.
