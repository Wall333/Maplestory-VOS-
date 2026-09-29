# Maplestory VOS

Current release: **2.1.0**. See [CHANGELOG.md](CHANGELOG.md) for the release
summary. This repository contains the full Python source, image assets,
Arduino/Teensy firmware, tests, and a self-contained Windows release ZIP.

A separate Windows helper that repeatedly sends a selected key while
`DreamMS.exe` is the foreground window. Available spam keys are `End`,
`Page Down`, `X`, `C`, `V`, `B`, `D`, `F`, and `Y`.

## Current packaged defaults

- Spam `F` every 2 seconds.
- Manual green anchor at the horizontal center (`0px`).
- Auto-align enabled with a 0.4s movement hold. Random mode is on by default:
  50–200px happy tolerance and a 2–10s pre-move wait while spam continues.
  Fixed-mode values (when random mode is off) are 200px tolerance and a 0.5s
  correction interval.
- Crystal display/looting, Yeti-required spam, and Thorns maintenance enabled.
- Map threshold `0.60`; alignment threshold `0.70`; Yeti threshold `0.70`; Thorns threshold `0.50`.
- Automatic Yeti vertical band (120 px padding; full reacquisition every 2 seconds).
- Spam badge at horizontal `85%`, vertical `4%`; latency badge at `20%`, `5%`.

## Portable Windows package

Download `Maplestory-VOS-v2.1.0-Windows-x64.zip` from the GitHub release,
extract the **entire** archive, and run `Maplestory-VOS.exe`. It includes Python and the required desktop
libraries; the other files and `_internal` directory must stay beside the EXE.
Settings and logs are written beside the EXE, so extract to a writable folder
(not `Program Files`). The Arduino/Teensy firmware still needs to be flashed to
the device once; it cannot be bundled into the Windows executable.

## Run from source

1. Install Python dependencies: `pip install -r requirements.txt`
2. Flash the updated Arduino sketch once (see below).
3. Run `run_vos_bot.bat`.

To build the portable Windows package yourself, install `pyinstaller` as well
and run `powershell -ExecutionPolicy Bypass -File .\build_release.ps1` from
this directory. The ZIP is written to `Releases/`.

Defaults: `F11` toggles the whole helper, and `F10` starts/stops VoS spam.
The output key, hold time, repeat interval, COM port, and hotkeys are editable.
The GUI keeps live Status and a prominent **Save settings** button at the top,
Logs at the bottom, and
groups feature controls into Spam, Alignment, Shop, Buff / Map, and General
tabs. Save after editing entry fields or selecting the character marker;
smaller windows can still scroll within each tab. Tabs are left-aligned. Drag
the divider above Logs to resize the log area, then click **Save settings**
to remember its height for the next launch.

The spam loop stops automatically if DreamMS loses focus. Turning off Arduino
mode uses Windows `SendInput` as a testing fallback.

The optional VoS Map Checker searches the active DreamMS client for
`assets/VOS_map.png`. Once found, it checks the exact cached position first;
if that misses, it immediately searches the full game window and updates the
cache when found elsewhere. If the map is absent, VoS stays enabled but pauses
with **Waiting for map**, then resumes automatically when it reappears.
Detection rate and match threshold are configurable in the GUI.

The optional Character / Area Alignment Test can track either `assets/lightbulb.png`
or the two-chevron shape derived at runtime from `assets/tracker.png` (choose
**arrows** under Character marker, then save). The arrows use a shape/edge model
instead of matching their changing colors or the background in the PNG. Arrow
tracking has its own shape threshold (default `0.60`); raise it if scenery
causes false matches. The lightbulb keeps the alignment match threshold.
The tracker also detects `assets/area.png`. Its transparent, click-through overlay draws a cyan line
downward from the character marker and a green vertical target line through the
middle of the rock-area template. The status row shows both live match scores.

### Vision performance

Character matching has its own single-worker lane, separate from the three
general matching workers. The periodic performance log reports
`character.queue` (time waiting for that worker), `character.match` (actual
search time), and `cycle.character` (total time to publish the result).
Character tracking also consumes shared capture frames in its own loop, so
slow area/crystal searches cannot hold back the next character check.

