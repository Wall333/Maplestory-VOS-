# Changelog

## 2.2.2

- Make crystal-contact tolerance configurable independently of normal and
  randomized alignment tolerance, including crystals clamped to side anchors.
- Add optional directional teleport with a selectable key, estimated jump
  distance, and distance allowance. Use walking near the target and wait for
  a fresh frame after each teleport before moving again.
- Use existing Arduino arrow-down/up commands and support Windows input.
- Include the current saved settings: 20 px crystal contact, teleport off
  (V selected, 150 px distance, 25 px allowance), random tolerance 20–100 px,
  and randomized pre-move wait of 1–10 seconds.
- Add movement/input regression tests. Minimap remains experimental WIP.
- Known limitation: walking commands acknowledge transmission, not Arduino
  hold completion. A movement pause can clear early with short check intervals;
  this release retains the saved 0.5 s interval and 0.4 s hold and does not
  include a hold-completion fix.

## 2.2.1

- Add optional Magic Guard maintenance using `assets/magic guard.png`, with
  its own buff key, key hold, recovery wait, detection rate, and match threshold.
- Pause spam and alignment when Magic Guard is missing, cast its key, wait,
  and recheck before resuming. Thorns and Magic Guard are maintained
  sequentially; shop handling keeps priority over both.
- Show Magic Guard's detection state in live status and draw a yellow box
  around its detected icon. Add regression tests for recovery and shop priority.
- Retain minimap detection as experimental WIP.

## 2.2.0

- Add left and right side anchors to constrain auto-alignment's reachable
  horizontal range. Normal and crystal targets are clamped to those limits;
  reaching a limit satisfies an otherwise unreachable crystal.
- Make the side-anchor guide lines optional without changing movement limits.
  Crystal contact uses a 5 px tolerance and retires the targeted crystal guide
  even if the image remains visible.
- Add an experimental minimap marker checker (WIP). It locates the minimap,
  counts red markers, identifies the yellow player marker, and can draw debug
  boxes. Detection does not affect spam or movement and still needs live-game
  tuning; its controls and saved settings are included for testing.
- Add minimap regression tests and fix its startup colour-template error.

## 2.1.1

- Make automatic selling take priority over the map gate, buffs, movement,
  and skill spam as soon as a changed inventory is detected.
- Keep a sale latched when later inventory frames flicker, instead of
  alternating between selling and spamming.
- Exit the shop after confirmation disappears without depending on
  `invent_empty.png`; recheck inventory afterward and retry if it is still
  changed. Resume normal operation only after two fresh clean checks.
- Use the current saved `config.json` values as the built-in fallback defaults
  and in the Windows release package.

## 2.1.0

- Share one DreamMS capture stream across image detectors, reuse preprocessing,
  and track capture, matching, and frame-age timings.
- Add adaptive search and a fast character-tracking lane, plus configurable
  automatic or manual monster search bands.
- Add randomized alignment tolerance and pre-move delay: skill spam continues
  during preparation, pauses only during movement, and resumes when aligned.
- Prioritize crystals during alignment; retire a crystal guide after the
  character reaches its line even if the crystal remains visible.
- Keep shop test independent of spam/map gating, handle unexpected open shops,
  and separate activity logs from detector/performance diagnostics.
- Organize settings into tabs and provide movable in-game status and latency
  overlays.
