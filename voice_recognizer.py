"""Распознавание речи через Vosk."""

import os
import json
import logging
import subprocess
import tempfile
from vosk import Model, KaldiRecognizer

from config import VOSK_MODEL_PATH

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        if not os.path.exists(VOSK_MODEL_PATH):
            raise RuntimeError("Модель Vosk не найдена.")
        logger.info(f"Загрузка Vosk: {VOSK_MODEL_PATH}")
        _model = Model(VOSK_MODEL_PATH)
        logger.info("Vosk загружен.")
    return _model


def recognize_ogg(ogg_path: str) -> str:
    wav_path = os.path.splitext(ogg_path)[0] + ".wav"
    logger.info(f"Recognize: ogg={ogg_path}, size={os.path.getsize(ogg_path)}")

    try:
        # Конвертация через ffmpeg напрямую
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            return ""

        logger.info(f"Exported WAV: {wav_path}, size={os.path.getsize(wav_path)}")

        recognizer = KaldiRecognizer(_get_model(), 16000)
        with open(wav_path, "rb") as f:
            while True:
                data = f.read(4000)
                if not data:
                    break
                recognizer.AcceptWaveform(data)

        result_json = json.loads(recognizer.FinalResult())
        text = result_json.get("text", "")
        logger.info(f"Recognized text: '{text}'")
        return text

    except Exception as e:
        logger.error(f"Voice recognition failed: {type(e).__name__}: {e}")
        return ""

    finally:
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except OSError:
            pass
