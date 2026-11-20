# Bug captures

A bug capture records where and how the game was when a player saw something wrong, so that the bug can be looked for
again at that place instead of somewhere else. The player presses **F8**; a test run then starts from what the press
wrote. Code: `runtime/bugcap.c`, `tools/capture_run.py`. Ocarina of Time 1.1.1 (the place and the camera come from the
debug tools, `runtime/debug_tools.c`); on other game versions a capture still has the picture, the timing, the
settings and the save.

## For the player

When you see a bug, press **F8** while the game window is in front. About a second later a note at the top of the
screen says *Bug capture 3 saved* with the folder's name. Tell whoever looks into the bug the number ("capture 3") and
what you saw; nothing else is needed. Press it as often as you like: each press is its own capture, and a press while
the one before is still being written is skipped.

The captures are in the game folder under `logs\captures`, one folder each, named by number and time
(`003-20261113-141502`). *Menu > Open log folder* shows `logs`. A capture is a few megabytes, most of it the picture (about
9 MB at 3440x1440 with HDR); delete old ones whenever you like. Nothing leaves your PC: a capture is files on your disk.

## Comparing motion vectors


On 1.1.1, the **Motion** tab shows whether forward ownership recording is enabled. Ownership hit/attempt counters are compiled out by default. To include them in a profiling build, set `NX2NAVI_PROFILE_OWNERSHIP=1` **when building** with the local game builder; no launch setting is needed. Prebuilt runtime archives cannot enable these counters. **Force reverse ownership lookup** skips forward capture and ignores previously recorded ownership ranges at replay. This compares against the lazy reverse fallback, not the old eager bind-time lookup. The switch takes effect at the next frame boundary and is not saved.

The named validation capture joined three simultaneously loaded world hearts to distinct live IDs. Each ID matched its replay ownership and two same-copy part/palette address pairs; none of those pairs was shared among the three. The load also logged a camera cut starting a new history. That confirms the reset event, not the appearance of the first frame after the cut.

The raw motion-vector view shows vector components, not a coverage mask. With the camera held still in Models mode, a stationary model can be black even when it writes a valid zero vector. Move a model to check for nonzero vectors; a black stationary silhouette alone cannot distinguish zero motion from missing coverage.

On 1.1.1, the per-view packet walker at `main+0x279510` is not the source of the indexed draws accepted by the motion picker in the warmed capture. Those draws came from reusable shape recordings first called at `main+0x67614`, `main+0x6d974`, `main+0x6b7d4`, and `main+0x590c4`. `runtime/nvn_api_cmd.c` (`nvnCommandBufferCallCommands`) reads the live work entry at those single-handle calls. Entry `+0x8` supplies the model owner and entry `+0x18` supplies the model shape, not the selector into the reusable recording table. The destination recording stores one optional ownership range around the copied commands; the source recording stays instance-neutral. Ordinary indexed draws carry no ownership payload, and later copies carry ownership ranges with the command bytes without scanning the copied stream.

In the warmed handoff capture, all 344,806 accepted indexed events agreed with the binding-based lifetime and shape; 246,206 also passed the same-copy binding check. These are replay events, not unique instances. `runtime/vk_skin_motion.inc` (`skin_pick`) checks the actual part and shader-selected palette before using the sample, and can resolve ownership from the bound part for commands without a usable sample. Neither a frustum survivor nor an accepted motion candidate alone proves that pixels were written.

In matched warmed SDR runs, the eager path made about 5,165 reverse lookups per motion frame; the default made about 435 work-entry lookups, 259 successful, and no reverse lookups in the sampled window. This measures lookup volume, not guest recording time. CPU motion replay and GPU motion timing did not materially change in the matched timing runs.

Enable **Debug menu (F9)** in the Game tab and open it with **F9**. **Motion Vectors** defaults to **Hybrid**
and switches on the next frame without saving to `nx2navi.ini`.

- **Off:** skips scene-depth reprojection and model replay; clears the motion texture to zero for active consumers.
- **Camera:** scene-depth camera reprojection only.
- **Models:** supported model draws write vectors over a zero background.
- **Hybrid:** supported model draws write vectors over camera reprojection.

Camera metadata and projection jitter remain active in every mode. Off also skips view-distance history for model visibility. Switching modes resets temporal history.

To check the switch, use the motion-vector debug view (`NX2NAVI_DLAA_MVDEBUG=1`) in a scene with both camera motion
and a moving character. **Off** should be black, **Camera** should show the reprojection across the scene, **Models**
should show vectors only at supported draws, and **Hybrid** should show both. Switch from **Hybrid** to **Off** for
several frames and back while moving: there should be no flash of the old vectors. With frame generation alone, check
that toggling the modes still supplies a valid camera when the scene has one.

