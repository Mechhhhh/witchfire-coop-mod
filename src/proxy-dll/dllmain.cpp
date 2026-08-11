// WFCoopProxy — wlasna biblioteka wstrzykiwana do Witchfire jako dwmapi.dll.
//
// Po co, skoro dziala UE4SS: klient ginie sekunde po wejsciu do swiata hosta i
// po 26 przebiegach wykluczylismy wszystko, co dalo sie wylaczyc z Lua i z
// konfiguracji — lacznie z KAZDYM opcjonalnym hakiem UE4SS. Zostal rdzen UE4SS:
// sama wstrzyknieta biblioteka, skanowanie GUObjectArray, przechwycone FName.
// Tego nie da sie wylaczyc przelacznikiem. Rozstrzygnie dopiero klient, ktory
// dolacza do sesji BEZ tej maszynerii — czyli ta biblioteka.
//
// Dlaczego akurat dwmapi: gra importuje z niej dokladnie cztery funkcje
// (DwmSetWindowAttribute, DwmGetCompositionTimingInfo, DwmIsCompositionEnabled,
// DwmFlush), wiec przekierowanie jest krotkie i bezpieczne. Ta sama sciezka,
// ktorej uzywa UE4SS, wiec wiemy, ze dziala pod Protonem.
//
// KROK 1 (ten plik): tylko wejsc do procesu, przekazac wywolania dalej i zostawic
// slad w logu. Zadnego dotykania silnika. Dopiero gdy to jest pewne, ma sens
// szukanie GEngine i wolanie travelu.
//
// UWAGA LICENCYJNA. W tym pliku wystepuja krotkie tablice bajtow kodu
// maszynowego POCHODZACE Z GRY (prologi latanych funkcji: raz do sprawdzenia,
// ze latamy to, co trzeba, raz przeniesione do trampoliny, zeby wykonac je
// zamiast nadpisanych instrukcji). To cytat z cudzego programu, niezbedny
// technicznie do zalozenia latki, a NIE kod tego projektu: licencja MIT
// obejmuje kod napisany tutaj i nie rozciaga sie na te bajty ani na zaden inny
// element gry. Prawa do nich naleza do jej autorow.

#include <windows.h>
#include <cstdio>
#include <cstdint>
#include <cstring>

// Nazwa biblioteki, ktora udajemy. Ustawiana przez -DWFCOOP_AS_VERSION przy
// budowaniu wariantu version.dll.
//
// Po co dwa warianty: obie instancje dziela katalog gry, wiec jeden plik nie
// moze nalezec naraz do UE4SS i do nas. Ale WINEDLLOVERRIDES dziala PER PROCES,
// wiec host bierze `dwmapi=n,b` (UE4SS) i `version=b` (nasza pomijana), a klient
// odwrotnie: `version=n,b` i `dwmapi=b`. Kazda instancja dostaje dokladnie
// jeden wstrzykiwacz — o to chodzi w tescie M4.
#ifdef WFCOOP_AS_XINPUT
// Wariant xinput niczego nie przekierowuje, ale realDll() jest wspolne dla
// wszystkich wariantow — musi miec jakas nazwe. Nieuzywana.
#  define WFCOOP_REAL_DLL L"\\xinput1_3.dll"
#  define WFCOOP_LOGNAME "WFCoopProxy(xinput)"
#elif defined(WFCOOP_AS_VERSION)
#  define WFCOOP_REAL_DLL L"\\version.dll"
#  define WFCOOP_LOGNAME "WFCoopProxy(version)"
#else
#  define WFCOOP_REAL_DLL L"\\dwmapi.dll"
#  define WFCOOP_LOGNAME "WFCoopProxy(dwmapi)"
#endif

namespace {

HMODULE g_real = nullptr;

// Pelna sciezka systemowa jest konieczna: nasza biblioteka nazywa sie TAK SAMO
// jak prawdziwa i lezy obok exe, wiec LoadLibrary po samej nazwie zaladowalby
// nas samych.
HMODULE realDll()
{
    if (g_real) return g_real;
    wchar_t path[MAX_PATH];
    UINT n = GetSystemDirectoryW(path, MAX_PATH);
    if (n == 0 || n > MAX_PATH - 16) return nullptr;
    wcscat_s(path, MAX_PATH, WFCOOP_REAL_DLL);
    g_real = LoadLibraryW(path);
    return g_real;
}

// Sciezka do katalogu `Saved` gry — WYLICZANA, nie zaszyta.
//
// Bylo tu na sztywno "C:\\users\\steamuser\\AppData\\Local\\Witchfire\\Saved".
// `steamuser` to nazwa konta, ktora tworzy Proton — dziala tylko pod Wine.
// Na prawdziwym Windowsie u drugiego gracza uzytkownik nazywa sie inaczej, wiec
// biblioteka nie zapisala logu ANI nie odczytala pliku z adresem hosta: wygladalo
// to jak "gra nie reaguje", a naprawde nie mielismy dokad skakac.
// %LOCALAPPDATA% daje pod Wine dokladnie te sama sciezke, wiec jedno rozwiazanie
// obsluguje oba srodowiska.
static const char* savedDir()
{
    static char buf[MAX_PATH] = {};
    if (buf[0]) return buf;
    char base[MAX_PATH] = {};
    DWORD n = GetEnvironmentVariableA("LOCALAPPDATA", base, MAX_PATH);
    if (n == 0 || n >= MAX_PATH)
        strcpy_s(base, MAX_PATH, "C:\\users\\steamuser\\AppData\\Local");
    sprintf_s(buf, MAX_PATH, "%s\\Witchfire\\Saved", base);
    return buf;
}

static const char* savedPath(const char* name)
{
    static char buf[MAX_PATH];
    sprintf_s(buf, MAX_PATH, "%s\\%s", savedDir(), name);
    return buf;
}

void logLine(const char* fmt, ...)
{
    // Ten sam katalog, w ktorym mod Lua trzyma swoj log — czyli wewnatrz
    // prefiksu Wine, osobno dla kazdej instancji.
    FILE* f = nullptr;
    if (fopen_s(&f, savedPath("WFCoopProxy.log"), "a") != 0 || !f)
        return;

    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(f, "%02d:%02d:%02d [proxy] ", t.wHour, t.wMinute, t.wSecond);

    va_list ap;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);

    fputc('\n', f);
    fclose(f);
}

template <typename T>
T resolve(const char* name)
{
    HMODULE m = realDll();
    return m ? reinterpret_cast<T>(GetProcAddress(m, name)) : nullptr;
}

} // namespace

// ── przekierowania ──────────────────────────────────────────────────────────
// Sygnatury sa udokumentowane i stale, wiec przekazujemy je wprost, bez trampolin
// w asemblerze. Gdyby prawdziwej funkcji zabraklo, zwracamy E_FAIL zamiast
// skakac pod null — gra ma sie wtedy zachowac jak przy braku kompozycji, a nie
// wywalic.

extern "C" HRESULT WINAPI DwmSetWindowAttribute(HWND hwnd, DWORD attr, LPCVOID value, DWORD size)
{
    using Fn = HRESULT(WINAPI*)(HWND, DWORD, LPCVOID, DWORD);
    static Fn fn = resolve<Fn>("DwmSetWindowAttribute");
    return fn ? fn(hwnd, attr, value, size) : E_FAIL;
}

extern "C" HRESULT WINAPI DwmGetCompositionTimingInfo(HWND hwnd, void* info)
{
    using Fn = HRESULT(WINAPI*)(HWND, void*);
    static Fn fn = resolve<Fn>("DwmGetCompositionTimingInfo");
    return fn ? fn(hwnd, info) : E_FAIL;
}

extern "C" HRESULT WINAPI DwmIsCompositionEnabled(BOOL* enabled)
{
    using Fn = HRESULT(WINAPI*)(BOOL*);
    static Fn fn = resolve<Fn>("DwmIsCompositionEnabled");
    if (!fn) { if (enabled) *enabled = FALSE; return E_FAIL; }
    return fn(enabled);
}

extern "C" HRESULT WINAPI DwmFlush(void)
{
    using Fn = HRESULT(WINAPI*)(void);
    static Fn fn = resolve<Fn>("DwmFlush");
    return fn ? fn() : E_FAIL;
}

#ifdef WFCOOP_AS_XINPUT
// Zadnego przekierowania: odpowiadamy "brak kontrolera". To uczciwa odpowiedz
// w rozumieniu XInput, a gra i tak jest testowana z klawiatura i mysza.
#define WF_NO_DEVICE 1167u   /* ERROR_DEVICE_NOT_CONNECTED */
extern "C" DWORD WINAPI XInputGetState(DWORD, void*)                  { return WF_NO_DEVICE; }
extern "C" DWORD WINAPI XInputSetState(DWORD, void*)                  { return WF_NO_DEVICE; }
extern "C" DWORD WINAPI XInputGetCapabilities(DWORD, DWORD, void*)    { return WF_NO_DEVICE; }
extern "C" void  WINAPI XInputEnable(BOOL)                            { }
extern "C" DWORD WINAPI XInputGetDSoundAudioDeviceGuids(DWORD, void*, void*) { return WF_NO_DEVICE; }
extern "C" DWORD WINAPI XInputGetBatteryInformation(DWORD, BYTE, void*)      { return WF_NO_DEVICE; }
extern "C" DWORD WINAPI XInputGetKeystroke(DWORD, DWORD, void*)       { return WF_NO_DEVICE; }
extern "C" DWORD WINAPI XInputGetStateEx(DWORD, void*)                { return WF_NO_DEVICE; }
#endif

#ifdef WFCOOP_AS_VERSION
// Gra importuje z VERSION.dll tylko te trzy, w wersjach ANSI.
extern "C" DWORD WINAPI GetFileVersionInfoSizeA(LPCSTR f, LPDWORD h)
{
    using Fn = DWORD(WINAPI*)(LPCSTR, LPDWORD);
    static Fn fn = resolve<Fn>("GetFileVersionInfoSizeA");
    return fn ? fn(f, h) : 0;
}
extern "C" BOOL WINAPI GetFileVersionInfoA(LPCSTR f, DWORD h, DWORD len, LPVOID data)
{
    using Fn = BOOL(WINAPI*)(LPCSTR, DWORD, DWORD, LPVOID);
    static Fn fn = resolve<Fn>("GetFileVersionInfoA");
    return fn ? fn(f, h, len, data) : FALSE;
}
extern "C" BOOL WINAPI VerQueryValueA(LPCVOID block, LPCSTR sub, LPVOID* out, PUINT len)
{
    using Fn = BOOL(WINAPI*)(LPCVOID, LPCSTR, LPVOID*, PUINT);
    static Fn fn = resolve<Fn>("VerQueryValueA");
    return fn ? fn(block, sub, out, len) : FALSE;
}
#endif

// ── wejscie ─────────────────────────────────────────────────────────────────

// ── adresy w grze ───────────────────────────────────────────────────────────
// Binarka laduje sie ZAWSZE pod 0x140000000 (brak ASLR — potwierdzone w
// zrzutach awaryjnych, w /proc/PID/maps i przez te wlasnie DLL). Adresy sa
// wiec stale i mozna je zaszyc.
//
// Skad: sonda dumpAddresses() w modzie Lua podala adresy OBIEKTOW, a
// tools/find-globals.py znalazl globalne zmienne, ktore na nie wskazuja.
// SetClientTravel wyszperany przez: Func UFunction ClientTravelInternal
// (offset +0xD8) -> natywny thunk -> wywolanie wirtualne przez vtable
// PlayerControllera +0x8C8 -> ClientTravelInternal_Implementation, a tam
// przygotowanie argumentow dokladnie w tej sygnaturze.
//
// SetClientTravel potwierdzony literalem "Listen" — to dokladnie ten fragment
// UE4: "Prevent crashing the game by attempting to connect to own listen
// server", if (Context.LastURL.HasOption(TEXT("Listen"))).
namespace addr {
constexpr uintptr_t BASE = 0x140000000ull;
constexpr uintptr_t GEngine_OFF = 0x6686DA0;
constexpr uintptr_t GWorld_OFF = 0x668AA68;
constexpr uintptr_t SetClientTravel_OFF = 0x3BF1590;
// Thunk wolajacy zdarzenie Blueprintu — miejsce, w ktorym ginie klient.
constexpr uintptr_t BpEventThunk_OFF = 0x1B7DDE0;
}

// ── TRAVEL Z WATKU GRY ──────────────────────────────────────────────────────
//
// Dlaczego to w ogole robimy: dotad wolalismy `SetClientTravel` z NASZEGO watku
// roboczego. Ta funkcja zapisuje URL podrozy do kontekstu swiata, a watek gry
// czyta te pola przy najblizszym tyknieciu. Zapis FString z obcego watku
// w chwili, gdy silnik moze go czytac, to wyscig — a jego objawem bywa dokladnie
// to, co widzimy u klienta: proces zyje, brak awarii, brak bledu, wszystko staje.
//
// To jedyny czynnik, ktory byl STALY we wszystkich przebiegach i ktorego nigdy
// nie sprawdzilismy. Tlumaczylby, czemu objaw nie drgnal przy zadnej zmianie
// mapy, transportu, kolejnosci wchodzenia, konta ani rozdzielenia instancji —
// bo zadna z tych rzeczy nie dotyka watku, z ktorego wolamy.
//
// Rozwiazanie: thunk zdarzen Blueprintu (ten sam, ktory juz latamy) jest wolany
// przez kod gry, czyli Z WATKU GRY. Podpinamy sie pod niego i przy pierwszym
// wywolaniu po uzbrojeniu wykonujemy travel stamtad.
using SetClientTravelFn = void(__fastcall*)(void* engine, void* world,
                                            const wchar_t* url, int travelType);

static bool          g_hooked      = false; // czy trampolina stoi
static volatile LONG g_travelArmed = 0;   // ustawia watek roboczy, gdy czas
static volatile LONG g_travelDone  = 0;   // zeby wykonac dokladnie raz
static wchar_t       g_travelUrl[128];
static void**        g_pGEngine = nullptr;
static void**        g_pGWorld  = nullptr;
static SetClientTravelFn g_setClientTravel = nullptr;

// Zapowiedz: samo wyjecie broni jest nizej, bo potrzebuje adresow i pomocnikow
// zdefiniowanych po travelu. Baza modulu trzymana osobno, bo na watku gry nie
// chcemy wolac GetModuleHandle przy kazdym wywolaniu.
static void wfcoopWyjmijBron(uintptr_t base);
static void kanalTick(uintptr_t base);
static void tikNapelniania(uintptr_t base);
static uintptr_t g_bazaModulu = 0;

// Wolane z trampoliny, czyli juz na watku gry.
extern "C" void wfcoopOnGameThread()
{
    // Wyjecie broni jest NIEZALEZNE od travelu i musi isc przed wyjsciem
    // wczesniejszym ponizej — inaczej u hosta (ktory nie ma uzbrojonego
    // travelu) nigdy by sie nie wykonalo.
    if (g_bazaModulu) wfcoopWyjmijBron(g_bazaModulu);

    // Kanal stanu ruchu MUSI isc stad, a nie z watku pulsu: wysylka to
    // `ProcessEvent` -> siec, czyli kod gry. Wolanie go z obcego watku bylo juz
    // raz zrodlem calodniowej diagnozy przy travelu — nie powtarzamy tego.
    if (g_bazaModulu) kanalTick(g_bazaModulu);

    // Powtorka napelniania magazynka — takze z watku gry, bo wola kod gry.
    if (g_bazaModulu) tikNapelniania(g_bazaModulu);

    if (!g_travelArmed) return;
    if (InterlockedExchange(&g_travelDone, 1)) return;   // tylko raz

    void* engine = g_pGEngine ? *g_pGEngine : nullptr;
    void* world  = g_pGWorld  ? *g_pGWorld  : nullptr;
    if (!engine || !world || !g_setClientTravel) {
        // Jeszcze nie ma swiata — pozwol sprobowac przy nastepnym wywolaniu.
        InterlockedExchange(&g_travelDone, 0);
        return;
    }
    logLine("TRAVEL Z WATKU GRY: wolam SetClientTravel(..., \"%ls\")", g_travelUrl);
    g_setClientTravel(engine, world, g_travelUrl, 0 /* TRAVEL_Absolute */);
    logLine("TRAVEL Z WATKU GRY: wrocil");
}

// ── WYJECIE BRONI PO STRONIE KLIENTA ────────────────────────────────────────
//
// Po co: ekwipunek tej gry NIE MA replikacji. `DimensionInventoryComponent` ma
// 50 funkcji i zero RPC, a `CurrentWeaponIndex` nie ma flagi `CPF_Net`
// (sprawdzone `tools/ue-funcs.py`; na 203 RPC w calej grze zadne nie wyjmuje
// broni). Host wykonuje „wyjmij bron" LOKALNIE, wiec klient nigdy tego kroku
// nie robi: jego wlasna postac ma dzialajace rece, ale `CurrentWeaponIndex`
// zostaje na -1 i zadna bron nie jest do niej przyczepiona.
//
// Dlaczego nie da sie tego zalatac przestawieniem flag z zewnatrz: sprawdzone
// i NIE dziala. Ustawienie `bHiddenInGame=True` na widocznej broni zostawilo ja
// na ekranie — UE trzyma widocznosc w stanie renderera i zmiana wymaga
// `MarkRenderStateDirty()`, czyli wykonania kodu gry. Dlatego wolamy funkcje
// gry, a nie piszemy po polach.
//
// Dlaczego akurat stad: trampolina wyzej daje nam WATEK GRY. Wolanie
// `SelectWeapon` z obcego watku byloby dokladnie tym bledem, ktory juz raz
// kosztowal nas dzien diagnozy przy travelu.
//
// Adres wziety z deasemblacji: `ue-funcs.py` podaje 0x141C17730, ale to
// przejsciowka skryptowa `execSelectWeapon`. Wchodzi ona w `rcx`=komponent,
// `edx`=indeks i wola prawdziwa metode pod 0x1418D7600 — i to ja wolamy.
namespace addr {
constexpr uintptr_t GUObjectArray_OFF = 0x6543810;
constexpr uintptr_t FNamePool_OFF     = 0x64EA8C0;
constexpr uintptr_t SelectWeapon_OFF  = 0x18D7600;
// Wolany CO KLATKE na watku gry — jedyny punkt, ktory na pewno sie odpali.
constexpr uintptr_t GameEngineTick_OFF = 0x37E9AC0;
}

using SelectWeaponFn = void(__fastcall*)(void* ekwipunek, int slot);

// Offsety potwierdzone refleksja na zywej grze (`ue-props.py --sprawdz`).
static constexpr uintptr_t UOBJ_CLASS_OFF = 0x10;
static constexpr uintptr_t UOBJ_NAME_OFF  = 0x18;
static constexpr uintptr_t UOBJ_OUTER_OFF = 0x20;
static constexpr uintptr_t ACTOR_ROLE_OFF = 0xF0;   // 2 = AutonomousProxy
static constexpr uintptr_t INV_CURRENT_WEAPON_OFF = 0x148;
static constexpr uintptr_t USTRUCT_SUPER_OFF = 0x40;   // UStruct::SuperStruct

static bool          g_bronWlaczona = false;
static bool          g_bronGotowa   = false;
static ULONGLONG     g_bronNastepna = 0;
static int           g_bronProby    = 0;

static bool sensownyWsk(uintptr_t p)
{
    return p > 0x10000ull && p < 0x7FFFFFFFFFFFull && (p & 7) == 0;
}

// Nazwa obiektu z puli FName. Nazwy klas w tej grze sa zawsze waskie (ASCII),
// wiec wariant szeroki po prostu odrzucamy zamiast go obslugiwac.
// Rozwiazanie surowego `FName` — bez obiektu. Potrzebne tam, gdzie nazwa lezy
// w danych gry, a nie w naglowku `UObject`: tak jest z akcjami wejscia
// w `InputsToCapture`, gdzie pierwsze 8 bajtow wpisu to wlasnie FName.
static bool nazwaFName(uintptr_t base, uint32_t idx, char* out, size_t cap)
{
    if (!idx) return false;
    const uintptr_t* bloki = (const uintptr_t*)(base + addr::FNamePool_OFF + 0x10);
    const uintptr_t p = bloki[idx >> 16];
    if (!sensownyWsk(p)) return false;
    const uintptr_t wpis = p + (uintptr_t)(idx & 0xFFFF) * 2;
    const uint16_t nag = *(const uint16_t*)wpis;
    const uint32_t dl = (uint32_t)(nag >> 6);
    if ((nag & 1) || dl == 0 || dl + 1 >= cap) return false;
    memcpy(out, (const char*)(wpis + 2), dl);
    out[dl] = 0;
    return true;
}

static bool nazwaObiektu(uintptr_t base, uintptr_t obj, char* out, size_t cap)
{
    if (!sensownyWsk(obj)) return false;
    const uint32_t idx = *(const uint32_t*)(obj + UOBJ_NAME_OFF);
    if (!idx) return false;
    const uintptr_t* bloki = (const uintptr_t*)(base + addr::FNamePool_OFF + 0x10);
    const uintptr_t p = bloki[idx >> 16];
    if (!sensownyWsk(p)) return false;
    const uintptr_t wpis = p + (uintptr_t)(idx & 0xFFFF) * 2;
    const uint16_t nag = *(const uint16_t*)wpis;
    const uint32_t dl = (uint32_t)(nag >> 6);
    if ((nag & 1) || dl == 0 || dl + 1 >= cap) return false;
    memcpy(out, (const char*)(wpis + 2), dl);
    out[dl] = 0;
    return true;
}

// Dopasowanie klasy MUSI isc po dziedziczeniu, nie po nazwie.
//
// Poprzednia wersja porownywala nazwe klasy wprost do
// "DimensionInventoryComponent" i cicho nie znajdowala nic. W tej grze prawie
// wszystko jest blueprintem (`BP..._C`), wiec porownanie samej nazwy trafia
// tylko w komponenty klasy natywnej — a jesli postac gracza nosi podklase,
// szukanie nie ma prawa jej zobaczyc. To samo spostrzezenie jest juz zapisane
// w `tools/ue_common.py` (funkcja `dziedziczy_po`), tylko po stronie DLL nigdy
// go nie zastosowano.
static bool dziedziczyPo(uintptr_t base, uintptr_t klasa, const char* bazowa)
{
    char n[128];
    for (int i = 0; i < 32 && sensownyWsk(klasa); ++i) {
        if (!nazwaObiektu(base, klasa, n, sizeof n)) return false;
        if (strcmp(n, bazowa) == 0) return true;
        klasa = *(const uintptr_t*)(klasa + USTRUCT_SUPER_OFF);
    }
    return false;
}

// Chodzenie po lancuchu klas dla KAZDEGO z ~300 tys. obiektow byloby drogie,
// a klas jest kilka tysiecy — wiec decyzje trzymamy przy wskazniku klasy.
// Tablica jest czyszczona przed kazdym przejsciem opisowym, zeby wpis po
// zwolnionej klasie blueprintu nie przezyl przeladowania mapy.
struct WpisKlasy { uintptr_t klasa; unsigned char pasuje; };
static WpisKlasy g_cacheKlas[8192];

static void wyczyscCacheKlas() { memset(g_cacheKlas, 0, sizeof g_cacheKlas); }

static bool klasaToEkwipunek(uintptr_t base, uintptr_t klasa)
{
    size_t h = (size_t)(((klasa >> 4) * 0x9E3779B97F4A7C15ull) >> 51) & 8191;
    for (size_t i = 0; i < 8192; ++i) {
        WpisKlasy& w = g_cacheKlas[(h + i) & 8191];
        if (w.klasa == klasa) return w.pasuje != 0;
        if (w.klasa == 0) {
            w.klasa  = klasa;
            w.pasuje = dziedziczyPo(base, klasa, "DimensionInventoryComponent") ? 1 : 0;
            return w.pasuje != 0;
        }
    }
    return dziedziczyPo(base, klasa, "DimensionInventoryComponent");
}

// Komponent ekwipunku LOKALNEGO gracza: jego wlasciciel to postac o Role == 2
// (AutonomousProxy). Kopia postaci hosta ma Role == 1 i nie wolno jej ruszac —
// to wlasnie ta pomylka sprawila, ze pierwszy pomiar niczego nie rozstrzygal.
//
// `opis` wypelniamy ZAWSZE, bo samo "nie znalazlem" nie mowi, ktory warunek
// zawiodl: czy nie ma komponentu, czy jest, ale jego wlasciciel ma inna role.
// Trzy przebiegi drogi B skonczyly sie linia "poddaje sie po 40 probach", z
// ktorej nie dalo sie wyciagnac niczego.
struct OpisSzukania {
    int  kandydatow;      // komponenty ekwipunku poza wzorcami klas
    int  rolaCount[5];    // 0,1,2,3 oraz „inne" w [4]
    char pierwszy[192];   // wlasciciel pierwszego kandydata, do wgladu
};

static uintptr_t znajdzEkwipunekLokalny(uintptr_t base, OpisSzukania* opis)
{
    if (opis) memset(opis, 0, sizeof *opis);

    const uintptr_t tab = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tab;
    const int32_t ile     = *(const int32_t*)(tab + 0x14);
    const int32_t nchunk  = *(const int32_t*)(tab + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return 0;

    uintptr_t wynik = 0;
    char nazwa[128], nazwaKl[128];
    for (int32_t ci = 0; ci < nchunk; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
            if (!sensownyWsk(klasa)) continue;
            if (!klasaToEkwipunek(base, klasa)) continue;
            const uintptr_t wl = *(const uintptr_t*)(obj + UOBJ_OUTER_OFF);
            if (!sensownyWsk(wl)) continue;
            if (!nazwaObiektu(base, wl, nazwa, sizeof nazwa)) continue;
            if (strncmp(nazwa, "Default__", 9) == 0) continue;

            const unsigned char rola = *(const unsigned char*)(wl + ACTOR_ROLE_OFF);
            if (opis) {
                opis->kandydatow++;
                opis->rolaCount[rola <= 3 ? rola : 4]++;
                if (opis->kandydatow == 1) {
                    const uintptr_t klWl = *(const uintptr_t*)(wl + UOBJ_CLASS_OFF);
                    if (!nazwaObiektu(base, klWl, nazwaKl, sizeof nazwaKl))
                        strcpy(nazwaKl, "?");
                    _snprintf_s(opis->pierwszy, sizeof opis->pierwszy, _TRUNCATE,
                                "%s (%s) Role=%u", nazwa, nazwaKl, (unsigned)rola);
                }
            }
            if (rola != 2) continue;
            if (!wynik) wynik = obj;
            if (!opis) return obj;     // bez opisu nie ma po co isc dalej
        }
    }
    return wynik;
}

// Wolane z watku gry. Musi byc TANIE: trampolina odpala sie bardzo czesto,
// a przejscie tablicy obiektow to ~300 tysiecy wpisow.
//
// Budzet prob liczy sie od CHWILI POLACZENIA, nie od zaladowania biblioteki.
// Powod jest zmierzony, nie teoretyczny: w kazdym z trzech przebiegow drogi B
// biblioteka wstawala o T+0, klient laczyl sie z hostem dopiero o T+38 s
// (30 s „wyciszenia" + ladowanie mapy), a limit 40 prob x 2 s wyczerpywal sie
// o T+100 s. Polowa budzetu szla wiec na przeszukiwanie MENU, w ktorym zadnej
// zdalnej postaci byc nie moze. Zegar zeruje hak `LoadMap`, gdy zobaczy mape
// z niepustym adresem hosta.
static void wfcoopWyjmijBron(uintptr_t base)
{
    if (!g_bronWlaczona || g_bronGotowa) return;
    const ULONGLONG teraz = GetTickCount64();
    if (teraz < g_bronNastepna) return;
    g_bronNastepna = teraz + 2000;          // najwyzej raz na 2 s
    if (++g_bronProby > 150) {              // ~5 min od polaczenia
        g_bronGotowa = true;
        logLine("BRON: poddaje sie po %d probach", g_bronProby - 1);
        return;
    }

    // Przejscie opisowe co dziesiata proba: wypelnia licznik rol i nazwe
    // pierwszego kandydata. Reszta prob idzie tania sciezka, ktora konczy sie
    // na pierwszym trafieniu.
    const bool opisowa = (g_bronProby % 10) == 1;
    OpisSzukania opis;
    if (opisowa) wyczyscCacheKlas();
    const uintptr_t ekw = znajdzEkwipunekLokalny(base, opisowa ? &opis : nullptr);

    if (opisowa) {
        // Logujemy tylko ZMIANE stanu — inaczej co 20 s leciałaby ta sama
        // linia i log przestalby sie nadawac do czytania.
        static char ostatni[320] = {};
        char teraz_opis[320];
        _snprintf_s(teraz_opis, sizeof teraz_opis, _TRUNCATE,
                    "BRON: kandydatow=%d role[0/1/2/3/inne]=%d/%d/%d/%d/%d pierwszy: %s",
                    opis.kandydatow, opis.rolaCount[0], opis.rolaCount[1],
                    opis.rolaCount[2], opis.rolaCount[3], opis.rolaCount[4],
                    opis.kandydatow ? opis.pierwszy : "brak");
        if (strcmp(teraz_opis, ostatni) != 0) {
            strcpy_s(ostatni, sizeof ostatni, teraz_opis);
            logLine("%s (proba %d)", teraz_opis, g_bronProby);
        }
    }

    if (!ekw) return;                        // postac jeszcze nie istnieje

    const int przed = *(const int*)(ekw + INV_CURRENT_WEAPON_OFF);
    if (przed >= 0) {                        // gra sama sobie poradzila
        g_bronGotowa = true;
        logLine("BRON: juz wyjeta bez nas (CurrentWeaponIndex=%d)", przed);
        return;
    }

    auto selectWeapon = (SelectWeaponFn)(base + addr::SelectWeapon_OFF);
    logLine("BRON: wolam SelectWeapon(ekwipunek=0x%llX, 0), CurrentWeaponIndex=%d",
            (unsigned long long)ekw, przed);
    selectWeapon((void*)ekw, 0);

    // Sprawdzamy WYNIK, nie fakt wywolania. Ta lekcja kosztowala nas caly
    // przebieg: `RestartPlayer` logowany po wartosci zwracanej wygladal na
    // porazke, choc dzialal — bo ta funkcja nic nie zwraca.
    const int po = *(const int*)(ekw + INV_CURRENT_WEAPON_OFF);
    logLine("BRON: CurrentWeaponIndex %d -> %d %s", przed, po,
            po >= 0 ? "(UDALO SIE)" : "(bez zmiany)");
    if (po >= 0) g_bronGotowa = true;
}

