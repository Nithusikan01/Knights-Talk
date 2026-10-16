"""
Turns what the player said (or typed) into a game command.

Speech recognisers are sloppy with chess: "e2 to e4" often arrives as "e to e 4"
or "e 2 2 e 4". The parser therefore works on a token stream and understands
number words, letter homophones and the NATO alphabet, and it also accepts
plain UCI ("e2e4") and SAN ("Nf3", "O-O") for typed input.
"""
import re

import chess

PIECE_WORDS = {
    "pawn": chess.PAWN,
    "knight": chess.KNIGHT,
    "night": chess.KNIGHT,
    "horse": chess.KNIGHT,
    "bishop": chess.BISHOP,
    "rook": chess.ROOK,
    "castle": None,  # handled separately: "castle" is also the castling verb
    "queen": chess.QUEEN,
    "king": chess.KING,
}
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

FILE_WORDS = {
    "a": "a", "alpha": "a", "alfa": "a",
    "b": "b", "be": "b", "bee": "b", "bravo": "b",
    "c": "c", "see": "c", "sea": "c", "charlie": "c",
    "d": "d", "dee": "d", "delta": "d",
    "e": "e", "echo": "e",
    "f": "f", "eff": "f", "foxtrot": "f",
    "g": "g", "gee": "g", "jee": "g", "golf": "g",
    "h": "h", "aitch": "h", "hotel": "h",
}
# Words that are only read as ranks directly after a file letter ("e to" = e2).
RANK_WORDS = {
    "1": "1", "one": "1", "won": "1",
    "2": "2", "two": "2", "to": "2", "too": "2",
    "3": "3", "three": "3", "tree": "3",
    "4": "4", "four": "4", "for": "4", "fore": "4",
    "5": "5", "five": "5",
    "6": "6", "six": "6",
    "7": "7", "seven": "7",
    "8": "8", "eight": "8", "ate": "8",
}

RESIGN = ("resign", "i resign", "give up", "i give up", "surrender", "i surrender", "i quit")
DRAW = ("draw", "offer draw", "offer a draw", "propose a draw", "propose draw", "i offer a draw")
UNDO = ("undo", "take back", "takeback", "go back", "undo move", "undo my move", "take that back")
NEW_GAME = ("new game", "start game", "start the game", "start a new game", "play again",
            "restart", "start over", "begin game", "start a game", "let's play", "play a game")
HINT = ("hint", "give me a hint", "suggest", "suggestion", "best move", "what should i play",
        "what should i do", "any ideas")
READ_BOARD = ("read board", "read the board", "describe board", "describe the board", "board",
              "where are my pieces", "list pieces", "read pieces", "position", "what is the position",
              "where are the pieces", "my pieces")
LAST_MOVE = ("repeat", "say again", "say that again", "last move", "what was the last move",
             "what happened", "repeat that")
CAPTURED = ("captured", "captured pieces", "taken pieces", "what was captured", "material", "who is winning",
            "score")
HELP = ("help", "what can i say", "commands", "instructions", "how do i play")
MIC_OFF = ("stop listening", "mute", "pause listening", "microphone off")


def _words(text):
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split()


def _phrase_in(words, phrases):
    joined = " " + " ".join(words) + " "
    return any(" " + p + " " in joined for p in phrases)


def _squares(tokens):
    """Reads squares out of the token stream. Returns (squares, other_words)."""
    squares, other = [], []
    pending = None
    for tok in tokens:
        if pending is not None:
            rank = RANK_WORDS.get(tok)
            if rank:
                squares.append(chess.parse_square(pending + rank))
                pending = None
                continue
            other.append(pending)  # a lone letter was not a file after all
            pending = None
        if tok in FILE_WORDS:
            pending = FILE_WORDS[tok]
        else:
            other.append(tok)
    if pending is not None:
        other.append(pending)
    return squares, other