The Alignment tab has a separate **Show latency badge in game** checkbox and
horizontal/vertical position sliders. The badge is click-through and can be
repositioned with those sliders; its position is saved. The always-visible
Status panel shows rolling capture FPS, capture and grayscale time, plus
character processing time and the age of the frame when the character result
was published. These are software-side timings, not measured display or input
latency. Character figures appear when tracking is enabled and producing results.

One capture thread now screenshots the active DreamMS client once per frame and
publishes the same color frame plus one grayscale conversion to all detectors.
The arrow tracker reuses that grayscale frame. Templates are loaded once, and a
bounded pool of three workers runs independent matches (including concurrent
Yeti/Crown and alignment searches). Existing color matching is retained for
other assets so their thresholds do not silently change.

Most moving targets first search a padded region around their last match, then
immediately search the full client if the local attempt fails. The **Moving-target
ROI padding** field on General defaults to 120 pixels and is saved with the
other settings. Yeti/Crown instead uses the full-width vertical band described
below. With a manual anchor, the unused `area.png` search is skipped.
When a Yeti/Crown match is enough for the spam gate, remaining queued matches
may be cancelled; enabling its debug boxes still checks all four images.

Every 30 seconds, the log reports rolling average and maximum milliseconds for
capture, grayscale, each template's local/full/total match, each detector cycle,
and frame age at detection. On a synthetic 1920×1080 test on the development PC,
arrow plus crystal matching took about 93 ms for a full search and 6 ms with
cached local hits. These are not live-game latency measurements. A local
comparison found OpenCV's default 24 internal threads plus three match workers
faster than forcing OpenCV to one thread, so the default was retained. Run
`python benchmark_vision.py --width 1920 --height 1080` to compare serial and
three-worker matching on your own PC without starting the bot.

The normal green target can use either the center of `area.png` or a manual
horizontal anchor. Manual offset `0` is the center of the DreamMS client;
negative pixel offsets move the target left and positive offsets move it right.
The visual guide and auto-alignment use the same selected target.

Auto alignment can optionally use those two center lines while VoS spam is
running. Inside the configured pixel tolerance it does nothing; outside the
tolerance it taps `LEFT` or `RIGHT` through the selected Arduino/Windows input
path. Skill spam pauses with a **Moving** status while the character is outside
the allowed tolerance, then resumes after a fresh tracker result confirms it
is back inside. Movement key hold and correction interval should be tuned
conservatively to avoid overshooting the target.

The optional **Movement randomizer** on the Alignment tab replaces the fixed
happy tolerance and correction interval with per-move ranges. Set minimum and
maximum tolerance in pixels and minimum and maximum wait in seconds, then save.
The GUI disables whichever set of numeric controls is inactive so it is clear
which values apply; movement key hold applies in both modes.
For each correction, the bot chooses one value from each range and keeps skill
spam running during the randomized wait. Once the wait expires, it checks the
latest tracked position; if still outside tolerance, it pauses spam with
**Moving** and keeps correcting without another randomized wait until aligned.
If the character reaches tolerance during preparation, the queued move is
cancelled. Leave the randomizer off to retain the fixed tolerance/interval
behavior.

The in-game overlay can show a large live `SPAMMER ON/OFF` badge. Enabling
**Show crystal** detects `assets/crystal.png` and draws a red vertical guide
while the crystal remains visible. With **Loot crystal** enabled,
auto-alignment prioritizes that red line, even during a pending randomized
move. Crystal contact uses a tight 5 px threshold instead of the normal happy
tolerance. Once the character reaches the line, that crystal's red guide is
retired and alignment returns to the normal target, even if the crystal image
remains visible because it cannot be looted. The same crystal is ignored until
it disappears for several checks; a newly appearing crystal can be targeted.

The resizable log area has two tabs: **Activity** for start/stop, shop/selling,
buff actions, and errors; **Diagnostics** for detector changes, template match
scores, and vision performance summaries. The corresponding text files are
`activity_logs.txt` and `diagnostic_logs.txt` beside `config.json`.
`recent_logs.txt` still contains the combined history for compatibility.

The spam status overlay can be shown or hidden independently. Horizontal and
vertical position sliders move it live using percentages of the DreamMS client,
and the selected position is saved automatically.

The optional **Yeti/Crown required** gate checks for `assets/yeti.png`, `assets/yeti2.png`,
`assets/crown.png`, or `assets/crown2.png`. With the gate enabled, only skill spam
pauses while all four are absent, then resumes when any one is detected.
Auto-alignment continues moving during this
wait. The GUI and in-game badge distinguish the waiting state from ON/OFF.

