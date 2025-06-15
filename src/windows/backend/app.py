import chess
import chess.engine
import speech_recognition as sr
import pyttsx3
import time
import sys
import json
import os
import platform

# Get the directory of the current script (app.py)
base_dir = os.path.dirname(os.path.abspath(__file__))

# Detect the operating system and set the Stockfish path accordingly

if platform.system() == "Windows":
    STOCKFISH_PATH = os.path.join(base_dir, 'stockfish', 'stockfish-windows-x86-64.exe')
else:
    raise OSError("Unsupported operating system")

# Constants
DELAY = 5  # Time delay for human player to think about the next move
TRIGGER_WORD = ["start", "game"]
CHESS_PIECES = chess.UNICODE_PIECE_SYMBOLS

# Initialize speech recognition and text-to-speech engines
recognizer = sr.Recognizer()
microphone = sr.Microphone(0)
tts_engine = pyttsx3.init()

# Start the Stockfish engine
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

# Initialize the chess board
board = chess.Board()

def speak(text):
    """
    Speaks and prints the given text.
    """
    print(json.dumps({"type": "speak", "message": text}))
    sys.stdout.flush()
    tts_engine.say(text)
    tts_engine.runAndWait()

def capture_speech(prompt):
    """
    Captures the user's speech input after prompting them with a message.
    """
    speak(prompt)
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        recognizer.dynamic_energy_threshold = True
        audio = recognizer.listen(source)
        try:
            speech_input = recognizer.recognize_google(audio, language="en-US").lower()
            return speech_input
        except sr.UnknownValueError:
            speak("Sorry, I didn't catch that. Could you please repeat?")
            return None
        except Exception as e:
            speak(f"An error occurred during speech recognition: {e}")
            return None

def parse_move(move):
    """
    Parses the move from the captured speech into a UCI-like format.
    """
    move_text_lst = move.split(' ')
    if len(move_text_lst) == 2:
        return f"{move_text_lst[0]}{move_text_lst[1]}"
    elif len(move_text_lst) == 3:
        return f"{move_text_lst[0]}{move_text_lst[2]}"
    elif len(move_text_lst) == 4:
        return f"{move_text_lst[1]}{move_text_lst[3]}"
    else:
        return None

def get_human_move():
    """
    Receives the human player's move and checks if it's legal.
    """
    while True:
        move = capture_speech("Move please: ")
        speak(move)
        if move:
            parsed_move = parse_move(move)
            #speak(f"The sparsed move {parsed_move}")
            if parsed_move:
                try:
                    chess_move = chess.Move.from_uci(parsed_move)
                    if chess_move in board.legal_moves:
                        return chess_move
                    else:
                        speak("Illegal move! Please try again.")
                except ValueError:
                    speak("Invalid move format! Please try again.")
            else:
                speak("Could not parse the move. Please try again.")




def return_chess_board(board, CHESS_PIECES):
    """
    Returns the current chess board as a multiline string with Unicode symbols.
    """

    board_str = ''
    
    for rank in range(7, -1, -1):  # Ranks are 7-0 (8th rank to 1st rank)
        for file in range(8):       # Files are 0-7 (a-h)
            piece = board.piece_at(chess.square(file, rank))
            if piece:
                board_str += CHESS_PIECES[piece.symbol()]
            else:
                board_str += '.'  # Empty squares represented by dots
        board_str += '\n'  # New line at the end of each rank
    
    return board_str.strip()  # Remove the trailing newline character

def listen_for_trigger():
    """
    Listens continuously for the trigger word.
    If no microphone is available, starts the game immediately.
    """
    if microphone is None:
        return True

    retry_count = 0
    max_retries = 3

    while retry_count < max_retries:
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source)
            try:
                audio = recognizer.listen(source, timeout=10)  # Added timeout to avoid hanging
                command = recognizer.recognize_google(audio, language="en-US").lower().split()
                if   any(trigger in command for trigger in TRIGGER_WORD):
                    speak("Starting the game.")
                    return True
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                speak(f"Could not request results from Google Speech Recognition service. Check your connection and try again.")
                retry_count += 1
                if retry_count >= max_retries:
                    speak("Failed to recognize the trigger word after multiple attempts. Exiting.")
                    return False
            except sr.WaitTimeoutError:
                speak("Listening timed out while waiting for trigger word. Please try again.")
                retry_count += 1
                if retry_count >= max_retries:
                    speak("Failed to recognize the trigger word after multiple attempts. Exiting.")
                    return False
            except Exception as e:
                speak(f"An unexpected error occurred while listening for the trigger word: {e}")
                
def resign_from_game(turn):
    """
    Handles resignation. The other player is declared the winner.
    """
    winner = "Stockfish" if turn == chess.WHITE else "You"
    speak(f"{winner} wins by resignation!")
    return True

def check_game_end_status(board):
    if board.is_checkmate():
        winner = "Stockfish" if board.turn == chess.WHITE else "You"
        speak(f"Checkmate! {winner} wins!")
    elif board.is_stalemate():
        speak("Stalemate!")
    elif board.is_insufficient_material():
        speak("Draw due to insufficient material!")
    elif board.is_seventyfive_moves():
        speak("Draw due to 75-move rule!")
    elif board.is_fivefold_repetition():
        speak("Draw due to fivefold repetition!")
    elif board.is_variant_draw():
        speak("Draw due to variant rule!")

def check_for_check(board):
    if board.is_check():
        check_ = "Stockfish" if board.turn == chess.WHITE else "You"
        if check_ == 'Stockfish':
            speak('Stockfish says check! Protect your King.')
            return False 
        else:
            speak("Great Move! Stockfish in check.")
            return True

def main(delay=DELAY):
    """
    Main function containing the core logic of the chess game.
    """
    # Listen for the trigger word
    speak("Please say 'Start the game' to play with stockfish.")
    if not listen_for_trigger():
        return
    
    # Main game loop
    while not board.is_game_over():
        # Print the current board
        print(json.dumps({"type": "board", "board": return_chess_board(board, CHESS_PIECES)}))
        sys.stdout.flush()

        time.sleep(delay)
        # Human player's move
        human_move = get_human_move()
        if human_move:
            board.push(human_move)
            speak(f"You moved {human_move}")
            check_for_check(board)
               
            # Check if the game is over after human's move
            if board.is_game_over():
                break

        # Print the current board
        print(json.dumps({"type": "board", "board": return_chess_board(board, CHESS_PIECES)}))
        sys.stdout.flush()

        # Stockfish's move
        result = engine.play(board, chess.engine.Limit(time=2.0))
        board.push(result.move)
        speak(f"Stockfish moved {result.move.uci()}")
        check_for_check(board)

    # Print final board
    print("Final board:")
    final_board = return_chess_board(board, CHESS_PIECES)
    print(json.dumps({"type": "board", "board": final_board}))
    sys.stdout.flush()

    # Print game result
    check_game_end_status(board)

    # Quit the engine
    engine.quit()

if __name__ == "__main__":
    main()