def _tokenize(text):
    # "e2e4" -> e 2 e 4, but keep real words like "knight" whole.
    return re.findall(r"[a-z']+|\d", text.lower().replace("-", " "))


def _legal_castle(board, kingside):
    for move in board.legal_moves:
        if board.is_kingside_castling(move) == kingside and board.is_castling(move):
            return move
    return None


def describe_move(board, move):
    """Plain-English description of a legal move, to be called *before* it is pushed."""
    if board.is_castling(move):
        return "castles kingside" if board.is_kingside_castling(move) else "castles queenside"
    piece = board.piece_at(move.from_square)
    name = PIECE_NAMES[piece.piece_type]
    src, dst = chess.square_name(move.from_square), chess.square_name(move.to_square)
    text = f"{name} from {src} to {dst}"
    if board.is_en_passant(move):
        text = f"{name} from {src} captures a pawn en passant on {dst}"
    elif board.is_capture(move):
        victim = PIECE_NAMES[board.piece_at(move.to_square).piece_type]
        text = f"{name} from {src} captures the {victim} on {dst}"
    if move.promotion:
        text += f" and promotes to a {PIECE_NAMES[move.promotion]}"
    return text


def _move_error(board, frm, to):
    piece = board.piece_at(frm)
    src, dst = chess.square_name(frm), chess.square_name(to)
    if piece is None:
        return f"There is no piece on {src}."
    if piece.color != board.turn:
        return f"The piece on {src} is not yours."
    # Would the move be legal if we ignored check?
    if chess.Move(frm, to) in board.pseudo_legal_moves or (
        piece.piece_type == chess.PAWN and chess.square_rank(to) in (0, 7)
        and chess.Move(frm, to, chess.QUEEN) in board.pseudo_legal_moves
    ):
        if board.is_check():
            return "Your king is in check. You must get out of check."
        return f"That move would leave your king in check."
    return f"A {PIECE_NAMES[piece.piece_type]} on {src} cannot move to {dst}."


def parse_command(text, board):
    """
    Returns a dict with a "type" key:
      move{move}, error{message}, resign, draw, undo, new_game{color?}, hint,
      read_board, last_move, captured, help, mic_off, unknown
    """
    raw = (text or "").strip()
    if not raw:
        return {"type": "unknown"}
    words = _words(raw)
    low = " ".join(words)

    # --- typed shorthand: UCI or SAN -------------------------------------
    compact = raw.replace(" ", "")
    if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbnQRBN]?", compact):
        return _from_to(board, chess.parse_square(compact[0:2]), chess.parse_square(compact[2:4]),
                        compact[4:].lower())
    if re.fullmatch(r"[KQRBNa-h0Oo][A-Za-h1-8xX=+#\-0Oo]*", compact) and not compact.isalpha():
        try:
            return {"type": "move", "move": board.parse_san(compact.replace("0", "O").replace("o", "O"))}
        except ValueError:
            pass

    # --- meta commands ---------------------------------------------------
    if _phrase_in(words, RESIGN):
        return {"type": "resign"}
    if _phrase_in(words, MIC_OFF):
        return {"type": "mic_off"}
    if _phrase_in(words, NEW_GAME):
        color = "black" if "black" in words else "white" if "white" in words else None
        return {"type": "new_game", "color": color}
    if low in ("play as black", "play black", "as black", "i want black", "i play black"):
        return {"type": "new_game", "color": "black"}
    if low in ("play as white", "play white", "as white", "i want white", "i play white"):
        return {"type": "new_game", "color": "white"}
    if _phrase_in(words, UNDO):
        return {"type": "undo"}
    if _phrase_in(words, DRAW) and not any(w in words for w in ("draws",)):
        return {"type": "draw"}
    if _phrase_in(words, HINT):
        return {"type": "hint"}
    if _phrase_in(words, READ_BOARD):
        return {"type": "read_board"}
    if _phrase_in(words, CAPTURED):
        return {"type": "captured"}
    if _phrase_in(words, LAST_MOVE):
        return {"type": "last_move"}
    if _phrase_in(words, HELP):
        return {"type": "help"}

    # --- castling ----------------------------------------------------------
    if "castle" in words or "castles" in words or "castling" in words:
        kingside = any(w in words for w in ("kingside", "short", "king"))
        queenside = any(w in words for w in ("queenside", "long", "queen"))
        if "king" in words and "side" in words:
            kingside = True
        if "queen" in words and "side" in words:
            queenside = True
        if kingside != queenside:
            move = _legal_castle(board, kingside)
            if move:
                return {"type": "move", "move": move}
            return {"type": "error", "message": "You cannot castle that way right now."}
        options = [m for m in board.legal_moves if board.is_castling(m)]
        if len(options) == 1:
            return {"type": "move", "move": options[0]}
        if not options:
            return {"type": "error", "message": "You cannot castle right now."}
        return {"type": "error", "message": "Say castle kingside or castle queenside."}

    # --- ordinary moves ----------------------------------------------------
    tokens = _tokenize(raw)
    squares, other = _squares(tokens)
    piece_types = [PIECE_WORDS[w] for w in other if PIECE_WORDS.get(w) is not None]
    promo = None
    if "promote" in other or "promotes" in other or "promotion" in other or "equals" in other:
        for w in reversed(other):
            if PIECE_WORDS.get(w) in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
                promo = PIECE_NAMES[PIECE_WORDS[w]][0] if PIECE_WORDS[w] != chess.KNIGHT else "n"
                break
        if promo and len(piece_types) > 0 and len(squares) == 2:
            piece_types = []  # the piece word named the promotion, not the mover
    if len(squares) >= 3:
        return {"type": "error", "message": "I heard too many squares. Please say your move again, for example e2 to e4."}
    if len(squares) == 2:
        return _from_to(board, squares[0], squares[1], promo or "")
    if len(squares) == 1:
        return _to_only(board, squares[0], piece_types[0] if piece_types else chess.PAWN, promo or "")
    return {"type": "unknown"}


