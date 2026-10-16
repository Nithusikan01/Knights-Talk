import chess
import pytest

from voice_commands import parse_command, describe_move


def move_of(text, fen=None):
    board = chess.Board(fen) if fen else chess.Board()
    cmd = parse_command(text, board)
    assert cmd["type"] == "move", cmd
    return cmd["move"].uci()


@pytest.mark.parametrize("text", [
    "e2 e4", "e2 to e4", "e2e4", "E2 E4", "move e2 to e4", "e 2 to e 4", "e two to e four",
    "e to e 4", "e to e4", "echo two echo four", "pawn e4", "e4", "pawn to e4", "e 2 e 4", "e2, e4.",
])
def test_pawn_opening_variants(text):
    assert move_of(text) == "e2e4"


@pytest.mark.parametrize("text", ["knight to f3", "night f3", "g1 to f3", "g one f three", "Nf3", "g1f3"])
def test_knight_variants(text):
    assert move_of(text) == "g1f3"


def test_see_and_be_homophones():
    assert move_of("see two see four") == "c2c4"
    assert move_of("bee 1 see 3") == "b1c3"


def test_castling():
    fen = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"
    assert move_of("castle kingside", fen) == "e1g1"
    assert move_of("castle queenside", fen) == "e1c1"
    assert move_of("castle short", fen) == "e1g1"
    assert move_of("O-O", fen) == "e1g1"
    assert parse_command("castle", chess.Board(fen))["type"] == "error"  # ambiguous
    assert parse_command("castle kingside", chess.Board())["type"] == "error"


def test_promotion_defaults_to_queen_and_can_be_chosen():
    fen = "8/P6k/8/8/8/8/8/K7 w - - 0 1"
    assert move_of("a7 a8", fen) == "a7a8q"
    assert move_of("a7 to a8 promote to knight", fen) == "a7a8n"
    assert move_of("a7a8r", fen) == "a7a8r"


def test_ambiguous_piece_move_asks_which():
    board = chess.Board("4k3/8/8/8/8/8/8/1N2KN2 w - - 0 1")  # knights b1 & f1 can both reach d2
    cmd = parse_command("knight to d2", board)
    assert cmd["type"] == "error" and "Which knight" in cmd["message"]


def test_errors_are_explained():
    board = chess.Board()
    assert "no piece" in parse_command("e4 e5", board)["message"]
    assert "not yours" in parse_command("e7 e5", board)["message"]
    assert "cannot move" in parse_command("e2 e5", board)["message"]


def test_pinned_piece_message():
    board = chess.Board("4r1k1/8/8/8/8/8/4N3/4K3 w - - 0 1")
    msg = parse_command("e2 c3", board)["message"]
    assert "king in check" in msg


@pytest.mark.parametrize("text,kind", [
    ("resign", "resign"), ("I resign", "resign"), ("I give up", "resign"),
    ("offer a draw", "draw"), ("draw", "draw"),
    ("undo", "undo"), ("take back", "undo"),
    ("hint", "hint"), ("read the board", "read_board"), ("repeat", "last_move"),
    ("captured pieces", "captured"), ("help", "help"), ("blah blah", "unknown"), ("", "unknown"),
    ("stop listening", "mic_off"),
])
def test_commands(text, kind):
    assert parse_command(text, chess.Board())["type"] == kind


def test_new_game_with_color():
    assert parse_command("start the game", chess.Board()) == {"type": "new_game", "color": None}
    assert parse_command("new game as black", chess.Board())["color"] == "black"
    assert parse_command("play as white", chess.Board())["color"] == "white"


def test_too_many_squares():
    assert parse_command("e2 e4 e5", chess.Board())["type"] == "error"


def test_describe_move():
    board = chess.Board()
    assert describe_move(board, chess.Move.from_uci("g1f3")) == "knight from g1 to f3"
    board = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    assert describe_move(board, chess.Move.from_uci("e4d5")) == "pawn from e4 captures the pawn on d5"
