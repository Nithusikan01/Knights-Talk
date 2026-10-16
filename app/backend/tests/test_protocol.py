"""End-to-end: runs app.py as a subprocess exactly like Electron does, with the real engine."""
import json
import os
import queue
import subprocess
import sys
import threading

import pytest

from game import stockfish_path

try:
    stockfish_path()
    HAVE_ENGINE = True
except FileNotFoundError:
    HAVE_ENGINE = False

pytestmark = pytest.mark.skipif(not HAVE_ENGINE, reason="Stockfish binary not available")
HERE = os.path.dirname(os.path.abspath(__file__))


class Backend:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "..", "app.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.events = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.events.put(json.loads(line))

    def send(self, **cmd):
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()

    def wait_for(self, predicate, timeout=20):
        seen = []
        while True:
            try:
                ev = self.events.get(timeout=timeout)
            except queue.Empty:
                raise AssertionError(f"timed out; saw {seen}")
            seen.append(ev)
            if predicate(ev):
                return ev

    def close(self):
        self.send(cmd="quit")
        self.proc.wait(timeout=10)


@pytest.fixture
def backend():
    b = Backend()
    yield b
    b.close()


def test_play_a_move_and_get_engine_reply(backend):
    backend.send(cmd="hello")
    s = backend.wait_for(lambda e: e["type"] == "state")
    assert not s["active"]
    backend.send(cmd="new_game", color="white", level=0)
    s = backend.wait_for(lambda e: e["type"] == "state" and e["active"])
    assert s["legal"]["e2"] == ["e3", "e4"]
    backend.send(cmd="text", text="e 2 to e 4")
    backend.wait_for(lambda e: e["type"] == "speak" and "You played pawn from e2 to e4" in e["message"])
    s = backend.wait_for(lambda e: e["type"] == "state" and e["turn"] == "white" and len(e["history"]) == 2)
    assert s["pieces"]["e4"] == "P"
    assert s["lastMove"]["from"] != "e2"  # engine's move


def test_play_as_black_engine_moves_first(backend):
    backend.send(cmd="new_game", color="black", level=0)
    s = backend.wait_for(lambda e: e["type"] == "state" and len(e["history"]) == 1)
    assert s["playerColor"] == "black" and s["turn"] == "black"


def test_resign_ends_game(backend):
    backend.send(cmd="new_game", color="white", level=0)
    backend.wait_for(lambda e: e["type"] == "state" and e["active"])
    backend.send(cmd="text", text="I resign")
    over = backend.wait_for(lambda e: e["type"] == "game_over")
    assert over["outcome"] == "loss" and over["reason"] == "resignation" and over["score"] == "0-1"
    backend.send(cmd="text", text="e2 e4")
    backend.wait_for(lambda e: e["type"] == "speak" and "no game in progress" in e["message"])


def test_undo_and_click_move(backend):
    backend.send(cmd="new_game", color="white", level=0)
    backend.wait_for(lambda e: e["type"] == "state" and e["active"])
    backend.send(cmd="move", **{"from": "d2", "to": "d4"})
    backend.wait_for(lambda e: e["type"] == "state" and len(e["history"]) == 2)
    backend.send(cmd="undo")
    s = backend.wait_for(lambda e: e["type"] == "state" and e["history"] == [])
    assert s["pieces"]["d2"] == "P"


def test_illegal_and_unknown_input_do_not_crash(backend):
    backend.send(cmd="new_game", color="white", level=0)
    backend.wait_for(lambda e: e["type"] == "state" and e["active"])
    backend.send(cmd="text", text="e2 e5")
    backend.wait_for(lambda e: e["type"] == "speak" and "cannot move" in e["message"])
    backend.send(cmd="text", text="gibberish")
    backend.wait_for(lambda e: e["type"] == "speak" and "didn't understand" in e["message"])
    backend.send(cmd="read_board")
    backend.wait_for(lambda e: e["type"] == "speak" and "Your white pieces" in e["message"])
    backend.send(cmd="audio", pcm="AAAA", rate=16000)  # far too short -> "didn't catch that"
    backend.wait_for(lambda e: e["type"] == "speak" and "didn't catch" in e["message"])