// ── PEWNY PUNKT WEJSCIA NA WATEK GRY: GameEngineTick ────────────────────────
//
// Po co drugi hak, skoro jeden juz jest: tamten wisi na thunku zdarzenia
// Blueprintu i w przebiegu 00:51 log powiedzial wprost
//   "BEZPIECZNIK: hak nie zostal wywolany przez 8 s"
// czyli ta funkcja w tym scenariuszu NIE JEST wolana. Wszystko, co od niej
// zawiesilem, nigdy sie nie wykonalo. `GameEngineTick` jest wolany KAZDA
// KLATKE na watku gry, wiec jest punktem, ktory nie zawiedzie.
//
// Roznica techniczna wzgledem tamtego haka jest istotna i dlatego to osobny
// kod, a nie kopia: podpinamy sie do PIERWSZEJ instrukcji funkcji, wiec
// w rejestrach siedza jeszcze ARGUMENTY. `GameEngineTick(this, DeltaSeconds,
// bIdleMode)` przekazuje `DeltaSeconds` jako float w **xmm1** — samo chowanie
// rejestrow calkowitych by nie wystarczylo i gra dostalaby losowy krok czasu.
// Dlatego chowamy takze xmm0-xmm5.
//
// Kradniemy 7 bajtow (dwie cale instrukcje), bo skok `E9 rel32` ma 5 bajtow
// i nie wolno przeciac instrukcji w polowie:
//   48 8B C4        mov rax,rsp
//   44 88 40 18     mov [rax+0x18],r8b
// Wykonujemy je w trampolinie DOPIERO po przywroceniu rsp, bo pierwsza z nich
// zapamietuje rsp i wynik musi byc taki sam jak bez haka.
static bool patchGameEngineTick(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::GameEngineTick_OFF);

    // Bajty ponizej to prolog funkcji GRY — cytat z jej kodu, niezbedny, zeby
    // sprawdzic, ze latamy wlasciwe miejsce. Nie sa objete licencja MIT tego
    // projektu (patrz uwaga licencyjna na poczatku pliku).
    static const unsigned char oczekiwane[] = {
        0x48, 0x8B, 0xC4,              // mov  rax,rsp
        0x44, 0x88, 0x40, 0x18,        // mov  [rax+0x18],r8b
        0x48, 0x89, 0x48, 0x08         // mov  [rax+8],rcx
    };
    if (memcmp(fn, oczekiwane, sizeof oczekiwane) != 0) {
        logLine("TICK: bajty pod 0x%llX inne niz oczekiwane — NIE zakladam haka",
                (unsigned long long)(uintptr_t)fn);
        return false;
    }

    unsigned char* tr = nullptr;
    for (uintptr_t a = base + 0x08000000; a < base + 0x40000000; a += 0x10000) {
        tr = static_cast<unsigned char*>(
            VirtualAlloc(reinterpret_cast<void*>(a), 0x1000,
                         MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
        if (tr) break;
    }
    if (!tr) { logLine("TICK: nie udalo sie zaalokowac trampoliny"); return false; }

    // Wyrownanie stosu: na wejsciu rsp%16==8. Siedem odlozen (56 B) daje rsp%16==0,
    // `sub rsp,0x60` na rejestry xmm tego nie zmienia, `sub rsp,0x20` (cien) tez —
    // czyli tuz przed `call` mamy rsp%16==0, zgodnie z ABI.
    //
    // Wiersze oznaczone „oryginal" to bajty przeniesione Z GRY — cytat niezbedny
    // do zalatania (patrz uwaga licencyjna na poczatku pliku).
    unsigned char code[] = {
        0x50, 0x51, 0x52,                          // push rax, rcx, rdx
        0x41,0x50, 0x41,0x51, 0x41,0x52, 0x41,0x53,// push r8, r9, r10, r11
        0x48,0x83,0xEC,0x60,                       // sub  rsp,0x60
        0x0F,0x11,0x04,0x24,                       // movups [rsp+0x00],xmm0
        0x0F,0x11,0x4C,0x24,0x10,                  // movups [rsp+0x10],xmm1
        0x0F,0x11,0x54,0x24,0x20,                  // movups [rsp+0x20],xmm2
        0x0F,0x11,0x5C,0x24,0x30,                  // movups [rsp+0x30],xmm3
        0x0F,0x11,0x64,0x24,0x40,                  // movups [rsp+0x40],xmm4
        0x0F,0x11,0x6C,0x24,0x50,                  // movups [rsp+0x50],xmm5
        0x48,0x83,0xEC,0x20,                       // sub  rsp,0x20  (cien)
        0x48,0xB8, 0,0,0,0,0,0,0,0,                // mov  rax,<wfcoopOnGameThread>
        0xFF,0xD0,                                 // call rax
        0x48,0x83,0xC4,0x20,                       // add  rsp,0x20
        0x0F,0x10,0x04,0x24,                       // movups xmm0,[rsp+0x00]
        0x0F,0x10,0x4C,0x24,0x10,                  // movups xmm1,[rsp+0x10]
        0x0F,0x10,0x54,0x24,0x20,                  // movups xmm2,[rsp+0x20]
        0x0F,0x10,0x5C,0x24,0x30,                  // movups xmm3,[rsp+0x30]
        0x0F,0x10,0x64,0x24,0x40,                  // movups xmm4,[rsp+0x40]
        0x0F,0x10,0x6C,0x24,0x50,                  // movups xmm5,[rsp+0x50]
        0x48,0x83,0xC4,0x60,                       // add  rsp,0x60
        0x41,0x5B, 0x41,0x5A, 0x41,0x59, 0x41,0x58,// pop  r11, r10, r9, r8
        0x5A, 0x59, 0x58,                          // pop  rdx, rcx, rax
        0x48,0x8B,0xC4,                            // mov  rax,rsp        (oryginal)
        0x44,0x88,0x40,0x18,                       // mov  [rax+0x18],r8b (oryginal)
        0xFF,0x25, 0x00,0x00,0x00,0x00,            // jmp  qword ptr [rip+0]
        0,0,0,0,0,0,0,0                            // adres powrotu
    };

    // Miejsce na adres funkcji znajdujemy SZUKAJAC wzorca `48 B8` (mov rax,imm64),
    // a nie liczac bajty na piechote. Pomylka o jeden przy recznym liczeniu
    // wpisalaby adres w srodek instrukcji i wywalila gre w sposob, ktorego
    // potem nie da sie odroznic od bledu w samej lacie.
    size_t gniazdo = 0;
    for (size_t i = 0; i + 1 < sizeof code; ++i)
        if (code[i] == 0x48 && code[i + 1] == 0xB8) { gniazdo = i + 2; break; }
    if (!gniazdo) { logLine("TICK: nie znalazlem gniazda na adres"); return false; }
    const uintptr_t fnPtr = reinterpret_cast<uintptr_t>(&wfcoopOnGameThread);
    memcpy(code + gniazdo, &fnPtr, sizeof fnPtr);
    const uintptr_t powrot = reinterpret_cast<uintptr_t>(fn) + 7;
    memcpy(code + sizeof(code) - 8, &powrot, sizeof powrot);
    memcpy(tr, code, sizeof code);

    DWORD stare = 0;
    if (!VirtualProtect(fn, 16, PAGE_EXECUTE_READWRITE, &stare)) {
        logLine("TICK: VirtualProtect nieudany");
        return false;
    }
    // E9 rel32 + dwa NOP-y, zeby wypelnic 7 ukradzionych bajtow.
    const int32_t rel = (int32_t)((intptr_t)tr - (intptr_t)(fn + 5));
    fn[0] = 0xE9;
    memcpy(fn + 1, &rel, 4);
    fn[5] = 0x90; fn[6] = 0x90;
    VirtualProtect(fn, 16, stare, &stare);
    FlushInstructionCache(GetCurrentProcess(), fn, 16);

    logLine("TICK: hak na GameEngineTick zalozony (0x%llX -> trampolina 0x%llX)",
            (unsigned long long)(uintptr_t)fn, (unsigned long long)(uintptr_t)tr);
    return true;
}

// ── HAK WYLACZNIE LOGUJACY NA LoadMap ───────────────────────────────────────
//
// Po co: chcemy hostowac BEZ wymuszania mapy. Gra sama podrozuje na mape misji
// po rozpoczeciu wyprawy — ale nie robi tego przez `GameplayStatics::OpenLevel`
// (hak Lua na tej funkcji nie odpalil sie ani razu w ~70 przebiegach; z
// zastrzezeniem, ze w zadnym z nich wyprawa nie zostala naprawde rozpoczeta).
// `UEngine::LoadMap` to lej nizej: przechodzi przez niego KAZDY travel
// niebezszwowy, niezaleznie od tego, ktora funkcja gra go zaczyna.
//
// Ten hak NICZEGO NIE ZMIENIA. Ma odpowiedziec na dwa pytania naraz:
//   1. czy to na pewno ta funkcja (odpali sie przy zmianach mapy albo nie),
//   2. jakim URL-em gra podrozuje — bo dopiero znajac ten URL ma sens
//      dopisanie do niego `?listen`.
// Kolejnosc jest celowa: najpierw pomiar, dopiero potem zmiana zachowania.
//
// UWAGA CO DO ADRESU: notatka mowila `LoadMap 0x143BEAE50`, ale pod tym adresem
// stoi `jmp qword ptr [rip-...]`, ktorego cel wypada POZA modulem — to nie jest
// poczatek funkcji. Czysty prolog (`push rsi/rdi/r12/r13/r14/r15`, ramka 0x180,
// ciasteczko stosu) zaczyna sie dopiero na **0x143BEAE56** i to jego lapiemy.
// Tozsamosci nie potwierdza zaden literal w poblizu, wiec traktujemy nazwe jako
// HIPOTEZE — ktora ten hak wlasnie sprawdzi.
//
// Sygnatura (UE 4.27):
//   bool UEngine::LoadMap(FWorldContext&, FURL URL, UPendingNetGame*, FString&)
// FURL jest duza struktura, wiec w ABI Windows x64 idzie PRZEZ WSKAZNIK — czyli
// w `r8` mamy `FURL*`. Uklad FURL: Protocol 0x00, Host 0x10, Port 0x20,
// Valid 0x24, Map 0x28, RedirectURL 0x38, Op (TArray<FString>) 0x48, Portal 0x58.
namespace addr {
constexpr uintptr_t LoadMap_OFF = 0x3BEAE56;
}

// FString = { TCHAR* Data; int32 Num; int32 Max }. Zwraca ASCII, bo nazwy map
// i opcji sa zawsze waskie, a do logu i tak nie chcemy szerokich znakow.
static void fstringDoAscii(const void* fstr, char* out, size_t cap)
{
    out[0] = 0;
    if (!fstr) return;
    const wchar_t* dane = *(const wchar_t* const*)fstr;
    const int n = *(const int*)((const unsigned char*)fstr + 8);
    if (!dane || n <= 0 || (size_t)n >= cap) return;
    int i = 0;
    for (; i < n && dane[i]; ++i) out[i] = (char)(dane[i] & 0x7F);
    out[i] = 0;
}

extern "C" void wfcoopOnLoadMap(void* url)
{
    if (!url) { logLine("LOADMAP: wywolane, ale URL = null"); return; }
    const unsigned char* u = (const unsigned char*)url;
    char host[256], mapa[512], portal[256];
    fstringDoAscii(u + 0x10, host, sizeof host);
    fstringDoAscii(u + 0x28, mapa, sizeof mapa);
    fstringDoAscii(u + 0x58, portal, sizeof portal);
    const int port = *(const int*)(u + 0x20);
    const int valid = *(const int*)(u + 0x24);

    logLine("LOADMAP: mapa=\"%s\" host=\"%s\" port=%d valid=%d portal=\"%s\"",
            mapa, host, port, valid, portal);

    // Opcje URL (`?listen`, `?bIsLanMatch`, ...) siedza w TArray<FString> Op.
    // To one sa wlasciwym celem tego pomiaru: chcemy wiedziec, co gra dopisuje
    // sama, zeby dolozyc `listen` do JEJ podrozy zamiast robic wlasna.
    const void* opDane = *(const void* const*)(u + 0x48);
    const int opIle = *(const int*)((const unsigned char*)(u + 0x48) + 8);
    if (opDane && opIle > 0 && opIle < 64) {
        for (int i = 0; i < opIle; ++i) {
            char opcja[256];
            fstringDoAscii((const unsigned char*)opDane + (size_t)i * 16, opcja, sizeof opcja);
            logLine("LOADMAP:   opcja[%d] = \"%s\"", i, opcja);
        }
    } else {
        logLine("LOADMAP:   opcji: %d (brak albo podejrzana liczba)", opIle);
    }

    // Zegar prob wyjecia broni zaczyna biec DOPIERO STAD. Mapa z niepustym
    // adresem hosta to jedyna chwila, od ktorej szukanie zdalnej postaci ma
    // sens — wczesniej klient siedzi w swoim menu i przeszukiwanie 300 tys.
    // obiektow jest czysta strata budzetu.
    if (host[0]) {
        g_bronProby = 0;
        g_bronGotowa = false;
        g_bronNastepna = 0;
        logLine("BRON: wchodzimy na mape hosta — licznik prob wyzerowany");
    }
}

static volatile unsigned* g_boosterLicznik = nullptr;
static volatile unsigned* g_wejscieLicznik = nullptr;

// ── STRAZNIK NULLA W OnItemAddedCallback ────────────────────────────────────
//
// Problem: host pada 2 s po dolaczeniu klienta, deterministycznie, zawsze z ta
// sama sygnatura (odczyt spod 0x24 na GameThread).
//
// Mechanizm, ustalony pomiarem i deasemblacja:
//   * `DimensionBoosterManager` NIE jest aktorem — to UObject zyjacy
//     w `GameInstance`, czyli JEDEN na caly proces, bez roli sieciowej,
//   * `DimensionInventoryComponent` jest PER POSTAC i przy kazdym dodaniu
//     przedmiotu wola `OnItemAddedCallback` do tego jednego menedzera,
//   * serwer napelnia ekwipunek startowy DRUGIEGO gracza, wiec przedmioty
//     trafiaja do menedzera gracza LOKALNEGO,
//   * menedzer szuka pasujacego wpisu (0x141911FF0) i przy braku trafienia
//     zwraca NULL,
//   * wynik NIE jest sprawdzany i leci prosto do kolejnego wywolania.
//
// To strukturalne zalozenie gry jednoosobowej („jest dokladnie jeden gracz"),
// a nie wyscig — dlatego objaw jest powtarzalny co do bajtu.
//
// Dlaczego to NIE jest ten sam blad, co skreslona latka na `AbilityCachedData`:
// tamta wstawiala straznika w funkcje SILNIKA wolana w tysiacu miejsc, wiec
// wyciszala objawy wszedzie i „zamieniala awarie na zawieszenie". Tutaj cel to
// JEDNA metoda gry, a menedzer i tak nie ma prawa nic zrobic z przedmiotem
// cudzego gracza. Skutkiem ubocznym bedzie najwyzej brak aktualizacji UI
// boosterow dla drugiego gracza — czyli stan, ktory w grze jednoosobowej
// i tak jest normalny.
//
// Kod oryginalny (11 bajtow miedzy dwoma `call`):
//   0x1419CA7CF  E8 ..           call 0x141911FF0   ; szukanie wpisu -> rax
//   0x1419CA7D4  48 8D 54 24 20  lea  rdx,[rsp+0x20]
//   0x1419CA7D9  48 8B C8        mov  rcx,rax
//   0x1419CA7DC  4C 8B F0        mov  r14,rax
//   0x1419CA7DF  E8 ..           call 0x1419FC470   ; <- tu ginie na nullu
//
// Podmieniamy 11 bajtow od 0x1419CA7D4 na skok do trampoliny, ktora:
//   test rax,rax; jz -> epilog funkcji; w przeciwnym razie wykonuje oryginalne
//   trzy instrukcje i wraca.
//
// Wyjscie bierzemy DOKLADNIE takie, jakiego gra uzywa przy swoim wlasnym
// straznikiu nulla kilka instrukcji wyzej (`je 0x1419CA8FD`) — czyli czysty
// epilog `add rsp,0x30; pop rdi; pop rsi; pop rbp; ret`. Nie wymyslamy nowego
// zachowania, tylko rozszerzamy istniejace na drugi, zapomniany wynik.
namespace addr {
constexpr uintptr_t BoosterNullCheck_OFF = 0x19CA7D4;   // lea rdx,[rsp+0x20]
constexpr uintptr_t BoosterEpilog_OFF    = 0x19CA8FD;   // add rsp,0x30; ...; ret
}

static bool patchBoosterNullGuard(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::BoosterNullCheck_OFF);
    // Bajty ponizej to prolog funkcji GRY — cytat z jej kodu, niezbedny, zeby
    // sprawdzic, ze latamy wlasciwe miejsce. Nie sa objete licencja MIT tego
    // projektu (patrz uwaga licencyjna na poczatku pliku).
    static const unsigned char oczekiwane[] = {
        0x48, 0x8D, 0x54, 0x24, 0x20,   // lea rdx,[rsp+0x20]
        0x48, 0x8B, 0xC8,               // mov rcx,rax
        0x4C, 0x8B, 0xF0                // mov r14,rax
    };
    if (memcmp(fn, oczekiwane, sizeof oczekiwane) != 0) {
        logLine("BOOSTER: bajty pod 0x%llX inne niz oczekiwane — NIE lataem",
                (unsigned long long)(uintptr_t)fn);
        return false;
    }

    unsigned char* tr = nullptr;
    for (uintptr_t a = base + 0x08000000; a < base + 0x40000000; a += 0x10000) {
        tr = (unsigned char*)VirtualAlloc((void*)a, 0x1000,
                                          MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (tr) break;
    }
    if (!tr) { logLine("BOOSTER: brak miejsca na trampoline"); return false; }

    // Licznik pominiec — zeby po przebiegu bylo widac, ILE RAZY to sie zdarzylo.
    // Bez tego nie odroznimy „latka nie byla potrzebna" od „latka uratowala 40
    // wywolan", a to zupelnie inne wnioski.
    // Offsety w kodzie maszynowym liczone SPRAWDZONE, nie na oko. Pierwsza
    // wersja miala trzy bledy naraz (skok ladowal w srodku adresu powrotu,
    // licznik i epilog przesuniete o 8) — wylapala je dopiero deasemblacja
    // kontrolna. Dlatego uklad jest tu wypisany z offsetami, a nizej stoi
    // asercja czasu wykonania.
    //   +0x00 test rax,rax
    //   +0x03 jz -> +0x1E            (przesuniecie 0x19 od +0x05)
    //   +0x05 lea rdx,[rsp+0x20]     oryginal
    //   +0x0A mov rcx,rax            oryginal
    //   +0x0D mov r14,rax            oryginal
    //   +0x10 jmp [rip+0]  -> +0x16  adres powrotu
    //   +0x16 <adres powrotu, 8 B>
    //   +0x1E inc [rip+0xE] -> +0x32 licznik
    //   +0x24 jmp [rip+0]  -> +0x2A  adres epilogu
    //   +0x2A <adres epilogu, 8 B>
    //   +0x32 <licznik, 4 B>
    //
    // Wiersze oznaczone „oryginal" to bajty przeniesione Z GRY: instrukcje,
    // ktore nadpisuje skok, musimy wykonac w trampolinie. Cytat niezbedny do
    // zalatania, nieobjety licencja MIT tego projektu.
    enum { OFF_POWROT = 0x16, OFF_EPILOG = 0x2A, OFF_LICZNIK = 0x32 };
    unsigned char code[] = {
        0x48, 0x85, 0xC0,                    // test rax,rax
        0x74, 0x19,                          // jz  -> +0x1E (pominiecie)
        0x48, 0x8D, 0x54, 0x24, 0x20,        // lea rdx,[rsp+0x20]   (oryginal)
        0x48, 0x8B, 0xC8,                    // mov rcx,rax          (oryginal)
        0x4C, 0x8B, 0xF0,                    // mov r14,rax          (oryginal)
        0xFF, 0x25, 0x00,0x00,0x00,0x00,     // jmp [rip+0] -> powrot
        0,0,0,0,0,0,0,0,                     // +0x16 adres powrotu
        // pominiecie: policz i wyjdz TA SAMA droga, ktorej gra uzywa przy
        // swoim wlasnym straznikiu nulla kilka instrukcji wyzej
        0xFF, 0x05, 0x0E,0x00,0x00,0x00,     // inc dword [rip+0xE] -> licznik
        0xFF, 0x25, 0x00,0x00,0x00,0x00,     // jmp [rip+0] -> epilog
        0,0,0,0,0,0,0,0,                     // +0x2A adres epilogu
        0,0,0,0                              // +0x32 licznik
    };
    // Asercja: gdyby ktos przestawil instrukcje, offsety musza zostac spojne.
    if (sizeof(code) != OFF_LICZNIK + 4) {
        logLine("BOOSTER: BLAD WEWNETRZNY — rozmiar trampoliny %zu, oczekiwano %d",
                sizeof(code), OFF_LICZNIK + 4);
        return false;
    }
    const uintptr_t powrot = (uintptr_t)fn + 11;
    memcpy(code + OFF_POWROT, &powrot, sizeof powrot);
    const uintptr_t epilog = base + addr::BoosterEpilog_OFF;
    memcpy(code + OFF_EPILOG, &epilog, sizeof epilog);
    memcpy(tr, code, sizeof code);
    g_boosterLicznik = (volatile unsigned*)(tr + OFF_LICZNIK);

    DWORD stare = 0;
    if (!VirtualProtect(fn, 16, PAGE_EXECUTE_READWRITE, &stare)) {
        logLine("BOOSTER: VirtualProtect nieudany"); return false;
    }
    const int32_t rel = (int32_t)((intptr_t)tr - (intptr_t)(fn + 5));
    fn[0] = 0xE9; memcpy(fn + 1, &rel, 4);
    for (int i = 5; i < 11; ++i) fn[i] = 0x90;   // dopelnienie do 11 bajtow
    VirtualProtect(fn, 16, stare, &stare);
    FlushInstructionCache(GetCurrentProcess(), fn, 16);
    logLine("BOOSTER: straznik nulla zalozony w OnItemAddedCallback "
            "(0x%llX -> trampolina 0x%llX)",
            (unsigned long long)(uintptr_t)fn, (unsigned long long)(uintptr_t)tr);
    return true;
}

// ── STRAZNIK NULLA W WIAZANIU AKCJI WEJSCIA (sciana #2) ─────────────────────
//
// Objaw: po naprawieniu sciany #1 host nadal pada 2 s po dolaczeniu klienta,
// ale JUZ Z INNA sygnatura — odczyt spod 0x430 zamiast 0x24.
//
// Lancuch ustalony przejsciem po ZYWYCH obiektach na wyprawie:
//   bron --[+0x998]--> BPDimensionPlayerCharacter_C   (wlasciciel)
//        --[+0x258]--> DimensionPlayerController_C    (Controller)
//        --[+0x348]--> DimensionPlayerInput           (komponent wejscia)
//   i dopiero to trafia tutaj jako `rcx`.
//
// Czym jest ta funkcja — ustalone przez `find-callers.py`, nie zgadniete:
// ma 14 wolajacych, a literaly w ich sasiedztwie to `Dash_Left`, `Dash_Right`,
// `Input.Tap`, `Input.DoublePress`, `LightSpell`, `HeavySpell`,
// `Setting.Controls.SpellMode`. To WIAZANIE AKCJI WEJSCIA — rejestrowanie
// dasha i zaklec w `DimensionPlayerInput` gracza.
//
// Dlaczego pada dla drugiego gracza: `DimensionPlayerInput` istnieje tam, gdzie
// siedzi czlowiek. Serwer nie ma komponentu wejscia gracza ZDALNEGO, wiec
// `TWeakObjectPtr::Get` zwraca nullptr, a wolajacy tego nie sprawdza. Kod robi
// wtedy `lea r11,[rcx+0x428]` i czyta `[r11+8]`, czyli spod 0x430.
//
// Dlaczego latamy WOLANA funkcje, a nie wolajacych: wolajacych jest 14 i kazdy
// powtarza ten sam wzorzec w petli (kolejne akcje). Jeden straznik na wejsciu
// zalatwia wszystkie naraz.
//
// Dlaczego pominiecie jest bezpieczne: funkcja NIC NIE ZWRACA — jej epilog to
// `add rsp,0x48; pop r15; pop r12; ret`, bez ustawiania `rax`. Wolajacy tez nie
// uzywa wyniku (zaraz po powrocie przygotowuje nastepne wywolanie). Wiec przy
// `rcx == 0` mozna wrocic NATYCHMIAST, zanim cokolwiek trafi na stos — nie
// trzeba nawet odtwarzac epilogu.
//
// Skutek uboczny: gracz zdalny nie dostanie na SERWERZE wiazania akcji wejscia.
// I dobrze — on tych akcji i tak nie wykonuje po stronie serwera, tylko u siebie.
namespace addr {
constexpr uintptr_t BindInputAction_OFF = 0x1A1A0C0;
}

static bool patchInputBindNullGuard(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::BindInputAction_OFF);
    // Bajty ponizej to prolog funkcji GRY — cytat z jej kodu, niezbedny, zeby
    // sprawdzic, ze latamy wlasciwe miejsce. Nie sa objete licencja MIT tego
    // projektu (patrz uwaga licencyjna na poczatku pliku).
    static const unsigned char oczekiwane[] = {
        0x41, 0x54,                    // push r12
        0x41, 0x57,                    // push r15
        0x48, 0x83, 0xEC, 0x48         // sub rsp,0x48
    };
    if (memcmp(fn, oczekiwane, sizeof oczekiwane) != 0) {
        logLine("WEJSCIE: bajty pod 0x%llX inne niz oczekiwane — NIE lataem",
                (unsigned long long)(uintptr_t)fn);
        return false;
    }

    unsigned char* tr = nullptr;
    for (uintptr_t a = base + 0x08000000; a < base + 0x40000000; a += 0x10000) {
        tr = (unsigned char*)VirtualAlloc((void*)a, 0x1000,
                                          MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (tr) break;
    }
    if (!tr) { logLine("WEJSCIE: brak miejsca na trampoline"); return false; }

    // Uklad trampoliny — offsety wypisane, bo recznie liczone myla sie latwo
    // (przy latce boostera mialem trzy bledy naraz):
    //   +0x00 test rcx,rcx
    //   +0x03 jz -> +0x16 (natychmiastowy ret)
    //   +0x05 push r12                oryginal
    //   +0x07 push r15                oryginal
    //   +0x09 sub rsp,0x48            oryginal
    //   +0x0D jmp [rip+0] -> +0x13
    //   +0x13 <adres powrotu, 8 B>    (fn+8)
    //   +0x1B inc [rip+X] -> licznik
    //   +0x21 ret
    //   +0x22 <licznik, 4 B>
    //
    // Wiersze oznaczone „oryginal" to bajty przeniesione Z GRY (patrz uwaga
    // licencyjna na poczatku pliku).
    enum { OFF_POWROT = 0x13, OFF_LICZNIK = 0x22 };
    unsigned char code[] = {
        0x48, 0x85, 0xC9,                    // test rcx,rcx
        0x74, 0x16,                          // jz -> +0x1B
        0x41, 0x54,                          // push r12   (oryginal)
        0x41, 0x57,                          // push r15   (oryginal)
        0x48, 0x83, 0xEC, 0x48,              // sub rsp,0x48 (oryginal)
        0xFF, 0x25, 0x00,0x00,0x00,0x00,     // jmp [rip+0] -> powrot
        0,0,0,0,0,0,0,0,                     // +0x13 adres powrotu
        0xFF, 0x05, 0x01,0x00,0x00,0x00,     // +0x1B inc [rip+1] -> licznik(+0x22)
        0xC3,                                // +0x21 ret  (nic nie zwraca!)
        0,0,0,0                              // +0x22 licznik
    };
    if (sizeof(code) != OFF_LICZNIK + 4) {
        logLine("WEJSCIE: BLAD WEWNETRZNY — rozmiar %zu, oczekiwano %d",
                sizeof(code), OFF_LICZNIK + 4);
        return false;
    }
    const uintptr_t powrot = (uintptr_t)fn + 8;
    memcpy(code + OFF_POWROT, &powrot, sizeof powrot);
    memcpy(tr, code, sizeof code);
    g_wejscieLicznik = (volatile unsigned*)(tr + OFF_LICZNIK);

    DWORD stare = 0;
    if (!VirtualProtect(fn, 16, PAGE_EXECUTE_READWRITE, &stare)) {
        logLine("WEJSCIE: VirtualProtect nieudany"); return false;
    }
    const int32_t rel = (int32_t)((intptr_t)tr - (intptr_t)(fn + 5));
    fn[0] = 0xE9; memcpy(fn + 1, &rel, 4);
    fn[5] = 0x90; fn[6] = 0x90; fn[7] = 0x90;
    VirtualProtect(fn, 16, stare, &stare);
    FlushInstructionCache(GetCurrentProcess(), fn, 16);
    logLine("WEJSCIE: straznik nulla zalozony w wiazaniu akcji wejscia "
            "(0x%llX -> trampolina 0x%llX)",
            (unsigned long long)(uintptr_t)fn, (unsigned long long)(uintptr_t)tr);
    return true;
}

// ── SCIANA #3: EFEKTY STRZALU U KLIENTA (odczyt spod 0x0) ───────────────────
//
// Objaw: klient znika 1-2 minuty po dolaczeniu, sygnatura `17fc181f`, trzy
// wystapienia (03:00, 14:54, 16:10). Wygladalo to na ZAMROZENIE — proces zyje,
// obraz stoi — ale to mylace: proces stoi w obsludze wyjatku. Na jego stosie
// uniksowym siedzi `0xC0000005`, a w katalogu `Crashes` lezy swiezy zrzut.
// Czyli klient PADL, a zawiesila sie dopiero obsluga awarii.
//
// Stos zrzutu (nazwany refleksja przez `nazwij-ramke.py`):
//   DimensionWeaponInstantHit::SpawnInstantHitEffects + 0x10C
//   DimensionWeaponInstantHit::SpawnTrailEffect       + 0x7E
//   0x141B59EAD                                        <- tu ginie
//
// Kod w miejscu awarii:
//   0x141B59EA6  48 8B 8E 98 09 00 00   mov  rcx,[rsi+0x998]   ; MyPawn
//   0x141B59EAD  48 8B 01               mov  rax,[rcx]         ; <- rcx == 0
//   0x141B59EB0  FF 90 C0 09 00 00      call [rax+0x9C0]
//   0x141B59EB6  84 C0                  test al,al
//   0x141B59EB8  74 7B                  je   0x141B59F35
//   0x141B59EBA  48 8B 8E 98 09 00 00   mov  rcx,[rsi+0x998]   ; TA SAMA wartosc
//   0x141B59EC1  E8 ..                  call 0x1418721A0
//   0x141B59EC6  48 8B D8 / 48 85 C0 / 74 ..                   ; ...i TU sprawdzona
//
// `+0x998` to `MyPawn` — sprawdzone refleksja (`ue-props.py --klasa
// DimensionWeapon`), nie odgadniete z sasiedztwa. Jest to pole REPLIKOWANE,
// ale gdy do klienta przychodzi multicast efektu strzalu broni HOSTA, referencja
// do pawna jeszcze nie jest rozwiazana. Dla jedynego gracza taka sytuacja nie
// zachodzi nigdy, wiec autorzy sprawdzili tylko jedno z dwoch uzyc.
//
// To trzecie wystapienie wzorca opisanego w WIEDZA.md §4 — i znow naprawiamy je
// tak samo: wychodzimy DOKLADNIE ta droga, ktorej gra uzywa przy wlasnym
// sprawdzeniu dwie instrukcje nizej (`je 0x141B59F35`). Skutkiem ubocznym jest
// brak smugi po pocisku cudzej broni w jednej klatce — czyli mniej, niz gra
// traci, gdy proces ginie.
//
// Sprawdzone przed wdrozeniem: w oknie 16 podmienianych bajtow nie lezy zaden
// cel skoku (skan rel8/rel32/jcc32 w promieniu 0x4000 — zero trafien).
namespace addr {
constexpr uintptr_t EffectsPawnLoad_OFF = 0x1B59EA6;   // mov rcx,[rsi+0x998]
constexpr uintptr_t EffectsPowrot_OFF   = 0x1B59EB6;   // test al,al
constexpr uintptr_t EffectsPominiecie_OFF = 0x1B59F35; // sciezka „bez pawna"
}

static volatile unsigned* g_efektyLicznik = nullptr;

static bool patchEffectsPawnNullGuard(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::EffectsPawnLoad_OFF);
    // Bajty ponizej pochodza Z GRY — cytat z jej kodu, niezbedny, zeby sprawdzic,
    // ze latamy wlasciwe miejsce. Nie sa objete licencja MIT tego projektu
    // (patrz uwaga licencyjna na poczatku pliku).
    static const unsigned char oczekiwane[] = {
        0x48, 0x8B, 0x8E, 0x98, 0x09, 0x00, 0x00,   // mov  rcx,[rsi+0x998]
        0x48, 0x8B, 0x01,                           // mov  rax,[rcx]
        0xFF, 0x90, 0xC0, 0x09, 0x00, 0x00          // call [rax+0x9C0]
    };
    if (memcmp(fn, oczekiwane, sizeof oczekiwane) != 0) {
        logLine("EFEKTY: bajty pod 0x%llX inne niz oczekiwane — NIE latam",
                (unsigned long long)(uintptr_t)fn);
        return false;
    }

    unsigned char* tr = nullptr;
    for (uintptr_t a = base + 0x08000000; a < base + 0x40000000; a += 0x10000) {
        tr = (unsigned char*)VirtualAlloc((void*)a, 0x1000,
                                          MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (tr) break;
    }
    if (!tr) { logLine("EFEKTY: brak miejsca na trampoline"); return false; }

    //   +0x00 mov  rcx,[rsi+0x998]   oryginal
    //   +0x07 test rcx,rcx
    //   +0x0A jz   -> +0x23          (przesuniecie 0x17 od +0x0C)
    //   +0x0C mov  rax,[rcx]         oryginal
    //   +0x0F call [rax+0x9C0]       oryginal
    //   +0x15 jmp  [rip+0] -> +0x1B  adres powrotu
    //   +0x1B <adres powrotu, 8 B>
    //   +0x23 inc  [rip+0xE] -> +0x37 licznik
    //   +0x29 jmp  [rip+0] -> +0x2F  adres pominiecia
    //   +0x2F <adres pominiecia, 8 B>
    //   +0x37 <licznik, 4 B>
    //
    // Instrukcje odtworzone w trampolinie (`mov rcx,[rsi+0x998]`, `mov rax,[rcx]`,
    // `call [rax+0x9C0]`) to bajty przeniesione Z GRY — cytat niezbedny do
    // zalatania (patrz uwaga licencyjna na poczatku pliku).
    enum { OFF_POWROT = 0x1B, OFF_POMIN = 0x2F, OFF_LICZNIK = 0x37 };
    unsigned char code[] = {
        0x48, 0x8B, 0x8E, 0x98, 0x09, 0x00, 0x00,   // mov  rcx,[rsi+0x998]
        0x48, 0x85, 0xC9,                           // test rcx,rcx
        0x74, 0x17,                                 // jz   -> +0x23
        0x48, 0x8B, 0x01,                           // mov  rax,[rcx]
        0xFF, 0x90, 0xC0, 0x09, 0x00, 0x00,         // call [rax+0x9C0]
        0xFF, 0x25, 0x00,0x00,0x00,0x00,            // jmp  [rip+0] -> powrot
        0,0,0,0,0,0,0,0,                            // +0x1B adres powrotu
        0xFF, 0x05, 0x0E,0x00,0x00,0x00,            // inc  dword [rip+0xE] -> licznik
        0xFF, 0x25, 0x00,0x00,0x00,0x00,            // jmp  [rip+0] -> pominiecie
        0,0,0,0,0,0,0,0,                            // +0x2F adres pominiecia
        0,0,0,0                                     // +0x37 licznik
    };
    if (sizeof(code) != OFF_LICZNIK + 4) {
        logLine("EFEKTY: BLAD WEWNETRZNY — rozmiar trampoliny %zu, oczekiwano %d",
                sizeof(code), OFF_LICZNIK + 4);
        return false;
    }
    const uintptr_t powrot = base + addr::EffectsPowrot_OFF;
    memcpy(code + OFF_POWROT, &powrot, sizeof powrot);
    const uintptr_t pomin = base + addr::EffectsPominiecie_OFF;
    memcpy(code + OFF_POMIN, &pomin, sizeof pomin);
    memcpy(tr, code, sizeof code);
    g_efektyLicznik = (volatile unsigned*)(tr + OFF_LICZNIK);

    DWORD stare = 0;
    if (!VirtualProtect(fn, 16, PAGE_EXECUTE_READWRITE, &stare)) {
        logLine("EFEKTY: VirtualProtect nieudany"); return false;
    }
    const int32_t rel = (int32_t)((intptr_t)tr - (intptr_t)(fn + 5));
    fn[0] = 0xE9; memcpy(fn + 1, &rel, 4);
    for (int i = 5; i < 16; ++i) fn[i] = 0x90;   // dopelnienie do 16 bajtow
    VirtualProtect(fn, 16, stare, &stare);
    FlushInstructionCache(GetCurrentProcess(), fn, 16);
    logLine("EFEKTY: straznik nulla zalozony na MyPawn w efektach strzalu "
            "(0x%llX -> trampolina 0x%llX)",
            (unsigned long long)(uintptr_t)fn, (unsigned long long)(uintptr_t)tr);
    return true;
}

// ── LICZNIK RPC RUCHU (ServerMove...) ───────────────────────────────────────
//
// Po co: klient rozpedza sie u siebie do 238 jednostek/s, a serwerowa kopia jego
// postaci ma predkosc 0,0 i nie drga w zadnej osi. Caly lancuch posiadania
// sieciowego jest po obu stronach poprawny (Role 3/2, Owner, Controller.Pawn,
// AcknowledgedPawn), wiec czytanie kolejnych pol niczego juz nie doda. Trzeba
// policzyc, czy `ServerMove` w ogole DOCHODZI do serwera.
//
// Co ten licznik mierzy, a czego NIE mierzy — to jest istotne przy czytaniu
// wyniku: podmieniamy `UFunction::Func`, czyli przejsciowke skryptowa wolana,
// gdy RPC zostaje WYKONANE. Na serwerze to znaczy „przyszlo i sie wykonalo".
// U klienta ta przejsciowka nie jest wolana wcale, bo `ProcessEvent` dla funkcji
// `NetServer` kieruje wywolanie do NetDrivera zamiast do `Func` — zero u klienta
// jest wiec stanem OCZEKIWANYM i nie znaczy nic zlego.
//
// Rozroznienie „klient nie wysyla" od „pakiety nie docieraja" mamy juz bez
// dodatkowego pomiaru: `AcknowledgedPawn` na serwerze jest ustawiony, a ustawia
// go RPC klienta `ServerAcknowledgePossession`. Kanal klient->serwer dziala.
//
// Podmiana wskaznika zamiast latania kodu jest tu swiadoma: nie wymaga
// relokacji instrukcji ani znajomosci dlugosci prologu, a cofa sie jednym
// zapisem.
namespace addr {
constexpr uintptr_t UFUNC_FUNC_OFF = 0xD8;   // SuperStruct(0x40) + 0x98
}

using FNativeFunc = void(__fastcall*)(void* ctx, void* stack, void* wynik);

static const char* const g_nazwyRuchu[] = {
    "ServerMove", "ServerMoveDual", "ServerMoveDualHybridRootMotion",
    "ServerMoveDualNoBase", "ServerMoveNoBase", "ServerMoveOld",
    "ServerMovePacked",
};
static constexpr int RUCH_ILE = (int)(sizeof g_nazwyRuchu / sizeof *g_nazwyRuchu);

static FNativeFunc      g_ruchOryginal[RUCH_ILE] = {};
static volatile LONG    g_ruchLicznik[RUCH_ILE] = {};
static bool             g_ruchWlaczony = false;

// ── PRZY OKAZJI: stad bierzemy adres `ProcessEvent` i uklad `FFrame` ────────
//
// Po co tutaj, a nie osobnym hakiem: pierwsze podejscie zakladalo hak na
// przejsciowke `ProcessInputAction` i MILCZALO. Powod ustalony na zrzucie, nie
// zgadniety: ta funkcja ma DWOCH wolajacych — przejsciowke skryptowa
// (`0x141CB3174`) i **bezposrednie wywolanie C++** z kodu wejscia
// (`0x141807041`). Gra uzywa tego drugiego, wiec przez `UFunction::Func` nic
// nie przechodzi i cisza nie znaczyla „gracz nie nacisnal".
//
// `ServerMovePacked` takiej watpliwosci nie ma: to RPC ODBIERANE, a odbior
// zawsze idzie `ProcessRemoteFunction` -> `ProcessEvent` -> `Func`. Wiec adres
// powrotu z tego thunku LEZY WEWNATRZ `ProcessEvent`.
//
// Uklad `FFrame` bierzemy z tej samej chwili: `ProcessEvent` alokuje bufor
// parametrow NA SWOIM STOSIE, wiec pole `Locals` to jedyny wskaznik w ramce
// celujacy tuz obok naszego `rsp`. To rozpoznanie po polozeniu, nie po
// zgadnietym offsecie.
static volatile LONG g_peZmierzone = 0;
static bool          g_logKanal = false;   // marker `WFCoop_log_kanal.txt`

static void zmierzProcessEvent(void* stos, void* powrot)
{
    if (!g_bazaModulu || InterlockedIncrement(&g_peZmierzone) != 1) return;
    uintptr_t sp = 0;
    __asm__ volatile ("mov %%rsp, %0" : "=r"(sp));
    logLine("KANAL: RPC ruchu wykonane z 0x%llX — to wnetrze ProcessEvent",
            (unsigned long long)((uintptr_t)powrot - g_bazaModulu + 0x140000000));
    char znal[256] = "";
    size_t uz = 0;
    for (int off = 0; off <= 0x60; off += 8) {
        const uintptr_t v = *(const uintptr_t*)((uintptr_t)stos + off);
        if (!v) continue;
        const long long odleglosc = (long long)v - (long long)sp;
        if (odleglosc > -0x400 && odleglosc < 0x4000) {
            const int w = _snprintf_s(znal + uz, sizeof znal - uz, _TRUNCATE,
                                      "%s+0x%02X (rsp%+lld)", uz ? ", " : "",
                                      off, odleglosc);
            if (w > 0) uz += (size_t)w;
        }
    }
    logLine("KANAL:    pola FFrame celujace w poblize stosu: %s",
            znal[0] ? znal : "(zadne)");
    // Rozmiar ramki tez sie przyda przy budowaniu wlasnego wywolania.
    logLine("KANAL:    FFrame=0x%llX  rsp=0x%llX",
            (unsigned long long)(uintptr_t)stos, (unsigned long long)sp);
}

// Osobna funkcja na kazde gniazdo — inaczej nie wiedzielibysmy, ktore RPC
// przyszlo. Szablon daje siedem roznych adresow bez pisania siedmiu kopii.
template <int N>
static void __fastcall thunkRuchu(void* ctx, void* stack, void* wynik)
{
    InterlockedIncrement(&g_ruchLicznik[N]);
    if (g_logKanal) zmierzProcessEvent(stack, __builtin_return_address(0));
    if (g_ruchOryginal[N]) g_ruchOryginal[N](ctx, stack, wynik);
}

static const FNativeFunc g_ruchThunki[RUCH_ILE] = {
    &thunkRuchu<0>, &thunkRuchu<1>, &thunkRuchu<2>, &thunkRuchu<3>,
    &thunkRuchu<4>, &thunkRuchu<5>, &thunkRuchu<6>,
};

static int patchServerMoveCounters(uintptr_t base)
{
    const uintptr_t tab = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tab;
    const int32_t ile    = *(const int32_t*)(tab + 0x14);
    const int32_t nchunk = *(const int32_t*)(tab + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) {
        logLine("RUCH: tablica obiektow niegotowa — nie zakladam licznikow");
        return 0;
    }

    int zalozone = 0;
    char nazwa[128], nazwaKl[128];
    for (int32_t ci = 0; ci < nchunk && zalozone < RUCH_ILE; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
            if (!nazwaObiektu(base, klasa, nazwaKl, sizeof nazwaKl)) continue;
            if (strcmp(nazwaKl, "Function") != 0) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;

            for (int n = 0; n < RUCH_ILE; ++n) {
                if (g_ruchOryginal[n]) continue;              // juz mamy
                if (strcmp(nazwa, g_nazwyRuchu[n]) != 0) continue;
                // Wlascicielem musi byc `Character` — nazwy RPC ruchu sa dosc
                // ogolne, zeby trafic w cudza klase.
                const uintptr_t wl = *(const uintptr_t*)(obj + UOBJ_OUTER_OFF);
                char nazwaWl[128];
                if (!sensownyWsk(wl)) continue;
                if (!nazwaObiektu(base, wl, nazwaWl, sizeof nazwaWl)) continue;
                if (strcmp(nazwaWl, "Character") != 0) continue;

                auto* gniazdo = (FNativeFunc*)(obj + addr::UFUNC_FUNC_OFF);
                g_ruchOryginal[n] = *gniazdo;
                *gniazdo = g_ruchThunki[n];
                ++zalozone;
                break;
            }
        }
    }
    logLine("RUCH: liczniki RPC zalozone na %d z %d funkcji ruchu", zalozone, RUCH_ILE);
    return zalozone;
}