After a match, Yeti/Crown checks search the full width of a learned vertical
band instead of the whole window. **Monster vertical band padding** sets how
far above/below a detected monster the band extends (default 120 px). A
full-window scan still runs periodically (default every 2 seconds) to discover
monsters at a different height and update the band. Before the first match,
only those periodic full scans run. A monster appearing outside the band can
therefore take up to the full-scan interval to be detected. The performance
log distinguishes `*.band` from `*.full` search time.

Alternatively, enable **Use manual monster search area** on the Spam tab.
The top and bottom sliders are pixel offsets from the game window's vertical
centre (0); negative values are above centre. This mode searches the full
width only between those two lines and does **not** do periodic full-window
reacquisition, so monsters outside the chosen band will be missed. **Show
monster search area in game** draws the two orange horizontal boundaries,
independently of the detected-monster boxes. Slider positions save automatically.

Enable **Draw box around detected Yeti/Crown** to show an orange outline at the
best match for each of the four templates. This debug display works independently
of the spam gate and uses the same Yeti/Crown threshold.

Optional Thorns maintenance checks `assets/thorns.png` with its own detection
rate and threshold. If the icon is missing during an active spam session, spam
and movement pause, the configured buff key is sent, and the helper waits the
configured recovery period (five seconds by default). It resumes only after
the wait has elapsed and Thorns is detected; otherwise it retries. A small
yellow rectangle marks the matched buff icon in the in-game overlay.

## Arduino compatibility

Automatic selling is optional. Enable the inventory debug box first and show
the inventory window: green indicates the clean grid and red indicates a
changed grid. Selling triggers on any detected grid change, not a count of full
slots. The inventory header must remain visible for this comparison.

The inventory check rate is adjustable from 1 to 30 checks per second (default 5).
This controls how often the inventory debug box and selling image checks update;
higher rates use more CPU. Enter a rate and save settings to apply it.

While VoS spam is running, the bot also checks `shop_open.png` for a shop that
was opened unexpectedly. The shop-open check rate is separate (default once per
second, adjustable from 0.2 to 10 per second). If the inventory is clean or
`invent_empty.png` is visible, it closes the shop. If the inventory has changed,
the **Sell changed inventory if shop is already open** option continues the
selling sequence when automatic selling is enabled; otherwise it closes the
shop. Spam pauses while the shop is being handled. If inventory cannot be
classified, the bot waits rather than selling blindly.

Inventory-triggered automatic selling requires VoS spam to be ON. The enabled
F8 shop test runs one cycle with spam ON or OFF, independently of the VoS map
gate. DreamMS must be foreground. Normal spam resumes only if its map check
passes after the test finishes.

Enable **Shop test hotkey** to run one selling cycle with F8 (configurable).
It bypasses the inventory-change trigger and works with automatic selling
disabled. During active spam it pauses inputs for the cycle and resumes
afterward; with spam off it runs the cycle alone. Repeated hotkey presses during
selling are ignored. DreamMS must be foreground; losing focus cancels the test.

The sequence clicks `shop.png`, waits for `shop_open.png`, clicks
`sell_button.png`, confirms `sell_confirm.png` with Y, then requires both
`shop_open.png` and `invent_empty.png` before clicking `shop_exit.png`. Inputs
are spaced by one second and spam/movement pause throughout selling. The shop
must disappear before spam resumes. Missing templates leave the sequence
waiting rather than advancing blindly.

The in-game badge and VoS status say **BUFFING** while the Thorns buff key is
being cast or the configured post-cast wait is in progress.

Character and green target alignment guides hide temporarily during selling
and return afterward if their overlay checkbox is enabled. The saved checkbox
preference is preserved.

Mouse positioning uses Windows screen coordinates; left clicks use the new
Arduino `CLICK` command. Reflash the updated firmware once for mouse support.
Windows fallback mode uses Windows mouse clicks instead.

The updated sketch is in `arduino_teensy_vos/arduino_teensy_vos.ino`. It keeps
all commands used by the Aran helper and adds the complete VoS key list. Because
those commands do not all exist in the old flashed firmware, the board must be
flashed once to add them; it does not need to be reflashed when switching
between apps.
