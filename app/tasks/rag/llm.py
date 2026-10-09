"""Необязательный LLM-слой. Используется ТОЛЬКО для авторской подготовки черновиков заданий (статус draft);
черновики проходят автоматические проверки и ручное утверждение. Для выдачи кандидатам LLM «на лету» не вызывается:
сопоставимая сложность и объективность обеспечиваются калиброванными генераторами и банком."""
from __future__ import annotations

import json
import re
from typing import Protocol


DRAFT_SYSTEM = (
    "Ты помогаешь составлять тестовые вопросы для IT-специалистов. Отвечай ТОЛЬКО валидным JSON без пояснений. "
    "Не копируй формулировки из переданных материалов — используй их лишь как тематический контекст."
)


class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str) -> dict: ...


class NullLLM:
    async def complete_json(self, system: str, user: str) -> dict:  # noqa: ARG002
        raise RuntimeError("LLM не настроен (задайте LLM_BASE_URL, LLM_MODEL, LLM_API_KEY)")


class OpenAICompatLLM:
    """Любой OpenAI-совместимый endpoint (облачный или локальный: vLLM, Ollama и т.п.)."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout

    async def complete_json(self, system: str, user: str) -> dict:
        import httpx  # ленивый импорт: зависимость нужна только при реальном вызове LLM

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                json={"model": self.model, "temperature": 0.4,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0) if m else content)


def build_draft_prompt(language: str, grade: str, topic: str, context: str, n: int) -> str:
    return (
        f"Составь {n} вопросов с одним правильным ответом по теме «{topic}» ({language}), уровень {grade}.\n"
        f"Материалы для контекста (не копировать):\n{context[:3000]}\n\n"
        'Формат: {"items":[{"statement":"...","options":["a","b","c","d"],"correct":"<точный текст одного из options>",'
        '"explanation":"..."}]}'
    )


def validate_draft_items(data: dict) -> list[dict]:
    """Жёсткая проверка схемы ответа LLM: 4 уникальных варианта, правильный среди них, непустые тексты."""
    out = []
    for it in data.get("items", []):
        opts = it.get("options")
        if (not isinstance(opts, list) or len(opts) != 4 or len({str(o).strip() for o in opts}) != 4
                or it.get("correct") not in opts or len(str(it.get("statement", ""))) < 15):
            continue
        out.append({"statement": str(it["statement"]).strip(), "options": [str(o).strip() for o in opts],
                    "correct": str(it["correct"]).strip(), "explanation": str(it.get("explanation", ""))[:500]})
    return out