// ── KANAL STANU RUCHU: pomiar dwoch brakujacych rzeczy ──────────────────────
//
// Do czego to zmierza. Sprint i slizg to stany maszyny stanow gracza, a serwer
// nigdy w nie nie wchodzi, bo maszyne napedza WEJSCIE, a serwer nie ma
// komponentu wejscia gracza zdalnego (sciana #2). Zmierzone: serwerowa kopia
// klienta siedzi w `Idle`, gdy klient przechodzi u siebie przez piec stanow.
//
// Gra daje gotowe wejscie „z zewnatrz": `ProcessExternalInputAction`
// (gniazdo 147) bierze `FInputActionStateDefinition` — 64 bajty, czyli
// 56-bajtowa DEFINICJE AKCJI plus `KeyEvent` (+0x38) i `bCustomTriggered`
// (+0x39). A gotowe definicje leza w samej maszynie, w `InputsToCapture`
// (+0x130, 10 pozycji po 56 B, pierwsze 8 bajtow to FName):
//
//   [0] Crouch  [1] RunToggle  [2] Run  [3] Jump  [4] Targeting
//   [5] Reload  [6] Fire       [7] LightSpell     [8] Melee  [9] Healing
//
// Czyli NIE trzeba niczego podrabiac: bierzemy wlasna definicje gry i podajemy
// ja z powrotem z wlasciwym zdarzeniem klawisza. Reszta — czy z tego wyjdzie
// `Running`, czy `Sliding` — zostaje decyzja maszyny stanow gry.
//
// Zeby to zrobic, brakuje DWOCH rzeczy, i obie mierzy ten jeden hak:
//
//   1. adres `UObject::ProcessEvent` — bez niego nie wyslemy RPC z klienta.
//      Szukanie po wzorcach kodu zawiodlo (przesuniecia `+0xD8`, `+0xB6` sa
//      zbyt pospolite: 128 kandydatow). Ale przejsciowke skryptowa wola
//      WLASNIE `ProcessEvent`, wiec wystarczy odczytac adres powrotu.
//
//   2. uklad `FFrame` — gdzie w nim lezy bufor parametrow. Rozpoznajemy go
//      bez zgadywania: pierwsze 8 bajtow parametru to FName akcji, wiec
//      porownujemy je z `InputsToCapture` tej samej maszyny. Zgodnosc
//      wskazuje offset jednoznacznie.
//
// Hak jest CZYSTO POMIAROWY: loguje i oddaje sterowanie oryginalowi.
namespace addr {
constexpr uintptr_t SM_INPUTS_TO_CAPTURE = 0x130;   // TArray, element 56 B
constexpr int       WEJSCIE_ROZMIAR      = 56;
}

static FNativeFunc   g_origProcInput = nullptr;
static volatile LONG g_kanalIle = 0;

static void __fastcall thunkProcInput(void* ctx, void* stos, void* wynik)
{
    void* powrot = __builtin_return_address(0);
    if (g_bazaModulu && InterlockedIncrement(&g_kanalIle) <= 4) {
        const uintptr_t base = g_bazaModulu;
        const uintptr_t sm = (uintptr_t)ctx;
        logLine("KANAL: ProcessInputAction wolane z 0x%llX  (to wnetrze ProcessEvent)",
                (unsigned long long)((uintptr_t)powrot - base + 0x140000000));

        // Gdzie w FFrame leza parametry — rozpoznajemy po FName akcji.
        const uintptr_t wejscia = *(const uintptr_t*)(sm + addr::SM_INPUTS_TO_CAPTURE);
        const int32_t   ileWej  = *(const int32_t*)(sm + addr::SM_INPUTS_TO_CAPTURE + 8);
        bool znalezione = false;
        if (sensownyWsk(wejscia) && ileWej > 0 && ileWej <= 32) {
            for (int off = 0; off <= 0x80 && !znalezione; off += 8) {
                const uintptr_t p = *(const uintptr_t*)((uintptr_t)stos + off);
                if (!sensownyWsk(p)) continue;
                const unsigned long long fname = *(const unsigned long long*)p;
                for (int i = 0; i < ileWej; ++i) {
                    const unsigned long long wz =
                        *(const unsigned long long*)(wejscia + (uintptr_t)i * addr::WEJSCIE_ROZMIAR);
                    if (fname != wz) continue;
                    logLine("KANAL:    parametry w FFrame pod +0x%02X -> akcja [%d], "
                            "KeyEvent=%u bCustomTriggered=%u",
                            off, i, (unsigned)*(const unsigned char*)(p + 0x38),
                            (unsigned)*(const unsigned char*)(p + 0x39));
                    znalezione = true;
                    break;
                }
            }
        }
        if (!znalezione)
            logLine("KANAL:    nie rozpoznalem bufora parametrow w FFrame "
                    "(wejsc do porownania: %d)", ileWej);
    }
    if (g_origProcInput) g_origProcInput(ctx, stos, wynik);
}

static bool patchKanalPomiar(uintptr_t base)
{
    const uintptr_t tab = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tab;
    const int32_t ile    = *(const int32_t*)(tab + 0x14);
    const int32_t nchunk = *(const int32_t*)(tab + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    char nazwa[128], nazwaKl[128], nazwaWl[128];
    for (int32_t ci = 0; ci < nchunk; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
            if (!nazwaObiektu(base, klasa, nazwaKl, sizeof nazwaKl)) continue;
            if (strcmp(nazwaKl, "Function") != 0) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;
            if (strcmp(nazwa, "ProcessInputAction") != 0) continue;
            const uintptr_t wl = *(const uintptr_t*)(obj + UOBJ_OUTER_OFF);
            if (!sensownyWsk(wl) || !nazwaObiektu(base, wl, nazwaWl, sizeof nazwaWl)) continue;
            if (strcmp(nazwaWl, "DimensionStateMachineComponent") != 0) continue;

            auto* gniazdo = (FNativeFunc*)(obj + addr::UFUNC_FUNC_OFF);
            g_origProcInput = *gniazdo;
            *gniazdo = &thunkProcInput;
            logLine("KANAL: hak pomiarowy na ProcessInputAction zalozony "
                    "(oryginal 0x%llX)",
                    (unsigned long long)((uintptr_t)g_origProcInput - base + 0x140000000));
            return true;
        }
    }
    logLine("KANAL: nie znalazlem UFunction ProcessInputAction");
    return false;
}

// ── KANAL STANU RUCHU: klient mowi serwerowi, co nacisnal ───────────────────
//
// PROBLEM, zmierzony (WIEDZA.md §3b): serwerowa kopia postaci klienta siedzi
// w `Idle` przez caly czas, gdy klient przechodzi u siebie przez `Walking`,
// `Running`, `Sliding`, `Airborne`. Przez to serwer liczy mu zwykla predkosc
// (615) albo kucanie (265) zamiast sprintu i slizgu (800) — i sciaga gracza
// do swojej pozycji. Stad cofanie, najmocniejsze przy slizgu (roznica 3x),
// slabsze przy sprincie (23%), zadne przy dashu (2500 = 2500, bo dash idzie
// przez system zdolnosci).
//
// DLACZEGO trzeba kanalu: `DimensionStateMachineComponent` ma 47 funkcji
// i ZERO RPC. Gra nie ma czym przeslac tego stanu — w grze jednoosobowej nie
// bylo po co. To siodme wystapienie wzorca §4.
//
// CZEGO NIE ROBIMY: nie podstawiamy predkosci i nie rozluzniamy korekty
// serwera. To by bylo zamiatanie objawu. Podajemy brakujace WEJSCIE, a to, czy
// wyjdzie z niego `Running`, czy `Sliding`, rozstrzyga maszyna stanow gry.
//
// JAK TO DZIALA
// -------------
// Klient  : odczytuje wlasny stan (`maszyna+0x178`, indeks do `States`) i przy
//           KAZDEJ ZMIANIE wysyla go istniejacym RPC gry
//           `ServerSetInversedScreenRatio(float)` jako `1000 + indeks`.
// Serwer  : przechwytuje to RPC. Wartosc >= 999 jest nasza (prawdziwy stosunek
//           ekranu to ~0,5–2,0), wiec ja zjadamy i NIE oddajemy grze — dzieki
//           temu prawdziwa funkcja RPC pozostaje nietknieta. Z indeksu
//           wyprowadzamy, ktore akcje maja byc wcisniete, i podajemy je
//           `ProcessExternalInputAction` (gniazdo 147) — wlasnym wejsciem gry.
//
// Wszystkie liczby ponizej sa ZMIERZONE, zadna nie jest zgadnieta:
//   ProcessEvent              gniazdo wirtualne 68   (przebieg 02:22)
//   FFrame::Locals            +0x28                  (przebieg 02:22)
//   ProcessExternalInputAction gniazdo wirtualne 147  (z deasemblacji thunku)
//   InputsToCapture           maszyna+0x130, element 56 B, FName na poczatku
//   stan biezacy              maszyna+0x178, indeks do States (+0x148)
namespace addr {
constexpr int       SLOT_PROCESS_EVENT     = 68;
constexpr int       SLOT_PROCESS_EXTERNAL  = 147;
constexpr uintptr_t FFRAME_LOCALS          = 0x28;
constexpr uintptr_t CHAR_STATE_MACHINE     = 0x968;
constexpr uintptr_t CHAR_CONTROLLER        = 0x258;   // AActor::Controller
constexpr uintptr_t PC_PLAYER              = 0x298;   // APlayerController::Player
constexpr uintptr_t SM_STATES              = 0x148;   // TArray<UObject*>
constexpr uintptr_t SM_CURRENT_IDX         = 0x178;   // int32, indeks do States
constexpr uintptr_t AKCJA_KEYEVENT         = 0x38;
constexpr uintptr_t AKCJA_CUSTOM           = 0x39;
constexpr int       AKCJA_STRUKTURA        = 64;      // rozmiar bufora parametru
constexpr float     KANAL_BAZA             = 1000.0f;

// ── DOLOZONE PO ROZBIORZE OBRAZU (11.08) — wszystko sprawdzone deasemblacja ──
//
// Gniazdo 150 (offset 0x4B0) to PELNA sciezka wejscia gry. Prawdziwe wejscie
// gracza wchodzi wylacznie tedy: `0x14183D720` (najbardziej pochodna maszyna
// stanow) nie ma w calym module ANI JEDNEGO bezposredniego wolajacego i lezy
// w obrazie dokladnie raz — jako wpis w tablicy metod pod `0x14507EF00`.
// Czyli kazde jej wywolanie to wywolanie wirtualne przez to gniazdo.
//
// Roznica wobec gniazda 147 (`ProcessExternalInputAction`) jest istotna:
// pelna sciezka `0x141800F20` przed oddaniem akcji stanowi robi jeszcze
//   0x141801001  call 0x1417B8210(this+0x2F8, klucz)   ; BRAMKA — czy to nasza akcja
//   0x1418010C3  call 0x1417A8A20(this+0x2F8, akcja)   ; zapis stanu wejscia
// a `ProcessExternalInputAction` obu tych rzeczy NIE robi. Jesli warunek
// przejscia pyta „czy Run jest TRZYMANY", to czyta wlasnie `+0x2F8`.
constexpr int       SLOT_INPUT_HANDLER     = 150;     // offset 0x4B0
constexpr uintptr_t SM_INPUT_STATES        = 0x2F8;   // TArray<FInputActionState>, element 64 B

// `FInputActionStateDefinition::operator=` — kopia definicji akcji WLASNYM
// kodem gry. Potrzebna, bo pod `+0x18`/`+0x20` definicji siedzi `TSharedPtr`
// (wskaznik + kontroler licznika odwolan), a `ProcessExternalInputAction`
// ZWALNIA go na koncu (`0x14180041B mov rbx,[rsi+0x20]` i sekwencja
// zmniejszania licznikow). Zwykly `memcpy` kopiowal wiec referencje BEZ
// podbicia licznika, a gra ja potem oddawala — czyli kazde podanie akcji
// zabieralo definicji gry jedno odwolanie. Ten operator podbija licznik tak,
// jak robi to gra u siebie (`0x1417A4B54 inc dword ptr [rbx+8]`).
constexpr uintptr_t KopiujAkcje_OFF        = 0x17A3E50;

// ── GRAF PRZEJSC (rozbior 18:41, `tools/przejscia.py`) ──────────────────────
//
// Podanie akcji NIE MOGLO zadzialac i to widac w danych samej gry: ze stanu
// `Idle` wychodza trzy przejscia — do `Walking`, `Crouching` i `Airborne`.
// Do `Running` nie ma z `Idle` ZADNEGO. Serwerowa kopia pionka klienta siedzi
// w `Idle`, wiec akcja `Run` nie miala tam czego uruchomic.
//
// Gra daje wlasne API do sterowania maszyna z zewnatrz — `AddTransitionToQueue`
// bierze NAZWE przejscia, a nazwy sa danymi klasy, wiec identyczne u obu
// graczy i nie trzeba ich przesylac kanalem.
constexpr uintptr_t SM_STATE_ENTRIES       = 0x158;   // TArray<DimensionStateEntry>
constexpr int       ENTRY_ROZMIAR          = 48;
constexpr uintptr_t ENTRY_TAG              = 0x00;    // FGameplayTag (FName)
constexpr uintptr_t ENTRY_TRANS_FROM       = 0x10;    // TArray<DimensionStateTransition>
constexpr int       TRANS_ROZMIAR          = 64;
constexpr uintptr_t TRANS_NAME             = 0x00;    // FName — to bierze AddTransitionToQueue
constexpr uintptr_t TRANS_TARGET_TAG       = 0x10;    // FGameplayTag stanu docelowego
constexpr uintptr_t TRANS_WAR_WLASNE       = 0x28;    // TArray<CountableGameplayTagCondition>
constexpr int       WARUNEK_ROZMIAR        = 20;      // z sygnatury CheckCondition
// Gniazdo, ktore PRZERABIA kolejke przejsc. Obie sciezki wejscia gry konczy
// sie tym samym wywolaniem (`0x14180103E`/`0x141801183 call [rax+0x420]`),
// wiec po zakolejkowaniu wolamy dokladnie to, co wola gra.
constexpr int       SLOT_PROCESS_TRANSITIONS = 132;   // offset 0x420
}

enum { KEY_PRESSED = 0, KEY_RELEASED = 1 };

// Gniazdo tablicy metod musi wskazywac KOD GRY. Bez tego pierwsze wywolanie
// byloby skokiem w nieznane, a awaria nie zostawilaby sladu w logu — zasada 4
// (offsety weryfikowac przed wdrozeniem) i 14 (hak ma dowodzic, ze zyje).
// Sprawdzamy raz na gniazdo i zapamietujemy werdykt.
static bool gniazdoSensowne(void* obiekt, int gniazdo, const char* opis)
{
    if (!obiekt || !g_bazaModulu) return false;
    auto** vt = *(void***)obiekt;
    if (!vt) return false;
    const uintptr_t cel = (uintptr_t)vt[gniazdo];
    const bool ok = cel >= g_bazaModulu && cel < g_bazaModulu + 0x08000000;
    static const char* zgloszone[4] = {};
    for (auto& z : zgloszone) {
        if (z == opis) return ok;
        if (!z) {
            z = opis;
            logLine("KANAL: gniazdo %d (%s) -> 0x%llX  %s", gniazdo, opis,
                    (unsigned long long)(ok ? cel - g_bazaModulu + 0x140000000 : cel),
                    ok ? "wyglada na kod gry" : "POZA MODULEM — nie wolam");
            return ok;
        }
    }
    return ok;
}

