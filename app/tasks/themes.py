"""Предметные темы для SQL-заданий. Структура задачи одна, «легенда» и имена таблиц разные —
поэтому ответы нельзя просто передать между кандидатами, а сложность остаётся сопоставимой."""
from __future__ import annotations

import random

THEMES: dict[str, dict] = {
    "shop": dict(
        parent="customers", child="orders", fk="customer_id", amt="amount",
        parent_sg="клиента", parent_gen="клиентов", child_sg="заказа", child_gen="заказов",
        amt_name="сумма заказа", ok="paid", bad="cancelled", other="new",
        keywords=("магазин", "заказ", "маркетплейс", "ecommerce", "shop", "order", "корзин", "retail", "ozon", "avito"),
    ),
    "delivery": dict(
        parent="couriers", child="deliveries", fk="courier_id", amt="fee",
        parent_sg="курьера", parent_gen="курьеров", child_sg="доставки", child_gen="доставок",
        amt_name="стоимость доставки", ok="done", bad="failed", other="new",
        keywords=("доставк", "курьер", "логистик", "delivery", "самокат", "wolt", "яндекс", "такси"),
    ),
    "bank": dict(
        parent="clients", child="transactions", fk="client_id", amt="amount",
        parent_sg="клиента", parent_gen="клиентов", child_sg="транзакции", child_gen="транзакций",
        amt_name="сумма транзакции", ok="done", bad="declined", other="pending",
        keywords=("банк", "платеж", "платёж", "транзакц", "fintech", "bank", "сбер", "тинькофф", "альфа"),
    ),
    "cinema": dict(
        parent="viewers", child="tickets", fk="viewer_id", amt="price",
        parent_sg="зрителя", parent_gen="зрителей", child_sg="билета", child_gen="билетов",
        amt_name="цена билета", ok="used", bad="refunded", other="booked",
        keywords=("кино", "билет", "афиш", "театр", "ivi", "cinema", "ticket", "событи"),
    ),
}


def pick_theme(rng: random.Random, context_text: str = "") -> str:
    """Тема выбирается по найденному контексту (RAG-подсказка); при ничьей — по seed."""
    text = (context_text or "").lower()
    scores = {name: sum(text.count(k) for k in t["keywords"]) for name, t in THEMES.items()}
    best = max(scores.values()) if scores else 0
    if best <= 0:
        return rng.choice(sorted(THEMES))
    return rng.choice(sorted(n for n, s in scores.items() if s == best))
