"""
Knights Talk backend.

Talks to the Electron UI with one JSON object per line on stdin/stdout.
The UI owns the microphone and the speakers; this process only does chess and
speech *recognition* (on audio the UI sends), so it works on any machine the
UI runs on.

Commands in  (stdin):
  {"cmd": "hello"}
  {"cmd": "new_game", "color": "white|black", "level": 0-20}
  {"cmd": "text",  "text": "e2 to e4"}               typed or already-transcribed input
  {"cmd": "audio", "pcm": "<base64 s16le mono>", "rate": 16000}
  {"cmd": "move",  "from": "e2", "to": "e4", "promotion": "q"}    board click
  {"cmd": "resign" | "draw" | "undo" | "hint" | "read_board" | "last_move" | "captured" | "help"}
  {"cmd": "set_level", "level": 5}
  {"cmd": "quit"}

Events out (stdout):
  {"type": "state", ...}                  see GameSession.state()
  {"type": "speak", "message": "..."}     the UI reads this aloud
  {"type": "transcript", "text": "..."}   what the recogniser heard
  {"type": "thinking", "on": true|false}
  {"type": "game_over", ...result}
  {"type": "error", "message": "..."}
"""
import json
import queue
import sys
import threading

import chess
import chess.engine

import speech
from game import GameSession
from voice_commands import describe_position, parse_command

HELP_TEXT = (
    "Say a move like e 2 to e 4, or knight to f 3. Say castle kingside, or castle queenside. "
    "Other commands: hint, undo, read board, repeat, captured pieces, offer draw, resign, new game."
)

_out_lock = threading.Lock()


def emit(**event):
    with _out_lock:
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()