static bool          g_fixStateWlaczony = false;
// Kanal WYSYLA tylko z klienta. Bez tego rozroznienia host bez konca
// przemiela tablice obiektow w poszukiwaniu pionka `Role == 2`, ktorego
// u niego z definicji nie ma — i to wlasnie zabilo plynnosc w menu.
static bool          g_jestemKlientem = false;
static uintptr_t     g_ufuncKanal   = 0;    // UFunction RPC uzytego za transport
static FNativeFunc   g_origKanal    = nullptr;
static volatile LONG g_kanalWyslane = 0;
static volatile LONG g_kanalOdebrane = 0;
static volatile LONG g_kanalPodane  = 0;

// Nazwa stanu -> ktore akcje maja byc wcisniete, zeby gra sama w ten stan
// weszla. To jedyne miejsce z odwzorowaniem i jest celowo malutkie: nie
// odtwarzamy logiki przejsc, tylko mowimy, co gracz TRZYMA.
struct OpisStanu { const char* stan; bool run; bool crouch; };
static const OpisStanu g_stany[] = {
    { "DimensionPlayerRunningState",   true,  false },
    { "DimensionPlayerSlidingState",   true,  true  },
    { "DimensionPlayerCrouchingState", false, true  },
};

// Stan -> para (Run, Crouch). Wspolne dla obu stron kanalu: klient uzywa tego
// do decyzji „czy w ogole warto wysylac", serwer do podania akcji. Jedno
// odwzorowanie w jednym miejscu, zeby strony nie mogly sie rozjechac.
static bool stanNaAkcje(uintptr_t base, uintptr_t sm, int indeksStanu,
                        bool* run, bool* crouch, char* nazwaOut, size_t cap)
{
    *run = *crouch = false;
    if (nazwaOut && cap) nazwaOut[0] = 0;
    const uintptr_t stany = *(const uintptr_t*)(sm + addr::SM_STATES);
    const int32_t n = *(const int32_t*)(sm + addr::SM_STATES + 8);
    if (!sensownyWsk(stany) || indeksStanu < 0 || indeksStanu >= n) return false;
    const uintptr_t obj = *(const uintptr_t*)(stany + (uintptr_t)indeksStanu * 8);
    if (!sensownyWsk(obj)) return false;
    char nz[128];
    if (!nazwaObiektu(base, *(const uintptr_t*)(obj + UOBJ_CLASS_OFF), nz, sizeof nz))
        return false;
    for (const auto& s : g_stany)
        if (strcmp(nz, s.stan) == 0) { *run = s.run; *crouch = s.crouch; break; }
    if (nazwaOut && cap) strcpy_s(nazwaOut, cap, nz);
    return true;
}

// Czy ten pionek nalezy do gracza ZDALNEGO. Zabezpieczenie kierunku: kanal ma
// sterowac wylacznie kopia drugiego gracza. U hosta jego wlasna postac i kopia
// klienta maja obie `Role == 3`, wiec rola tego nie rozstrzyga — rozstrzyga
// dopiero obiekt `Player` kontrolera (`DimensionLocalPlayer` = czlowiek przy
// tym procesie).
static bool pionekZdalny(uintptr_t base, uintptr_t postac)
{
    const uintptr_t pc = *(const uintptr_t*)(postac + addr::CHAR_CONTROLLER);
    if (!sensownyWsk(pc)) return false;
    const uintptr_t gracz = *(const uintptr_t*)(pc + addr::PC_PLAYER);
    if (!sensownyWsk(gracz)) return false;
    char n[128];
    const uintptr_t kl = *(const uintptr_t*)(gracz + UOBJ_CLASS_OFF);
    if (!sensownyWsk(kl) || !nazwaObiektu(base, kl, n, sizeof n)) return false;
    return strcmp(n, "DimensionLocalPlayer") != 0;
}

static int indeksAkcji(uintptr_t base, uintptr_t sm, const char* szukana)
{
    const uintptr_t dane = *(const uintptr_t*)(sm + addr::SM_INPUTS_TO_CAPTURE);
    const int32_t n = *(const int32_t*)(sm + addr::SM_INPUTS_TO_CAPTURE + 8);
    if (!sensownyWsk(dane) || n <= 0 || n > 64) return -1;
    char nz[64];
    for (int i = 0; i < n; ++i) {
        const uint32_t idx = *(const uint32_t*)(dane + (uintptr_t)i * addr::WEJSCIE_ROZMIAR);
        if (!nazwaFName(base, idx, nz, sizeof nz)) continue;
        if (strcmp(nz, szukana) == 0) return i;
    }
    return -1;
}

// ── PODSLUCH PRAWDZIWEGO WEJSCIA (gniazdo 150) ──────────────────────────────
//
// Po co: kanal dziala od konca do konca — klient wysyla, host odbiera i podaje
// akcje (liczniki 6/8/8) — ale maszyna stanow serwera i tak nie przechodzi.
// Zamiast zgadywac, co niesie prawdziwa akcja, podgladamy JA i zapamietujemy.
//
// To jest zasada 12 („instancja solo to wzorzec") przelozona na kod: czlowiek
// siedzacy przy TYM procesie naciska sprint, my zapamietujemy, jak wtedy
// wyglada struktura akcji, i dokladnie to odtwarzamy dla pionka zdalnego.
// Zadna wartosc nie jest juz zgadywana.
//
// Hak siedzi na gnieździe 150, bo prawdziwe wejscie wchodzi WYLACZNIE tedy
// (uzasadnienie przy `addr::SLOT_INPUT_HANDLER`). Hak zapamietuje zawsze,
// a loguje tylko przy markerze `log_kanal`.
using WejscieFn = void(__fastcall*)(void*, void*);
static WejscieFn     g_origWejscie = nullptr;
static volatile LONG g_wejscieIle = 0;

// Wzorzec bajtow `+0x38..+0x3F` prawdziwej akcji, osobno dla WCISNIECIA
// i PUSZCZENIA — bo nic nie gwarantuje, ze reszta pol jest w obu przypadkach
// taka sama.
struct WzorAkcji {
    uint32_t      fname;
    bool          znany[2];
    unsigned char bajty[2][8];
};
static WzorAkcji g_wzory[16] = {};
static volatile LONG g_wzorowZnanych = 0;

static WzorAkcji* wzorDla(uint32_t fname, bool utworz)
{
    for (auto& w : g_wzory) {
        if (w.fname == fname && (w.znany[0] || w.znany[1])) return &w;
        if (!w.znany[0] && !w.znany[1] && !w.fname) {
            if (!utworz) return nullptr;
            w.fname = fname;
            return &w;
        }
    }
    return nullptr;
}

static void __fastcall thunkWejscie(void* sm, void* akcja)
{
    if (g_bazaModulu && sensownyWsk((uintptr_t)akcja)) {
        const uintptr_t a  = (uintptr_t)akcja;
        const uint32_t  fn = *(const uint32_t*)a;
        const unsigned char* b = (const unsigned char*)(a + addr::AKCJA_KEYEVENT);
        const unsigned char ke = b[0];
        if (ke <= 1) {                       // 0 = wcisniecie, 1 = puszczenie
            WzorAkcji* w = wzorDla(fn, true);
            if (w && !w->znany[ke]) {
                memcpy(w->bajty[ke], b, 8);
                w->znany[ke] = true;
                InterlockedIncrement(&g_wzorowZnanych);
                char nz[64] = "?";
                nazwaFName(g_bazaModulu, fn, nz, sizeof nz);
                logLine("WEJSCIE-PODSLUCH: akcja=%s  KeyEvent=%d  "
                        "bajty +0x38..+0x3F: %02X %02X %02X %02X %02X %02X %02X %02X",
                        nz, (int)ke, b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]);
                // Proba kontrolna dla pytania „czy serwer w ogole ma czym
                // ocenic wejscie": ile pozycji ma tablica stanow wejscia
                // u gracza, ktory NAPRAWDE naciska klawisze. To jest wzorzec,
                // do ktorego porownamy pionek zdalny.
                if (g_wzorowZnanych == 1)
                    logLine("WEJSCIE-PODSLUCH: WZORZEC — maszyna 0x%llX ma "
                            "InputStates=%d, InputsToCapture=%d, stan=%d",
                            (unsigned long long)sm,
                            (int)*(const int32_t*)((uintptr_t)sm + addr::SM_INPUT_STATES + 8),
                            (int)*(const int32_t*)((uintptr_t)sm + addr::SM_INPUTS_TO_CAPTURE + 8),
                            (int)*(const int32_t*)((uintptr_t)sm + addr::SM_CURRENT_IDX));
            }
        }
        if (g_logKanal && InterlockedIncrement(&g_wejscieIle) <= 24) {
            char nz[64] = "?";
            nazwaFName(g_bazaModulu, fn, nz, sizeof nz);
            logLine("WEJSCIE-PRZEPLYW: akcja=%s  KeyEvent=%d  stan=%d",
                    nz, (int)b[0],
                    (int)*(const int32_t*)((uintptr_t)sm + addr::SM_CURRENT_IDX));
        }
    }
    if (g_origWejscie) g_origWejscie(sm, akcja);
}

// Kopia definicji akcji WLASNYM operatorem przypisania gry. Zwraca `false`,
// gdy adres nie wyglada na kod gry — wtedy nie wolamy niczego.
using KopiujAkcjeFn = void*(__fastcall*)(void*, const void*);

static bool kopiujDefinicje(uintptr_t base, void* dst, const void* src)
{
    const uintptr_t f = base + addr::KopiujAkcje_OFF;
    if (f < base || f >= base + 0x08000000) return false;
    ((KopiujAkcjeFn)f)(dst, src);
    return true;
}

// Zwolnienie `TSharedPtr` z naszego bufora — przypisaniem struktury pustej,
// czyli znowu kodem gry. `0x1417A4B30` zwalnia stara wartosc i podbija nowa
// (tu: zerowa), wiec licznik wraca do stanu sprzed kopii.
static void zwolnijDefinicje(uintptr_t base, void* bufor)
{
    static const unsigned char pusta[addr::AKCJA_STRUKTURA] = {};
    kopiujDefinicje(base, bufor, pusta);
}

// Podanie akcji maszynie stanow — kopiujemy JEJ WLASNA definicje, dokladamy
// bajty podpatrzone u prawdziwego wejscia i oddajemy JEJ WLASNEJ funkcji.
// Nic tu nie jest wymyslone.
//
// Proba jest DWUSTOPNIOWA i to jest jej wbudowana proba kontrolna:
//   1. gniazdo 147 (`ProcessExternalInputAction`) — punkt, ktory gra sama daje
//      pod „wejscie spoza komponentu wejscia",
//   2. jesli po nim stan sie NIE zmienil — gniazdo 150, czyli pelna sciezka
//      wejscia gry, ta sama, ktora obsluguje czlowieka przy klawiaturze.
// Log mowi wprost, ktory stopien zadzialal, wiec jeden przebieg rozstrzyga
// pytanie, na ktore inaczej trzeba by dwoch.
//
// UWAGA o wlasnosci referencji — rozne dla obu gniazd, sprawdzone w obrazie:
//   gniazdo 147: samo zwalnia `[param+0x20]` (0x14180041B) — oddajemy referencje,
//   gniazdo 150: NIE zwalnia; robi to jego wolajacy (`ProcessInputAction`
//                0x1418005F2) — wiec zwalniamy sami.
static void podajAkcje(uintptr_t sm, int indeksWejscia, unsigned char keyEvent)
{
    const uintptr_t dane = *(const uintptr_t*)(sm + addr::SM_INPUTS_TO_CAPTURE);
    if (!sensownyWsk(dane) || indeksWejscia < 0 || !g_bazaModulu) return;
    const uintptr_t def = dane + (uintptr_t)indeksWejscia * addr::WEJSCIE_ROZMIAR;
    if (!sensownyWsk(def)) return;

    auto** vt = *(void***)sm;
    if (!vt) return;

    // Bufor musi byc wyrownany do 16 B: `0x1417A4B30` czyta stara wartosc
    // przez `movups`, ale kopia definicji uzywa tez `movaps` w gralach ruchu.
    alignas(16) unsigned char bufor[addr::AKCJA_STRUKTURA] = {};

    auto zbuduj = [&]() -> bool {
        memset(bufor, 0, sizeof bufor);
        if (!kopiujDefinicje(g_bazaModulu, bufor, (const void*)def)) return false;
        const WzorAkcji* w = wzorDla(*(const uint32_t*)def, false);
        const int ke = keyEvent & 1;
        if (w && w->znany[ke])
            memcpy(bufor + addr::AKCJA_KEYEVENT, w->bajty[ke], 8);
        else
            // Awaryjnie: same zera. To NIE jest zgadywanie — tyle wpisuje gra
            // w swoim wlasnym miejscu budowania tej struktury
            // (`0x141806FDB mov dword ptr [rbp+0x1F],1`, czyli KeyEvent=1
            // i trzy kolejne bajty zerowe, oraz `[rbp+0x23]=0`).
            memset(bufor + addr::AKCJA_KEYEVENT, 0, 8);
        bufor[addr::AKCJA_KEYEVENT] = keyEvent;
        return true;
    };

    const int32_t przed = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);

    // ── stopien 1: ProcessExternalInputAction ──
    int32_t po147 = przed;
    if (gniazdoSensowne((void*)sm, addr::SLOT_PROCESS_EXTERNAL,
                        "ProcessExternalInputAction") && zbuduj()) {
        using PodajFn = void(__fastcall*)(void*, void*);
        ((PodajFn)vt[addr::SLOT_PROCESS_EXTERNAL])((void*)sm, bufor);
        po147 = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);
        InterlockedIncrement(&g_kanalPodane);
    }

    // ── stopien 2: pelna sciezka wejscia gry ──
    //
    // UWAGA: w gniezdzie 150 siedzi juz NASZ podsluch, wiec nie wolno pytac
    // `gniazdoSensowne`, czy gniazdo wskazuje kod gry — wskazuje nasza
    // biblioteke i odpowiedz brzmialaby „nie wolam". Sprawdzamy wiec cel
    // WLASCIWY: oryginal zapamietany przy zakladaniu haka. Ten sam blad
    // (skan tablicy metod widzi nasze latki, nie kod gry) zjadl juz raz
    // `vtable-diff.py` — zasada 20.
    int32_t po150 = po147;
    bool probowano150 = false;
    if (po147 == przed) {
        WejscieFn cel = (WejscieFn)vt[addr::SLOT_INPUT_HANDLER];
        if (cel == &thunkWejscie) cel = g_origWejscie;   // omijamy wlasny hak
        const uintptr_t celA = (uintptr_t)cel;
        const bool celOk = celA >= g_bazaModulu && celA < g_bazaModulu + 0x08000000;
        static bool zgloszone = false;
        if (!zgloszone) {
            zgloszone = true;
            logLine("KANAL: gniazdo %d (wejscie) -> 0x%llX  %s",
                    addr::SLOT_INPUT_HANDLER,
                    (unsigned long long)(celOk ? celA - g_bazaModulu + 0x140000000 : celA),
                    celOk ? "wyglada na kod gry" : "POZA MODULEM — nie wolam");
        }
        if (celOk && zbuduj()) {
            probowano150 = true;
            cel((void*)sm, bufor);
            po150 = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);
            zwolnijDefinicje(g_bazaModulu, bufor);  // gniazdo 150 nie zwalnia samo
        }
    }

    if (g_kanalPodane <= 16)
        logLine("KANAL: akcja[%d] KeyEvent=%d  stan %d -> po147=%d%s  "
                "(InputStates=%d, wzorzec=%s)",
                indeksWejscia, (int)keyEvent, (int)przed, (int)po147,
                probowano150 ? (po150 != po147 ? " -> gniazdo150 ZADZIALALO"
                                               : " -> gniazdo150 tez nic")
                             : "",
                (int)*(const int32_t*)(sm + addr::SM_INPUT_STATES + 8),
                wzorDla(*(const uint32_t*)def, false) ? "jest" : "BRAK");
}

// Stan, ktory ostatnio ustawilismy dla danej maszyny — zeby wysylac tylko
// ZMIANY i zeby kazde wcisniecie mialo swoje puszczenie.
struct PamiecStanu { uintptr_t sm; bool run; bool crouch; };
static PamiecStanu g_pamiec[8] = {};

static PamiecStanu* pamiecDla(uintptr_t sm)
{
    for (auto& p : g_pamiec) if (p.sm == sm) return &p;
    for (auto& p : g_pamiec) if (!p.sm) { p.sm = sm; return &p; }
    return nullptr;
}

// ── STEROWANIE MASZYNA JEJ WLASNYM API PRZEJSC ──────────────────────────────
//
// Dlaczego to, a nie podanie akcji: pomiar 18:34 pokazal, ze akcja dociera
// idealnie (bajty z podsluchu, `InputStates=10`) i **nic nie robi**, bo ze
// stanu `Idle` nie ma przejscia do `Running`. Trzeba przejsc przez `Walking`.
//
// Nadal nie podrabiamy mechaniki: podajemy grze JEJ WLASNE nazwy przejsc JEJ
// WLASNA funkcja, a o tym, czy przejscie dojdzie do skutku, decyduje jej
// maszyna (przejscia maja warunki i my ich nie omijamy).
static uintptr_t g_ufAddTransition = 0;   // AddTransitionToQueue(Name)
static uintptr_t g_ufGetStateByTag = 0;   // GetStateByTag(Tag) -> Object
static uintptr_t g_ufUpdateWarunku = 0;   // UpdateCustomConditionBool(Tag, bool)
static uint64_t  g_tagRuchu = 0;          // State.Condition.Player.HasMovementInput
static volatile LONG g_warunkowUstawionych = 0;
static volatile LONG g_przejscZakolejkowanych = 0;
static volatile LONG g_przejscUdanych = 0;

// Znacznik -> indeks stanu, rozwiazany WLASNA funkcja gry. Pamiec podreczna,
// bo rozwiazanie idzie przez `ProcessEvent`, a to nie jest darmowe.
struct TagNaStan { uintptr_t sm; uint64_t tag; int stan; };
static TagNaStan g_tagi[32] = {};

static int indeksStanuPoTagu(uintptr_t sm, uint64_t tag)
{
    if (!tag) return -1;
    for (auto& t : g_tagi)
        if (t.sm == sm && t.tag == tag) return t.stan;
    if (!g_ufGetStateByTag) return -1;
    if (!gniazdoSensowne((void*)sm, addr::SLOT_PROCESS_EVENT, "ProcessEvent")) return -1;

    struct { uint64_t tag; uintptr_t wynik; } par = { tag, 0 };
    auto** vt = *(void***)sm;
    using PEFn = void(__fastcall*)(void*, void*, void*);
    ((PEFn)vt[addr::SLOT_PROCESS_EVENT])((void*)sm, (void*)g_ufGetStateByTag, &par);

    int znaleziony = -1;
    if (sensownyWsk(par.wynik)) {
        const uintptr_t dane = *(const uintptr_t*)(sm + addr::SM_STATES);
        const int32_t n = *(const int32_t*)(sm + addr::SM_STATES + 8);
        if (sensownyWsk(dane) && n > 0 && n <= 32)
            for (int i = 0; i < n; ++i)
                if (*(const uintptr_t*)(dane + (uintptr_t)i * 8) == par.wynik) { znaleziony = i; break; }
    }
    for (auto& t : g_tagi)
        if (!t.sm) { t.sm = sm; t.tag = tag; t.stan = znaleziony; break; }
    return znaleziony;
}

// ── JEDEN FAKT, KTOREGO SERWER NIE MOZE ZOBACZYC SAM ────────────────────────
//
// Zmierzone 19:0x: przejscie `IdleToWalking` ma zero warunkow wejsciowych
// i DWA warunki wlasne, ktore gra nazywa sama:
//
//   State.Condition.Player.HasMovementInput
//   State.Condition.Player.IsOnGround
//
// Drugi serwer wylicza sam (wie, czy pionek stoi na ziemi). Pierwszego
// wyliczyc NIE MOZE — wejscie gracza zdalnego istnieje tylko tam, gdzie
// siedzi czlowiek (sciana #2). Dlatego pionek klienta nie wychodzi z `Idle`,
// a skoro nie wchodzi w `Walking`, to nie ma szans wejsc w `Running` —
// bo z `Idle` do `Running` nie prowadzi zadne przejscie.
//
// To jest DRUGIE (i mam nadzieje ostatnie) miejsce w calym modzie, w ktorym
// przesylamy FAKT zamiast ponownie uruchomic kod gry. Uzasadnienie jest to
// samo co przy kanale: to informacja, ktorej serwer nie ma skad wziac, a nie
// mechanika, ktora podrabiamy. Ustawiamy JEDEN warunek, wlasna funkcja gry
// (`UpdateCustomConditionBool`), a wszystkie decyzje — czy przejscie
// nastapi, ktore, i co z tego wyniknie — zostaja przy maszynie stanow.
//
// Znacznika NIE wpisujemy z palca: czytamy go z warunkow przejscia
// `IdleToWalking` w danych samej gry. Jedyne, co rozpoznajemy po nazwie, to
// KTORY z dwoch warunkow jest tym od wejscia — i to jest tu jedyne miejsce
// oparte na nazwie, wiec jest wypisane wprost, zeby nie zginelo.
static bool znajdzTagRuchu(uintptr_t base, uintptr_t sm)
{
    if (g_tagRuchu) return true;
    const uintptr_t we = *(const uintptr_t*)(sm + addr::SM_STATE_ENTRIES);
    const int32_t n = *(const int32_t*)(sm + addr::SM_STATE_ENTRIES + 8);
    if (!sensownyWsk(we) || n <= 0 || n > 32) return false;
    char nz[128];
    for (int i = 0; i < n; ++i) {
        const uintptr_t e = we + (uintptr_t)i * addr::ENTRY_ROZMIAR;
        const uintptr_t td = *(const uintptr_t*)(e + addr::ENTRY_TRANS_FROM);
        const int32_t tn = *(const int32_t*)(e + addr::ENTRY_TRANS_FROM + 8);
        if (!sensownyWsk(td) || tn <= 0 || tn > 64) continue;
        for (int j = 0; j < tn; ++j) {
            const uintptr_t t = td + (uintptr_t)j * addr::TRANS_ROZMIAR;
            const uintptr_t wd = *(const uintptr_t*)(t + addr::TRANS_WAR_WLASNE);
            const int32_t wn = *(const int32_t*)(t + addr::TRANS_WAR_WLASNE + 8);
            if (!sensownyWsk(wd) || wn <= 0 || wn > 16) continue;
            for (int k = 0; k < wn; ++k) {
                const uintptr_t w = wd + (uintptr_t)k * addr::WARUNEK_ROZMIAR;
                const uint64_t tag = *(const uint64_t*)w;
                if (!nazwaFName(base, (uint32_t)tag, nz, sizeof nz)) continue;
                if (!strstr(nz, "MovementInput")) continue;
                g_tagRuchu = tag;
                logLine("KANAL: znacznik wejscia ruchu = %s (z warunkow przejscia)", nz);
                return true;
            }
        }
    }
    return false;
}

static void ustawWarunekRuchu(uintptr_t base, uintptr_t sm, bool ma)
{
    if (!g_ufUpdateWarunku || !znajdzTagRuchu(base, sm)) return;
    if (!gniazdoSensowne((void*)sm, addr::SLOT_PROCESS_EVENT, "ProcessEvent")) return;
#pragma pack(push, 1)
    struct { uint64_t tag; unsigned char wartosc; } par;
#pragma pack(pop)
    par.tag = g_tagRuchu;
    par.wartosc = ma ? 1 : 0;
    auto** vt = *(void***)sm;
    using PEFn = void(__fastcall*)(void*, void*, void*);
    ((PEFn)vt[addr::SLOT_PROCESS_EVENT])((void*)sm, (void*)g_ufUpdateWarunku, &par);
    InterlockedIncrement(&g_warunkowUstawionych);
}

// Magazynek trzymanej broni pionka zdalnego. Maszyna stanow siedzi w postaci
// pod `+0x968`, wiec z niej wracamy do postaci przez `Outer` — komponenty maja
// swojego aktora jako obiekt nadrzedny.
using TrzymanaBronFn = void*(__fastcall*)(void*);
namespace addr {
constexpr uintptr_t NapelnijMagazynek_OFF = 0x1B242F0;   // void(DimensionWeapon*)
}
// `TrzymanaBron_OFF` jest juz zdefiniowane nizej, przy latce predkosci —
// tam ma swoje uzasadnienie pomiarowe, wiec nie dublujemy go tutaj.
namespace addr { constexpr uintptr_t TrzymanaBronKanal_OFF = 0x1874570; }
// Definicje nizej, przy haku amunicji — tu tylko zapowiedzi, zeby kanal mogl
// z nich skorzystac bez przenoszenia calej sekcji.
using NapelnijFn = void(__fastcall*)(void*);
extern bool g_fixAmmoWlaczony;
extern thread_local bool g_wNapelnianiu;

static uintptr_t g_naprawioneBronie[8] = {};
static int       g_naprawProby[8] = {};

void naprawMagazynekPostaci(uintptr_t base, uintptr_t postac);
void naprawMagazynekPostaci(uintptr_t base, uintptr_t postac)
{
    if (!g_fixAmmoWlaczony || !base || !sensownyWsk(postac)) return;

    const uintptr_t fb = base + addr::TrzymanaBronKanal_OFF;
    const uintptr_t fn = base + addr::NapelnijMagazynek_OFF;
    if (fb >= base + 0x08000000 || fn >= base + 0x08000000) return;

    void* bron = ((TrzymanaBronFn)fb)((void*)postac);
    if (!bron || !sensownyWsk((uintptr_t)bron)) return;

    int* proby = nullptr;
    for (int i = 0; i < 8; ++i) {
        if (g_naprawioneBronie[i] == (uintptr_t)bron) { proby = &g_naprawProby[i]; break; }
        if (!g_naprawioneBronie[i]) {
            g_naprawioneBronie[i] = (uintptr_t)bron;
            g_naprawProby[i] = 0;
            proby = &g_naprawProby[i];
            break;
        }
    }
    if (!proby || *proby >= 5) return;
    ++*proby;

    char nazwaBroni[128] = "?";
    const uintptr_t kl = *(const uintptr_t*)((uintptr_t)bron + UOBJ_CLASS_OFF);
    if (sensownyWsk(kl)) nazwaObiektu(base, kl, nazwaBroni, sizeof nazwaBroni);

    g_wNapelnianiu = true;
    ((NapelnijFn)fn)(bron);
    g_wNapelnianiu = false;

    logLine("AMUNICJA: napelniam trzymana bron pionka zdalnego (%d/5) — %s",
            *proby, nazwaBroni);
}

// Przejscia wychodzace ze stanu — wprost z danych maszyny.
struct Krawedz { int cel; uint64_t nazwa; };

static int krawedzieZe(uintptr_t sm, int stan, Krawedz* out, int maks)
{
    const uintptr_t we = *(const uintptr_t*)(sm + addr::SM_STATE_ENTRIES);
    const int32_t n = *(const int32_t*)(sm + addr::SM_STATE_ENTRIES + 8);
    if (!sensownyWsk(we) || stan < 0 || stan >= n || n > 32) return 0;
    const uintptr_t e = we + (uintptr_t)stan * addr::ENTRY_ROZMIAR;
    const uintptr_t td = *(const uintptr_t*)(e + addr::ENTRY_TRANS_FROM);
    const int32_t tn = *(const int32_t*)(e + addr::ENTRY_TRANS_FROM + 8);
    if (!sensownyWsk(td) || tn <= 0 || tn > 64) return 0;
    int ile = 0;
    for (int i = 0; i < tn && ile < maks; ++i) {
        const uintptr_t t = td + (uintptr_t)i * addr::TRANS_ROZMIAR;
        const uint64_t cel = *(const uint64_t*)(t + addr::TRANS_TARGET_TAG);
        const int idx = indeksStanuPoTagu(sm, cel);
        if (idx < 0) continue;
        out[ile].cel = idx;
        out[ile].nazwa = *(const uint64_t*)(t + addr::TRANS_NAME);
        ++ile;
    }
    return ile;
}

// Zakolejkowanie jednego przejscia po nazwie + przerobienie kolejki tym samym
// gniazdem, ktorego uzywa gra na koncu obslugi wejscia.
static void zakolejkujPrzejscie(uintptr_t sm, uint64_t nazwa)
{
    if (!g_ufAddTransition) return;
    if (!gniazdoSensowne((void*)sm, addr::SLOT_PROCESS_EVENT, "ProcessEvent")) return;
    auto** vt = *(void***)sm;
    using PEFn = void(__fastcall*)(void*, void*, void*);
    uint64_t par = nazwa;
    ((PEFn)vt[addr::SLOT_PROCESS_EVENT])((void*)sm, (void*)g_ufAddTransition, &par);
    InterlockedIncrement(&g_przejscZakolejkowanych);

    const uintptr_t cel = (uintptr_t)vt[addr::SLOT_PROCESS_TRANSITIONS];
    if (cel >= g_bazaModulu && cel < g_bazaModulu + 0x08000000) {
        using TickFn = void(__fastcall*)(void*);
        ((TickFn)cel)((void*)sm);
    }
}

