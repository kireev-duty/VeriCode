"""Why local embeddings are not in the product: `uv run --with fastembed python -m validation.embeddings_probe`.

fastembed is deliberately not a project dependency (the probe downloads ~220 MB of ONNX weights). Two checks:
1. term mapping: which catalog skill is nearest to IT jargon / transliterations that the rules must handle;
2. text similarity: a payment-gateway vacancy vs. profiles of different relevance, embeddings vs. the 4-gram cosine
   that the matching uses now (nlp.text_similarity).
The numbers are quoted in docs/validation/report.md, section 7.
"""

import numpy as np

from app.catalog import SKILLS
from app.modules.nlp import text_similarity

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
JARGON = ["постгрес", "кубер", "реакт", "свифт", "терраформ", "ансибл", "графана", "эластик", "очереди сообщений",
          "табличные данные", "машинное обучение", "микросервисная архитектура"]
NEED = "Ищем разработчика в команду платёжного шлюза: высокие нагрузки, обработка транзакций, интеграции с банками."
PROFILES = {
    "процессинг платежей (релевантен)": "Разрабатывал процессинг карточных платежей, держали 5 тысяч запросов в "
                                        "секунду, интегрировал эквайринг.",
    "то же по-английски (релевантен)": "Built a card payment processing service handling 5k RPS, bank acquiring "
                                       "integrations.",
    "кредитный скоринг (частично)": "Обучаю модели кредитного скоринга, градиентный бустинг, фичи из транзакций.",
    "игровой сервер (частично)": "Делаю игровой сервер для мобильной игры, высокие нагрузки, тысячи игроков онлайн.",
    "экраны переводов в банке (слабо)": "Работал в банке над мобильным приложением, делал экраны переводов.",
    "лендинги (нерелевантен)": "Верстаю лендинги и интернет-магазины на Tilda и WordPress.",
}


def main() -> None:
    from fastembed import TextEmbedding  # optional: see the module docstring

    model = TextEmbedding(MODEL)

    def emb(texts: list[str]) -> np.ndarray:
        e = np.array(list(model.embed(texts)))
        return e / np.linalg.norm(e, axis=1, keepdims=True)

    labels, terms = [], []
    for s in SKILLS:
        for t in (s.title, *s.synonyms):
            labels.append(s.id)
            terms.append(t)
    catalog = emb(terms)
    print("1. Nearest catalog skill for jargon (cosine):")
    for q, v in zip(JARGON, emb(JARGON)):
        j = int(np.argmax(catalog @ v))
        print(f"   {q:28s} -> {labels[j]:14s} ({terms[j]}) {float(catalog[j] @ v):.2f}")
    print("\n2. Vacancy vs. profiles: embedding cosine | 4-gram cosine")
    need = emb([NEED])[0]
    for (name, text), v in zip(PROFILES.items(), emb(list(PROFILES.values()))):
        print(f"   {name:34s} {float(v @ need):.2f} | {text_similarity(NEED, text):.2f}")


if __name__ == "__main__":
    main()
