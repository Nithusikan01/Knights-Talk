"""Speech-to-text for audio that the UI recorded and sent over (no microphone access here)."""
import base64

import speech_recognition as sr


class RecognitionUnavailable(Exception):
    """The speech service could not be reached (usually: no internet)."""


class NothingHeard(Exception):
    """The audio contained no intelligible speech."""


_recognizer = sr.Recognizer()


def recognize_pcm(pcm_b64, sample_rate=16000, language="en-US"):
    """
    pcm_b64: base64 of mono, signed 16-bit little-endian PCM.
    Returns the transcript in lower case.
    """
    pcm = base64.b64decode(pcm_b64)
    if len(pcm) < sample_rate // 5:  # shorter than 0.2 s
        raise NothingHeard()
    audio = sr.AudioData(pcm, sample_rate, 2)
    try:
        return _recognizer.recognize_google(audio, language=language).lower()
    except sr.UnknownValueError:
        raise NothingHeard()
    except sr.RequestError as exc:
        raise RecognitionUnavailable(str(exc))