Camera and Hybrid use direct clip reprojection.

Supported tracked draws use the existing `MoDraw` queue. A same-slot match of the actual bound part and
reflected palette adds model lifetime and shape to the mesh and shader key. Unkeyed draws keep their original
pairing rules; unsupported draws keep camera motion. There is no separate geometry capture or replay.

Program 4337's vertex shader was recovered by matching the capture's declared SHA-256 to the 1,408-byte native
program in the local shader cache. Offline motion translation reports position mask `0x58` (c3, c4, c6) and
previous-position output location 15. The disassembly loads location 6 as a float, bitcasts its first component to
an integer, and multiplies by 48 to address c6; the previous-position path repeats the load from c21. This is not
a constant-offset rigid transform. The live draw submitted location 6 as `NVN_FORMAT_R8UI` (format 3),
stream 0, byte offset 20, stride 24. This agrees with the byte offset of `_i0` in the local model's `FVTX`;
the asset record alone did not establish the submitted format or location.

`runtime/gfx_shader.c` (`reflect_palette`) distinguishes that raw-bit load from integer input provenance:
location 6 component 0 must be loaded as a 32-bit float, reinterpreted as a 32-bit integer, and used to address
the c6 palette with a 48-byte matrix stride. `runtime/vk_skin_motion.inc` (`skin_pick`, `skin_try`) requires a byte
joint input at the reflected location, the reflected palette in the motion variant's position-bank mask, and exact
part and palette ranges from the same copy of a registered shape. The palette range must contain whole matrices.
Neither the resource name nor the geometry's index count, base vertex, or byte layout identifies an instance.
Other draws still require unsigned integer formats for reflected joint inputs; numeric float conversions are not joint inputs.

### World pickup binding evidence (1.1.1)

`main+0x27ffa0` selects the packet entry at `x3+0xc8` or `+0xd0` using bit 0 of `w5`. On the ordinary
path it takes the model from entry `+8`, the shape index from entry `+0x18`, and selects an element of the
model's `+0x100` table with stride `0x70`. When `x4` is nonnull, `main+0x2800ac` instead uses `x4+0x10`
as the uniform source and gives `main+0x27f590` the selector `((flags >> 2) & 3) * width + (flags & 3)`
from the halfwords at `x4+0x88` and `+0x84`. On the built-in alignment path, `main+0x27f590` selects
`source[+0x80] + align_up(size, 256) * (selector + source[+0x48] * (source[+0x4a] >> 4))`, where `size`
is the word at `source+0x40`. It uses signed bytes from the binding record for per-stage indices, not a fixed
palette index. Its VS branch at `main+0x27f690` passes `(command, VS, index, address, size)` to
`nvnCommandBufferBindUniformBuffer` (proc slot initialized at `main+0x12a11e8`). The later call
at `main+0x280188` dispatches indexed geometry through `main+0x27fef0`, whose call at `main+0x27ff7c`
uses the index range and base vertex from the geometry record, not the palette. Palette copies are initialized
from the producer at wrapper `+0x20`: `main+0x14dfbc4` iterates `producer+0xa` descriptors of stride `0x48`
at `producer+0x38` and sizes each output in 48-byte matrices.

In the local `hearts-50664.txt` capture, join pre-`DRAW_IDX` vertex bindings by exact address and size: bank 4 to a
shape's part descriptor and bank 6 or 7 to its owner's palette descriptor from the same copy slot in
`scene-instance-map-50664.json`. All matching world-heart draws used bank 6. At `main+0x27ff7c`, events 634–636
match three different `Obj_Heart.Obj_Heart` wrappers; events 1846, 1850, 1852, 1854, 1856, 1858 and 1860 match
seven different wrappers. All ten matches are shape 0, copy 1, using VS index 1 for the part and VS index 3 for the
48-byte palette; the bound VS index 4 does not match their palettes. These are single-instance draws sharing an
index range. The seven matches at `main+0x2382c0` are separate blended, non-depth-writing draws.

The capture does not say whether a matching palette was bound by the nonnull-selector branch of `main+0x27ffa0`
or inherited from earlier setup. The descriptors were read after capture. This verifies the recorded binding
association, not cross-frame lifetimes or the output of keyed replay. The draw selects the bank by shader
reflection and uses the effective replay bindings, not the guest call site, to identify the instance.