// Doprowadzenie maszyny do stanu docelowego. Przeglad wszerz po grafie
// przejsc — graf ma szesc stanow, wiec to jest tanie, a przy okazji ogolne:
// nie wpisujemy zadnej sciezki na sztywno.
static bool prowadzDoStanu(uintptr_t base, uintptr_t sm, int cel, char* opisOut, size_t cap)
{
    (void)base;
    if (opisOut && cap) opisOut[0] = 0;
    for (int krok = 0; krok < 4; ++krok) {
        const int teraz = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);
        if (teraz == cel) return true;

        // przeglad wszerz: skad da sie dojsc do celu
        int poprzednik[8];
        bool odwiedzony[8] = {};
        for (auto& p : poprzednik) p = -1;
        int kolejka[8], glowa = 0, ogon = 0;
        if (teraz < 0 || teraz >= 8) return false;
        kolejka[ogon++] = teraz;
        odwiedzony[teraz] = true;
        bool jest = false;
        while (glowa < ogon && !jest) {
            const int u = kolejka[glowa++];
            Krawedz kr[16];
            const int ile = krawedzieZe(sm, u, kr, 16);
            for (int i = 0; i < ile; ++i) {
                const int v = kr[i].cel;
                if (v < 0 || v >= 8 || odwiedzony[v]) continue;
                odwiedzony[v] = true;
                poprzednik[v] = u;
                if (v == cel) { jest = true; break; }
                if (ogon < 8) kolejka[ogon++] = v;
            }
        }
        if (!jest) return false;

        // pierwszy krok sciezki (cofamy sie od celu do stanu biezacego)
        int v = cel;
        while (poprzednik[v] != teraz && poprzednik[v] >= 0) v = poprzednik[v];
        if (poprzednik[v] != teraz) return false;

        // Wszystkie przejscia prowadzace tam, po kolei — o tym, ktore z nich
        // gra przyjmie, decyduja JEJ warunki, nie my.
        Krawedz kr[16];
        const int ile = krawedzieZe(sm, teraz, kr, 16);
        bool ruszylo = false;
        for (int i = 0; i < ile && !ruszylo; ++i) {
            if (kr[i].cel != v) continue;
            zakolejkujPrzejscie(sm, kr[i].nazwa);
            if (*(const int32_t*)(sm + addr::SM_CURRENT_IDX) != teraz) ruszylo = true;
        }
        if (opisOut && cap) {
            const size_t uz = strlen(opisOut);
            _snprintf_s(opisOut + uz, cap - uz, _TRUNCATE, "%s%d->%d%s",
                        uz ? " " : "", teraz, v, ruszylo ? "" : "(nie)");
        }
        if (!ruszylo) return false;
        InterlockedIncrement(&g_przejscUdanych);
    }
    return *(const int32_t*)(sm + addr::SM_CURRENT_IDX) == cel;
}

static void ustawStanNaSerwerze(uintptr_t base, uintptr_t sm, int indeksStanu)
{
    char nz[128];
    bool run = false, crouch = false;
    if (!stanNaAkcje(base, sm, indeksStanu, &run, &crouch, nz, sizeof nz)) return;

    PamiecStanu* p = pamiecDla(sm);
    if (!p) return;

    // KROK 1 — podanie akcji. Samo w sobie stanu nie zmienia (zmierzone 18:34),
    // ale pelna sciezka wejscia gry zapisuje „co jest trzymane" do tablicy
    // `+0x2F8` (`0x1417A8A20`), a warunki wejsciowe przejsc czytaja wlasnie ja.
    // Czyli to nie jest juz proba naprawy, tylko przygotowanie warunku.
    if (p->run != run) {
        const int a = indeksAkcji(base, sm, "Run");
        if (a >= 0) podajAkcje(sm, a, run ? KEY_PRESSED : KEY_RELEASED);
        p->run = run;
    }
    if (p->crouch != crouch) {
        const int a = indeksAkcji(base, sm, "Crouch");
        if (a >= 0) podajAkcje(sm, a, crouch ? KEY_PRESSED : KEY_RELEASED);
        p->crouch = crouch;
    }

    // KROK 1b — magazynek trzymanej broni. Wyzwalacz oparty na obserwowaniu
    // zapisow ZAWIODL (przebieg 19:11): trzymany HandCannon klienta nie
    // dostaje zapisu `CurrentAmmoInClip` ani razu, wiec nie bylo na co czekac.
    // Bierzemy wiec bron wprost z pionka — WLASNA funkcja gry `0x141874570`,
    // ta sama, ktorej uzywa `GetMaxSpeed`, zeby zapytac o trzymana bron —
    // i wolamy na niej wlasne napelnianie gry. Sufit prob jest po broni,
    // wiec gdy magazynek juz jest pelny, przestajemy po kilku wywolaniach.
    naprawMagazynekPostaci(base, *(const uintptr_t*)(sm + UOBJ_OUTER_OFF));

    // KROK 2 — jedyny fakt, ktorego serwer nie ma skad wziac: czy zdalny
    // gracz TRZYMA wejscie ruchu. Bez tego warunek `HasMovementInput` jest
    // falszem i przejscie `IdleToWalking` nie ma prawa zajsc — a bez `Walking`
    // nie ma drogi do `Running`.
    ustawWarunekRuchu(base, sm, indeksStanu != 0);

    // KROK 3 — doprowadzenie maszyny do stanu, w ktorym jest klient.
    const int32_t przed = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);
    char droga[96] = "";
    const bool ok = prowadzDoStanu(base, sm, indeksStanu, droga, sizeof droga);
    const int32_t po = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);

    if (InterlockedIncrement(&g_kanalOdebrane) <= 20)
        logLine("KANAL: odebrany stan [%d] %s -> Run=%d Crouch=%d | maszyna %d -> %d %s"
                "  droga: %s  (warunek ruchu ustawiony %ld razy)",
                indeksStanu, nz, (int)run, (int)crouch, (int)przed, (int)po,
                ok ? "OSIAGNIETY" : "nie doszla", droga[0] ? droga : "(brak)",
                g_warunkowUstawionych);
}

// Przechwycenie RPC uzytego za transport. Wartosci ponizej progu to prawdziwe
// wywolania gry — oddajemy je nietkniete.
static void __fastcall thunkKanal(void* ctx, void* stos, void* wynik)
{
    if (g_fixStateWlaczony && g_bazaModulu && stos) {
        const uintptr_t locals = *(const uintptr_t*)((uintptr_t)stos + addr::FFRAME_LOCALS);
        if (sensownyWsk(locals)) {
            const float v = *(const float*)locals;
            if (v >= addr::KANAL_BAZA - 1.0f) {
                // Kierunek zabezpieczony: sterujemy WYLACZNIE kopia gracza
                // zdalnego. Gdyby to samo wywolanie wrocilo u nadawcy, nic sie
                // nie stanie — jego wlasna postac ma `DimensionLocalPlayer`.
                const uintptr_t postac = (uintptr_t)ctx;
                if (sensownyWsk(postac) && pionekZdalny(g_bazaModulu, postac)) {
                    const uintptr_t sm =
                        *(const uintptr_t*)(postac + addr::CHAR_STATE_MACHINE);
                    if (sensownyWsk(sm))
                        ustawStanNaSerwerze(g_bazaModulu, sm,
                                            (int)(v - addr::KANAL_BAZA + 0.5f));
                }
                return;                       // nasze — nie oddajemy grze
            }
        }
    }
    if (g_origKanal) g_origKanal(ctx, stos, wynik);
}

// Wysylka z klienta: `ProcessEvent(UFunction, &float)`. Wolamy przez GNIAZDO,
// bo `AActor` ma wlasne nadpisanie `ProcessEvent` — pod stalym adresem
// omineloby sie logike aktora.
static void wyslijStan(uintptr_t postac, int indeksStanu)
{
    if (!g_ufuncKanal) return;
    if (!gniazdoSensowne((void*)postac, addr::SLOT_PROCESS_EVENT, "ProcessEvent")) return;
    auto** vt = *(void***)postac;
    float wartosc = addr::KANAL_BAZA + (float)indeksStanu;
    using PEFn = void(__fastcall*)(void*, void*, void*);
    ((PEFn)vt[addr::SLOT_PROCESS_EVENT])((void*)postac, (void*)g_ufuncKanal, &wartosc);
    InterlockedIncrement(&g_kanalWyslane);
}

// Zalozenie podsluchu prawdziwego wejscia na gniezdzie 150 (opis mechanizmu
// i po co to jest — przy `thunkWejscie` wyzej).
//
// Hak zaklada sie na tablicy metod WZORCA klasy (`Default__...`), wiec dziala
// dla wszystkich egzemplarzy tej klasy. Oryginal, ktory zapisujemy i logujemy,
// mowi przy okazji, ktora z trzech tablic metod maszyny stanow tu trafila:
//   0x141800F20  bazowa `DimensionStateMachineComponent`
//   0x141800D30  posrednia
//   0x14183D720  najbardziej pochodna — TA obsluguje prawdziwe wejscie gracza
// Jesli w logu bedzie inna niz `0x14183D720`, to znaczy, ze wzorzec, ktorego
// szukamy po nazwie, nie jest klasa faktycznie uzywanej maszyny stanow —
// i wtedy cisza w logu ma inne znaczenie niz „gracz nic nie nacisnal".
static bool patchPodsluchWejscia(uintptr_t base)
{
    const uintptr_t tabObj = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tabObj;
    const int32_t ile    = *(const int32_t*)(tabObj + 0x14);
    const int32_t nchunk = *(const int32_t*)(tabObj + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    uintptr_t cdo = 0;
    char nazwa[128];
    for (int32_t ci = 0; ci < nchunk && !cdo; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;
            if (strcmp(nazwa, "Default__DimensionPlayerStateMachineComponent") == 0) {
                cdo = obj; break;
            }
        }
    }
    if (!cdo) { logLine("WEJSCIE-PODSLUCH: nie znalazlem wzorca maszyny stanow"); return false; }

    auto** vt = *(WejscieFn**)cdo;
    if (!vt) return false;
    const uintptr_t cel = (uintptr_t)vt[addr::SLOT_INPUT_HANDLER];
    if (cel < base || cel >= base + 0x08000000) {
        logLine("WEJSCIE-PODSLUCH: gniazdo %d wskazuje 0x%llX — poza modulem",
                addr::SLOT_INPUT_HANDLER, (unsigned long long)cel);
        return false;
    }
    DWORD stare = 0;
    void* gniazdo = (void*)&vt[addr::SLOT_INPUT_HANDLER];
    if (!VirtualProtect(gniazdo, 8, PAGE_READWRITE, &stare)) return false;
    g_origWejscie = vt[addr::SLOT_INPUT_HANDLER];
    vt[addr::SLOT_INPUT_HANDLER] = &thunkWejscie;
    VirtualProtect(gniazdo, 8, stare, &stare);
    logLine("WEJSCIE-PODSLUCH: hak na gniazdo %d zalozony (oryginal 0x%llX)",
            addr::SLOT_INPUT_HANDLER,
            (unsigned long long)(cel - base + 0x140000000));
    return true;
}

static bool patchKanalStanu(uintptr_t base)
{
    const uintptr_t tab = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tab;
    const int32_t ile    = *(const int32_t*)(tab + 0x14);
    const int32_t nchunk = *(const int32_t*)(tab + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    char nazwa[128], nazwaKl[128], nazwaWl[128];
    bool znalazlemTransport = false;
    for (int32_t ci = 0; ci < nchunk; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
            if (!nazwaObiektu(base, klasa, nazwaKl, sizeof nazwaKl)) continue;
            if (strcmp(nazwaKl, "Function") != 0) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;

            // Dwie funkcje maszyny stanow — do sterowania nia jej wlasnym API.
            // Szukamy ich w tym samym przejsciu tablicy, bo przejscie 280 tys.
            // obiektow jest drogie i nie ma powodu robic go trzy razy.
            if (strcmp(nazwa, "AddTransitionToQueue") == 0 ||
                strcmp(nazwa, "GetStateByTag") == 0 ||
                strcmp(nazwa, "UpdateCustomConditionBool") == 0) {
                const uintptr_t wl2 = *(const uintptr_t*)(obj + UOBJ_OUTER_OFF);
                if (sensownyWsk(wl2) && nazwaObiektu(base, wl2, nazwaWl, sizeof nazwaWl)
                    && strcmp(nazwaWl, "DimensionStateMachineComponent") == 0) {
                    if      (nazwa[0] == 'A') g_ufAddTransition = obj;
                    else if (nazwa[0] == 'G') g_ufGetStateByTag = obj;
                    else                      g_ufUpdateWarunku = obj;
                    logLine("KANAL: znalazlem UFunction %s (0x%llX)",
                            nazwa, (unsigned long long)obj);
                }
                continue;
            }

            if (strcmp(nazwa, "ServerSetInversedScreenRatio") != 0) continue;
            const uintptr_t wl = *(const uintptr_t*)(obj + UOBJ_OUTER_OFF);
            if (!sensownyWsk(wl) || !nazwaObiektu(base, wl, nazwaWl, sizeof nazwaWl)) continue;
            if (strcmp(nazwaWl, "DimensionPlayerCharacter") != 0) continue;

            g_ufuncKanal = obj;
            auto* gniazdo = (FNativeFunc*)(obj + addr::UFUNC_FUNC_OFF);
            g_origKanal = *gniazdo;
            *gniazdo = &thunkKanal;

            znalazlemTransport = true;
        }
    }

    if (znalazlemTransport) {
        logLine("KANAL: transport gotowy — UFunction 0x%llX, oryginal 0x%llX;"
                " AddTransitionToQueue=%s GetStateByTag=%s",
                (unsigned long long)g_ufuncKanal,
                (unsigned long long)((uintptr_t)g_origKanal - base + 0x140000000),
                g_ufAddTransition ? "jest" : "BRAK",
                g_ufGetStateByTag ? "jest" : "BRAK");
        return true;
    }
    logLine("KANAL: nie znalazlem UFunction ServerSetInversedScreenRatio");
    return false;
}

// Strona klienta: pilnujemy WLASNEJ postaci i wysylamy przy zmianie stanu.
// `Role == 2` (AutonomousProxy) znaczy „jestem klientem w sesji" — u hosta
// jego wlasna postac ma `Role == 3` i ta funkcja nic nie robi. To jej wlasna
// proba kontrolna: licznik wyslanych ma u hosta zostac na zerze.
static void kanalTick(uintptr_t base)
{
    if (!g_fixStateWlaczony || !g_ufuncKanal || !g_jestemKlientem) return;

    // Wlasna postac ZAPAMIETANA. Ta funkcja idzie z watku gry przy KAZDEJ
    // klatce, a przejscie tablicy obiektow to 280 tysiecy wpisow — robienie
    // tego 60 razy na sekunde poloczyloby gre. Szukamy wiec rzadko i tylko
    // wtedy, gdy nie mamy waznego wskaznika.
    //
    // Wskaznik przestaje byc wazny po respawnie albo zmianie mapy, dlatego
    // sprawdzamy go tanio przy kazdym wejsciu: rola musi byc nadal 2, a klasa
    // musi sie zgadzac. Gdy przestanie — szukamy jeszcze raz.
    static uintptr_t postacCache = 0;
    static int odKiedyNieSzukalem = 0;
    static int ostatniStan = -2;

    if (postacCache) {
        // Tu odczyt spod `+0xF0` i `+0x968` jest bezpieczny, bo wskaznik
        // pochodzi ze skanu, ktory juz potwierdzil klase obiektu.
        const bool wazna =
            sensownyWsk(postacCache) &&
            *(const unsigned char*)(postacCache + ACTOR_ROLE_OFF) == 2 &&
            sensownyWsk(*(const uintptr_t*)(postacCache + addr::CHAR_STATE_MACHINE));
        if (!wazna) { postacCache = 0; ostatniStan = -2; }
    }
    // Szukanie wlasnej postaci — TYLKO gdy nie mamy zapamietanej, i nie czesciej
    // niz raz na 120 klatek (okolo dwoch sekund). Zaraz po dolaczeniu postaci
    // jeszcze nie ma, wiec bez tego ograniczenia przemielalibysmy cala tablice
    // obiektow w kazdej klatce, dopoki sie nie pojawi.
    if (!postacCache) {
        if (--odKiedyNieSzukalem > 0) return;
        odKiedyNieSzukalem = 120;

        const uintptr_t tab = base + addr::GUObjectArray_OFF + 0x10;
        const uintptr_t chunks = *(const uintptr_t*)tab;
        const int32_t ile    = *(const int32_t*)(tab + 0x14);
        const int32_t nchunk = *(const int32_t*)(tab + 0x1C);
        if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return;

        char nazwaKl[128];
        for (int32_t ci = 0; ci < nchunk && !postacCache; ++ci) {
            const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
            if (!sensownyWsk(blok)) continue;
            int32_t tu = ile - ci * 65536;
            if (tu > 65536) tu = 65536;
            if (tu <= 0) break;
            for (int32_t i = 0; i < tu; ++i) {
                const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
                if (!sensownyWsk(obj)) continue;
                // Rola 2 (AutonomousProxy) = „to moj pionek, ale nie ja jestem
                // serwerem". U hosta jego wlasna postac ma role 3, wiec ta
                // funkcja u niego nigdy nic nie wysle — i to jest jej proba
                // kontrolna.
                // KOLEJNOSC TU NIE JEST KOSMETYCZNA — to poprawka po awarii.
                //
                // Pierwsza wersja zaczynala od odczytu roli sieciowej spod
                // `obj+0xF0`. Robila to dla KAZDEGO obiektu w tablicy, a wiekszosc
                // `UObject` jest znacznie mniejsza niz 0xF1 bajtow: odczyt
                // wychodzil poza koniec obiektu i przy trafieniu w koniec strony
                // wywalal gre. Padly tak obie instancje (host 16:27, klient 16:36),
                // za kazdym razem z ramkami w naszej bibliotece.
                //
                // Teraz zaczynamy od `obj+0x10` (wskaznik klasy), ktore lezy
                // w naglowku KAZDEGO `UObject`, i dopiero po potwierdzeniu klasy
                // siegamy glebiej. Przy okazji jest to tansze: nazwe klasy
                // rozwiazujemy raz na obiekt, a glebokie odczyty robimy dla
                // garstki.
                const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
                if (!sensownyWsk(klasa)) continue;
                if (!nazwaObiektu(base, klasa, nazwaKl, sizeof nazwaKl)) continue;
                if (strncmp(nazwaKl, "BPDimensionPlayerCharacter", 26) != 0) continue;
                if (!dziedziczyPo(base, klasa, "DimensionPlayerCharacter")) continue;
                if (!nazwaObiektu(base, obj, nazwaKl, sizeof nazwaKl)) continue;
                if (strncmp(nazwaKl, "Default__", 9) == 0) continue;
                // Dopiero teraz wiadomo, ze obiekt jest postacia gracza, wiec
                // wolno czytac pola lezace gleboko w jej ukladzie.
                if (*(const unsigned char*)(obj + ACTOR_ROLE_OFF) != 2) continue;
                if (!sensownyWsk(*(const uintptr_t*)(obj + addr::CHAR_STATE_MACHINE))) continue;
                postacCache = obj;
                ostatniStan = -2;
                logLine("KANAL: znalazlem wlasna postac %s (0x%llX)",
                        nazwaKl, (unsigned long long)obj);
                break;
            }
        }
        if (!postacCache) return;
    }

    const uintptr_t sm = *(const uintptr_t*)(postacCache + addr::CHAR_STATE_MACHINE);
    const int stan = *(const int32_t*)(sm + addr::SM_CURRENT_IDX);
    if (stan == ostatniStan) return;
    ostatniStan = stan;

    // Wysylamy tylko wtedy, gdy zmienia sie to, co serwer ma ustawic. Przejscia
    // `Idle <-> Walking` zdarzaja sie przy kazdym kroku i nie nios zadnej
    // informacji — bez tego filtra zalalibysmy pewny kanal RPC kilkudziesiecioma
    // pakietami na sekunde.
    static bool ostRun = false, ostCrouch = false;
    bool run = false, crouch = false;
    char nz[128];
    if (!stanNaAkcje(base, sm, stan, &run, &crouch, nz, sizeof nz)) return;
    if (run == ostRun && crouch == ostCrouch) return;
    ostRun = run; ostCrouch = crouch;

    wyslijStan(postacCache, stan);
    if (g_kanalWyslane <= 12)
        logLine("KANAL: wyslany stan [%d] %s -> Run=%d Crouch=%d (wyslanych razem %ld)",
                stan, nz, (int)run, (int)crouch, g_kanalWyslane);
}

// ── KTO WPISUJE AMUNICJE DO MAGAZYNKA ───────────────────────────────────────
//
// Problem: trzymana bron dolaczajacego gracza ma na serwerze
// `CurrentAmmoInClip = 0` przy zapasie 90. Bron ma przy tym KOMPLET pieciu
// zdolnosci (z `AbilityWeaponLoadAmmo_C`), wiec „brak zdolnosci" odpada.
//
// Dwa tropy juz zamkniete na zrzucie obrazu (WIEDZA.md §3d):
//   - `0x141B242F0` to ZACISK, nie napelnianie: zapisuje
//     `min(CurrentAmmo, min(CurrentAmmoInClip, ClipSize))`, wiec przy zerze
//     wpisuje z powrotem zero,
//   - literal „RefillAmmo Invalid Player." to cialo komendy CHEATU.
//
// Zamiast szukac dalej po kodzie — pytamy grę, KTO naprawde wpisuje szostke.
// Wszystkie zapisy atrybutow ida przez jedno gniazdo tablicy metod ASC
// (offset `0x5A0`, ustalone z `0x141B243BB call qword ptr [rdi+0x5a0]`), wiec
// jeden hak lapie wszystkie.
//
// Nazwa atrybutu nie jest zgadywana: pierwszym polem `FGameplayAttribute` jest
// `FString AttributeName`, co ustalone na globalnych kluczach uzywanych przez
// funkcje limitow ruchu. Napis jest szeroki (UTF-16), a dlugosc liczy znak
// konca — stad tani filtr wstepny po samej dlugosci, jeszcze przed czytaniem
// znakow. To wazne, bo przez to gniazdo przechodza takze zdrowie, stamina
// i cala reszta, kilkadziesiat razy na sekunde.
//
// Sygnatura ustalona z miejsca wywolania: rcx = ASC, rdx = FGameplayAttribute*,
// xmm2 = nowa wartosc. Wynik jest bezpieczny do pominiecia — sprawdzone: na 38
// miejsc wywolania ZADNE nie uzywa xmm0 po powrocie.
//
// SPOSOB UZYCIA (zasada 12 — instancja solo to wzorzec): najpierw grac SOLO
// i strzelac oraz przeladowywac. Lista adresow powrotu z solo jest wzorcem;
// dopiero potem porownac ja z lista dla broni dolaczajacego gracza i zobaczyc,
// ktorego adresu BRAKUJE. To jest miejsce awarii.
namespace addr {
constexpr int SLOT_SET_ATTRYBUT = 180;   // offset 0x5A0
}

// Spis stosu lezy nizej (przy haku `SetOwner`, gdzie powstal) — tu tylko
// zapowiedz, zeby hak amunicji mogl go uzyc bez przenoszenia kodu.
static void spisStosu(uintptr_t sp, char* out, size_t cap, int ile);

using SetAttrFn = void(__fastcall*)(void*, void*, float);
static SetAttrFn     g_origSetAttr = nullptr;
static bool          g_logAmmo = false;
static volatile LONG g_ammoIle = 0;

// Zgloszone pary (adres powrotu, ASC) — kazda pokazujemy RAZ. Chodzi o LISTE
// MIEJSC, a nie o strumien wywolan; bez tego log zalalby sie powtorkami tej
// samej linijki kodu.
//
// POPRAWKA po przebiegu 18:34: klucz musi zawierac ASC, nie sam adres powrotu.
// Przy dolaczeniu klienta licznik zapisow podskoczyl z 2 na 4 — czyli bron
// klienta DOSTALA swoje dwa zapisy — ale zaden nie trafil do logu, bo adresy
// powrotu byly juz zgloszone dla broni HOSTA. Odsiew po samym adresie mowil
// wiec „nic nowego" tam, gdzie zdarzylo sie dokladnie to, o co pytamy.
struct ZnanyZapis { uintptr_t powrot; uintptr_t asc; };
static ZnanyZapis g_ammoZnane[48] = {};

// ── NAPRAWA MAGAZYNKA (marker `WFCoop_fix_ammo.txt`) ────────────────────────
//
// Zmierzone 18:53, dwaj gracze, jeden przebieg:
//
//   host   CurrentAmmoInClip = 6   (wolajacy 0x141B243C1)
//   klient CurrentAmmoInClip = 0   (wolajacy 0x141B243C1)   <- TEN SAM kod
//
// Czyli napelnianie magazynka DZIALA takze dla broni dolaczajacego gracza —
// tylko liczy zero. A stan pozniejszy pokazuje, dlaczego to zero zostaje
// na zawsze:
//
//   bron klienta:  ClipSize=6  CurrentAmmoInClip=0  CurrentAmmo=90
//
// Zapas JEST. Magazynek zostal zerem, bo `0x141B242F0` policzylo
// `min(dostepne, ClipSize)` w chwili, gdy zapasu jeszcze nie bylo — i nic
// tego nie powtorzylo. To ten sam ksztalt co przy mapie atrybutow ruchu
// (`fix_attrs`): kolejnosc, ktora zawsze wychodzi dla jedynego gracza, nie
// wychodzi dla drugiego.
//
// Naprawa jest wiec ta sama: wolamy `0x141B242F0` — WLASNA funkcje gry, ta
// sama, ktora dziala u hosta — dopiero wtedy, gdy zapas juz jest. Zadnej
// podstawionej liczby; magazynek napelnia gra, po swojemu.
//
// Wyzwalacz jest sam objawem: podgladamy zapisy atrybutow i pamietamy dla
// kazdego ASC ostatnia znana pare (magazynek, zapas). Gdy magazynek jest
// zerem, a zapas dodatni — powtarzamy napelnienie. Nie trzeba do tego znac
// offsetow zestawu atrybutow: wartosci biora sie z obserwowanych zapisow.
namespace addr {
constexpr uintptr_t ASC_OWNER_ACTOR       = 0x3D0;       // -> bron
}

bool                 g_fixAmmoWlaczony = false;
static volatile LONG g_ammoNapraw = 0;

struct StanAmuna { uintptr_t asc; float clip; float zapas; int prob; bool wClip, wZapas; };
static StanAmuna g_stanAmuna[16] = {};
thread_local bool g_wNapelnianiu = false;

static StanAmuna* stanDla(uintptr_t asc)
{
    for (auto& s : g_stanAmuna) if (s.asc == asc) return &s;
    for (auto& s : g_stanAmuna) if (!s.asc) { s.asc = asc; return &s; }
    return nullptr;
}

// `nz` to nazwa atrybutu z zapisu, `v` jego nowa wartosc.
//
// POPRAWKA po przebiegu 19:03: pierwszy wyzwalacz czekal, az zobaczy przez ten
// sam hak ZAPIS zapasu — i nie doczekal sie ani razu. Zapas trzymanej broni
// klienta wynosi 90, ale przez gniazdo 180 nigdy nie przechodzi; wpisuje go
// co innego (najpewniej inicjalizacja zestawu atrybutow). Czyli wyzwalacz
// opieral sie na zalozeniu, ktorego nie sprawdzilem — i cisza w logu znaczyla
// „nie doczekalem sie", a nie „objawu nie ma".
//
// Teraz wyzwalaczem jest sam objaw i nic wiecej: zobaczylismy zapis
// `CurrentAmmoInClip = 0`, wiec zapamietujemy te bron i powtarzamy JEJ WLASNE
// napelnianie kilka razy w odstepach. Nie czytamy zapasu — bo do tego trzeba
// by znac offset w zestawie atrybutow, a ten jest w dokumentacji niepewny.
// Decyzje, ile naboi wlozyc (i czy w ogole), podejmuje funkcja gry. Jesli
// zapasu jeszcze nie ma, wpisze zero drugi raz i nic sie nie stanie.
//
// Sprawdzian jest wbudowany: napelnienie idzie tym samym gniazdem, wiec jego
// skutek zobaczymy w logu jako kolejny zapis `CurrentAmmoInClip`.
static void mozeNapelnijMagazynek(uintptr_t base, void* asc, const char* nz, float v)
{
    if (!g_fixAmmoWlaczony || g_wNapelnianiu || !base) return;
    if (strlen(nz) != 17) return;                   // tylko `CurrentAmmoInClip`
    if (v > 0.5f) return;                           // napelniony — nie ma objawu

    StanAmuna* s = stanDla((uintptr_t)asc);
    if (!s) return;
    s->clip = v;
    s->wClip = true;                                // „ta bron czeka na powtorke"
}

// Powtorka napelniania — z watku gry, nie z haka. Rozdzielenie jest celowe:
// w chwili zapisu zera zapasu zwykle jeszcze nie ma, wiec natychmiastowa
// powtorka policzylaby to samo zero.
static void tikNapelniania(uintptr_t base)
{
    if (!g_fixAmmoWlaczony || !base) return;
    static int odliczanie = 0;
    if (--odliczanie > 0) return;
    odliczanie = 120;                               // mniej wiecej dwie sekundy

    const uintptr_t f = base + addr::NapelnijMagazynek_OFF;
    if (f < base || f >= base + 0x08000000) return;

    for (auto& s : g_stanAmuna) {
        if (!s.asc || !s.wClip || s.prob >= 5) continue;
        const uintptr_t bron = *(const uintptr_t*)(s.asc + addr::ASC_OWNER_ACTOR);
        if (!sensownyWsk(bron)) continue;
        ++s.prob;

        char nazwaBroni[128] = "?";
        const uintptr_t kl = *(const uintptr_t*)(bron + UOBJ_CLASS_OFF);
        if (sensownyWsk(kl)) nazwaObiektu(base, kl, nazwaBroni, sizeof nazwaBroni);

        g_wNapelnianiu = true;             // napelnienie pisze tym samym
        ((NapelnijFn)f)((void*)bron);      // gniazdem, wiec bez tego weszlibysmy
        g_wNapelnianiu = false;            // sami w siebie

        logLine("AMUNICJA: POWTORZONE napelnienie (%d/5) dla %s"
                "  [napraw razem: %ld]  — skutek widac jako kolejny zapis",
                s.prob, nazwaBroni, InterlockedIncrement(&g_ammoNapraw));
        s.wClip = false;                   // czekamy, co wpisze gra
    }
}

static bool nazwaAtrybutu(void* attr, char* out, size_t cap)
{
    const uintptr_t p = *(const uintptr_t*)attr;
    const int32_t dlugosc = *(const int32_t*)((uintptr_t)attr + 8);
    // Tani filtr: „CurrentAmmoInClip" ma 17 znakow, „CurrentAmmo" 11 —
    // a dlugosc w `FString` liczy jeszcze znak konca.
    if (dlugosc != 18 && dlugosc != 12) return false;
    if (!sensownyWsk(p) || (size_t)dlugosc >= cap) return false;
    const wchar_t* w = (const wchar_t*)p;
    for (int i = 0; i < dlugosc - 1; ++i) {
        if (w[i] < 32 || w[i] > 126) return false;
        out[i] = (char)w[i];
    }
    out[dlugosc - 1] = 0;
    return strncmp(out, "CurrentAmmo", 11) == 0;
}