def _from_to(board, frm, to, promo):
    promo_type = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}.get(promo)
    piece = board.piece_at(frm)
    if piece and piece.piece_type == chess.PAWN and chess.square_rank(to) in (0, 7):
        promo_type = promo_type or chess.QUEEN
    else:
        promo_type = None
    move = chess.Move(frm, to, promo_type)
    if move in board.legal_moves:
        return {"type": "move", "move": move}
    # Castling spoken as the king's two-square (or rook) move is handled by python-chess for the former.
    return {"type": "error", "message": _move_error(board, frm, to)}


def _to_only(board, to, piece_type, promo):
    promo_type = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}.get(promo)
    candidates = [m for m in board.legal_moves
                  if m.to_square == to and board.piece_type_at(m.from_square) == piece_type
                  and (m.promotion in (None, promo_type or chess.QUEEN))]
    name, dst = PIECE_NAMES[piece_type], chess.square_name(to)
    if len(candidates) == 1:
        return {"type": "move", "move": candidates[0]}
    if not candidates:
        return {"type": "error", "message": f"No {name} can move to {dst}."}
    starts = " or ".join(chess.square_name(m.from_square) for m in candidates)
    return {"type": "error",
            "message": f"Which {name}? You can move from {starts}. Say the starting square, then {dst}."}


def spoken_square(sq):
    name = chess.square_name(sq)
    return f"{name[0]} {name[1]}"


def describe_position(board, color):
    """Lists one side's pieces by type for the 'read board' command."""
    groups = {}
    for sq, piece in board.piece_map().items():
        if piece.color == color:
            groups.setdefault(piece.piece_type, []).append(chess.square_name(sq))
    order = [chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]
    parts = []
    for pt in order:
        squares = sorted(groups.get(pt, []))
        if squares:
            parts.append(f"{PIECE_NAMES[pt]} {', '.join(squares)}")
    return "; ".join(parts)
