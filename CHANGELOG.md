# Changelog

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