static void __fastcall thunkSetAttr(void* asc, void* attr, float v)
{
    if (g_logAmmo && g_bazaModulu && sensownyWsk((uintptr_t)attr)) {
        char nz[64];
        if (nazwaAtrybutu(attr, nz, sizeof nz)) {
            const uintptr_t powrot = (uintptr_t)__builtin_return_address(0);
            // Kazdy adres powrotu pokazujemy RAZ — chodzi o LISTE MIEJSC,
            // nie o strumien wywolan. Gdy tablica sie zapelni, przestajemy
            // logowac zamiast logowac wszystko: inaczej po 24 roznych miejscach
            // kazde kolejne wywolanie otwieraloby plik logu, co przy dziesiatkach
            // zapisow na sekunde zabiloby plynnosc.
            bool nowy = false;
            for (auto& z : g_ammoZnane) {
                if (z.powrot == powrot && z.asc == (uintptr_t)asc) break;
                if (!z.powrot) {
                    z.powrot = powrot; z.asc = (uintptr_t)asc; nowy = true; break;
                }
            }
            if (nowy) {
                // Czyja to bron — po obiekcie nadrzednym ASC.
                char wl[128] = "?";
                const uintptr_t outer = *(const uintptr_t*)((uintptr_t)asc + UOBJ_OUTER_OFF);
                if (sensownyWsk(outer)) nazwaObiektu(g_bazaModulu, outer, wl, sizeof wl);
                // Sam adres powrotu nie odroznia DWOCH SCIEZEK, ktore prowadza
                // do `0x141B242F0` (`0x1418CAAC0` oraz `0x1418D3290` — ta druga
                // to droga komendy cheatu `RefillAmmo`). Bez spisu stosu nie da
                // sie powiedziec, KTOREJ z nich brakuje u dolaczajacego gracza,
                // a to jest cale pytanie w sprawie amunicji.
                char stos[220] = "";
                uintptr_t rsp = 0;
                __asm__ volatile ("mov %%rsp, %0" : "=r"(rsp));
                spisStosu(rsp, stos, sizeof stos, 6);
                logLine("AMUNICJA: %s = %.0f   dla %s   (wolajacy 0x%llX)  [%ld]\n"
                        "          stos: %s",
                        nz, v, wl,
                        (unsigned long long)(powrot - g_bazaModulu + 0x140000000),
                        InterlockedIncrement(&g_ammoIle), stos);
            } else {
                InterlockedIncrement(&g_ammoIle);
            }
        }
    }
    if (g_origSetAttr) g_origSetAttr(asc, attr, v);

    // Naprawa magazynka PO oddaniu zapisu grze — inaczej powtorne napelnienie
    // policzyloby stan sprzed tego zapisu.
    if (g_fixAmmoWlaczony && g_bazaModulu && sensownyWsk((uintptr_t)attr)) {
        char nz[64];
        if (nazwaAtrybutu(attr, nz, sizeof nz))
            mozeNapelnijMagazynek(g_bazaModulu, asc, nz, v);
    }
}

static bool patchAmmoLog(uintptr_t base)
{
    const uintptr_t tabObj = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tabObj;
    const int32_t ile    = *(const int32_t*)(tabObj + 0x14);
    const int32_t nchunk = *(const int32_t*)(tabObj + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    uintptr_t cdo = 0;
    char nazwa[128];
    for (int32_t ci = 0; ci < nchunk && !cdo; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;
            if (strcmp(nazwa, "Default__DimensionAbilitySystemComponent") == 0) {
                cdo = obj;
                break;
            }
        }
    }
    if (!cdo) { logLine("AMUNICJA: nie znalazlem wzorca DimensionAbilitySystemComponent"); return false; }

    auto** vt = *(SetAttrFn**)cdo;
    if (!vt) { logLine("AMUNICJA: wzorzec bez tablicy metod"); return false; }
    const uintptr_t cel = (uintptr_t)vt[addr::SLOT_SET_ATTRYBUT];
    if (cel < base || cel >= base + 0x08000000) {
        logLine("AMUNICJA: gniazdo %d wskazuje 0x%llX — POZA MODULEM, nie latam",
                addr::SLOT_SET_ATTRYBUT, (unsigned long long)cel);
        return false;
    }

    DWORD stare = 0;
    void* gniazdo = (void*)&vt[addr::SLOT_SET_ATTRYBUT];
    if (!VirtualProtect(gniazdo, 8, PAGE_READWRITE, &stare)) {
        logLine("AMUNICJA: VirtualProtect nieudany"); return false;
    }
    g_origSetAttr = vt[addr::SLOT_SET_ATTRYBUT];
    vt[addr::SLOT_SET_ATTRYBUT] = &thunkSetAttr;
    VirtualProtect(gniazdo, 8, stare, &stare);
    logLine("AMUNICJA: hak na zapis atrybutu zalozony (gniazdo %d, oryginal 0x%llX)",
            addr::SLOT_SET_ATTRYBUT,
            (unsigned long long)(cel - base + 0x140000000));
    return true;
}

// ── SCIANA #4: SERWER NIE RUSZA PIONKIEM ZDALNEGO GRACZA ────────────────────
//
// Objaw: klient „rusza sie o milimetr i wraca". Zmierzone po obu stronach naraz:
// klient rozpedza sie u siebie do 270, serwerowa kopia jego postaci ma predkosc
// 0,0 i nie drga w zadnej osi, mimo ze `ServerMovePacked` dochodzi 53 razy na
// sekunde (licznik dobil do 475 tysiecy).
//
// Przyczyna, znaleziona pulapka sprzetowa na zapis (`tools/pulapka-zapisu.py`)
// i porownaniem tablic metod (`tools/vtable-diff.py`):
//
//   0x1436DB7DB  Acceleration = 2000        ; z RPC, dociera POPRAWNIE
//   0x1436DB7EF  call [rax+0x6F8]           ; GetMaxAcceleration() gry -> 0
//   0x1436DB7FF  jae ...                    ; limit ~0 => gałąź zerujaca
//                Acceleration = 0
//   ... a dalej tak samo ginie predkosc:
//   0x1436D0AD9  Velocity = 39.43           ; policzona poprawnie
//   0x1436D0BAE  Velocity = 0.00            ; przycieta do limitu = 0
//
// Czyli DWA nadpisania gry zwracaja ZERO dla pionka, ktory na serwerze nie jest
// sterowany lokalnie. To czwarte wystapienie wzorca z WIEDZA.md §4.
//
// Probka kontrolna, ktora to rozstrzygnela: host przechodzi przez DOKLADNIE te
// same instrukcje, tylko u niego predkosc po przycieciu zostaje (20.44 -> 20.44),
// a u pionka klienta ginie (39.43 -> 0.00).
//
// Przejsciowki na tych dwoch gniazdach zostaly: wolaja oryginal, oddaja jego
// wynik nietkniety i sluza wylacznie pomiarowi (`log_speed`) oraz naprawie
// mapy atrybutow wlasnym kodem gry (`fix_attrs`).
namespace addr {
constexpr int SLOT_GET_MAX_SPEED = 130;   // wolane przy przycinaniu predkosci
constexpr int SLOT_GET_MAX_ACCEL = 223;   // wolane z [rax+0x6F8]
constexpr uintptr_t COMP_CHARACTER_OWNER = 0x148;  // potwierdzone refleksja
constexpr uintptr_t COMP_MAX_WALK_SPEED  = 0x18C;
}

using FloatFn = float(__fastcall*)(void*);

static FloatFn       g_origMaxSpeed = nullptr;
static FloatFn       g_origMaxAccel = nullptr;

// ── DIAGNOSTYKA ZEROWEGO LIMITU ─────────────────────────────────────────────
//
// Po co osobno od latki: latka `fix_move` podstawia wartosc i zostala odrzucona.
// Ale samo miejsce jest dobre na POMIAR — thunk stoi dokladnie tam, gdzie gra
// policzyla zero, wiec moze w tej samej chwili odczytac, co bylo tego przyczyna.
//
// Co czytamy: podreczna mape atrybutow ruchu (`komponent+0xB18`). Z niej czytaja
// wszystkie funkcje limitow (sprawdzone skanem odwolan na zrzucie obrazu), wiec
// jej rozmiar w chwili zera rozstrzyga miedzy „bufor pusty" a „bufor pelny,
// a zero bierze sie skadinad".
//
// Dlaczego to musi byc hak, a nie odczyt z zewnatrz: pojedynczy odczyt mapy
// z zewnatrz dal raz zero i raz 19 (10.08, dwa przebiegi) — bo trafial w
// przypadkowa chwile, w tym w rozbiorke pionka. Hak trafia w moment OBJAWU.
namespace addr {
constexpr uintptr_t COMP_MAPA_ILE   = 0xB20;  // Num mapy atrybutow ruchu
constexpr uintptr_t COMP_MAPA_WOLNE = 0xB4C;  // NumFreeIndices — gra testuje `Num == to`
// Postac bierzemy spod `+0x130`, bo DOKLADNIE stad bierze ja sama gra
// (`mov rbx,[rcx+0x130]` w `GetMaxSpeed` i w predykatach znacznikow).
constexpr uintptr_t COMP_POSTAC     = 0x130;

// Predykaty gry rozstrzygajace o zerze — nazwane po literalach w ich wnetrzu.
// Wolamy JE SAME zamiast odtwarzac ich logike: to znaczniki rozgrywki, a ich
// pojemniki (`komponent+0xB68` i `+0xB78`) mialyby caly wlasny uklad do
// odgadniecia. Funkcje sa czystymi zapytaniami, bez skutkow ubocznych.
constexpr uintptr_t BlockedNormal_OFF  = 0x178AE70;  // "Status.Movement.Blocked.Normal"
constexpr uintptr_t BlockedWalk_OFF    = 0x178B930;  // "Status.Movement.Blocked.Walk"
constexpr uintptr_t BlockedRunning_OFF = 0x178B5E0;  // "Status.Movement.Blocked.Running"
constexpr uintptr_t TrzymanaBron_OFF   = 0x1874570;  // postac -> trzymana bron albo NULL

// Wlasna synchronizacja gry: „dla kazdego atrybutu z listy `komponent+0xB88`
// wpisz do podrecznej mapy wynik `GetNumericAttribute` z ASC". Wolana przez
// `DimensionMovementComponent::OnOwnerAbilitySystemLoad` (0x141C43740).
// Rozpoznana po literale `&UDimensionMovementComponent::OnAttributeUpdate`
// w jej ogonie — tam rejestruje delegata na zmiany atrybutow.
constexpr uintptr_t SyncAtrybutow_OFF  = 0x178E6E0;
}

using PredykatFn = unsigned char(__fastcall*)(void*);
using BronFn     = void*(__fastcall*)(void*);
using SyncFn     = void(__fastcall*)(void*);

static bool          g_logSpeed = false;
static bool          g_predykatyOk = false;   // czy wolno wolac funkcje gry
static void*         g_znaneKomp[8] = {};
static volatile LONG g_zeraKomp[8] = {};

// Adresy funkcji gry sprawdzamy PROLOGIEM, zanim je zawolamy. Wywolanie zlego
// adresu wywroci gre bez sladu w logu, a offsety pochodza z jednego builda.
// Wzorce wziete z deasemblacji zrzutu obrazu, nie z pamieci.
static bool sprawdzPredykaty(uintptr_t base)
{
    struct { uintptr_t off; const unsigned char* wzor; size_t ile; const char* nazwa; } lista[] = {
        { addr::BlockedNormal_OFF,  (const unsigned char*)"\x40\x53\x57\x48\x83\xEC\x28", 7, "Blocked.Normal" },
        { addr::BlockedWalk_OFF,    (const unsigned char*)"\x40\x53\x57\x48\x83\xEC\x28", 7, "Blocked.Walk" },
        { addr::BlockedRunning_OFF, (const unsigned char*)"\x48\x89\x5C\x24\x18\x55\x56\x57", 8, "Blocked.Running" },
        { addr::TrzymanaBron_OFF,   (const unsigned char*)"\x48\x89\x5C\x24\x08\x57\x48\x83\xEC\x20", 10, "TrzymanaBron" },
        { addr::SyncAtrybutow_OFF,  (const unsigned char*)"\x48\x89\x4C\x24\x08\x55\x56", 7, "SyncAtrybutow" },
    };
    for (auto& p : lista) {
        if (memcmp((const void*)(base + p.off), p.wzor, p.ile) != 0) {
            logLine("LIMIT: prolog %s pod 0x%llX INNY niz oczekiwany — nie wolam funkcji gry",
                    p.nazwa, (unsigned long long)(0x140000000ull + p.off));
            return false;
        }
    }
    logLine("LIMIT: prologi %d funkcji gry zgodne — moge je wolac",
            (int)(sizeof lista / sizeof *lista));
    return true;
}

// Czy to pionek hosta, czy dolaczonego gracza. Bez tego log nie odroznia
// dwoch komponentow, bo obiekty maja te sama klase.
static const char* czyjKomponent(uintptr_t base, uintptr_t comp)
{
    const uintptr_t postac = *(const uintptr_t*)(comp + addr::COMP_CHARACTER_OWNER);
    if (!sensownyWsk(postac)) return "?";
    const uintptr_t pc = *(const uintptr_t*)(postac + addr::CHAR_CONTROLLER);
    if (!sensownyWsk(pc)) return "bez kontrolera";
    const uintptr_t gracz = *(const uintptr_t*)(pc + addr::PC_PLAYER);
    if (!sensownyWsk(gracz)) return "bez Player";
    const uintptr_t klasa = *(const uintptr_t*)(gracz + UOBJ_CLASS_OFF);
    char n[128];
    if (!sensownyWsk(klasa) || !nazwaObiektu(base, klasa, n, sizeof n)) return "?";
    return strcmp(n, "DimensionLocalPlayer") == 0 ? "HOST" : "KLIENT";
}

static void zglosZero(void* comp, const char* ktora, float v)
{
    if (!g_logSpeed || !g_bazaModulu) return;
    int gniazdo = -1;
    for (int i = 0; i < 8; ++i) {
        if (g_znaneKomp[i] == comp) { gniazdo = i; break; }
        if (!g_znaneKomp[i]) { g_znaneKomp[i] = comp; gniazdo = i; break; }
    }
    if (gniazdo < 0) return;
    const LONG ile = InterlockedIncrement(&g_zeraKomp[gniazdo]);
    // Logujemy PIERWSZE wystapienie dla kazdego komponentu (zeby cisza znaczyla
    // „nie bylo zera") i potem co 600., zeby widziec, czy stan sie zmienia.
    if (ile != 1 && ile % 600 != 0) return;
    const uintptr_t c = (uintptr_t)comp;
    const uintptr_t b = g_bazaModulu;

    const int32_t mapaIle   = *(const int32_t*)(c + addr::COMP_MAPA_ILE);
    const int32_t mapaWolne = *(const int32_t*)(c + addr::COMP_MAPA_WOLNE);
    logLine("LIMIT: %s = %.3f  komponent %s (0x%llX)  wystapienie %ld", ktora, v,
            czyjKomponent(b, c), (unsigned long long)c, ile);
    logLine("LIMIT:    mapa atrybutow ruchu: %d wpisow, wolnych %d%s   MaxWalkSpeed=%.1f",
            mapaIle, mapaWolne,
            mapaIle == mapaWolne ? "  <-- PUSTA wg testu gry" : "",
            *(const float*)(c + addr::COMP_MAX_WALK_SPEED));
    if (!g_predykatyOk) return;

    // Ktora galaz dala zero — pytamy o to KODEM GRY, nie odtwarzaniem logiki.
    // `GetMaxSpeed` zwraca zero wprost, gdy `Status.Movement.Blocked.Walk` jest
    // ustawiony (`0x14177F93F  xorps xmm6,xmm6`); pozostale dwa znaczniki
    // decyduja, ktora sciezka w ogole zostanie wybrana.
    const auto blkNormal  = (PredykatFn)(b + addr::BlockedNormal_OFF);
    const auto blkWalk    = (PredykatFn)(b + addr::BlockedWalk_OFF);
    const auto blkRunning = (PredykatFn)(b + addr::BlockedRunning_OFF);
    const auto bronPostaci = (BronFn)(b + addr::TrzymanaBron_OFF);
    const uintptr_t postac = *(const uintptr_t*)(c + addr::COMP_POSTAC);
    void* bron = sensownyWsk(postac) ? bronPostaci((void*)postac) : nullptr;

    char nazwaBroni[128] = "NULL (sciezka domyslna)";
    if (bron) {
        const uintptr_t kl = *(const uintptr_t*)((uintptr_t)bron + UOBJ_CLASS_OFF);
        if (!kl || !nazwaObiektu(b, kl, nazwaBroni, sizeof nazwaBroni))
            strcpy_s(nazwaBroni, "?");
    }

    logLine("LIMIT:    Blocked.Normal=%u  Blocked.Walk=%u  Blocked.Running=%u"
            "   trzymana bron: %s",
            (unsigned)blkNormal(comp), (unsigned)blkWalk(comp),
            (unsigned)blkRunning(comp), nazwaBroni);
}

// ── NAPRAWA RUCHU: ponowna synchronizacja podrecznej mapy atrybutow ─────────
//
// Zmierzone (przebieg 01:11, host na wyprawie, probka kontrolna w tym samym
// procesie): serwerowa kopia postaci klienta ma w podrecznej mapie atrybutow
// ruchu TRZYNASCIE z dziewietnastu wpisow wyzerowanych, przy poprawnych
// wartosciach w samym ASC:
//
//   atrybut                    host    kopia klienta      ASC klienta
//   Acceleration               2000    0                  2000
//   MovementModifier           1.0     0                  —
//   SprintSpeed                800     0                  800
//   NormalSpeed                615     615                —
//
// `MovementModifier` mnozy wynik, wiec zeruje OBIE sciezki predkosci naraz —
// i to sie zgadza z logiem: zero pada tak samo bez broni (sciezka domyslna),
// jak i z bronia. Znaczniki blokady sa przy tym wszystkie zerowe, wiec
// hipoteza „Blocked.Walk" odpada.
//
// Czyli atrybuty sa dobre, a zepsuta jest tylko ICH PODRECZNA KOPIA: gra
// zbudowala ja, zanim atrybuty dolaczajacego gracza dostaly wartosci, a
// pozniejsze powiadomienia juz nie przyszly.
//
// NIE PODSTAWIAMY WARTOSCI. Wolamy `0x14178E6E0` — WLASNA funkcje gry, ktora
// przechodzi po jej wlasnej liscie atrybutow (`komponent+0xB88`, 19 pozycji
// takich samych u obu graczy) i wpisuje do mapy wynik `GetNumericAttribute`
// z ASC. To jest ta sama praca, ktora gra wykonuje przy
// `OnOwnerAbilitySystemLoad` — tylko wykonana wtedy, gdy dane juz sa.
//
// Petla wypelniajaca jest idempotentna (znajdz-albo-dodaj, potem nadpisz),
// a rejestracja delegata na koncu w najgorszym razie zapisze go drugi raz —
// procedura obslugi tylko przepisuje wartosc, wiec powtorka nic nie zmienia.
//
// Wyzwalaczem jest SAM OBJAW: zerowy limit. Najwyzej piec razy na komponent,
// zeby ewentualna powtorka byla widoczna w liczniku, a nie zapetlila sie.
static bool          g_fixAttrsWlaczony = false;
static void*         g_syncKomp[8] = {};
static LONG          g_syncIle[8] = {};
static volatile LONG g_syncRazem = 0;

static void odswiezAtrybuty(void* comp, const char* ktora, float przed)
{
    if (!g_fixAttrsWlaczony || !g_predykatyOk || !g_bazaModulu) return;
    int gniazdo = -1;
    for (int i = 0; i < 8; ++i) {
        if (g_syncKomp[i] == comp) { gniazdo = i; break; }
        if (!g_syncKomp[i]) { g_syncKomp[i] = comp; gniazdo = i; break; }
    }
    if (gniazdo < 0 || g_syncIle[gniazdo] >= 5) return;
    ++g_syncIle[gniazdo];
    InterlockedIncrement(&g_syncRazem);

    ((SyncFn)(g_bazaModulu + addr::SyncAtrybutow_OFF))(comp);

    // Dowod skutku: ten sam oryginal pytany raz jeszcze, zaraz po odswiezeniu.
    const float po = (strcmp(ktora, "GetMaxSpeed") == 0)
                         ? (g_origMaxSpeed ? g_origMaxSpeed(comp) : 0.0f)
                         : (g_origMaxAccel ? g_origMaxAccel(comp) : 0.0f);
    logLine("ATRYBUTY: odswiezone (%d/5) dla komponentu %s (0x%llX) — %s przed=%.3f po=%.3f",
            g_syncIle[gniazdo], czyjKomponent(g_bazaModulu, (uintptr_t)comp),
            (unsigned long long)(uintptr_t)comp, ktora, przed, po);
}

static float __fastcall thunkMaxSpeed(void* comp)
{
    // Dowod, ze hak zyje (zasada 14): bez tego cisza w logu znaczylaby naraz
    // „zera nie bylo" i „przejsciowka nie stoi w tablicy metod".
    static volatile LONG pierwsze = 0;
    if (g_logSpeed && InterlockedIncrement(&pierwsze) == 1)
        logLine("LIMIT: przejsciowka GetMaxSpeed zyje (pierwsze wywolanie)");

    const float v = g_origMaxSpeed ? g_origMaxSpeed(comp) : 0.0f;

    // Naprawa magazynka wisi TUTAJ, a nie na kanale stanu ruchu. Powod jest
    // pomiarem, nie gustem: kanal wysyla tylko przy zmianie sprintu albo
    // kucania, wiec gracz, ktory po prostu chodzi, nigdy by jej nie wyzwolil.
    // Ten hak odpala sie dla pionka zdalnego bez przerwy, a komponent ruchu ma
    // swoja postac jako obiekt nadrzedny — czyli mamy do niej darmowa droge.
    // Rzadko, bo `naprawMagazynekPostaci` wola kod gry.
    if (g_fixAmmoWlaczony && g_bazaModulu && comp) {
        static volatile LONG licznik = 0;
        if ((InterlockedIncrement(&licznik) % 300) == 0
            && strcmp(czyjKomponent(g_bazaModulu, (uintptr_t)comp), "KLIENT") == 0)
            naprawMagazynekPostaci(g_bazaModulu,
                                   *(const uintptr_t*)((uintptr_t)comp + UOBJ_OUTER_OFF));
    }

    if (v > 1.0f) {
        // Probkowanie limitu NIEZEROWEGO — do sprawy szarpania. Po naprawie mapy
        // atrybutow obie strony maja te same liczby, a mimo to serwer i klient
        // licza rozne predkosci w biegu (zmierzone: 510 kontra 332). Roznica
        // musi wiec siedziec w STANIE postaci, nie w atrybutach, a limit zwrocony
        // przez serwer mowi wprost, ktora galez zostala wybrana:
        //   355 chod | 615 normalna | 800 sprint  (x0,83 gdy stamina nadwatlona)
        // Rzadko, zeby nie zalac logu: co 600. wywolanie dla danego komponentu.
        if (g_logSpeed) {
            static volatile LONG licznik = 0;
            if (InterlockedIncrement(&licznik) % 600 == 0 && g_bazaModulu) {
                const char* czyj = czyjKomponent(g_bazaModulu, (uintptr_t)comp);
                if (strcmp(czyj, "HOST") != 0)   // interesuje nas pionek zdalny
                    logLine("LIMIT: GetMaxSpeed = %.1f dla komponentu %s (0x%llX)",
                            v, czyj, (unsigned long long)(uintptr_t)comp);
            }
        }
        return v;                                // gra policzyla sama — nie ruszamy
    }
    zglosZero(comp, "GetMaxSpeed", v);
    odswiezAtrybuty(comp, "GetMaxSpeed", v);
    return v;
}

static float __fastcall thunkMaxAccel(void* comp)
{
    const float v = g_origMaxAccel ? g_origMaxAccel(comp) : 0.0f;
    if (v > 1.0f) return v;
    zglosZero(comp, "GetMaxAcceleration", v);
    odswiezAtrybuty(comp, "GetMaxAcceleration", v);
    return v;
}

static bool patchRemoteMovement(uintptr_t base)
{
    // Tablica metod klasy — bierzemy ja ze wzorca klasy (CDO), bo tam na pewno
    // stoi ta sama, ktorej uzywaja wszystkie instancje.
    const uintptr_t tabObj = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tabObj;
    const int32_t ile     = *(const int32_t*)(tabObj + 0x14);
    const int32_t nchunk  = *(const int32_t*)(tabObj + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    uintptr_t cdo = 0;
    char nazwa[128];
    for (int32_t ci = 0; ci < nchunk && !cdo; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;
            if (strcmp(nazwa, "Default__DimensionMovementComponent") == 0) {
                cdo = obj;
                break;
            }
        }
    }
    if (!cdo) { logLine("RUCH: nie znalazlem wzorca DimensionMovementComponent"); return false; }

    auto** vt = *(FloatFn**)cdo;
    if (!vt) { logLine("RUCH: wzorzec bez tablicy metod"); return false; }

    DWORD stare = 0;
    void* obszar = (void*)&vt[addr::SLOT_GET_MAX_SPEED];
    if (!VirtualProtect(obszar, 8, PAGE_READWRITE, &stare)) {
        logLine("RUCH: VirtualProtect (predkosc) nieudany"); return false;
    }
    g_origMaxSpeed = vt[addr::SLOT_GET_MAX_SPEED];
    vt[addr::SLOT_GET_MAX_SPEED] = &thunkMaxSpeed;
    VirtualProtect(obszar, 8, stare, &stare);

    obszar = (void*)&vt[addr::SLOT_GET_MAX_ACCEL];
    if (!VirtualProtect(obszar, 8, PAGE_READWRITE, &stare)) {
        logLine("RUCH: VirtualProtect (przyspieszenie) nieudany"); return false;
    }
    g_origMaxAccel = vt[addr::SLOT_GET_MAX_ACCEL];
    vt[addr::SLOT_GET_MAX_ACCEL] = &thunkMaxAccel;
    VirtualProtect(obszar, 8, stare, &stare);

    logLine("RUCH: latka zdalnego ruchu zalozona (tablica metod 0x%llX, "
            "oryginaly: predkosc 0x%llX, przyspieszenie 0x%llX)",
            (unsigned long long)(uintptr_t)vt,
            (unsigned long long)(uintptr_t)g_origMaxSpeed,
            (unsigned long long)(uintptr_t)g_origMaxAccel);
    return true;
}

// ── KTO PRZYPISUJE BRON: log wywolan AActor::SetOwner ───────────────────────
//
// Po co: przy dolaczeniu klienta powstaje SZESC broni, z ktorych dwie trafiaja
// do kontrolera HOSTA, a dwie zostaja bez wlasciciela (zmierzone migawka
// `ue-snapshot.py`). Klient trzyma pusty egzemplarz, a ten z amunicja dostaje
// host. Trzeba znalezc kod, ktory to przypisuje.
//
// Dlaczego hak w procesie, a nie pulapka sprzetowa: pulapka na `SetOwner`
// zatrzymuje watek gry przy KAZDYM wywolaniu. Sprobowalem — 400 zatrzyman
// w trakcie dolaczania zamrozilo hosta i wywrocilo gre (awaria `fc5c66e3`,
// zapisana w PRZEBIEGI.md jako artefakt pomiaru). Hak zapisuje do logu i wraca,
// wiec nie zatrzymuje niczego.
//
// `SetOwner` jest wirtualne (gniazdo 139 — ustalone z deasemblacji przejsciowki
// skryptowej: `call qword ptr [rax+0x458]`). Podmieniamy gniazdo w tablicy metod
// klasy broni, a nie prolog funkcji — nie wymaga to relokacji instrukcji.
//
// Kluczowe jest logowanie ADRESU POWROTU: to on wskazuje funkcje, ktora
// przypisanie robi. Sama para (bron, wlasciciel) mowi „co", a nie „gdzie".
namespace addr {
constexpr int SLOT_SET_OWNER = 139;
}

using SetOwnerFn = void(__fastcall*)(void* aktor, void* wlasciciel);
static SetOwnerFn    g_origSetOwner = nullptr;
static bool          g_logOwnerWlaczony = false;
static volatile LONG g_logOwnerIle = 0;

// Lancuch obiektow nadrzednych spisany do jednego napisu. Funkcja gry
// `0x1418718E0` wybiera kontroler wlasnie chodzac po tym lancuchu, wiec to on
// rozstrzyga, KTORY gracz dostanie bron.
static void lancuchOuter(uintptr_t base, uintptr_t obj, char* out, size_t cap)
{
    out[0] = 0;
    size_t uz = 0;
    char n[128];
    for (int i = 0; i < 5 && sensownyWsk(obj) && uz + 4 < cap; ++i) {
        const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
        if (!sensownyWsk(klasa) || !nazwaObiektu(base, klasa, n, sizeof n)) break;
        const int w = _snprintf_s(out + uz, cap - uz, _TRUNCATE,
                                  i ? " < %s" : "%s", n);
        if (w <= 0) break;
        uz += (size_t)w;
        obj = *(const uintptr_t*)(obj + UOBJ_OUTER_OFF);
    }
    if (!out[0]) strcpy(out, "-");
}

// Spis stosu: kilka pierwszych wartosci, ktore wygladaja na adresy powrotu do
// modulu gry. Sam wolajacy mowi „kto to zrobil", a dopiero lancuch wyzej mowi,
// CO uruchomilo cala sekwencje.
//
// Nie jest to prawdziwe rozwijanie stosu (kod gry nie ma wskaznika ramki), wiec
// beda falszywe trafienia po starych ramkach — ale kolejnosc jest zachowana
// i to wystarcza do wskazania miejsca. Bez filtra „przed adresem stoi `call`"
// spis lapal adres lezacy ZA instrukcja `ret` i wyszedl z tego falszywy wniosek.
//
// `sp` bierze WOLAJACY — inaczej mierzylibysmy ramke tej funkcji, nie haka.
static void spisStosu(uintptr_t sp, char* out, size_t cap, int ile)
{
    out[0] = 0;
    size_t uz = 0;
    int zn = 0;
    for (uintptr_t a = sp; a < sp + 0x800 && zn < ile && uz + 20 < cap; a += 8) {
        const uintptr_t v = *(const uintptr_t*)a;
        if (v < 0x140000000ull || v >= 0x148000000ull) continue;
        const unsigned char* b = (const unsigned char*)v;
        const bool poCall =
            b[-5] == 0xE8 ||                                  // call rel32
            (b[-2] == 0xFF && (b[-1] & 0x38) == 0x10) ||      // call r/m (krotkie)
            (b[-3] == 0xFF && (b[-2] & 0x38) == 0x10) ||
            (b[-6] == 0xFF && (b[-5] & 0x38) == 0x10) ||      // call [rXX+disp32]
            (b[-7] == 0xFF && (b[-6] & 0x38) == 0x10);
        if (!poCall) continue;
        const int w = _snprintf_s(out + uz, cap - uz, _TRUNCATE,
                                  zn ? " < 0x%llX" : "0x%llX", (unsigned long long)v);
        if (w <= 0) break;
        uz += (size_t)w;
        ++zn;
    }
}