The shared draw stack is a consumer path. In the 1.1.1 ARM64 code, no direct `B` or `BL` targets `main+0x6402e0`;
that is consistent with callback entry, but does not identify its registration. This entry dispatches on the work
descriptor's type at `x1+0x1c`. Its call at `main+0x6402f4` is the only direct caller of `main+0x640320`, which reads
fields at `x1+0x0`, `+0x8`, `+0x10` and the type at `+0x18`. The direct callers of `main+0x27ffa0` are
`main+0x27a694`, `main+0x27b10c`, `main+0x27b92c`, `main+0x27bef0`, and `main+0x27ce48`. These xrefs do not show
who writes the descriptor or the instance transform.

The callback registration is now identified: `main+0xecb788`/`+0xecb78c` materialize the function pointer,
`main+0xecb790` stores it, and `main+0xecb794` calls `main+0xecd160` with ID `0x10518bd0`. The initializer at
`main+0xe2cd98`–`+0xe2cddc` builds the matching registry record at `main+0x4e95420`. The callee at
`main+0xe2d090` stores registration triples in a 24-byte table, and `main+0xecd160` links registrations by ID.
The companion path at `main+0x66f800` unlinks registrations; it is not an enqueue site. The callback's type-1
branch at `main+0x63fe30` also reads the incoming descriptor. None of these sites has been verified to create
per-draw work or produce the instance transform; the needed evidence is the caller that builds the descriptor
passed as `x1`, not the registry record's initializer.

## What a capture holds

| File | What |
|---|---|
| `capture.txt` | Written last: a folder that has it is complete. `key = value` lines under `[sections]`, see below |
| `frame.png` | The frame on screen as the window got it, the overlay included, without the capture's own note (an HDR picture converted to sRGB) |
| `frames.tsv` | The last 600 presents before the press and the 30 after: frame, interval and replay time in ms |
| `log-tail.txt` | The last 256 KB of the run's log |
| `settings.ini` | Every setting that had a value (from `nx2navi.ini`, the menu or the environment) as `nx2navi.ini` lines, without the private ones (`runtime/cfg_private.h`) |
| `NX2navi-save-<time>.zip` | The save the game would load next, as *Menu > Export save* writes it |
| `flags.tsv`, `texts.tsv` | The game's on/off flags and its 64-character texts, by the hash of their names |
| `flight/` | With `flight = 1`: the flight recorder's dump of the same moment (`tools/flight_view.py` reads it) |

`capture.txt`:

- `[capture]`: `number`, `name`, `time`, `time_utc`, `trigger` (`F8`, `NX2NAVI_CAPTURE_AT`, `replay`), the NX2navi and
  game versions, the presented `frame`, `run_seconds`, `menu_open`.
