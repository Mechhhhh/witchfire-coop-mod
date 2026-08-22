# witchfire-coop

An unofficial two-player co-op mod for **Witchfire** — a game that ships with no
multiplayer at all. It is a proxy DLL injected into the game process that patches
memory, hooks vtables, and calls the game's own code to switch on networking the
game already contains but never exposes.

Runs on Linux through Proton. Works on Windows too — the mod itself is a plain
Windows DLL; only the launch scripts are Linux-specific.

**Status: not finished, and honestly not close.** Two players can play together
for over two hours without a crash, and a joining client now survives in the
hub with camera, world and a fully acknowledged pawn. **One thing blocks
playability: the joined client accepts no input at all** — no movement keys, no
mouse, no menu key. Read "What does not work" before you try it.

---

## What works

Every claim below was measured, not assumed.

- **Both players are in the same world and see each other.** Over two hours of
 joint play without a crash.
- **The host is not disturbed by a join.** A joining player used to reload the
 host's inventory a second time, giving the host a duplicate weapon set, wiping
 the currency earned in the run, and breaking the first-person view. Fixed by a
 guard that skips the repeated fill; the player's own report was *"the host now
 behaves like in singleplayer."*
- **The client can walk.** The client's movement component had 13 of 19 cached
 movement attributes zeroed, so the server's speed limit for that pawn computed
 `0.0` and pulled the player back on every step. Fixed by re-running the game's
 own attribute synchronisation once the data exists: `0.000 → 355.000`.
- **The client draws a weapon** and can shoot the host's world.

## What does not work

- **The whole session flow is being rebuilt around the hub (course change
 08-12).** Joining a running expedition — the old flow — is the hardest
 networking case Unreal has, and an expedition can never be *finished*
 together: the return to the hub is a local map load that tears the session
 apart. The new target is meeting in the hub and travelling together.
- **The joined client accepts no input — this is the blocker.** Not the camera
 only: no keys, no mouse, no menu key. The delivery path is healthy and that is
 measured, not assumed. Input events reach the process, reach the game's own
 input filter, reach the viewport dispatcher and reach the player controller —
 the last of those at a hundred percent of attempts, matching the host exactly,
 with the host measured as a control in the same seconds. What dies is further
 down: the movement binding is never invoked once, while on the host it runs
 every frame.

 Two separate causes are known so far. The first is fixed: the game turns
 global input off while a map loads and back on afterwards, and the client only
 ever did the first half. A patch calls the game's own script-callable setter to
 toggle it back, and the movement binding then starts dispatching — measured,
 from zero to full frame rate. It is not enough. After the client travels to the
 host the binding stops again with that flag on, so a second cause remains
 unidentified. The current lead is the pawn's input component, which carries
 fewer bindings on the client than on the host and never builds its cached key
 map.
- **Joining in the hub survives now.** The client used to die seconds after
 travel — a Blueprint timer event fired on an object destroyed by the travel.
 A null guard holds: 453 s of connection instead of death at 64 s. After a drop,
 the host's game thread still parks on a lock ~50 s later while the render keeps
 drawing.
- **The host is dropped to the main menu when its map reloads.** After resuming
 it returns to the same place and the client sees it where it was, so world
 state appears unaffected — but it costs a manual resume once per run. The
 trigger is not established.
- **Sprinting and sliding stutter; the client's magazine stays empty.** Both
 parked while the session flow is rebuilt — they may be symptoms of the
 mission-start sequence never running for the second player.
- Several HUD elements are not filled in for the client (potion counter, run
 currency, objective panel, own arrow on the minimap). The underlying data is
 correct — this is display only.

---

## How it works

- **Hosting is a two-byte patch.** `UEngine::LoadMap` checks whether the map URL
 contains `listen` and skips `UWorld::Listen` if not. Replacing that conditional
 jump with two `NOP`s makes the game call its own listen-server setup, with its
 own world and its own URL, at exactly the right point of its own mission
 startup. Forcing the map from outside instead (the first approach tried) breaks
 the mission sequence and was abandoned.
- **The mod almost never substitutes values.** When something is wrong, the fix
 is to run the game's own function again once its inputs are ready. Both working
 fixes are of that shape. Substituting a number is treated as *proof of cause*,
 not as a repair.