static void __fastcall thunkSetOwner(void* aktor, void* wlasciciel)
{
    // `rsi` wolajacego, przechwycone przed czymkolwiek innym. W `0x141903067`
    // gra wola nim funkcje wybierajaca kontroler, wiec to ten obiekt rozstrzyga
    // o przydziale. `rsi` jest rejestrem zachowywanym przez wolanego, wiec na
    // wejsciu ma jeszcze wartosc wolajacego. Traktujemy go jako PODEJRZANY:
    // jesli nie wyglada na obiekt, log to pokaze i nie bedzie z czego wnioskowac.
    uintptr_t rsiWolajacego = 0;
    __asm__ volatile ("mov %%rsi, %0" : "=r"(rsiWolajacego));
    // Adres powrotu = wolajacy. To jest wlasciwy cel tego pomiaru.
    void* powrot = __builtin_return_address(0);
    if (g_bazaModulu && InterlockedIncrement(&g_logOwnerIle) <= 60) {
        // Sama nazwa KLASY nie wystarcza: obaj gracze maja kontroler klasy
        // `DimensionPlayerController_C`, wiec pierwszy log nie rozstrzygal,
        // ktory z nich dostaje bron. Dlatego dokladamy WSKAZNIK i numer
        // instancji z FName — to razem wskazuje obiekt jednoznacznie.
        char nb[128] = "?", nw[128] = "-";
        const uintptr_t kl = aktor ? *(const uintptr_t*)((uintptr_t)aktor + UOBJ_CLASS_OFF) : 0;
        if (kl) nazwaObiektu(g_bazaModulu, kl, nb, sizeof nb);
        unsigned nrB = aktor ? *(const unsigned*)((uintptr_t)aktor + UOBJ_NAME_OFF + 4) : 0;
        unsigned nrW = 0;
        if (wlasciciel) {
            const uintptr_t kw = *(const uintptr_t*)((uintptr_t)wlasciciel + UOBJ_CLASS_OFF);
            if (!kw || !nazwaObiektu(g_bazaModulu, kw, nw, sizeof nw)) strcpy(nw, "?");
            nrW = *(const unsigned*)((uintptr_t)wlasciciel + UOBJ_NAME_OFF + 4);
        } else {
            strcpy(nw, "NULL");
        }
        char lanc[256];
        lancuchOuter(g_bazaModulu, rsiWolajacego, lanc, sizeof lanc);

        char stos[256] = "";
        {
            uintptr_t sp = 0;
            __asm__ volatile ("mov %%rsp, %0" : "=r"(sp));
            spisStosu(sp, stos, sizeof stos, 6);
        }
        logLine("WLASCICIEL: %s_%u (0x%llX) -> %s_%u (0x%llX)   (wolajacy 0x%llX)"
                "   wejscie=0x%llX [%s]",
                nb, nrB ? nrB - 1 : 0, (unsigned long long)(uintptr_t)aktor,
                nw, nrW ? nrW - 1 : 0, (unsigned long long)(uintptr_t)wlasciciel,
                (unsigned long long)((uintptr_t)powrot - g_bazaModulu + 0x140000000),
                (unsigned long long)rsiWolajacego, lanc);
        if (stos[0]) logLine("WLASCICIEL:    stos: %s", stos);
    }
    if (g_origSetOwner) g_origSetOwner(aktor, wlasciciel);
}

static bool patchSetOwnerLog(uintptr_t base)
{
    const uintptr_t tabObj = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tabObj;
    const int32_t ile    = *(const int32_t*)(tabObj + 0x14);
    const int32_t nchunk = *(const int32_t*)(tabObj + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    // Pierwsza wersja latala tablice metod `DimensionWeaponInstantHit`
    // i hak nie odpalil sie ANI RAZU. Powod: `BP_HandCannon_Medium_C` uzywa
    // INNEJ tablicy (0x1450C8F58 zamiast 0x1450C4CA8), bo dziedziczy po innej
    // klasie natywnej. Zalozenie „wszystkie bronie maja wspolna tablice" bylo
    // po prostu falszywe — dlatego teraz zbieramy WSZYSTKIE rozne tablice
    // wsrod zyjacych broni i latamy kazda.
    uintptr_t tablice[16] = {};
    int ileTablic = 0;
    for (int32_t ci = 0; ci < nchunk; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            const uintptr_t klasa = *(const uintptr_t*)(obj + UOBJ_CLASS_OFF);
            if (!sensownyWsk(klasa)) continue;
            if (!dziedziczyPo(base, klasa, "DimensionWeapon")) continue;
            const uintptr_t vt = *(const uintptr_t*)obj;
            if (!sensownyWsk(vt)) continue;
            bool mamy = false;
            for (int k = 0; k < ileTablic; ++k) if (tablice[k] == vt) { mamy = true; break; }
            if (!mamy && ileTablic < 16) tablice[ileTablic++] = vt;
        }
    }
    if (!ileTablic) { logLine("WLASCICIEL: nie znalazlem zadnej tablicy metod broni"); return false; }

    int zalozone = 0;
    for (int k = 0; k < ileTablic; ++k) {
        auto** vt = (SetOwnerFn*)tablice[k];
        DWORD stare = 0;
        void* gniazdo = (void*)&vt[addr::SLOT_SET_OWNER];
        if (!VirtualProtect(gniazdo, 8, PAGE_READWRITE, &stare)) continue;
        if (!g_origSetOwner) g_origSetOwner = vt[addr::SLOT_SET_OWNER];
        vt[addr::SLOT_SET_OWNER] = &thunkSetOwner;
        VirtualProtect(gniazdo, 8, stare, &stare);
        ++zalozone;
    }
    logLine("WLASCICIEL: log SetOwner zalozony na %d tablicach metod (oryginal 0x%llX)",
            zalozone, (unsigned long long)(uintptr_t)g_origSetOwner);
    return zalozone > 0;
}

// ── CO URUCHAMIA NAPELNIANIE EKWIPUNKU: hak na gniazdo 99 magazynu ─────────
//
// Problem: dolaczenie klienta uruchamia napelnianie ekwipunku DWA RAZY — raz
// dla magazynu klienta i raz dla magazynu HOSTA. Host dostaje przez to zbedny
// drugi komplet broni (w tym karabin z amunicja 28231) i to jest najlepszy
// kandydat na przyczyne znikajacej waluty i utraty widoku pierwszoosobowego.
//
// Czego brakowalo: KTO to uruchamia. Poprzednie dochodzenie utknelo na tym, ze
// skan `call rel32` do funkcji `0x141923AA0` daje ZERO wolajacych. Powod jest
// prosty i ustalony na zrzucie obrazu (`tools/obraz.py`): ten adres lezy
// dokladnie raz jako DANA, pod `0x145097118` — czyli jest wpisem w tablicy
// metod. Sprawdzenie, ktory zywy obiekt ma te tablice, wskazalo klase
// jednoznacznie:
//
//     tablica 0x145096E00 = UDimensionItemStorage, gniazdo 99 (offset 0x318)
//
// Wywolanie jest wiec wirtualne — dlatego skan kodu go nie widzial. Podmieniamy
// gniazdo we wzorcu klasy (CDO), tak jak przy `SetOwner`.
//
// Sygnatura ustalona z deasemblacji prologu, nie zgadnieta:
//     0x141923AC5  mov r14,rcx      ; magazyn
//     0x141923AD4  movzx ebx,dl     ; flaga (bool)
//     0x141923ADD  cmp bl,1 / jne <koniec>   ; przy zerze funkcja nic nie robi
// Argumenty 3 i 4 nie sa czytane — ich miejsca w cieniu stosu sluza za spill,
// wiec zwykla przejsciowka `__fastcall` o dwoch argumentach jest bezpieczna.
//
// Hak LOGUJE PIERWSZE WYWOLANIE, zeby cisza znaczyla „zjawisko nie zaszlo",
// a nie „hak siedzi w zlej tablicy" (zasada 14 z START-TUTAJ.md).
namespace addr {
constexpr int SLOT_STORAGE_LOAD = 99;      // offset 0x318
constexpr uintptr_t PC_PLAYER_OFF = 0x298; // APlayerController::Player
}

using StorageLoadFn = void(__fastcall*)(void*, unsigned char);
static StorageLoadFn g_origStorageLoad = nullptr;
static bool          g_logFillWlaczony = false;
static bool          g_fixDupWlaczony  = false;
static volatile LONG g_fillIle = 0;
static volatile LONG g_fillPominiete = 0;

// Czyj to magazyn — po obiekcie `Player` kontrolera. Sama nazwa klasy nie
// rozroznia graczy: obaj maja `DimensionPlayerController_C`. Rozstrzyga dopiero
// `DimensionLocalPlayer` (czlowiek przy tym procesie) kontra `IpConnection`
// (gracz po drugiej stronie sieci).
//
// UWAGA na `this`: gniazdo 99 nalezy do DRUGIEJ tablicy metod magazynu, ktora
// stoi pod `obiekt + 0x38` (dziedziczenie po interfejsie). Metoda dostaje wiec
// wskaznik przesuniety — zmierzone: hak zobaczyl 0x4E3A6D98, a obiektem
// `DimensionItemStorage` jest 0x4E3A6D60. Bez odjecia 0x38 chodzenie po
// naglowku UObject trafia w smieci i log pokazuje przypadkowe klasy.
static constexpr uintptr_t STORAGE_IFACE_OFF = 0x38;
// `ItemContainers` — tablica przedmiotow magazynu (refleksja: `+0x258`, element
// `0x2a8`). Napelnianie zaczyna od jej WYCZYSZCZENIA (`0x141930cc0` na
// `this+0x220` = `magazyn+0x258`, licznik zerowany na koncu), wiec sam magazyn
// sie nie dubluje. Dubluja sie zespawnowane AKTORY BRONI: stare nie sa
// niszczone, a napelnianie tworzy nowy komplet. Stad niepusta tablica jest
// dobrym i sprawdzalnym znakiem „ten magazyn juz raz napelniono".
static constexpr uintptr_t STORAGE_ITEMS_NUM = 0x258 + 8;

static void czyjMagazyn(uintptr_t base, uintptr_t magazyn, uintptr_t* pc_out,
                        char* out, size_t cap)
{
    if (pc_out) *pc_out = 0;
    strcpy_s(out, cap, "?");
    if (!sensownyWsk(magazyn)) return;
    magazyn -= STORAGE_IFACE_OFF;
    const uintptr_t pc = *(const uintptr_t*)(magazyn + UOBJ_OUTER_OFF);
    if (!sensownyWsk(pc)) return;
    if (pc_out) *pc_out = pc;
    const uintptr_t gracz = *(const uintptr_t*)(pc + addr::PC_PLAYER_OFF);
    if (!sensownyWsk(gracz)) { strcpy_s(out, cap, "bez Player"); return; }
    const uintptr_t klasa = *(const uintptr_t*)(gracz + UOBJ_CLASS_OFF);
    char n[128];
    if (!sensownyWsk(klasa) || !nazwaObiektu(base, klasa, n, sizeof n)) return;
    if (strcmp(n, "DimensionLocalPlayer") == 0) strcpy_s(out, cap, "HOST (DimensionLocalPlayer)");
    else if (strstr(n, "Connection"))           strcpy_s(out, cap, "KLIENT (IpConnection)");
    else                                        strcpy_s(out, cap, n);
}

static void __fastcall thunkStorageLoad(void* magazyn, unsigned char flaga)
{
    uintptr_t sp = 0;
    __asm__ volatile ("mov %%rsp, %0" : "=r"(sp));
    void* powrot = __builtin_return_address(0);

    // ── STRAZNIK PODWOJNEGO NAPELNIANIA ────────────────────────────────────
    //
    // Zjawisko, zmierzone hakiem 22:52: dolaczenie klienta uruchamia zadanie
    // „LoadGameDataForTags", ktore ROZGLASZA sie po liscie wszystkich
    // zarejestrowanych magazynow (petla `0x1418D2C30`, wolana z `0x1419EEAFC`
    // z flaga 1). W liscie siedzi tez magazyn HOSTA — bo zarejestrowal sie przy
    // swoim wlasnym wczytaniu i nikt go nie wyrejestrowal. Host dostaje przez to
    // drugi komplet broni, dwa duplikaty zdolnosci i amunicje 28231.
    //
    // To jest wzorzec z WIEDZA.md §4 w wersji „za duzo, nie za malo": kod pisany
    // dla jednego gracza traktuje wczytanie jako zdarzenie CALEJ GRY, a nie
    // jednego gracza.
    //
    // Dlaczego akurat taki warunek: napelnianie samo czysci `ItemContainers`
    // przed praca, wiec magazyn z NIEPUSTA tablica to magazyn juz napelniony.
    // Nie podstawiamy zadnej wartosci i nie zgadujemy — pomijamy przebieg,
    // ktory z definicji jest powtorka. Przy pierwszym wczytaniu (solo start,
    // dolaczajacy gracz) tablica jest pusta, wiec gra dziala jak dotad.
    //
    // Bramkowane markerem i LICZONE; potwierdzac przez USUNIECIE markera.
    if (g_fixDupWlaczony && flaga == 1 && sensownyWsk((uintptr_t)magazyn)) {
        const uintptr_t obj = (uintptr_t)magazyn - STORAGE_IFACE_OFF;
        const int32_t ile = *(const int32_t*)(obj + STORAGE_ITEMS_NUM);
        if (ile > 0) {
            const LONG n = InterlockedIncrement(&g_fillPominiete);
            if (n <= 8 && g_bazaModulu) {
                uintptr_t pc = 0;
                char czyj[160];
                czyjMagazyn(g_bazaModulu, (uintptr_t)magazyn, &pc, czyj, sizeof czyj);
                logLine("NAPELNIANIE: POMINIETE powtorne napelnianie #%ld — magazyn 0x%llX"
                        " (%s) ma juz %d przedmiotow", n, (unsigned long long)obj, czyj, ile);
            }
            return;
        }
    }

    if (g_bazaModulu) {
        const LONG nr = InterlockedIncrement(&g_fillIle);
        if (nr <= 40) {
            uintptr_t pc = 0;
            char czyj[160];
            czyjMagazyn(g_bazaModulu, (uintptr_t)magazyn, &pc, czyj, sizeof czyj);
            unsigned nrPc = pc ? *(const unsigned*)(pc + UOBJ_NAME_OFF + 4) : 0;
            char stos[320] = "";
            spisStosu(sp, stos, sizeof stos, 8);
            logLine("NAPELNIANIE: #%ld magazyn=0x%llX kontroler=0x%llX_%u  %s  flaga=%u"
                    "  (wolajacy 0x%llX)",
                    nr, (unsigned long long)((uintptr_t)magazyn - STORAGE_IFACE_OFF),
                    (unsigned long long)pc, nrPc ? nrPc - 1 : 0, czyj, (unsigned)flaga,
                    (unsigned long long)((uintptr_t)powrot - g_bazaModulu + 0x140000000));
            if (stos[0]) logLine("NAPELNIANIE:    stos: %s", stos);
        }
    }
    if (g_origStorageLoad) g_origStorageLoad(magazyn, flaga);
}

static bool patchStorageLoadLog(uintptr_t base)
{
    const uintptr_t tabObj = base + addr::GUObjectArray_OFF + 0x10;
    const uintptr_t chunks = *(const uintptr_t*)tabObj;
    const int32_t ile    = *(const int32_t*)(tabObj + 0x14);
    const int32_t nchunk = *(const int32_t*)(tabObj + 0x1C);
    if (!sensownyWsk(chunks) || ile <= 0 || nchunk <= 0) return false;

    uintptr_t cdo = 0;
    char nazwa[128];
    for (int32_t ci = 0; ci < nchunk && !cdo; ++ci) {
        const uintptr_t blok = ((const uintptr_t*)chunks)[ci];
        if (!sensownyWsk(blok)) continue;
        int32_t tu = ile - ci * 65536;
        if (tu > 65536) tu = 65536;
        if (tu <= 0) break;
        for (int32_t i = 0; i < tu; ++i) {
            const uintptr_t obj = *(const uintptr_t*)(blok + (uintptr_t)i * 0x18);
            if (!sensownyWsk(obj)) continue;
            if (!nazwaObiektu(base, obj, nazwa, sizeof nazwa)) continue;
            if (strcmp(nazwa, "Default__DimensionItemStorage") == 0) { cdo = obj; break; }
        }
    }
    if (!cdo) { logLine("NAPELNIANIE: nie znalazlem wzorca DimensionItemStorage"); return false; }

    auto** vt = *(StorageLoadFn**)cdo;
    if (!vt) { logLine("NAPELNIANIE: wzorzec bez tablicy metod"); return false; }

    DWORD stare = 0;
    void* gniazdo = (void*)&vt[addr::SLOT_STORAGE_LOAD];
    if (!VirtualProtect(gniazdo, 8, PAGE_READWRITE, &stare)) {
        logLine("NAPELNIANIE: VirtualProtect nieudany"); return false;
    }
    g_origStorageLoad = vt[addr::SLOT_STORAGE_LOAD];
    vt[addr::SLOT_STORAGE_LOAD] = &thunkStorageLoad;
    VirtualProtect(gniazdo, 8, stare, &stare);

    // Kontrola tozsamosci: gniazdo ma wskazywac funkcje, ktora rozebralismy.
    // Gdyby build sie zmienil, log to pokaze od razu, zamiast dawac cisze.
    const uintptr_t oczekiwany = base + 0x1923AA0;
    logLine("NAPELNIANIE: hak zalozony (tablica 0x%llX, gniazdo %d, oryginal 0x%llX%s)",
            (unsigned long long)(uintptr_t)vt, addr::SLOT_STORAGE_LOAD,
            (unsigned long long)((uintptr_t)g_origStorageLoad - base + 0x140000000),
            (uintptr_t)g_origStorageLoad == oczekiwany ? "" : "  <-- INNA NIZ OCZEKIWANA");
    return true;
}

static bool patchLoadMapLog(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::LoadMap_OFF);
    // Bajty ponizej to prolog funkcji GRY — cytat z jej kodu, niezbedny, zeby
    // sprawdzic, ze latamy wlasciwe miejsce. Nie sa objete licencja MIT tego
    // projektu (patrz uwaga licencyjna na poczatku pliku).
    static const unsigned char oczekiwane[] = {
        0x56,             // push rsi
        0x57,             // push rdi
        0x41, 0x54,       // push r12
        0x41, 0x55,       // push r13
        0x41, 0x56,       // push r14
        0x41, 0x57        // push r15
    };
    if (memcmp(fn, oczekiwane, sizeof oczekiwane) != 0) {
        logLine("LOADMAP: bajty pod 0x%llX inne niz oczekiwane — NIE zakladam haka",
                (unsigned long long)(uintptr_t)fn);
        return false;
    }

    unsigned char* tr = nullptr;
    for (uintptr_t a = base + 0x08000000; a < base + 0x40000000; a += 0x10000) {
        tr = (unsigned char*)VirtualAlloc((void*)a, 0x1000,
                                          MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (tr) break;
    }
    if (!tr) { logLine("LOADMAP: brak miejsca na trampoline"); return false; }

    // Kradniemy 6 bajtow = cztery cale instrukcje (push rsi/rdi/r12/r13).
    // Wykonujemy je po przywroceniu rejestrow, zeby stos wygladal jak bez haka.
    // Wiersz oznaczony „oryginal" to bajty przeniesione Z GRY — cytat niezbedny
    // do zalatania (patrz uwaga licencyjna na poczatku pliku).
    unsigned char code[] = {
        0x50, 0x51, 0x52,                          // push rax, rcx, rdx
        0x41,0x50, 0x41,0x51, 0x41,0x52, 0x41,0x53,// push r8, r9, r10, r11
        0x48,0x83,0xEC,0x60,                       // sub  rsp,0x60
        0x0F,0x11,0x04,0x24,                       // movups [rsp+0x00],xmm0
        0x0F,0x11,0x4C,0x24,0x10,                  // movups [rsp+0x10],xmm1
        0x0F,0x11,0x54,0x24,0x20,                  // movups [rsp+0x20],xmm2
        0x0F,0x11,0x5C,0x24,0x30,                  // movups [rsp+0x30],xmm3
        0x0F,0x11,0x64,0x24,0x40,                  // movups [rsp+0x40],xmm4
        0x0F,0x11,0x6C,0x24,0x50,                  // movups [rsp+0x50],xmm5
        0x48,0x83,0xEC,0x20,                       // sub  rsp,0x20 (cien)
        0x4C,0x89,0xC1,                            // mov  rcx,r8   (FURL* -> arg 1)
        0x48,0xB8, 0,0,0,0,0,0,0,0,                // mov  rax,<wfcoopOnLoadMap>
        0xFF,0xD0,                                 // call rax
        0x48,0x83,0xC4,0x20,                       // add  rsp,0x20
        0x0F,0x10,0x04,0x24,                       // movups xmm0,[rsp+0x00]
        0x0F,0x10,0x4C,0x24,0x10,
        0x0F,0x10,0x54,0x24,0x20,
        0x0F,0x10,0x5C,0x24,0x30,
        0x0F,0x10,0x64,0x24,0x40,
        0x0F,0x10,0x6C,0x24,0x50,
        0x48,0x83,0xC4,0x60,                       // add  rsp,0x60
        0x41,0x5B, 0x41,0x5A, 0x41,0x59, 0x41,0x58,// pop  r11,r10,r9,r8
        0x5A, 0x59, 0x58,                          // pop  rdx,rcx,rax
        0x56, 0x57, 0x41,0x54, 0x41,0x55,          // oryginal: push rsi/rdi/r12/r13
        0xFF,0x25, 0x00,0x00,0x00,0x00,            // jmp qword ptr [rip+0]
        0,0,0,0,0,0,0,0                            // adres powrotu
    };
    size_t gniazdo = 0;
    for (size_t i = 0; i + 1 < sizeof code; ++i)
        if (code[i] == 0x48 && code[i + 1] == 0xB8) { gniazdo = i + 2; break; }
    if (!gniazdo) { logLine("LOADMAP: nie znalazlem gniazda na adres"); return false; }
    const uintptr_t fnPtr = (uintptr_t)&wfcoopOnLoadMap;
    memcpy(code + gniazdo, &fnPtr, sizeof fnPtr);
    const uintptr_t powrot = (uintptr_t)fn + 6;
    memcpy(code + sizeof(code) - 8, &powrot, sizeof powrot);
    memcpy(tr, code, sizeof code);

    DWORD stare = 0;
    if (!VirtualProtect(fn, 16, PAGE_EXECUTE_READWRITE, &stare)) {
        logLine("LOADMAP: VirtualProtect nieudany"); return false;
    }
    const int32_t rel = (int32_t)((intptr_t)tr - (intptr_t)(fn + 5));
    fn[0] = 0xE9; memcpy(fn + 1, &rel, 4); fn[5] = 0x90;
    VirtualProtect(fn, 16, stare, &stare);
    FlushInstructionCache(GetCurrentProcess(), fn, 16);
    logLine("LOADMAP: hak logujacy zalozony (0x%llX -> trampolina 0x%llX)",
            (unsigned long long)(uintptr_t)fn, (unsigned long long)(uintptr_t)tr);
    return true;
}

// ── HOSTOWANIE BEZ WYMUSZANIA MAPY: DWA BAJTY ───────────────────────────────
//
// Problem, ktory to rozwiazuje: zeby hostowac, robilismy wlasne
// `OpenLevel(mapa, "listen")`. To omija sekwencje startu misji, a wtedy sypie
// sie wszystko po kolei — bron nie strzela, celowanie nie dziala, klient nie
// dostaje ekranu smierci, minimapa wariuje. Kazdy z tych objawow to osobny
// kawalek TEJ SAMEJ pominietej sekwencji i odtwarzanie ich po jednym jest
// zbiorem otwartym (dwie proby z bronia obalone pomiarem).
//
// Rozwiazanie odwraca problem: niech gra podrozuje SAMA, jak zawsze, a my tylko
// dolozymy nasluch do JEJ podrozy.
//
// Jak to znalezione (powtarzalnie, nie zgadywaniem — `tools/find-xref.py`):
// w `UEngine::LoadMap` stoi kod
//     lea  rdx,[rip+...]        ; literal L"Listen"
//     mov  rcx,rsi              ; FURL*
//     call FURL::HasOption      ; 0x143BFC430
//     test al,al
//     je   pomin                ; <-- 0x143BEC200: `74 0F`
//     mov  rcx,[r13+0x280]      ; UWorld*
//     mov  rdx,rsi              ; ten sam FURL
//     call UWorld::Listen       ; 0x143C3ECE0
//
// Gra ma wiec juz wszystko: wlasciwy swiat, wlasciwy URL i wlasciwy moment
// w sekwencji ladowania. Brakuje tylko tego, zeby warunek przeszedl. Zamieniamy
// `je` na dwa NOP-y — dwa bajty — i nasluch wlacza sie przy KAZDYM ladowaniu
// mapy, wykonany przez sam silnik.
//
// Dlaczego to lepsze niz dopisanie `listen` do opcji URL: tablica opcji to
// `TArray<FString>` nalezaca do UE. Podmiana jej wskaznika na nasza pamiec
// skonczylaby sie tym, ze alokator gry sprobuje ja zwolnic — uszkodzeniem
// sterty widocznym dlugo po fakcie i nie do powiazania z przyczyna.
//
// Bramkowane markerem, zeby dalo sie zrobic przebieg kontrolny bez latki.
namespace addr {
constexpr uintptr_t ListenBranch_OFF = 0x3BEC1FE;   // `test al,al` + `je`
}

static bool patchAlwaysListen(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::ListenBranch_OFF);
    // Kontrola: `84 C0` (test al,al) i `74 0F` (je +0x0F). Bez zgody co do
    // bajtu nie ruszamy niczego — slepe pisanie w kod to najkrotsza droga do
    // awarii trudniejszej niz naprawiany problem. Same bajty pochodza Z GRY
    // i nie sa objete licencja MIT tego projektu (patrz poczatek pliku).
    static const unsigned char oczekiwane[] = { 0x84, 0xC0, 0x74, 0x0F };
    if (memcmp(fn, oczekiwane, sizeof oczekiwane) != 0) {
        logLine("NASLUCH: bajty pod 0x%llX inne niz oczekiwane (%02X %02X %02X %02X) "
                "— NIE lataem", (unsigned long long)(uintptr_t)fn,
                fn[0], fn[1], fn[2], fn[3]);
        return false;
    }

    DWORD stare = 0;
    if (!VirtualProtect(fn, 8, PAGE_EXECUTE_READWRITE, &stare)) {
        logLine("NASLUCH: VirtualProtect nieudany");
        return false;
    }
    fn[2] = 0x90;   // je -> nop
    fn[3] = 0x90;   // nop
    VirtualProtect(fn, 8, stare, &stare);
    FlushInstructionCache(GetCurrentProcess(), fn, 8);
    logLine("NASLUCH ZALOZONY: gra bedzie wolac UWorld::Listen przy KAZDYM "
            "ladowaniu mapy (0x%llX: je -> nop nop)",
            (unsigned long long)(uintptr_t)(fn + 2));
    return true;
}