- `[place]`: `area` (the game's own name, which says child or adult for the outdoor areas: `HyruleField_Adult`),
  `player_pos` in metres (`none` at the title screen and while loading), `player_rot` (Link's 3x3 rotation by rows) and
  `player_yaw`, and `nearest_start`, the area's start position nearest to him, when the list of start positions was
  read (the debug menu or a test reads it).
- `[camera]`: `camera_pos`, `camera_dir`, `camera_yaw` and `camera_pitch` (radians; the camera looks along
  `(cos pitch sin yaw, sin pitch, cos pitch cos yaw)`, the free camera's convention) with `camera_source`: the frame on
  screen when DLSS, DLAA or FSR runs (then also `camera_fov_y_degrees`, `camera_aspect`, the near and far planes),
  else the free camera when it is on, else the game's own camera. `game_camera_pos` / `game_camera_target` and
  `event_camera_pos` / `event_camera_target` are the game's two scene cameras as its camera update chose them in the
  frames after the press, whatever was drawn.
- `[picture]`: the window's size, the game image's size, HDR, the scaler, the present mode, the display's rate.
- `[timing]`: over the presents before the press: the average frame rate, the median, 95th and 99th percentile and
  the longest frame time, how many frames took over 33 and 50 ms, the last 30 intervals before and the first after,
  and the performance overlay's numbers when it was on.
- `[system]`: OS, CPU, RAM, GPU, driver.
- `[settings that differ from the defaults]`: the settings whose value is not the default; a private one shows only
  that it is set.

Position, rotation, area and the camera of the frame on screen are read on the render thread at the press, so they
belong to the frame the timing ends with; the picture is the next present.

## Starting a test run from a capture

```
python tools/capture_run.py 3
python tools/capture_run.py "C:\...\game\logs\captures\003-20261113-141502" --set FSR4=0 --hold 30
```

The argument is a capture's folder or its number under the installed game's `logs\captures` (`--game` names another
game folder). The script

1. refuses to start while a game is running (one game at a time);
2. makes a throwaway profile: the game's own profile without its saves, with the capture's save as a waiting import,
   which the game makes the save when it starts;
3. starts the game with `NX2NAVI_CAPTURE_REPLAY=<the capture's folder>`, in a window of the capture's size that takes
   neither the focus nor your input (`--foreground` and `--fullscreen` change that), co-op and Discord off;
4. waits while the game presses A through the title screen and the file menu, teleports to the capture's area,
   walks Link to where he stood, puts the free camera where the camera was and takes a capture of its own;
5. closes the game and prints both captures side by side: area, positions, the distance between them, cameras, and
   the mean difference of the two pictures.

The run's log and its capture are in `<capture>/replays` (`--out` names another folder). `--set KEY=VALUE` puts one
setting on top of the capture's for this run, which is how a suspected setting is tried: run once as captured and
once with `--set`. `--hold <seconds>` keeps the game open after its capture; `--no-camera` leaves the camera to the
game, for a bug that is about the camera itself. Any other test setting can ride along with `--set` (`DUMP`, `SHOT_DIR`
and `SHOT_EVERY`, `DBG_TEST`, `TRACE`).

What the game does in such a run (`NX2NAVI_CAPTURE_REPLAY`, environment only):

- The capture's `settings.ini` stands in for `nx2navi.ini`, which is neither read nor written; the environment still
  wins over it. The log's first lines say so and list the settings.
- Until Link appears the pad presses A (four reads in every hundred).
- Three seconds later the game changes area as its own doors do (`dbg_warp`), to the start position of the capture's
  area that is nearest to the captured place; when the save already starts within 60 m of it, there is no teleport.
  A refused teleport (an event still running after the load) is asked again, up to six times.
- Link runs to the captured `x z` (`dbg_route_to`), steered by the game's own camera and walking the last three
  metres, and counts as there within half a metre. He is walked, not put: his position cannot be written
  (`debug_tools.c`). When something is in the way he sidesteps, and after ten tries the walk is given up where he is.
  When he does not move at all for two seconds, the game holds him (a conversation that began where the teleport
  arrived, on a save that had not been there): A is pressed until he moves, and the walk is asked for again.
- The free camera is turned on standing (the pad still plays the game) and put at `camera_pos`, `camera_yaw`,
  `camera_pitch`. `NX2NAVI_CAPTURE_REPLAY_CAMERA=0` leaves the game's camera.
- Three seconds later the log says `capture: replay of <name> ready: ...` with how far Link is from the captured
  place, and the run takes its own capture (`trigger = replay`), whose `capture.txt` adds `replay_of`,
  `replay_player_off_metres`, `replay_walk` and `replay_camera`.

What a replay does not bring back: the time of day, enemies and other actors, Link's pose and what he holds, an event
or cutscene that was running, the camera's field of view where the game had changed it (the comparison shows both),
and progress made since the last save (the save is the one on disk at the press; the flags that differed are in
`flags.tsv`). A capture taken at the title screen or while loading has no area: its replay applies the settings and
stops.

Measured on the PC the feature was written on (RX 7900 XT, HDR on): in a 3232x1352 window a capture is written in
1.2 s and holds about 9 MB, eight of them the picture; in a 1720x720 window 0.6 to 0.8 s and 3.5 MB. The frame after
the press is some 10 ms longer, for the read-back of the picture. A replay of a capture taken three metres from where
the save starts took 45 s from start to its own capture, with Link 0.4 to 0.5 m from the captured place and the
camera's position and angles equal to the last digit; one that teleports to another area and ends a conversation on
the way took about 100 s.

Without the script: set `NX2NAVI_CAPTURE_REPLAY` to the folder and start the game with `--profile <a copy of a
profile>`; `NX2NAVI_CAPTURE_DIR` says where the run's own capture goes (default `<capture>/replays`).

## Test settings

Environment or `nx2navi.ini`, for runs without a keyboard:

- `NX2NAVI_CAPTURE_AT=<frame>[,<frame>...]`: a capture at each of those presented frames (up to 16).
- `NX2NAVI_CAPTURE_DIR=<folder>`: the folder captures go to, in place of `logs/captures`.

## The flight recorder

`flight = 1` keeps a ring of the last frames with a small picture each (`runtime/flight.c`). Its dump on F8 now
belongs to the capture: it goes to the capture's `flight` folder. Its other dumps (a frame over `flight_spike_ms`,
`NX2NAVI_FLIGHT_AT`, `NX2NAVI_FLIGHT_EVERY`) go to the `flight` folder beside the game folder as before.
