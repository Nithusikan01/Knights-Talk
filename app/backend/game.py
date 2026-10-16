"""Game logic: board, engine, captured pieces and game-over detection. No I/O in here."""
import os
import platform
import shutil
import stat
import sys

import chess
import chess.engine

from voice_commands import describe_move


def stockfish_path():
    """Finds the Stockfish binary for this OS (works from source and from a PyInstaller bundle)."""
    override = os.environ.get("KNIGHTS_STOCKFISH")
    if override and os.path.exists(override):
        return override
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    names = {
        "Linux": "stockfish-ubuntu-x86-64",
        "Windows": "stockfish-windows-x86-64.exe",
    }
    candidates = []
    name = names.get(platform.system())
    if name:
        candidates.append(os.path.join(base, "stockfish", name))
    system_wide = shutil.which("stockfish")
    if system_wide:
        candidates.append(system_wide)
    for path in candidates:
        if os.path.exists(path):
            if os.name != "nt" and not os.access(path, os.X_OK):
                try:
                    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except OSError:
                    pass
            return path
    raise FileNotFoundError(
        "Stockfish was not found for this operating system. Install it or set KNIGHTS_STOCKFISH.")


class GameSession:
    def __init__(self, engine_path=None):
        self.engine_path = engine_path
        self.engine = None
        self.board = chess.Board()
        self.player_color = chess.WHITE
        self.level = 8  # 0-20, Stockfish "Skill Level"
        self.active = False
        self.result = None  # dict once the game has ended

    # ---- engine ---------------------------------------------------------
    def _ensure_engine(self):
        if self.engine is None:
            path = self.engine_path or stockfish_path()
            self.engine = chess.engine.SimpleEngine.popen_uci(path)
        self.engine.configure({"Skill Level": self.level})

    def close(self):
        if self.engine is not None:
            try:
                self.engine.quit()
            except Exception:
                pass
            self.engine = None

    def _think_time(self):
        return 0.3 + self.level * 0.1  # 0.3s on level 0 up to 2.3s on level 20

    # ---- lifecycle --------------------------------------------------------
    def new_game(self, color=None, level=None):
        if level is not None:
            self.level = max(0, min(20, int(level)))
        if color in ("white", "black"):
            self.player_color = chess.WHITE if color == "white" else chess.BLACK
        self._ensure_engine()
        self.board = chess.Board()
        self.active = True
        self.result = None

    @property
    def player_name(self):
        return "white" if self.player_color == chess.WHITE else "black"

    def is_player_turn(self):
        return self.board.turn == self.player_color

    # ---- moves ------------------------------------------------------------
    def describe(self, move):
        return describe_move(self.board, move)

    def push(self, move):
        """Plays a move and returns a spoken suffix for check / game-over notices."""
        san = self.board.san(move)
        self.board.push(move)
        return san

    def engine_move(self):
        """Lets Stockfish move. Returns (move, description) with the description made before pushing."""
        self._ensure_engine()
        result = self.engine.play(self.board, chess.engine.Limit(time=self._think_time()))
        description = describe_move(self.board, result.move)
        self.push(result.move)
        return result.move, description

    def hint(self):
        self._ensure_engine()
        self.engine.configure({"Skill Level": 20})
        try:
            info = self.engine.analyse(self.board, chess.engine.Limit(time=0.5))
        finally:
            self.engine.configure({"Skill Level": self.level})
        move = info["pv"][0]
        return move, describe_move(self.board, move)

    def undo(self):
        """Takes back the player's last move and the engine's reply. Returns False if impossible."""
        if not self.is_player_turn() or len(self.board.move_stack) < (2 if self.player_color == chess.WHITE else 3):
            return False
        self.board.pop()
        self.board.pop()
        return True

    def draw_acceptable(self):
        """Stockfish accepts a draw when it is not clearly better."""
        self._ensure_engine()
        info = self.engine.analyse(self.board, chess.engine.Limit(time=0.4))
        engine_color = not self.player_color
        score = info["score"].pov(engine_color).score(mate_score=10000)
        return score <= 25

    # ---- end of game ---------------------------------------------------------
    def check_game_over(self):
        """Sets and returns self.result if the game has ended by the rules."""
        b = self.board
        outcome = b.outcome(claim_draw=True)
        if outcome is None:
            return None
        reason = {
            chess.Termination.CHECKMATE: "checkmate",
            chess.Termination.STALEMATE: "stalemate",
            chess.Termination.INSUFFICIENT_MATERIAL: "insufficient material",
            chess.Termination.SEVENTYFIVE_MOVES: "the 75-move rule",
            chess.Termination.FIVEFOLD_REPETITION: "fivefold repetition",
            chess.Termination.FIFTY_MOVES: "the 50-move rule",
            chess.Termination.THREEFOLD_REPETITION: "threefold repetition",
        }.get(outcome.termination, "the rules")
        winner = None if outcome.winner is None else ("white" if outcome.winner else "black")
        return self._finish(winner, reason)

    def resign(self):
        winner = "black" if self.player_color == chess.WHITE else "white"
        return self._finish(winner, "resignation")

    def agree_draw(self):
        return self._finish(None, "agreement")

    def _finish(self, winner, reason):
        self.active = False
        if winner is None:
            outcome, headline = "draw", "The game is a draw"
            message = f"The game is a draw by {reason}." if reason != "agreement" else "Draw agreed."
        elif winner == self.player_name:
            outcome, headline = "win", "You win!"
            message = ("Checkmate! You win!" if reason == "checkmate"
                       else f"You win by {reason}!")
        else:
            outcome, headline = "loss", "Stockfish wins"
            if reason == "resignation":
                message = "You resigned. Stockfish wins."
            elif reason == "checkmate":
                message = "Checkmate. Stockfish wins."
            else:
                message = f"Stockfish wins by {reason}."
        score = {"white": "1-0", "black": "0-1"}.get(winner, "1/2-1/2")
        self.result = {"outcome": outcome, "winner": winner, "reason": reason, "score": score,
                       "headline": headline, "message": message}
        return self.result

    # ---- state for the UI ------------------------------------------------------
    def captured(self):
        """Pieces each side has captured, replayed from the move stack (handles en passant)."""
        replay = chess.Board()
        by_white, by_black = [], []
        for move in self.board.move_stack:
            victim = None
            if replay.is_en_passant(move):
                victim = chess.Piece(chess.PAWN, not replay.turn)
            else:
                victim = replay.piece_at(move.to_square)
            if victim is not None:
                (by_white if replay.turn == chess.WHITE else by_black).append(victim.symbol())
            replay.push(move)
        order = "qrbnp"
        key = lambda s: order.index(s.lower())
        return {"byWhite": sorted(by_white, key=key), "byBlack": sorted(by_black, key=key)}

    def material_balance(self):
        """Positive = white is ahead (pawn units)."""
        values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
        total = 0
        for piece in self.board.piece_map().values():
            v = values.get(piece.piece_type, 0)
            total += v if piece.color == chess.WHITE else -v
        return total

    def history(self):
        replay = chess.Board()
        sans = []
        for move in self.board.move_stack:
            sans.append(replay.san(move))
            replay.push(move)
        return sans

    def state(self):
        b = self.board
        last = b.move_stack[-1] if b.move_stack else None
        check_square = None
        if b.is_check():
            check_square = chess.square_name(b.king(b.turn))
        legal = {}
        if self.active and self.is_player_turn():
            for m in b.legal_moves:
                legal.setdefault(chess.square_name(m.from_square), []).append(chess.square_name(m.to_square))
        return {
            "fen": b.fen(),
            "pieces": {chess.square_name(sq): p.symbol() for sq, p in b.piece_map().items()},
            "turn": "white" if b.turn == chess.WHITE else "black",
            "playerColor": self.player_name,
            "level": self.level,
            "active": self.active,
            "lastMove": None if last is None else
            {"from": chess.square_name(last.from_square), "to": chess.square_name(last.to_square)},
            "check": check_square,
            "legal": legal,
            "captured": self.captured(),
            "balance": self.material_balance(),
            "history": self.history(),
            "result": self.result,
        }