// ── LATKA: nie wolaj zdarzenia Blueprintu na pustym obiekcie ────────────────
//
// Klient ginie 1–3 s po wejsciu do swiata hosta. Raport awarii gry (XML z
// katalogu Saved/Crashes, czytany przez tools/read-crash-xml.py) daje dokladna
// sciezke: timer systemu
// zdrowia/wskrzeszania -> `UDimensionSpawnManager::OnActorDestroyed` ->
// odczyt `AbilityCachedData` -> null. Podczas travelu sieciowego silnik niszczy
// aktorow starego swiata klienta, a handler zniszczenia siega po obiekcie,
// ktorego juz nie ma.
//
// Funkcja pod 0x141B7DDE0 to wygenerowany thunk zdarzenia Blueprintu:
//   mov rbx,[rcx]   <- czyta vtable Z OBIEKTU (rcx = this)  ← tu pada przy rcx=0
//   mov rdx,[rip+X] <- zapamietana UFunction
//   call ...        <- pobranie funkcji
//   call [rbx+0x220]<- ProcessEvent
// Czyli rcx to `this`. Wywolanie zdarzenia na nullu jest ZAWSZE bledem, wiec
// najbezpieczniejsza mozliwa poprawka to „gdy this == nullptr, wroc bez akcji".
// Funkcja nic nie zwraca, wiec samo `ret` na wejsciu jest poprawne.
//
// Technika: pierwsze 5 bajtow (`mov [rsp+8],rbx`) zastepujemy skokiem `E9 rel32`
// do wlasnej trampoliny, ktora sprawdza rcx, a gdy jest niezerowy — wykonuje
// oryginalne 5 bajtow i wraca do reszty funkcji. Trampoline alokujemy w zasiegu
// ±2 GB od modulu, bo `E9` operuje na przesunieciu 32-bitowym.
static bool patchBpEventNullGuard(uintptr_t base)
{
    auto* fn = reinterpret_cast<unsigned char*>(base + addr::BpEventThunk_OFF);

    // Kontrola bezpieczenstwa: po patchu gry adresy moga sie przesunac, a slepe
    // pisanie w kod to najkrotsza droga do awarii trudniejszej niz naprawiana.
    // Bajty ponizej to prolog funkcji GRY — cytat niezbedny do zalatania,
    // nieobjety licencja MIT tego projektu (patrz poczatek pliku).
    static const unsigned char expect[] = {
        0x48, 0x89, 0x5C, 0x24, 0x08,  // mov [rsp+8],rbx
        0x57,                          // push rdi
        0x48, 0x83, 0xEC, 0x30,        // sub rsp,0x30
        0x48, 0x8B, 0x19               // mov rbx,[rcx]
    };
    if (memcmp(fn, expect, sizeof(expect)) != 0) {
        logLine("LATKA: bajty pod 0x%llX nie zgadzaja sie z oczekiwanymi — NIE lataem",
                (unsigned long long)(uintptr_t)fn);
        return false;
    }

    unsigned char* tr = nullptr;
    for (uintptr_t a = base + 0x08000000; a < base + 0x40000000; a += 0x10000) {
        tr = static_cast<unsigned char*>(
            VirtualAlloc(reinterpret_cast<void*>(a), 0x1000,
                         MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
        if (tr) break;
    }
    if (!tr) { logLine("LATKA: nie udalo sie zaalokowac trampoliny"); return false; }

    // Trampolina robi dwie rzeczy: najpierw daje nam punkt zaczepienia NA WATKU
    // GRY (stad travel), potem pilnuje, zeby nie wolac zdarzenia na nullu.
    //
    // Wyrownanie stosu: na wejsciu do funkcji rsp%16 == 8 (adres powrotu). Zeby
    // wolac funkcje zgodnie z ABI, tuz przed `call` musi byc rsp%16 == 0 —
    // stad `sub rsp,0x48` (8-0x48 przystaje do 0 modulo 16). W tym miejscu
    // 0x20 to obowiazkowa przestrzen cienia dla wolanego, a wyzej chowamy
    // cztery rejestry argumentowe, bo nasza funkcja moze je zniszczyc.
    //
    // Wiersz oznaczony „oryginal" to bajty przeniesione Z GRY — cytat niezbedny
    // do zalatania (patrz uwaga licencyjna na poczatku pliku).
    unsigned char code[] = {
        0x48, 0x83, 0xEC, 0x48,              // sub  rsp,0x48
        0x48, 0x89, 0x4C, 0x24, 0x20,        // mov  [rsp+0x20],rcx
        0x48, 0x89, 0x54, 0x24, 0x28,        // mov  [rsp+0x28],rdx
        0x4C, 0x89, 0x44, 0x24, 0x30,        // mov  [rsp+0x30],r8
        0x4C, 0x89, 0x4C, 0x24, 0x38,        // mov  [rsp+0x38],r9
        0x48, 0xB8, 0,0,0,0,0,0,0,0,         // mov  rax,<wfcoopOnGameThread>
        0xFF, 0xD0,                          // call rax
        0x48, 0x8B, 0x4C, 0x24, 0x20,        // mov  rcx,[rsp+0x20]
        0x48, 0x8B, 0x54, 0x24, 0x28,        // mov  rdx,[rsp+0x28]
        0x4C, 0x8B, 0x44, 0x24, 0x30,        // mov  r8,[rsp+0x30]
        0x4C, 0x8B, 0x4C, 0x24, 0x38,        // mov  r9,[rsp+0x38]
        0x48, 0x83, 0xC4, 0x48,              // add  rsp,0x48
        0x48, 0x85, 0xC9,                    // test rcx,rcx
        0x74, 0x13,                          // jz   -> ret
        0x48, 0x89, 0x5C, 0x24, 0x08,        // mov  [rsp+8],rbx  (oryginal)
        0xFF, 0x25, 0x00, 0x00, 0x00, 0x00,  // jmp  qword ptr [rip+0]
        0, 0, 0, 0, 0, 0, 0, 0,              // adres powrotu
        0xC3                                 // ret
    };
    const uintptr_t fnPtr = reinterpret_cast<uintptr_t>(&wfcoopOnGameThread);
    memcpy(code + 26, &fnPtr, sizeof(fnPtr));           // cel `mov rax,imm64`
    const uintptr_t back = base + addr::BpEventThunk_OFF + 5;
    memcpy(code + sizeof(code) - 9, &back, sizeof(back)); // adres powrotu
    memcpy(tr, code, sizeof(code));

    DWORD old = 0;
    if (!VirtualProtect(fn, 5, PAGE_EXECUTE_READWRITE, &old)) {
        logLine("LATKA: VirtualProtect odmowil");
        return false;
    }
    const int32_t rel = static_cast<int32_t>(
        reinterpret_cast<intptr_t>(tr) - reinterpret_cast<intptr_t>(fn + 5));
    fn[0] = 0xE9;
    memcpy(fn + 1, &rel, sizeof(rel));
    VirtualProtect(fn, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, 5);

    g_hooked = true;
    logLine("LATKA ZALOZONA: straznik nulla + wejscie na watek gry "
            "(0x%llX -> trampolina 0x%llX)",
            (unsigned long long)(uintptr_t)fn, (unsigned long long)(uintptr_t)tr);
    return true;
}


// Adres hosta czytamy z pliku — ten sam, z ktorego korzysta mod Lua, zeby oba
// swiaty testowe konfigurowalo sie tak samo.
static bool readJoinTarget(wchar_t* out, size_t cap)
{
    FILE* f = nullptr;
    if (fopen_s(&f, savedPath("WFCoop_join_ip.txt"), "r") != 0 || !f)
        return false;
    char buf[128] = {};
    char* got = fgets(buf, (int)sizeof(buf), f);
    fclose(f);
    if (!got) return false;
    // obetnij bialy znak na koncu
    for (char* p = buf; *p; ++p)
        if (*p == '\r' || *p == '\n' || *p == ' ' || *p == '\t') { *p = 0; break; }
    if (!buf[0]) return false;
    size_t n = 0;
    mbstowcs_s(&n, out, cap, buf, _TRUNCATE);
    return n > 1;
}

// Ile sekund odczekac po tym, jak swiat sie pojawi, ZANIM zawolamy travel.
//
// Nie jest to kosmetyka: GWorld pojawia sie juz ~7 s po starcie procesu, a gra
// dochodzi do menu dopiero po ~40-60 s. Travel wolany w srodku wlasnego
// ladowania mierzylby cos innego niz przebiegi z UE4SS, gdzie klient dolaczal
// dopiero, gdy przestal sobie doladowywac poziomy. Domyslne 75 s daje travel
// w okolicach 80. sekundy zycia procesu, czyli grubo po menu.
//
// Wartosc czytamy z pliku, zeby nie przebudowywac biblioteki przy kazdej
// zmianie tempa testu.
static int readJoinDelay(int fallback)
{
    FILE* f = nullptr;
    if (fopen_s(&f, savedPath("WFCoop_join_delay.txt"), "r") != 0 || !f)
        return fallback;
    char buf[32] = {};
    char* got = fgets(buf, (int)sizeof(buf), f);
    fclose(f);
    if (!got) return fallback;
    int v = atoi(buf);
    return (v > 0 && v <= 600) ? v : fallback;
}

// ── PULS: czy proces zyje i czy swiat sie zmienil ───────────────────────────
//
// Po co: u klienta nie mamy UE4SS, wiec po jego stronie nie widzimy NICZEGO.
// Caly dzisiejszy dzien diagnozowalismy „klient zamarza" po tym, co widac na
// ekranie i po liczniku `conn` u hosta — a to za malo, bo `conn` spada zawsze
// po ~60 s (timeout silnika), niezaleznie od tego, co sie naprawde stalo.
//
// Ten watek jest NIEZALEZNY od watku gry, wiec rozroznia trzy sytuacje, ktorych
// dotad nie umielismy rozroznic:
//   * log sie urywa            -> zamarzl CALY proces
//   * log leci, GWorld stoi    -> zyje proces, ale travel nigdy sie nie dokonczyl
//   * log leci, GWorld zmienil -> travel sie udal, problem jest juz PO wejsciu
//
// Zapisujemy rzadko (co 5 s), ale kazda ZMIANE swiata natychmiast — dzieki temu
// log jest krotki, a moment przejscia widoczny co do sekundy.
static DWORD WINAPI heartbeat(LPVOID)
{
    const uintptr_t base = (uintptr_t)GetModuleHandleW(nullptr);
    auto* pGWorld = (void**)(base + addr::GWorld_OFF);
    const ULONGLONG t0 = GetTickCount64();
    void* lastWorld = nullptr;
    int since = 0;

    for (;;) {
        Sleep(1000);
        // Czytamy zmienna globalna w sekcji danych modulu — ta strona istnieje
        // przez cale zycie procesu, wiec odczyt jest bezpieczny bez oslony SEH
        // (MinGW i tak nie ma `__try`). Wartosc moze byc chwilowo w trakcie
        // podmiany, ale to tylko diagnostyka: zla wartosc pokaze sie jako jedna
        // dziwna linia, a nie jako awaria.
        void* w = *pGWorld;

        // Licznik pominietych wywolan boostera. Raportujemy TYLKO przy zmianie,
        // bo inaczej log tonie w powtorzeniach. Bez tej liczby nie odroznimy
        // „latka nie byla potrzebna" od „latka uratowala 40 wywolan".
        if (g_wejscieLicznik) {
            static unsigned ostatniW = 0;
            const unsigned teraz = *g_wejscieLicznik;
            if (teraz != ostatniW) {
                logLine("WEJSCIE: pominiete wiazania z nullem: %u", teraz);
                ostatniW = teraz;
            }
        }
        if (g_efektyLicznik) {
            static unsigned ostatniE = 0;
            const unsigned teraz = *g_efektyLicznik;
            if (teraz != ostatniE) {
                logLine("EFEKTY: pominiete efekty strzalu bez pawna: %u", teraz);
                ostatniE = teraz;
            }
        }

        if (g_logOwnerWlaczony) {
            static bool zal = false;
            if (!zal && g_bazaModulu && w) zal = patchSetOwnerLog(g_bazaModulu);
        }

        // Hak na zapis amunicji. Zakladany tutaj, bo szuka wzorca klasy ASC.
        // Sluzy i do logowania (`log_ammo`), i do naprawy magazynka
        // (`fix_ammo`) — ta druga potrzebuje go tak samo, wiec warunek
        // obejmuje oba markery.
        if (g_logAmmo || g_fixAmmoWlaczony) {
            static bool zal = false;
            if (!zal && g_bazaModulu && w) zal = patchAmmoLog(g_bazaModulu);
            static LONG ostatnio = 0;
            if (zal && g_ammoIle != ostatnio) {
                ostatnio = g_ammoIle;
                logLine("AMUNICJA: zapisow do CurrentAmmo*: %ld", ostatnio);
            }
        }

        // Kanal stanu ruchu: znalezienie UFunction transportu i przechwycenie.
        // Zakladane po OBU stronach — u klienta sluzy do wysylki, u hosta do
        // odbioru. Licznik wyslanych ma u hosta zostac na zerze (jego wlasna
        // postac ma `Role == 3`), i to jest proba kontrolna tej latki.
        if (g_fixStateWlaczony) {
            static bool zal = false;
            if (!zal && g_bazaModulu && w) zal = patchKanalStanu(g_bazaModulu);
            static LONG ostW = -1, ostO = -1, ostP = -1;
            if (zal && (g_kanalWyslane != ostW || g_kanalOdebrane != ostO
                        || g_kanalPodane != ostP)) {
                ostW = g_kanalWyslane; ostO = g_kanalOdebrane; ostP = g_kanalPodane;
                logLine("KANAL: wyslanych %ld, odebranych %ld, podanych akcji %ld",
                        ostW, ostO, ostP);
            }
        }

        // Podsluch prawdziwego wejscia. Zakladany takze przy `fix_state`, bo to
        // z niego bierze sie WZORZEC bajtow struktury akcji — bez niego kanal
        // musialby zgadywac, a zgadywanie kosztowalo juz jeden przebieg.
        if (g_logKanal || g_fixStateWlaczony) {
            static bool zal = false;
            if (!zal && g_bazaModulu && w) zal = patchPodsluchWejscia(g_bazaModulu);
            static LONG ostWz = -1;
            if (zal && g_wzorowZnanych != ostWz) {
                ostWz = g_wzorowZnanych;
                logLine("WEJSCIE-PODSLUCH: zapamietanych wzorcow akcji: %ld", ostWz);
            }
        }

        // Pomiar do kanalu stanu ruchu. Zakladany tutaj, bo szuka `UFunction`
        // w tablicy obiektow. To latka KLIENTA — u niego maszyna stanow dostaje
        // prawdziwe wejscie, wiec cisza po stronie serwera jest oczekiwana.
        if (g_logKanal) {
            static bool zal = false;
            if (!zal && g_bazaModulu && w) zal = patchKanalPomiar(g_bazaModulu);
        }

        // Hak na napelnianie ekwipunku. Zakladany tutaj, bo potrzebuje gotowej
        // tablicy obiektow (szuka wzorca klasy magazynu). Ten sam hak sluzy do
        // logowania (`log_fill`) i do strazniku duplikatu (`fix_dup`).
        if (g_logFillWlaczony || g_fixDupWlaczony) {
            static bool zal = false;
            if (!zal && g_bazaModulu && w) zal = patchStorageLoadLog(g_bazaModulu);
            static LONG ostatnio = 0;
            if (zal && g_fillPominiete != ostatnio) {
                ostatnio = g_fillPominiete;
                logLine("NAPELNIANIE: pominietych powtorek: %ld", ostatnio);
            }
        }

        // Przejsciowki limitow ruchu — zakladane tutaj z tego samego powodu co
        // liczniki: potrzebuja gotowej tablicy obiektow. Sluza do pomiaru
        // (`log_speed`) i do naprawy mapy atrybutow (`fix_attrs`).
        if (g_logSpeed || g_fixAttrsWlaczony) {
            static bool zalozona = false;
            if (!zalozona && g_bazaModulu && w) {
                zalozona = patchRemoteMovement(g_bazaModulu);
            }
            static LONG ostatnioSync = 0;
            if (zalozona && g_syncRazem != ostatnioSync) {
                ostatnioSync = g_syncRazem;
                logLine("ATRYBUTY: odswiezen mapy razem: %ld", ostatnioSync);
            }
        }

        // Liczniki RPC ruchu. Zakladamy je dopiero tutaj, bo w chwili startu
        // watku roboczego tablica obiektow jeszcze nie istnieje.
        if (g_ruchWlaczony) {
            static bool zalozone = false;
            if (!zalozone && g_bazaModulu && w) {
                zalozone = patchServerMoveCounters(g_bazaModulu) > 0;
            }
            if (zalozone) {
                static LONG ostatnie[RUCH_ILE] = {};
                for (int n = 0; n < RUCH_ILE; ++n) {
                    const LONG teraz = g_ruchLicznik[n];
                    if (teraz != ostatnie[n]) {
                        logLine("RUCH: %s wykonane %ld razy", g_nazwyRuchu[n], teraz);
                        ostatnie[n] = teraz;
                    }
                }
            }
        }
        if (g_boosterLicznik) {
            static unsigned ostatni = 0;
            const unsigned teraz = *g_boosterLicznik;
            if (teraz != ostatni) {
                logLine("BOOSTER: pominiete wywolania z nullem: %u", teraz);
                ostatni = teraz;
            }
        }

        const unsigned sec = (unsigned)((GetTickCount64() - t0) / 1000);
        if (w != lastWorld) {
            logLine("PULS t=%us: GWorld ZMIENIL SIE 0x%llX -> 0x%llX", sec,
                    (unsigned long long)(uintptr_t)lastWorld,
                    (unsigned long long)(uintptr_t)w);
            lastWorld = w;
            since = 0;
        } else if (++since >= 5) {
            logLine("PULS t=%us: zyje, GWorld=0x%llX bez zmian", sec,
                    (unsigned long long)(uintptr_t)w);
            since = 0;
        }
    }
    return 0;
}

static DWORD WINAPI worker(LPVOID)
{
    // Wszystkie operacje na pliku MUSZA byc tutaj, nie w DllMain. fopen pod
    // blokada ladowarki to klasyczna droga do zakleszczenia: proba pierwsza
    // (02:08) logowala z DllMain i gra stala na czarnym ekranie przy 257% CPU,
    // zamiast dojsc do menu w ~40 s.
    Sleep(2000);

    logLine("=== " WFCOOP_LOGNAME " zaladowany ===");
    logLine("watek roboczy wstal, PID=%lu", GetCurrentProcessId());

    const uintptr_t base = (uintptr_t)GetModuleHandleW(nullptr);
    logLine("baza procesu: 0x%llX", (unsigned long long)base);
    g_bazaModulu = base;

    // Wyjecie broni u klienta — bramkowane markerem, zeby dalo sie zrobic
    // przebieg kontrolny BEZ niego i porownac. Bez tego nie wiadomo, czy bron
    // pojawila sie dzieki nam, czy sama.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_weapon.txt"), "r") == 0 && f) {
            fclose(f);
            g_bronWlaczona = true;
            logLine("BRON: marker WFCoop_fix_weapon.txt — bede wolal SelectWeapon "
                    "z watku gry, gdy pojawi sie lokalna postac");
        } else {
            logLine("BRON: brak markera WFCoop_fix_weapon.txt — nie ruszam broni");
        }
    }
    // Kiedys tu bylo „baza inna niz 0x140000000 -> nie robimy nic". To bylo
    // nadmiernie ostrozne i szkodliwe: WSZYSTKIE nasze adresy sa i tak trzymane
    // jako PRZESUNIECIA od bazy (`base + OFF`), wiec dzialaja pod dowolnym
    // adresem zaladowania. Pod Wine baza jest stala, ale na Windowsie u drugiego
    // gracza ASLR moze ja przesunac — i wtedy stary warunek cicho wylaczalby
    // dolaczanie, zostawiajac w logu jedna linijke do wypatrzenia.
    if (base != addr::BASE) {
        logLine("UWAGA: baza inna niz 0x%llX — licze adresy wzgledem RZECZYWISTEJ bazy",
                (unsigned long long)addr::BASE);
    }

    // Latka idzie PRZED dolaczaniem: awaria wypada 1–3 s po wejsciu w swiat
    // hosta, wiec musi byc zalozona, zanim w ogole zawolamy travel.
    // Wylacznik na wypadek, gdyby latka sama cos psula — wtedy wystarczy
    // stworzyc plik i porownac przebiegi bez przebudowy biblioteki.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_no_patch.txt"), "r") == 0 && f) {
            fclose(f);
            logLine("LATKA: marker WFCoop_no_patch.txt — pomijam latanie");
        } else {
            patchBpEventNullGuard(base);
        }
    }

    // Drugi, PEWNY punkt wejscia na watek gry. Tamten hak wisi na thunku
    // zdarzenia Blueprintu, ktory w przebiegu 00:51 nie zostal wywolany ani
    // razu ("BEZPIECZNIK: hak nie zostal wywolany przez 8 s") — wiec wszystko,
    // co od niego zawiesilismy, nigdy sie nie wykonalo.
    patchGameEngineTick(base);

    // Hak WYLACZNIE logujacy — nie zmienia zachowania gry, ma tylko
    // pokazac, czy i jakim URL-em gra sama podrozuje.
    patchLoadMapLog(base);

    // Nasluch bez wymuszania mapy — bramkowany markerem, zeby dalo sie zrobic
    // przebieg kontrolny bez latki i porownac.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_always_listen.txt"), "r") == 0 && f) {
            fclose(f);
            patchAlwaysListen(base);
        } else {
            logLine("NASLUCH: brak markera WFCoop_always_listen.txt — nie latam");
        }
    }

    // Straznik nulla w OnItemAddedCallback — to on ma zatrzymac smierc hosta
    // przy dolaczeniu klienta. Bramkowany osobno, zeby dalo sie zmierzyc
    // przebieg z nim i bez niego.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_booster.txt"), "r") == 0 && f) {
            fclose(f);
            patchBoosterNullGuard(base);
        } else {
            logLine("BOOSTER: brak markera WFCoop_fix_booster.txt — nie latam");
        }
    }

    // Sciana #2: straznik nulla w wiazaniu akcji wejscia. Osobny marker, zeby
    // dalo sie zmierzyc, ktora latka co daje.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_input.txt"), "r") == 0 && f) {
            fclose(f);
            patchInputBindNullGuard(base);
        } else {
            logLine("WEJSCIE: brak markera WFCoop_fix_input.txt — nie latam");
        }
    }

    // Log przypisan wlasciciela — czysta diagnostyka do sprawy podwojnego
    // kompletu broni. Zapisuje najwyzej 60 wpisow, wiec nie zaleje logu.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_log_owner.txt"), "r") == 0 && f) {
            fclose(f);
            g_logOwnerWlaczony = true;
            logLine("WLASCICIEL: marker WFCoop_log_owner.txt — bede logowal SetOwner");
        }
    }

    // Log napelniania ekwipunku — odpowiada na pytanie „kto uruchamia drugi
    // przebieg". Zakladany po OBU stronach: u klienta jego wlasny magazyn tez
    // sie napelnia, wiec jego log jest probka kontrolna dla tego samego haka.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_log_fill.txt"), "r") == 0 && f) {
            fclose(f);
            g_logFillWlaczony = true;
            logLine("NAPELNIANIE: marker WFCoop_log_fill.txt — bede logowal napelnianie ekwipunku");
        } else {
            logLine("NAPELNIANIE: brak markera WFCoop_log_fill.txt — nie loguje");
        }
    }

    // Straznik podwojnego napelniania — to latka HOSTA. U klienta jego wlasny
    // magazyn napelnia sie pierwszy raz, wiec licznik ma tam zostac na zerze
    // i to jest jej proba kontrolna.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_dup.txt"), "r") == 0 && f) {
            fclose(f);
            g_fixDupWlaczony = true;
            logLine("NAPELNIANIE: marker WFCoop_fix_dup.txt — bede pomijal powtorne napelnianie");
        } else {
            logLine("NAPELNIANIE: brak markera WFCoop_fix_dup.txt — nie latam duplikatu");
        }
    }

    // Pomiar zerowego limitu ruchu — bez podstawiania czegokolwiek. Loguje
    // PIERWSZE zero dla kazdego komponentu razem z rozmiarem mapy atrybutow
    // ruchu odczytanym w tej samej chwili, wiec cisza znaczy „zera nie bylo".
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_log_speed.txt"), "r") == 0 && f) {
            fclose(f);
            g_logSpeed = true;
            logLine("LIMIT: marker WFCoop_log_speed.txt — bede logowal zerowe limity ruchu");
        } else {
            logLine("LIMIT: brak markera WFCoop_log_speed.txt — nie loguje limitow");
        }
    }

    // Kto wpisuje amunicje do magazynka — czysty pomiar, nic nie zmienia.
    // Zakladac po OBU stronach: u hosta zbiera wzorzec z gry solo i stan broni
    // dolaczajacego gracza, u klienta pokazuje jego wlasna, lokalna kopie.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_log_ammo.txt"), "r") == 0 && f) {
            fclose(f);
            g_logAmmo = true;
            logLine("AMUNICJA: marker WFCoop_log_ammo.txt — bede logowal zapisy CurrentAmmo*");
        } else {
            logLine("AMUNICJA: brak markera WFCoop_log_ammo.txt — nie loguje");
        }
        FILE* fa = nullptr;
        if (fopen_s(&fa, savedPath("WFCoop_fix_ammo.txt"), "r") == 0 && fa) {
            fclose(fa);
            g_fixAmmoWlaczony = true;
            logLine("AMUNICJA: marker WFCoop_fix_ammo.txt — powtorze napelnienie "
                    "magazynka, gdy zapas jest, a magazynek zerowy");
        }
    }

    // Kanal stanu ruchu — jedyna latka, ktora DOKLADA wlasny przekaz danych.
    // Reszta modu tylko wola kod gry albo usuwa warunek; tu gra nie ma czym
    // przeslac stanu (47 funkcji maszyny stanow, zero RPC), wiec transportem
    // jest jej istniejace RPC. Marker ten sam po obu stronach: klient wysyla,
    // host odbiera i podaje akcje maszynie stanow.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_state.txt"), "r") == 0 && f) {
            fclose(f);
            g_fixStateWlaczony = true;
            logLine("KANAL: marker WFCoop_fix_state.txt — kanal stanu ruchu wlaczony");
        } else {
            logLine("KANAL: brak markera WFCoop_fix_state.txt — kanal wylaczony");
        }
    }

    // Pomiar wstepny do kanalu stanu ruchu: adres `ProcessEvent` i uklad
    // `FFrame`. Same odczyty, nic nie zmienia w zachowaniu gry.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_log_kanal.txt"), "r") == 0 && f) {
            fclose(f);
            g_logKanal = true;
            logLine("KANAL: marker WFCoop_log_kanal.txt — zmierze ProcessEvent i uklad FFrame");
        } else {
            logLine("KANAL: brak markera WFCoop_log_kanal.txt — nie mierze");
        }
    }

    // Naprawa ruchu: ponowna synchronizacja podrecznej mapy atrybutow, wlasna
    // funkcja gry. To latka HOSTA — u klienta jego wlasny pionek liczy limity
    // poprawnie, wiec licznik ma tam zostac na zerze (proba kontrolna).
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_attrs.txt"), "r") == 0 && f) {
            fclose(f);
            g_fixAttrsWlaczony = true;
            logLine("ATRYBUTY: marker WFCoop_fix_attrs.txt — przy zerowym limicie odswieze mape atrybutow");
        } else {
            logLine("ATRYBUTY: brak markera WFCoop_fix_attrs.txt — nie odswiezam");
        }
    }

    // Przejsciowki limitow potrzebuja sprawdzonych adresow funkcji gry — i to
    // dotyczy tak samo pomiaru, jak i naprawy. Sprawdzamy raz, po odczytaniu
    // obu markerow, zeby log mowil o tym jednoznacznie.
    if (g_logSpeed || g_fixAttrsWlaczony)
        g_predykatyOk = sprawdzPredykaty(base);

    // Licznik RPC ruchu — czysta diagnostyka, nic nie zmienia w zachowaniu gry.
    // Zakladany po obu stronach, bo zero u klienta jest OCZEKIWANE (patrz opis
    // przy `patchServerMoveCounters`) i sluzy za probke kontrolna samego haka.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_count_move.txt"), "r") == 0 && f) {
            fclose(f);
            g_ruchWlaczony = true;
            logLine("RUCH: marker WFCoop_count_move.txt — bede liczyl RPC ruchu");
        } else {
            logLine("RUCH: brak markera WFCoop_count_move.txt — nie licze");
        }
    }

    // Sciana #3: straznik nulla na `MyPawn` w efektach strzalu. To latka
    // KLIENTA — u hosta pawn broni istnieje zawsze, wiec licznik ma tam zostac
    // na zerze i to jest jej proba kontrolna.
    {
        FILE* f = nullptr;
        if (fopen_s(&f, savedPath("WFCoop_fix_effects.txt"), "r") == 0 && f) {
            fclose(f);
            patchEffectsPawnNullGuard(base);
        } else {
            logLine("EFEKTY: brak markera WFCoop_fix_effects.txt — nie latam");
        }
    }

    wchar_t target[128] = {};
    if (!readJoinTarget(target, 128)) {
        logLine("brak WFCoop_join_ip.txt — nie dolaczam (to normalne dla hosta)");
        return 0;
    }
    logLine("cel dolaczenia: %ls", target);
    // Od tej chwili wiadomo, ze jestesmy KLIENTEM — dopiero teraz kanal stanu
    // ruchu ma czego szukac. U hosta ta linia nigdy nie pada, wiec jego watek
    // gry nie tknie tablicy obiektow ani razu.
    g_jestemKlientem = true;

    auto* pGEngine = (void**)(base + addr::GEngine_OFF);
    auto* pGWorld = (void**)(base + addr::GWorld_OFF);
    auto setClientTravel = (SetClientTravelFn)(base + addr::SetClientTravel_OFF);

    // Czekamy, az silnik zbuduje swiat. Bez tego wolalibysmy travel na nullu.
    // 180 s to z zapasem: przy zimnym starcie gra potrzebuje ~60 s do menu.
    for (int i = 0; i < 180; ++i) {
        void* engine = *pGEngine;
        void* world = *pGWorld;
        if (engine && world) {
            const int delay = readJoinDelay(75);
            logLine("GEngine=0x%llX GWorld=0x%llX — czekam jeszcze %d s na wyciszenie",
                    (unsigned long long)(uintptr_t)engine,
                    (unsigned long long)(uintptr_t)world, delay);
            // Klient ginie, gdy dolacza w trakcie wlasnego streamingu, wiec
            // dajemy grze dojsc do siebie. Wartosc dobrana jak w modzie Lua.
            Sleep((DWORD)delay * 1000u);
            engine = *pGEngine;
            world = *pGWorld;
            if (!engine || !world) {
                logLine("swiat zniknal w trakcie czekania — przerywam");
                return 0;
            }
            // Nie wolamy juz travelu STAD. Ten watek nie jest watkiem gry,
            // a zapis URL podrozy z obcego watku to wyscig z silnikiem — jedyny
            // czynnik staly we wszystkich dotychczasowych przebiegach.
            // Zamiast tego uzbrajamy flage; wywolanie wykona trampolina przy
            // najblizszym zdarzeniu Blueprintu, czyli juz na watku gry.
            if (g_hooked) {
                wcsncpy_s(g_travelUrl, target, _TRUNCATE);
                g_pGEngine = pGEngine;
                g_pGWorld = pGWorld;
                g_setClientTravel = setClientTravel;
                InterlockedExchange(&g_travelArmed, 1);
                logLine("UZBROJONE: travel wykona sie z WATKU GRY przy najblizszym zdarzeniu BP");

                // BEZPIECZNIK. Zahaczony thunk zdarzen BP okazal sie w menu
                // NIGDY nie wolany — uzbrojenie wisialo, travel nie nastapil,
                // a caly przebieg poszedl na marne (log z 20:15: „UZBROJONE"
                // bez ani jednego „TRAVEL Z WATKU GRY"). Jesli wiec w ciagu
                // 20 s nikt nas z watku gry nie odwiedzi, wolamy po staremu.
                // Lepszy pomiar z gorszej sciezki niz zaden pomiar.
                for (int s = 0; s < 8 && !g_travelDone; ++s) Sleep(1000);
                if (!g_travelDone) {
                    logLine("BEZPIECZNIK: hak nie zostal wywolany przez 8 s "
                            "— wolam SetClientTravel z watku roboczego (stara droga)");
                    InterlockedExchange(&g_travelDone, 1);
                    setClientTravel(engine, world, target, 0 /* TRAVEL_Absolute */);
                    logLine("BEZPIECZNIK: SetClientTravel wrocil");
                }
            } else {
                // Bez haka nie mamy jak wejsc na watek gry — wtedy stara droga,
                // zeby w ogole cokolwiek dalo sie zmierzyc.
                logLine("BRAK HAKA — wolam SetClientTravel po staremu (z obcego watku)");
                setClientTravel(engine, world, target, 0 /* TRAVEL_Absolute */);
                logLine("SetClientTravel wrocil");
            }
            return 0;
        }
        Sleep(1000);
    }
    logLine("nie doczekalem sie GEngine/GWorld");
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(inst);
        // Tylko utworzenie watku — nic wiecej. Zadnego I/O, zadnego
        // LoadLibrary: jedno i drugie pod blokada ladowarki potrafi zawiesic
        // caly proces.
        HANDLE h = CreateThread(nullptr, 0, worker, nullptr, 0, nullptr);
        if (h) CloseHandle(h);
        HANDLE hb = CreateThread(nullptr, 0, heartbeat, nullptr, 0, nullptr);
        if (hb) CloseHandle(hb);
    }
    return TRUE;
}
