import chess

from game import GameSession


def play(session, ucis):
    for uci in ucis:
        session.board.push_uci(uci)


def test_checkmate_player_wins():
    g = GameSession()
    g.active = True
    play(g, ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"])
    r = g.check_game_over()
    assert r["outcome"] == "win" and r["reason"] == "checkmate" and r["score"] == "1-0"
    assert not g.active


def test_checkmate_player_loses():
    g = GameSession()
    g.active = True
    play(g, ["f2f3", "e7e5", "g2g4", "d8h4"])
    r = g.check_game_over()
    assert r["outcome"] == "loss" and r["winner"] == "black" and r["score"] == "0-1"


def test_stalemate_is_draw():
    g = GameSession()
    g.board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    g.active = True
    r = g.check_game_over()
    assert r["outcome"] == "draw" and r["reason"] == "stalemate" and r["score"] == "1/2-1/2"


def test_insufficient_material_and_threefold():
    g = GameSession()
    g.board = chess.Board("8/8/4k3/8/8/4K3/8/8 w - - 0 1")
    assert g.check_game_over()["reason"] == "insufficient material"
    g = GameSession()
    g.active = True
    play(g, ["g1f3", "g8f6", "f3g1", "f6g8"] * 2)
    assert g.check_game_over()["reason"] == "threefold repetition"


def test_resign_and_agreed_draw():
    g = GameSession()
    g.active = True
    r = g.resign()
    assert r["outcome"] == "loss" and r["reason"] == "resignation" and r["winner"] == "black"
    g = GameSession()
    g.player_color = chess.BLACK
    assert g.resign()["winner"] == "white"
    assert GameSession().agree_draw()["outcome"] == "draw"


def test_captured_pieces_including_en_passant():
    g = GameSession()
    play(g, ["e2e4", "a7a6", "e4e5", "d7d5", "e5d6", "d8d6", "d2d4", "d6d4", "d1d4"])
    cap = g.captured()
    assert cap["byWhite"] == ["q", "p"]  # black queen, and the pawn taken en passant
    assert cap["byBlack"] == ["P", "P"]
