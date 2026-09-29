#include <Arduino.h>
#include <Keyboard.h>
#include <Mouse.h>

void pressKey(uint8_t key, int delayMs) {
  Keyboard.press(key);
  if (delayMs > 0) delay(delayMs);
  Keyboard.release(key);
}

void setup() {
  Serial.begin(9600);
  Keyboard.begin();
  Mouse.begin();
}

void loop() {
  if (!Serial.available()) return;

  String command = Serial.readStringUntil('\n');
  command.trim();
  int spaceIndex = command.indexOf(' ');
  String cmd = (spaceIndex > 0) ? command.substring(0, spaceIndex) : command;
  int delayMs = (spaceIndex > 0) ? command.substring(spaceIndex + 1).toInt() : 10;

  // VoS commands.
  if (cmd == "CLICK") Mouse.click(MOUSE_LEFT);
  if (cmd == "END") pressKey(KEY_END, delayMs);
  if (cmd == "PGDN" || cmd == "PAGEDOWN") pressKey(KEY_PAGE_DOWN, delayMs);
  if (cmd == "X") pressKey('x', delayMs);
  if (cmd == "C") pressKey('c', delayMs);
  if (cmd == "V") pressKey('v', delayMs);
  if (cmd == "B") pressKey('b', delayMs);
  if (cmd == "D") pressKey('d', delayMs);
  if (cmd == "Y") pressKey('y', delayMs);

  // Existing Aran commands, retained for one shared firmware.
  if (cmd == "F") pressKey('f', delayMs);
  if (cmd == "ALT" || cmd == "JUMP" || cmd == "COMBAT") pressKey(KEY_LEFT_ALT, delayMs);
  if (cmd == "CTRL") pressKey(KEY_LEFT_CTRL, delayMs);
  if (cmd == "LEFT") pressKey(KEY_LEFT_ARROW, delayMs);
  if (cmd == "RIGHT") pressKey(KEY_RIGHT_ARROW, delayMs);
  if (cmd == "UP") pressKey(KEY_UP_ARROW, delayMs);
  if (cmd == "DOWN") pressKey(KEY_DOWN_ARROW, delayMs);

  if (cmd == "DOWN_DOWN") Keyboard.press(KEY_DOWN_ARROW);
  if (cmd == "DOWN_UP") Keyboard.release(KEY_DOWN_ARROW);
  if (cmd == "LEFT_DOWN") Keyboard.press(KEY_LEFT_ARROW);
  if (cmd == "LEFT_UP") Keyboard.release(KEY_LEFT_ARROW);
  if (cmd == "RIGHT_DOWN") Keyboard.press(KEY_RIGHT_ARROW);
  if (cmd == "RIGHT_UP") Keyboard.release(KEY_RIGHT_ARROW);
}
