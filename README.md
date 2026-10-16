# ♞ Knights Talk – Voice-Controlled Chess for Accessibility

**Knights Talk** is an innovative voice-powered chess game built to ensure that everyone, including individuals with motor disabilities or visual impairments, can fully enjoy the game of chess. By leveraging speech recognition technology, users can interact with the chessboard entirely through voice commands—issuing moves, undoing steps, or even resetting the board—without ever needing a mouse or keyboard.

The game is designed with accessibility, simplicity, and inclusivity in mind. Whether you're a beginner learning the rules or a seasoned player looking to play hands-free, Knights Talk offers an intuitive and empowering chess experience.

### 🔧 Key Features:

* 🎤 Hands-free voice control (e.g. “e2 to e4”, “knight to f3”, “castle kingside”)
* ♙ Standard rules and gameplay for classic chess
* 🖥️ Cross-platform support (Windows and Linux builds)
* 💬 Clear voice feedback for every move and interaction
* 🧑‍🦽 Designed with accessibility-first principles

---

### 🆕 What's new in 2.0

* **Voice is captured and spoken in the app window, not in the backend.** The microphone is recorded by the UI and sent to the backend for recognition; replies are read aloud by the UI. This is what makes the game work on a remote or virtual machine — the audio devices that matter are the ones on the machine you are sitting at.
* **Clear game results.** Checkmate, stalemate, resignation, agreed draw, insufficient material, threefold/fivefold repetition and the 50/75-move rules are all detected, announced aloud and shown in a result dialog with the score (1-0, 0-1, ½-½) and a *Play again* button.
* **Resign / draw / undo / hint by voice or button.** Stockfish accepts a draw offer only when it is not clearly better.
* **Play as White or Black**, with 21 difficulty levels.
* **Modern UI**: dark theme, vector pieces, last-move/check/legal-move highlights, click-to-move, captured pieces and material advantage beside each player, move list, live conversation log, high-contrast board option.
* **Accessible by design**: every control is keyboard reachable, arrow keys move around the board, screen-reader labels on all squares, “read the board” and “captured pieces” voice commands, adjustable voice, speed and microphone sensitivity.
* A smarter command parser: understands “e to e 4” (mis-heard “e2 e4”), number words, NATO letters, piece names, castling, promotion, UCI and SAN.
* One shared code base for Windows and Linux (it used to be two diverging copies).

### 🗣️ What you can say

| Goal | Examples |
|---|---|
| Move | “e2 to e4”, “knight to f3”, “g1 f3”, “castle kingside”, “a7 a8 promote to knight” |
| Game | “new game”, “play as black”, “undo”, “offer a draw”, “resign” |
| Information | “hint”, “read the board”, “repeat”, “captured pieces”, “help” |
| Microphone | “stop listening” (press **M** to start again) |

Keys: **M** microphone · **Enter** start / play again · **Esc** stop speech · **/** focus the command box · **F1** help.

### 🏗️ Architecture

```
app/
  main.js, preload.js       Electron shell; starts the Python backend, passes JSON lines both ways
  renderer/                 UI: board, mic capture + voice-activity detection (voice-input.js), text-to-speech (speaker.js)
  backend/
    app.py                  JSON-lines protocol loop
    game.py                 board, Stockfish, captured pieces, game-over detection
    voice_commands.py       natural-language → move/command parser
    speech.py               speech-to-text of audio sent by the UI
    tests/                  parser, game rules and end-to-end protocol tests
    stockfish/              Stockfish builds for Linux and Windows
```

Speech recognition uses Google's free web recogniser, so **an internet connection is required for voice input** (typing always works). Text-to-speech uses the operating system's voices; on Linux install `speech-dispatcher` and `espeak-ng`.

### 🧑‍💻 Development

```bash
cd app
npm install
pip install -r backend/requirements.txt
npm start                      # runs the UI with the Python backend from source
npm run test:backend           # parser, game and protocol tests
npm run dist:linux             # or dist:win — bundles the backend with PyInstaller, then packages with electron-builder
```

---

### 📦 Download Builds

* 🔗 [Download Knights Talk – Windows Build (.exe)](https://drive.google.com/drive/folders/1QehG5GFtLDYsTzh327CJgN2_KGjQj1wi?usp=sharing)
* 🔗 [Download Knights Talk – Linux Build (.AppImage / .deb)](https://drive.google.com/drive/folders/1XbfPC2X9N8b1Z_rtw6idjMesJRFMJ9dW?usp=sharing)

---