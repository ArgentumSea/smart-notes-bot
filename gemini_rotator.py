"""Модуль для работы с Gemini API через google-genai SDK."""

import asyncio
import json
import logging
from datetime import datetime

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from config import GEMINI_API_KEY, GEMINI_MODELS, TZ

logger = logging.getLogger(__name__)


class GeminiRotator:
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.models = GEMINI_MODELS
        self.backoff_seconds = 1
        self.max_backoff = 60

    async def process_note(self, text: str) -> dict:
        prompt = self._build_prompt(text)
        raw = await self._generate_with_fallback(prompt)
        return self._parse_json(raw)

    def _build_prompt(self, text: str) -> str:
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")
        return (
            "Ты — ассистент по обработке заметок. "
            "Проанализируй текст и верни ТОЛЬКО JSON без markdown-код-блоков.\n\n"
            "Формат:\n"
            '{"summary": "краткое содержание 2-3 предложения", '
            '"action_items": [{"task": "описание задачи", "deadline": "YYYY-MM-DDTHH:MM или null"}]}\n\n'
            "Правила:\n"
            "- Если в тексте есть дата/время задачи — извлеки в поле deadline.\n"
            f"- Относительные даты ('завтра', 'через 2 часа') считай от {now}.\n"
            "- Если время не указано явно — ставь только дату (время 00:00).\n"
            "- Только чистый JSON. Никаких ``` в ответе.\n\n"
            "Текст заметки:\n" + text
        )

    async def _generate_with_fallback(self, prompt: str) -> str:
        attempt = 0
        while True:
            for model_name in self.models:
                try:
                    result = await self._call_model(model_name, prompt)
                    self.backoff_seconds = 1
                    logger.info(f"Gemini OK: {model_name}")
                    return result
                except ClientError as e:
                    code = getattr(e, "code", 0)
                    if code == 429:
                        logger.warning(f"Quota exceeded (429) on {model_name}")
                        continue
                    logger.error(f"Client error {code} on {model_name}")
                    raise
                except ServerError as e:
                    code = getattr(e, "code", 0)
                    logger.warning(f"Server error {code} on {model_name}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error on {model_name}: {type(e).__name__}")
                    raise

            attempt += 1
            sleep_time = min(self.backoff_seconds, self.max_backoff)
            logger.warning(f"All Gemini models exhausted. Backoff {sleep_time}s (attempt {attempt})")
            await asyncio.sleep(sleep_time)
            self.backoff_seconds = min(self.backoff_seconds * 2, self.max_backoff)

    async def _call_model(self, model_name: str, prompt: str) -> str:
        def _sync():
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2048),
            )
            if not response.text:
                raise RuntimeError("Empty response from Gemini")
            return response.text
        return await asyncio.to_thread(_sync)

    def _parse_json(self, raw: str) -> dict:
        original = raw.strip()

        # Убираем префиксы типа "ONLY!", "Here is the JSON:", etc.
        prefixes = ["ONLY!", "Here is the JSON:", "JSON:", "Response:"]
        for prefix in prefixes:
            if original.startswith(prefix):
                original = original[len(prefix):].strip()
                break

        raw = original

        if "```" in original:
            lines = original.splitlines()
            inside_block = False
            cleaned_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("```"):
                    inside_block = not inside_block
                    continue
                if inside_block:
                    cleaned_lines.append(line)
            if cleaned_lines:
                raw = "\n".join(cleaned_lines).strip()
            else:
                parts = original.split("```")
                if len(parts) >= 3:
                    raw = parts[1].strip()
                    if raw.lower().startswith("json"):
                        raw = raw[4:].strip()

        for candidate in [raw, self._extract_json(raw)]:
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
                if "summary" not in data:
                    data["summary"] = ""
                if "action_items" not in data or not isinstance(data["action_items"], list):
                    data["action_items"] = []
                return data
            except json.JSONDecodeError:
                continue

        logger.error(f"JSON parse failed. Raw: {original[:2000]}")
        return {"summary": original[:1000], "action_items": []}

    def _extract_json(self, raw: str) -> str:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return raw[start:end + 1]
        return ""
