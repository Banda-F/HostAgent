"""
HostAgent — LLM клиент
Единый интерфейс для работы с разными LLM-провайдерами.
Поддерживает: OpenAI API, Ollama (локальные модели), совместимые API.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config.config import LLMConfig, get_config

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str  # "system", "user", "assistant"
    content: str


class LLMClient:
    """Клиент для взаимодействия с языковыми моделями."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or get_config().llm
        self._client = httpx.AsyncClient(timeout=120.0)
        self._conversation_history: list[Message] = []

    async def chat(
        self,
        messages: list[Message],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Отправляет сообщения в LLM и возвращает ответ."""
        temperature = temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            if self.config.provider == "ollama":
                response = await self._call_ollama(payload)
            else:
                # OpenAI и совместимые API
                response = await self._call_openai_compatible(payload)

            logger.debug(f"LLM response ({len(response)} chars)")
            return response

        except httpx.TimeoutException:
            logger.error("LLM request timed out")
            return "Извините, запрос к AI занял слишком много времени. Попробуйте ещё раз."
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return f"Ошибка при обращении к AI: {e}"

    async def _call_openai_compatible(self, payload: dict) -> str:
        """Вызов OpenAI-совместимого API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        response = await self._client.post(
            f"{self.config.base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _call_ollama(self, payload: dict) -> str:
        """Вызов локального Ollama API."""
        payload.pop("max_tokens", None)  # Ollama использует num_predict

        response = await self._client.post(
            f"{self.config.base_url}/api/chat",
            json={**payload, "stream": False},
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]

    def add_to_history(self, role: str, content: str):
        """Добавляет сообщение в историю диалога."""
        self._conversation_history.append(Message(role=role, content=content))
        # Ограничиваем историю последними 20 сообщениями
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]

    def clear_history(self):
        """Очищает историю диалога."""
        self._conversation_history.clear()

    def get_history(self) -> list[Message]:
        """Возвращает текущую историю диалога."""
        return list(self._conversation_history)

    async def close(self):
        """Закрывает HTTP-клиент."""
        await self._client.aclose()


def load_prompt(name: str) -> str:
    """Загружает промпт из файла prompts/{name}.txt."""
    from pathlib import Path

    prompt_path = Path(__file__).parent.parent.parent / "prompts" / f"{name}.txt"
    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return ""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()