class Controller:
    def __init__(self, session=None):
        self.game = session or GameSession()
        self.last_text = "No moves have been played yet."
        self.inbox = queue.Queue()
        self._offline_warned = False

    # ---- output helpers -----------------------------------------------------
    def speak(self, message):
        emit(type="speak", message=message)

    def push_state(self):
        emit(type="state", **self.game.state())

    # ---- command dispatch ---------------------------------------------------
    def handle(self, cmd):
        name = cmd.get("cmd")
        try:
            if name == "hello":
                self.push_state()
            elif name == "new_game":
                self.start_game(cmd.get("color"), cmd.get("level"))
            elif name == "set_level":
                self.game.level = max(0, min(20, int(cmd.get("level", 8))))
                self.push_state()
            elif name == "text":
                self.handle_text(cmd.get("text", ""))
            elif name == "audio":
                self.start_recognition(cmd)
            elif name == "move":
                self.handle_click_move(cmd)
            elif name in ("resign", "draw", "undo", "hint", "read_board", "last_move", "captured", "help"):
                self.run_command({"type": name})
            elif name == "quit":
                return False
        except FileNotFoundError as exc:
            emit(type="error", message=str(exc))
            self.speak("The chess engine could not be found.")
        except chess.engine.EngineError as exc:
            emit(type="error", message=f"Chess engine error: {exc}")
            self.speak("The chess engine stopped working. Say new game to restart it.")
            self.game.close()
        except Exception as exc:  # keep the app alive whatever happens
            emit(type="error", message=f"{type(exc).__name__}: {exc}")
        return True

    # ---- speech recognition runs off-thread so the game never blocks ---------------
    def start_recognition(self, cmd):
        def work():
            try:
                text = speech.recognize_pcm(cmd["pcm"], int(cmd.get("rate", 16000)))
            except speech.NothingHeard:
                emit(type="transcript", text="", heard=False)
                self.speak("Sorry, I didn't catch that. Please say it again.")
                return
            except speech.RecognitionUnavailable:
                emit(type="transcript", text="", heard=False)
                if not self._offline_warned:
                    self._offline_warned = True
                    self.speak("I can't reach the speech recognition service. "
                               "Check your internet connection, or type your move.")
                return
            except Exception as exc:
                emit(type="error", message=f"Speech recognition failed: {exc}")
                return
            self._offline_warned = False
            emit(type="transcript", text=text, heard=True)
            self.inbox.put({"cmd": "text", "text": text})

        threading.Thread(target=work, daemon=True).start()

    # ---- game flow ------------------------------------------------------------------
    def start_game(self, color=None, level=None):
        g = self.game
        g.new_game(color, level)
        self.last_text = "No moves have been played yet."
        self.push_state()
        if g.is_player_turn():
            self.speak(f"New game. You are {g.player_name}. It's your move.")
        else:
            self.speak(f"New game. You are {g.player_name}. Stockfish moves first.")
            self.engine_turn()

    def handle_text(self, text):
        command = parse_command(text, self.game.board)
        self.run_command(command)

    def run_command(self, command):
        g = self.game
        kind = command["type"]

        if kind == "new_game":
            return self.start_game(command.get("color"))
        if kind == "help":
            return self.speak(HELP_TEXT)
        if kind == "mic_off":
            return emit(type="mic", on=False)
        if kind == "unknown":
            return self.speak("Sorry, I didn't understand. Say help to hear what you can say.")
        if kind == "error":
            return self.speak(command["message"])

        if not g.active:
            if kind in ("move", "resign", "draw", "undo", "hint"):
                return self.speak("There is no game in progress. Say new game to start one.")
        if kind == "read_board":
            return self.speak(self.board_description())
        if kind == "last_move":
            return self.speak(self.last_text)
        if kind == "captured":
            return self.speak(self.captured_description())
        if kind == "resign":
            return self.finish(g.resign())
        if kind == "draw":
            return self.offer_draw()
        if kind == "undo":
            if g.undo():
                self.push_state()
                self.last_text = "Your last move was taken back."
                return self.speak("I took back your last move and Stockfish's reply. It's your move.")
            return self.speak("There is nothing to take back yet.")
        if kind == "hint":
            if not g.is_player_turn():
                return self.speak("Wait for your turn.")
            _, description = g.hint()
            return self.speak(f"Stockfish suggests {description}.")
        if kind == "move":
            return self.player_move(command["move"])

    def handle_click_move(self, cmd):
        g = self.game
        if not g.active or not g.is_player_turn():
            return
        try:
            frm = chess.parse_square(cmd["from"])
            to = chess.parse_square(cmd["to"])
        except (KeyError, ValueError):
            return
        promo = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}.get(cmd.get("promotion"))
        piece = g.board.piece_at(frm)
        if piece and piece.piece_type == chess.PAWN and chess.square_rank(to) in (0, 7):
            promo = promo or chess.QUEEN
        move = chess.Move(frm, to, promo)
        if move in g.board.legal_moves:
            self.player_move(move)
        else:
            self.speak("That move is not allowed.")

    def player_move(self, move):
        g = self.game
        if not g.is_player_turn():
            return self.speak("Please wait, it is not your turn.")
        description = g.describe(move)
        g.push(move)
        self.last_text = f"You played {description}."
        self.push_state()
        parts = [f"You played {description}."]
        result = g.check_game_over()
        if result:
            return self.finish(result, prefix=parts)
        if g.board.is_check():
            parts.append("Stockfish is in check.")
        self.speak(" ".join(parts))
        self.engine_turn()

    def engine_turn(self):
        g = self.game
        emit(type="thinking", on=True)
        try:
            move, description = g.engine_move()
        finally:
            emit(type="thinking", on=False)
        self.last_text = f"Stockfish played {description}."
        self.push_state()
        parts = [f"Stockfish plays {description}."]
        result = g.check_game_over()
        if result:
            return self.finish(result, prefix=parts)
        if g.board.is_check():
            parts.append("Check! Protect your king.")
        parts.append("Your move.")
        self.speak(" ".join(parts))

    def offer_draw(self):
        g = self.game
        if len(g.board.move_stack) < 10:
            return self.speak("Stockfish declines the draw. It's too early in the game.")
        if g.draw_acceptable():
            return self.finish(g.agree_draw())
        self.speak("Stockfish declines the draw offer.")

    def finish(self, result, prefix=()):
        self.push_state()
        emit(type="game_over", **result)
        self.speak(" ".join([*prefix, result["message"], "Say new game to play again."]))

    # ---- descriptions for blind players -----------------------------------------------
    def board_description(self):
        g = self.game
        mine, theirs = g.player_color, not g.player_color
        name = lambda c: "white" if c == chess.WHITE else "black"
        return (f"Your {name(mine)} pieces: {describe_position(g.board, mine)}. "
                f"Stockfish's {name(theirs)} pieces: {describe_position(g.board, theirs)}.")

    def captured_description(self):
        cap = self.game.captured()
        mine_key, theirs_key = ("byWhite", "byBlack") if self.game.player_color == chess.WHITE else ("byBlack", "byWhite")

        def say(symbols):
            if not symbols:
                return "nothing"
            counts = {}
            for s in symbols:
                counts[s.lower()] = counts.get(s.lower(), 0) + 1
            names = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen"}
            return ", ".join(f"{n} {names[k]}{'s' if n > 1 else ''}" for k, n in counts.items())

        return f"You have captured {say(cap[mine_key])}. Stockfish has captured {say(cap[theirs_key])}."


def reader(controller):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            controller.inbox.put(json.loads(line))
        except json.JSONDecodeError:
            emit(type="error", message="Bad command received.")
    controller.inbox.put({"cmd": "quit"})  # UI closed our stdin


def main():
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    controller = Controller()
    threading.Thread(target=reader, args=(controller,), daemon=True).start()
    try:
        while controller.handle(controller.inbox.get()):
            pass
    finally:
        controller.game.close()


if __name__ == "__main__":
    main()