- **The game has no inventory replication at all.** `DimensionInventoryComponent`
 has 50 functions and zero RPCs; of 203 RPCs in the whole game, none draws a
 weapon. The authors knew how to replicate — `Actor`, `Character` and
 `DimensionWeapon` have replicated properties — they simply did not replicate
 this subsystem, because in a single-player game there was no reason to.
- **The same is true of the player state machine**: 47 functions, zero RPCs.
 Sprinting and sliding are states of that machine, driven by input — and the
 server has no input component for a remote player. That is why sprint desyncs
 while dash does not: dash is an *ability*, and abilities replicate.
- **Analysis runs offline.** Questions about the game's code are answered from an
 image of the executable, without a running game: disassembly, cross-references,
 string literals and function bounds all come from that image. The repository
 ships neither such an image nor any tool for producing one — `tools/obraz.py`
 reads an image the user supplies.

---

## Requirements

- **Every player needs their own, legally purchased copy of Witchfire.** This mod
 is not a way for two people to play from one copy, and it is not meant to be
 used that way.
- Linux with Proton, or Windows.
- Two instances of the game, each with its own prefix/save.
- Built with mingw-w64 (`x86_64-w64-mingw32-g++`).

This repository contains no game assets and no unreleased content — only source
code, tools and notes written for this project. The single exception is a handful
of short machine-code byte sequences quoted from the game in
`src/proxy-dll/dllmain.cpp`; they are technically required to check and install
the patches, they are **not** covered by this project's Apache 2.0 licence, and the file
says so at every place they appear.

This is not an official multiplayer mode and never will be one. It is not
affiliated with or endorsed by The Astronauts. Expect it to break.

The code, comments and documentation are currently in Polish; a switch to English
is planned.

---

## About the author, and about the AI — read this part

The project is run by one person working alone, roughly ten hours
a day and sometimes more, since **8 August 2026**. At the time of writing that is
about four days. It is a short, very intense stretch of work, and it is described
that way on purpose: nobody here is claiming months of effort.

**The code and most of the reverse engineering were produced together with an AI
model** (Claude, via Claude Code). That is not a footnote — it is most of the
typing. The model writes the C++, reads the disassembly, forms hypotheses and
keeps the documentation.

What the human does is not decoration either, and the repository has the receipts:

- **He runs the game, and only he can.** Nearly every finding here needed
 someone actually playing — sprinting, sliding, reloading — while hooks recorded
 what happened. Measurements taken without a real player produced silence that
 looked exactly like a result and was not.
- **He overturned the model's wrong conclusions, more than once.** The model
 concluded that the client's data was fine and only the HUD was lying. The
 player killed it with one sentence: *if it were only the display, the gun would
 still fire.* He was right; the measurement then showed the ammunition was zero
 on the server too.
- **He proposed the measurement that cracked the movement bug**: *check how the
 host's movement works, since he can move.* Comparing the two players inside one
 process is what located the exact instruction where the paths diverge.
- **He rejected fixes that were fakes.** A patch that returned a hard-coded speed
 ceiling was thrown out on the grounds that it substitutes a number instead of
 repairing a mechanism. That rule shaped the whole mod.

And the honest other half: **the model has been wrong repeatedly, in ways that
would have been shipped without a human checking.** It read one function as a
clamp and then as a fill, changing its mind twice from disassembly alone. It
guessed a byte value that turned out to be wrong, wrote in the notes that another
byte pattern was "measured in the game's code" when it had actually read a
synthetic code path, and twice wrote patches that crashed both game instances.
The documentation in this repository records those corrections on purpose,
because in this project the corrections were often worth more than the original
conclusions.

If you are looking for a project where the AI worked autonomously, this is not
it. It is also not a project where the AI was a spell-checker. It is somewhere in
the middle, and that is worth being precise about.

Full list of contributors: [CONTRIBUTORS.md](CONTRIBUTORS.md).

## Support

If you want to support the work: **https://ko-fi.com/mechhhh**

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

The license was chosen for one reason: **attribution**. If you distribute this
project or something derived from it, section 4 requires you to keep the NOTICE
file and pass its attribution along, so it stays visible that the work is based
on this project. Beyond that you are free to use, modify and redistribute it,
including commercially.

Open source, and intended to stay that way.

## Disclaimer

This modifies a single-player game's memory in your own process to enable
cooperative play. It is not a cheat for online games and is not designed for
anything of the sort. Use at your own risk; you are responsible for how you use
it.
