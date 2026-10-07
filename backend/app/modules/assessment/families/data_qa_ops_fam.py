"""Data/ML, QA and DevOps families."""

import math
import random
import statistics
from collections import Counter

from app.modules.assessment.families.base import NAMES, Instance, Tier, choice_instance, family

# ------------------------------------------------------------------------------------------------ statistics


@family("stats_basic", "Описательная статистика и вероятность", "statistics", "посчитай",
        {1: Tier(-1.0, 1.4, 120), 2: Tier(0.2, 1.5, 180), 3: Tier(1.1, 1.7, 210)})
def stats_basic(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        xs = [rng.randint(1, 50) for _ in range(rng.choice([6, 7, 8]))]
        xs.append(rng.randint(150, 400))  # outlier: median vs mean
        rng.shuffle(xs)
        return Instance(prompt=f"Выборка времени ответа сервиса (мс): {', '.join(map(str, xs))}.\n\n"
                               "Чему равна медиана?", kind="number", answer=statistics.median(xs), tolerance=0.01)
    if tier == 2:
        r, b = rng.randint(3, 9), rng.randint(3, 9)
        n = r + b
        setting, events = rng.choice([
            (f"В урне {r} красных и {b} синих шаров.", ("оба красные", "оба синие", "шары разного цвета")),
            (f"В пуле {r} исправных и {b} сбойных серверов.",
             ("оба исправные", "оба сбойные", "один исправный, а другой сбойный")),
        ])
        k = rng.randrange(3)
        p = [r / n * (r - 1) / (n - 1), b / n * (b - 1) / (n - 1), 2 * r * b / (n * (n - 1))][k]
        return Instance(prompt=f"{setting} Без возвращения выбирают 2. Какова вероятность, что {events[k]}? "
                               "Ответ в процентах, округлите до целого.",
                        kind="number", answer=round(p * 100), tolerance=1)
    prev = rng.choice([0.5, 1, 2, 3, 5])
    sens = rng.choice([80, 90, 95, 99])
    fpr = rng.choice([1, 2, 5, 10])
    p = (sens / 100 * prev / 100) / (sens / 100 * prev / 100 + fpr / 100 * (1 - prev / 100))
    base, catch, flag, what = rng.choice([
        ("Мошеннических транзакций", "Антифрод-модель ловит", "Транзакция помечена", "она действительно мошенническая"),
        ("Писем-спама во входящих", "Фильтр распознаёт", "Письмо попало в спам", "это действительно спам"),
        ("Больных в популяции", "Тест выявляет", "Тест положительный", "человек действительно болен"),
    ])
    return Instance(prompt=f"{base} {prev}%. {catch} {sens}% из них и ошибочно срабатывает на {fpr}% остальных. "
                           f"{flag}. Какова вероятность, что {what}? В процентах, до целого.",
                    kind="number", answer=round(p * 100), tolerance=1,
                    explanation="Формула Байеса: P(F|+) = P(+|F)P(F) / P(+).")


@family("ml_metrics", "Метрики качества моделей", "ml", "посчитай",
        {1: Tier(-0.6, 1.5, 150), 2: Tier(0.4, 1.6, 180), 3: Tier(1.3, 1.7, 240)})
def ml_metrics(rng: random.Random, tier: int) -> Instance:
    tp, fp, fn, tn = rng.randint(20, 90), rng.randint(5, 40), rng.randint(5, 40), rng.randint(100, 400)
    matrix = f"TP = {tp}, FP = {fp}, FN = {fn}, TN = {tn}"
    if tier == 1:
        metric, val = rng.choice([("precision", tp / (tp + fp)), ("recall", tp / (tp + fn))])
        return Instance(prompt=f"Матрица ошибок бинарного классификатора: {matrix}.\n\nЧему равен {metric}? "
                               "Ответ в процентах, до целого.", kind="number", answer=round(val * 100),
                        tolerance=1)
    if tier == 2:
        p, r = tp / (tp + fp), tp / (tp + fn)
        return Instance(prompt=f"Матрица ошибок: {matrix}.\n\nЧему равна F1-мера? В процентах, до целого.",
                        kind="number", answer=round(2 * p * r / (p + r) * 100), tolerance=1)
    n = rng.randint(6, 8)
    scores = sorted(rng.sample(range(5, 99), n), reverse=True)
    labels = [1] * (n // 2) + [0] * (n - n // 2)
    rng.shuffle(labels)
    if len(set(labels)) < 2:
        labels[0], labels[-1] = 1, 0
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    auc = sum(1 for a in pos for b in neg if a > b) / (len(pos) * len(neg))
    rows = "\n".join(f"{s / 100:.2f}  {y}" for s, y in zip(scores, labels))
    return Instance(prompt="Скоры модели и истинные метки:\n\nЧему равен ROC-AUC? В процентах, до целого.",
                    kind="number", answer=round(auc * 100), tolerance=1, code=f"score label\n{rows}", lang="text",
                    explanation="AUC = доля пар (позитив, негатив), упорядоченных моделью верно.")


ML_DIAG = [
    ("train_loss {a:.2f}, val_loss {b:.2f} и продолжает расти с каждой эпохой", "Переобучение",
     lambda r: {"a": r.uniform(0.02, 0.1), "b": r.uniform(0.6, 1.2)}),
    ("train_accuracy {a:.0%}, val_accuracy {b:.0%}, обе кривые вышли на плато", "Недообучение",
     lambda r: {"a": r.uniform(0.55, 0.65), "b": r.uniform(0.52, 0.62)}),
    ("accuracy {a:.1%} на тесте, но положительный класс составляет {b:.1%} выборки, recall по нему — 3%",
     "Дисбаланс классов: accuracy вводит в заблуждение",
     lambda r: {"a": r.uniform(0.95, 0.99), "b": r.uniform(0.01, 0.04)}),
    ("val_accuracy {a:.1%} с первой эпохи; самый важный признак — id записи, присвоенный после разметки",
     "Утечка целевой переменной", lambda r: {"a": r.uniform(0.995, 0.999), "b": 0}),
]


@family("ml_diagnosis", "Диагностика обучения", "ml", "выбери диагноз",
        {2: Tier(0.0, 1.3, 120), 3: Tier(0.9, 1.4, 120)})
def ml_diagnosis(rng: random.Random, tier: int) -> Instance:
    pool = ML_DIAG[:2] if tier == 2 else ML_DIAG[2:]
    text, correct, gen = rng.choice(pool)
    return choice_instance(rng, f"Наблюдение: {text.format(**gen(rng))}.\n\nНаиболее вероятная причина?", correct,
                           [d[1] for d in ML_DIAG] + ["Слишком маленький learning rate"])


@family("pandas_ops", "Группировки и соединения таблиц", "pandas", "посчитай",
        {1: Tier(-0.5, 1.4, 120), 2: Tier(0.5, 1.6, 180)})
def pandas_ops(rng: random.Random, tier: int) -> Instance:
    keys = [rng.choice("ABCD") for _ in range(rng.randint(5, 8))]
    vals = [rng.randint(1, 20) for _ in keys]
    df = "df = pd.DataFrame({'k': " + str(keys) + ", 'v': " + str(vals) + "})"
    if tier == 1:
        t = rng.randint(5, 15)
        code = f"{df}\nres = df[df.v > {t}].groupby('k')['v'].sum()\nprint(len(res))"
        ans = len({k for k, v in zip(keys, vals) if v > t})
    else:
        right = [rng.choice("ABCE") for _ in range(rng.randint(3, 5))]
        code = (f"{df}\nright = pd.DataFrame({{'k': {right}, 'w': range({len(right)})}})\n"
                f"res = df.merge(right, on='k', how='left')\nprint(len(res))")
        cnt = Counter(right)
        ans = sum(max(cnt.get(k, 0), 1) for k in keys)
    return Instance(prompt="Что выведет программа?", kind="number", answer=ans, code=code, lang="python",
                    explanation="left merge даёт по строке на каждое совпадение справа (минимум одну).")


# ------------------------------------------------------------------------------------------------ QA


@family("qa_design", "Техники тест-дизайна", "test_design", "посчитай / выбери",
        {1: Tier(-1.1, 1.3, 120), 2: Tier(0.0, 1.5, 150), 3: Tier(1.0, 1.6, 180)})
def qa_design(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        lo, hi = rng.randint(1, 30), rng.randint(50, 150)
        field = rng.choice(["возраст", "количество товаров", "срок в днях"])
        return choice_instance(rng, f"Поле «{field}» принимает целые числа от {lo} до {hi} включительно. "
                                    "Какой набор — классический анализ граничных значений (2 значения на границу)?",
                               f"{lo - 1}, {lo}, {hi}, {hi + 1}",
                               [f"{lo}, {hi}", f"{lo + 1}, {hi - 1}", f"{lo - 1}, {hi + 1}",
                                f"{lo}, {(lo + hi) // 2}, {hi}"])
    if tier == 2:
        contexts = [
            ("Скидка в корзине", ["клиент новый", "есть промокод", "сумма больше порога", "товар по акции",
                                  "оплата картой банка-партнёра", "доставка самовывозом"]),
            ("Одобрение кредитной заявки", ["есть зарплатный проект", "стаж больше года", "нет просрочек",
                                            "подтверждён доход", "есть поручитель", "клиент VIP"]),
            ("Маршрутизация тикета поддержки", ["клиент платный", "ошибка блокирующая", "рабочее время",
                                               "повторное обращение", "язык не русский", "есть вложение"]),
            ("Доступ к документу", ["пользователь автор", "состоит в группе", "документ опубликован",
                                    "включён режим аудита", "есть подпись руководителя", "доступ из офиса"]),
        ]
        title, conds = rng.choice(contexts)
        k = rng.randint(2, 6)
        used = rng.sample(conds, k)
        extra = rng.randint(0, 1)
        prompt = (f"{title} зависит от {k} независимых булевых условий: {', '.join(used)}."
                  + (" Ещё одно условие — категория клиента — принимает 3 значения." if extra else "")
                  + " Сколько правил (столбцов) в полной таблице решений?")
        return Instance(prompt=prompt, kind="number", answer=2**k * (3 if extra else 1))
    counts = [rng.randint(2, 7) for _ in range(rng.randint(3, 5))]
    names = rng.sample(["браузер", "ОС", "язык", "тариф", "роль", "регион", "способ оплаты"], len(counts))
    params = ", ".join(f"{name}: {c}" for name, c in zip(names, counts))
    counts = sorted(counts, reverse=True)
    return Instance(prompt=f"Параметры и число их значений: {params}. Какое минимальное число тестов теоретически "
                           "требуется для попарного (pairwise) покрытия? (нижняя оценка)", kind="number",
                    answer=counts[0] * counts[1],
                    explanation="Каждую пару значений двух самых «широких» параметров нужно покрыть хотя бы раз.")


SEVERITY = [  # (tier, text, verdict)
    (1, "При оплате картой списываются деньги, но заказ не создаётся (воспроизводится у {n}% пользователей).",
     "Blocker/Critical: высокий приоритет"),
    (1, "После обновления {n}% пользователей не могут войти в приложение, обходного пути нет.",
     "Blocker/Critical: высокий приоритет"),
    (1, "В футере опечатка в названии компании (страница «{page}»).", "Trivial: низкий приоритет"),
    (1, "На странице «{page}» иконка смещена на {n} px относительно макета.", "Trivial: низкий приоритет"),
    (2, "Логотип клиента на странице «{page}» отображается неправильно перед завтрашним запуском.",
     "Minor по серьёзности, но высокий приоритет"),
    (2, "В юридическом тексте оферты на странице «{page}» неверная дата вступления в силу; релиз через {n} ч.",
     "Minor по серьёзности, но высокий приоритет"),
    (2, "Отчёт за год строится {n} минут вместо 10 секунд, обходной путь — выгрузка по месяцам.",
     "Major: средний приоритет"),
    (2, "Фильтр «{page}» в админке сбрасывается после {n} переходов, данные можно найти поиском.",
     "Major: средний приоритет"),
]
_PAGES = ["Корзина", "Профиль", "Каталог", "Главная", "Оплата", "Доставка", "О компании", "Тарифы"]


@family("qa_severity", "Серьёзность и приоритет дефектов", "test_design", "выбери вариант",
        {1: Tier(-0.8, 1.2, 90), 2: Tier(0.3, 1.3, 90)})
def qa_severity(rng: random.Random, tier: int) -> Instance:
    _, text, correct = rng.choice([s for s in SEVERITY if s[0] == tier])
    text = text.format(n=rng.randint(3, 40), page=rng.choice(_PAGES))
    return choice_instance(rng, text + "\n\nКак классифицировать дефект?", correct, sorted({s[2] for s in SEVERITY}))


API_FIELDS = [("id", "integer"), ("email", "string"), ("age", "integer"), ("active", "boolean"),
              ("score", "number"), ("name", "string"), ("tags", "array")]
_BAD = {"integer": '"42"', "string": "17", "boolean": '"yes"', "number": '"9.5"', "array": '"a,b"'}
_GOOD = {"integer": "42", "string": '"text"', "boolean": "true", "number": "9.5", "array": '["a", "b"]'}


@family("api_contract", "Контракт API", "api_testing", "найди нарушение",
        {1: Tier(-0.6, 1.4, 120), 2: Tier(0.5, 1.6, 150)})
def api_contract(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        res = rng.choice(["orders", "tickets", "users", "invoices", "projects"])
        n = rng.randint(2, 6)
        m = rng.randint(1, 5)
        rid = rng.randint(10, 999)
        method, ans = rng.choice([
            (f"POST /{res}", m + n),
            (f"PUT /{res}/{rid}", m + 1),
            (f"DELETE /{res}/{rid}", m - 1),
        ])
        state = (f"{m} записей, записи с id={rid} среди них нет" if method.startswith("PUT")
                 else f"{m} записей, включая запись с id={rid}" if method.startswith("DELETE") else f"{m} записей")
        return Instance(prompt=f"До теста в коллекции `/{res}` было {state}. Тест {n} раз подряд отправил "
                               f"одинаковый запрос `{method}` с одним и тем же телом (ключа идемпотентности нет). "
                               f"Сколько записей останется, если API реализовано по семантике HTTP?",
                        kind="number", answer=ans,
                        explanation="PUT и DELETE идемпотентны, POST — нет; PUT на несуществующий id создаёт запись.")
    fields = rng.sample(API_FIELDS, 5)
    required = [f for f in fields if rng.random() < 0.7] or fields[:1]
    broken = rng.choice(fields)
    mode = "missing" if broken in required and rng.random() < 0.5 else "type"
    schema = "\n".join(f"  {n}: {t}{' (required)' if (n, t) in required else ''}" for n, t in fields)
    body = []
    for n, t in fields:
        if (n, t) == broken and mode == "missing":
            continue
        if (n, t) == broken:
            body.append(f'  "{n}": {_BAD[t]}')
        elif (n, t) in required or rng.random() < 0.6:
            body.append(f'  "{n}": {_GOOD[t]}')
    return choice_instance(rng, "Какое поле ответа нарушает контракт?", broken[0], [f[0] for f in fields],
                           code=f"# схема\n{schema}\n\n# ответ\n{{\n" + ",\n".join(body) + "\n}", lang="text")


@family("pytest_fixtures", "Фикстуры и параметризация pytest", "autotests", "посчитай",
        {2: Tier(0.3, 1.5, 150), 3: Tier(1.2, 1.7, 180)})
def pytest_fixtures(rng: random.Random, tier: int) -> Instance:
    if tier == 2:
        files = rng.randint(2, 4)
        per = [rng.randint(1, 5) for _ in range(files)]
        scope = rng.choice(["function", "module", "session"])
        ans = {"function": sum(per), "module": files, "session": 1}[scope]
        fx = rng.choice(["db", "client", "browser", "redis", "tmp_repo"])
        code = (f"# conftest.py\n@pytest.fixture(scope='{scope}')\ndef {fx}():\n    print('setup')\n"
                f"    yield make_{fx}()\n\n"
                + "\n".join(f"# test_{i + 1}.py: {p} тест(а), каждый использует {fx}" for i, p in enumerate(per)))
        return Instance(prompt="Сколько раз напечатается «setup» при запуске всех тестов?", kind="number",
                        answer=ans, code=code, lang="python")
    a = rng.sample(["'ru'", "'en'", "'de'", "'fr'"], rng.randint(2, 3))
    b = list(range(rng.randint(2, 4)))
    extra = rng.randint(1, 3)
    code = (f"@pytest.mark.parametrize('lang', [{', '.join(a)}])\n@pytest.mark.parametrize('n', {b})\n"
            f"def test_render(lang, n): ...\n\n" + "\n".join(f"def test_other_{i}(): ..." for i in range(extra)))
    return Instance(prompt="Сколько тестов соберёт pytest?", kind="number", answer=len(a) * len(b) + extra,
                    code=code, lang="python")


# ------------------------------------------------------------------------------------------------ DevOps


def _sym(octal: str) -> str:
    out = ""
    for d in octal:
        v = int(d)
        out += ("r" if v & 4 else "-") + ("w" if v & 2 else "-") + ("x" if v & 1 else "-")
    return out


@family("linux_perms", "Права доступа Linux", "linux", "посчитай",
        {1: Tier(-0.9, 1.5, 90), 2: Tier(0.2, 1.6, 120), 3: Tier(1.0, 1.6, 150)})
def linux_perms(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        octal = "".join(str(rng.choice([7, 6, 5, 4, 0, 1, 2, 3])) for _ in range(3))
        return Instance(prompt=f"Как будут выглядеть права после `chmod {octal} app.sh` в выводе `ls -l` "
                               "(9 символов, например rwxr-x---)?", kind="text", answer=_sym(octal))
    if tier == 2:
        umask = rng.choice("002") + rng.choice("02357") + rng.choice("024567")
        obj, base = rng.choice([("файл", 0o666), ("каталог", 0o777)])
        val = base & ~int(umask, 8)
        if rng.random() < 0.5:
            return Instance(prompt=f"umask = {umask}. С какими правами (в восьмеричном виде, 3 цифры) будет создан "
                                   f"новый {obj}?", kind="text", answer=f"{val:03o}")
        return Instance(prompt=f"umask = {umask}. Как будут выглядеть права нового объекта ({obj}) в выводе `ls -l` "
                               "(9 символов, например rwxr-x---)?", kind="text", answer=_sym(f"{val:03o}"))
    start = rng.choice(["644", "664", "755", "600", "666"])
    perms = [int(d) for d in start]
    ops = []
    for who, idx in rng.sample([("u", 0), ("g", 1), ("o", 2)], 2):
        bit, ch = rng.choice([(4, "r"), (2, "w"), (1, "x")])
        op = rng.choice(["+", "-", "="])
        if op == "+":
            perms[idx] |= bit
        elif op == "-":
            perms[idx] &= ~bit
        else:
            perms[idx] = bit
        ops.append(f"{who}{op}{ch}")
    return Instance(prompt=f"У файла права {start}. Выполнили `chmod {','.join(ops)} file`. Какие права теперь "
                           f"(восьмеричные, 3 цифры)?", kind="text", answer="".join(map(str, perms)))


@family("bash_pipeline", "Конвейеры shell", "bash", "предскажи вывод",
        {1: Tier(-0.5, 1.4, 120), 2: Tier(0.5, 1.6, 150), 3: Tier(1.3, 1.7, 180)})
def bash_pipeline(rng: random.Random, tier: int) -> Instance:
    users = rng.sample(NAMES, 4)
    codes = ["200", "404", "500", "301"]
    lines = [f"{rng.choice(users)},{rng.choice(codes)}" for _ in range(rng.randint(7, 10))]
    if tier == 1:
        code = rng.choice(codes)
        cmd = f"grep -c ',{code}$' access.log"
        ans = str(sum(1 for ln in lines if ln.endswith("," + code)))
    elif tier == 2:
        cmd = "cut -d, -f1 access.log | sort -u | wc -l"
        ans = str(len({ln.split(",")[0] for ln in lines}))
    else:
        cmd = "cut -d, -f2 access.log | sort | uniq -c | sort -rn | head -1"
        cnt = Counter(ln.split(",")[1] for ln in lines)
        top = max(cnt.values())
        winners = sorted([c for c, v in cnt.items() if v == top], reverse=True)  # sort -rn tie → reverse lexical
        ans = f"{top} {winners[0]}"
    return Instance(prompt="Что выведет команда?", kind="text", answer=ans,
                    code="$ cat access.log\n" + "\n".join(lines) + f"\n\n$ {cmd}", lang="bash")


@family("docker_cache", "Кэш слоёв Docker", "docker", "посчитай",
        {1: Tier(-0.4, 1.4, 120), 2: Tier(0.6, 1.6, 150)})
def docker_cache(rng: random.Random, tier: int) -> Instance:
    lang = rng.choice(["python", "node"])
    if lang == "python":
        steps = ["FROM python:3.12-slim", "WORKDIR /app", "RUN apt-get update && apt-get install -y libpq5",
                 "COPY requirements.txt .", "RUN pip install -r requirements.txt", "COPY . .",
                 "RUN python -m compileall .", 'CMD ["python", "main.py"]']
        files = ["src/main.py", "requirements.txt"]
    else:
        steps = ["FROM node:20-alpine", "WORKDIR /app", "COPY package.json package-lock.json ./", "RUN npm ci",
                 "COPY . .", "RUN npm run build", 'CMD ["node", "dist/index.js"]']
        files = ["src/index.ts", "package.json"]
    # surface variety: optional extra instructions before the dependency layer and after the source copy
    steps[2:2] = rng.sample(["ENV TZ=Europe/Moscow", "RUN useradd -m app", "ARG BUILD_ID", "RUN mkdir -p /data",
                             "LABEL team=core", "RUN apk add --no-cache curl", "ENV LANG=C.UTF-8"], rng.randint(0, 3))
    src = steps.index("COPY . .")
    steps[src + 1:src + 1] = rng.sample(["RUN chown -R app /app", "EXPOSE 8000", "RUN rm -rf /tmp/*",
                                         "ENV MODE=prod", "RUN ./scripts/check.sh", "USER app"], rng.randint(0, 3))
    if tier == 2 and rng.random() < 0.6:
        # anti-pattern: copy everything before installing dependencies
        steps.insert(next(i for i, s in enumerate(steps) if s.startswith("COPY")), steps.pop(steps.index("COPY . .")))
    changed = rng.choice(files) if tier == 2 else files[0]

    def covers(step: str) -> bool:
        return step.startswith("COPY") and (step == "COPY . ." or changed.split("/")[-1] in step)

    first = next(i for i, s in enumerate(steps) if covers(s))
    rebuilt = sum(1 for s in steps[first:] if s.split()[0] in ("RUN", "COPY"))
    dockerfile = "\n".join(steps)
    return Instance(prompt=f"Образ уже собран. Разработчик изменил только `{changed}` и снова запустил `docker build`."
                           " Сколько инструкций RUN/COPY выполнится заново (не из кэша)?", kind="number",
                    answer=rebuilt, code=dockerfile, lang="dockerfile",
                    explanation="Кэш инвалидируется с первой инструкции, чьи входные файлы изменились, и далее.")


@family("k8s_capacity", "Ресурсы и автомасштабирование Kubernetes", "kubernetes", "посчитай",
        {2: Tier(0.5, 1.5, 150), 3: Tier(1.4, 1.7, 180)})
def k8s_capacity(rng: random.Random, tier: int) -> Instance:
    if tier == 2:
        alloc = rng.choice([3800, 3900, 7800, 7900])
        used = rng.choice(range(300, 1501, 100))
        req = rng.choice([250, 300, 400, 500, 600])
        return Instance(prompt=f"На ноде allocatable CPU = {alloc}m, уже запрошено {used}m. Под запрашивает "
                               f"requests.cpu = {req}m (limits = {req * 2}m). Сколько таких подов ещё поместится на "
                               "ноду?", kind="number", answer=(alloc - used) // req,
                        explanation="Планировщик учитывает requests, а не limits.")
    cur = rng.randint(2, 8)
    util = rng.randint(55, 160)
    target = rng.choice([50, 60, 70, 80])
    mx = rng.randint(6, 14)
    desired = min(mx, math.ceil(cur * util / target))
    return Instance(prompt=f"HPA: сейчас {cur} реплик, средняя загрузка CPU {util}% от requests, целевая — "
                           f"{target}%, maxReplicas = {mx}. Сколько реплик выставит HPA?", kind="number",
                    answer=desired, explanation="desired = ceil(current × currentMetric / target), "
                                                "в пределах min/max.")


def _cron_count(minute: str, hour: str, dow: str) -> int:
    def expand(f: str, lo: int, hi: int) -> set[int]:
        out: set[int] = set()
        for part in f.split(","):
            step = 1
            if "/" in part:
                part, s = part.split("/")
                step = int(s)
            if part == "*":
                a, b = lo, hi
            elif "-" in part:
                a, b = map(int, part.split("-"))
            else:
                a = b = int(part)
            out |= set(range(a, b + 1, step))
        return out

    return len(expand(minute, 0, 59)) * len(expand(hour, 0, 23)) * len(expand(dow, 0, 6))


@family("cron_schedule", "Расписания cron", "ci_cd", "посчитай",
        {1: Tier(-0.6, 1.4, 120), 2: Tier(0.5, 1.6, 150)})
def cron_schedule(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        minute = rng.choice(["0", "30", "*/15", "*/20", "0,30", "*/10", "15,45", "*/5", "0,20,40", "*/30", "5",
                             "10-14"])
        hour = rng.choice(["*", "3", "9-17", "*/6", "8-20", "*/2", "0,12", "10-18/2", "*/3", "1-5", "9,13,18", "22"])
        expr = f"{minute} {hour} * * *"
        return Instance(prompt=f"Сколько раз в сутки запустится задача по расписанию `{expr}`?", kind="number",
                        answer=_cron_count(minute, hour, "*") // 7, code=expr, lang="text")
    minute = rng.choice(["*/10", "*/15", "0,30", "5", "*/20", "0,15,45"])
    hour = rng.choice(["9-18", "8-20/2", "*/4", "10,14,18", "0-6", "12"])
    dow = rng.choice(["1-5", "1,3,5", "6,0", "*", "2-4", "5"])
    expr = f"{minute} {hour} * * {dow}"
    return Instance(prompt=f"Сколько раз в неделю запустится CI-задача по расписанию `{expr}`?", kind="number",
                    answer=_cron_count(minute, hour, dow), code=expr, lang="text")


# ------------------------------------------------------------------------------------------------ bank extension
# Specialization pools were too small for an 18-item test: QA, DevOps and Data candidates saw almost every slot of
# their pool. The families below widen the thin skills, so that exposure control has alternatives to rotate.


@family("stats_inference", "Выборочные оценки и A/B-тесты", "statistics", "посчитай",
        {1: Tier(-0.7, 1.4, 150), 2: Tier(0.3, 1.6, 180), 3: Tier(1.3, 1.7, 240)})
def stats_inference(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        n1, n2 = rng.randint(5, 40), rng.randint(5, 40)
        m1, m2 = rng.randint(20, 90), rng.randint(20, 90)
        what = rng.choice([("сотрудников", "средний стаж в месяцах"), ("заказов", "средний чек в сотнях рублей"),
                           ("запросов", "среднее время ответа в мс")])
        return Instance(prompt=f"В группе A {n1} {what[0]}, {what[1]} — {m1}. В группе B {n2} {what[0]}, "
                               f"{what[1]} — {m2}. Каково среднее по объединённой группе? До десятых.",
                        kind="number", answer=round((n1 * m1 + n2 * m2) / (n1 + n2), 1), tolerance=0.1,
                        explanation="Среднее объединённой группы — взвешенное по размерам групп.")
    if tier == 2:
        n = rng.choice([16, 25, 36, 49, 64, 100, 144])
        s = rng.randint(4, 40)
        mean = rng.randint(50, 500)
        half = 1.96 * s / math.sqrt(n)
        return Instance(prompt=f"Выборка из {n} измерений: среднее {mean}, стандартное отклонение {s}. Какова "
                               "полуширина 95%-го доверительного интервала для среднего (z = 1,96)? До десятых.",
                        kind="number", answer=round(half, 1), tolerance=0.1,
                        explanation="Полуширина = z · s / √n.")
    n = rng.choice([1000, 2000, 4000, 5000])
    pa = rng.choice(range(40, 121, 5)) / 1000
    pb = pa + rng.choice([-1, 1]) * rng.choice(range(5, 31, 5)) / 1000
    ca, cb = round(n * pa), round(n * pb)
    p = (ca + cb) / (2 * n)
    z = (cb / n - ca / n) / math.sqrt(p * (1 - p) * 2 / n)
    return Instance(prompt=f"A/B-тест: в каждой группе по {n} пользователей. Конверсий в A — {ca}, в B — {cb}. "
                           "Чему равна z-статистика двухвыборочного теста для долей (объединённая оценка дисперсии, "
                           "B минус A)? До десятых.", kind="number", answer=round(z, 1), tolerance=0.15,
                    explanation="z = (p_B − p_A) / √(p(1−p)(1/n_A + 1/n_B)), p — общая доля конверсий.")


@family("pandas_clean", "Пропуски, дубликаты и transform", "pandas", "предскажи вывод",
        {1: Tier(-0.4, 1.4, 120), 2: Tier(0.4, 1.5, 150), 3: Tier(1.2, 1.7, 180)})
def pandas_clean(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        vals = [rng.choice([None, rng.randint(1, 20)]) for _ in range(rng.randint(5, 7))]
        if all(v is None for v in vals):
            vals[0] = rng.randint(1, 20)
        if None not in vals:
            vals[-1] = None
        filled = rng.random() < 0.5
        expr = "df['v'].fillna(0).mean()" if filled else "df['v'].mean()"
        known = [v for v in vals if v is not None]
        ans = sum(known) / (len(vals) if filled else len(known))
        shown = "[" + ", ".join("None" if v is None else str(v) for v in vals) + "]"
        return Instance(prompt="Что выведет программа? До сотых.", kind="number", answer=round(ans, 2),
                        tolerance=0.01, code=f"df = pd.DataFrame({{'v': {shown}}})\nprint({expr})", lang="python",
                        explanation="mean() по умолчанию пропускает NaN; после fillna(0) пропуски считаются нулями.")
    keys = [rng.choice("ABCD") for _ in range(rng.randint(6, 9))]
    vals = [rng.randint(1, 9) for _ in keys]
    df = "df = pd.DataFrame({'k': " + str(keys) + ", 'v': " + str(vals) + "})"
    if tier == 2:
        keep = rng.choice(["first", "last"])
        chosen: dict[str, int] = {}
        for k, v in zip(keys, vals):
            if keep == "last" or k not in chosen:
                chosen[k] = v
        return Instance(prompt="Что выведет программа?", kind="number", answer=sum(chosen.values()),
                        code=f"{df}\nprint(df.drop_duplicates(subset='k', keep='{keep}')['v'].sum())",
                        lang="python")
    agg = rng.choice(["max", "min"])
    pick = max if agg == "max" else min
    best = {k: pick(v for kk, v in zip(keys, vals) if kk == k) for k in set(keys)}
    ans = sum(1 for k, v in zip(keys, vals) if v == best[k])
    return Instance(prompt="Что выведет программа?", kind="number", answer=ans, lang="python",
                    code=f"{df}\ndf['m'] = df.groupby('k')['v'].transform('{agg}')\n"
                         "print((df['v'] == df['m']).sum())",
                    explanation="transform возвращает значение агрегата для каждой строки группы; ничьи считаются "
                                "все.")


@family("api_resilience", "Пагинация, лимиты и повторы", "api_testing", "посчитай",
        {1: Tier(-0.8, 1.4, 120), 2: Tier(0.4, 1.6, 180), 3: Tier(1.1, 1.6, 180)})
def api_resilience(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        total, per = rng.randint(41, 997), rng.choice([10, 20, 25, 50, 100])
        res = rng.choice(["заказов", "пользователей", "тикетов", "платежей"])
        if rng.random() < 0.5:
            return Instance(prompt=f"API отдаёт список {res} страницами (`?page=N&per_page={per}`), всего {total} "
                                   "записей. Сколько запросов нужно, чтобы выгрузить все записи?",
                            kind="number", answer=math.ceil(total / per))
        return Instance(prompt=f"API отдаёт список {res} страницами по {per}, всего {total} записей. Сколько "
                               "записей будет на последней странице?", kind="number", answer=total % per or per)
    if tier == 2:
        cap, refill = rng.randint(5, 20), rng.randint(1, 5)
        b1, gap, b2 = rng.randint(cap - 2, cap + 10), rng.randint(1, 6), rng.randint(3, 15)
        ok1 = min(b1, cap)
        tokens = min(cap, cap - ok1 + refill * gap)
        rejected = (b1 - ok1) + max(0, b2 - tokens)
        return Instance(prompt=f"Лимит запросов — token bucket: ёмкость {cap} токенов, пополнение {refill} в секунду, "
                               "каждый запрос тратит 1 токен, при пустом ведре сервер отвечает 429. Ведро полное. "
                               f"Тест мгновенно отправляет {b1} запросов, ждёт {gap} с и мгновенно отправляет ещё "
                               f"{b2}. Сколько ответов 429 получит тест?", kind="number", answer=rejected,
                        explanation="Ведро не наполняется выше ёмкости; токены за паузу = скорость × время.")
    base, factor = rng.choice([0.2, 0.5, 1, 2, 3]), rng.choice([2, 3])
    retries, cap = rng.randint(3, 7), rng.choice([5, 10, 15, 20, 30])
    waits = [min(cap, base * factor ** i) for i in range(retries)]
    return Instance(prompt=f"Клиент повторяет неуспешный запрос с экспоненциальной задержкой: первая пауза {base} с, "
                           f"каждая следующая в {factor} раза длиннее, но не больше {cap} с; максимум {retries} "
                           "повторов. Сервис всё время отвечает 503. Сколько секунд в сумме клиент проведёт в "
                           "паузах? (время самих запросов не учитывайте)", kind="number",
                    answer=round(sum(waits), 1), tolerance=0.05,
                    explanation="Паузы: base · factor^i, обрезанные сверху значением cap.")


_TEST_AREAS = ["login", "cart", "search", "profile", "payment"]
_TEST_CASES = ["ok", "invalid", "slow", "timeout", "empty"]


@family("autotest_runs", "Отбор, перезапуски и распределение автотестов", "autotests", "посчитай",
        {1: Tier(-0.6, 1.4, 120), 2: Tier(0.5, 1.6, 180), 3: Tier(1.2, 1.6, 210)})
def autotest_runs(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        names = sorted(rng.sample([f"test_{a}_{c}" for a in _TEST_AREAS for c in _TEST_CASES], rng.randint(6, 9)))
        a, b = rng.sample(_TEST_AREAS, 2)
        expr, pred = rng.choice([
            (f"{a} and not slow", lambda n: a in n and "slow" not in n),
            (f"{a} or {b}", lambda n: a in n or b in n),
            (f"not {a} and not timeout", lambda n: a not in n and "timeout" not in n),
            (f"({a} or {b}) and ok", lambda n: (a in n or b in n) and "ok" in n),
        ])
        return Instance(prompt=f"Сколько тестов выполнит `pytest -k \"{expr}\"`?", kind="number",
                        answer=sum(1 for n in names if pred(n)), code="\n".join(names), lang="text",
                        explanation="-k сопоставляет выражение с подстроками имён тестов.")
    if tier == 2:
        flaky, p, reruns = rng.randint(2, 15), rng.choice([5, 10, 15, 20, 25, 30]), rng.choice([0, 1, 2])
        green = (1 - (p / 100) ** (reruns + 1)) ** flaky
        return Instance(prompt=f"В наборе {flaky} нестабильных тестов, каждый независимо падает с вероятностью {p}% "
                               f"при каждом запуске; остальные тесты стабильны. CI запускает набор с `--reruns "
                               f"{reruns}` (упавший тест перезапускается до {reruns} раз). Какова вероятность "
                               "зелёного прогона? В процентах, до целого.", kind="number",
                        answer=round(green * 100), tolerance=1,
                        explanation="Тест красный, только если упал во всех reruns + 1 попытках.")
    workers = rng.randint(2, 4)
    durations = [rng.randint(1, 12) for _ in range(rng.randint(6, 9))]
    load = [0] * workers
    for d in sorted(durations, reverse=True):
        load[load.index(min(load))] += d
    return Instance(prompt=f"Тесты длительностью (мин) {', '.join(map(str, durations))} распределяются на {workers} "
                           "параллельных воркера жадно: по убыванию длительности, каждый тест — на наименее "
                           "загруженный воркер. Через сколько минут закончится весь прогон?", kind="number",
                    answer=max(load), explanation="Время прогона — нагрузка самого загруженного воркера.")


_PORTS = [80, 8000, 3000, 5000, 8080]


@family("docker_runtime", "Порты, перезапуски и многоэтапная сборка", "docker", "посчитай / выбери",
        {1: Tier(-0.6, 1.4, 120), 2: Tier(0.3, 1.5, 150), 3: Tier(1.2, 1.6, 180)})
def docker_runtime(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        host, cont = rng.choice([8080, 8000, 3000, 5000, 9090]), rng.choice(_PORTS)
        app = cont if rng.random() < 0.6 else rng.choice([p for p in _PORTS if p != cont])
        bind = "0.0.0.0" if rng.random() < 0.75 else "127.0.0.1"
        ok = app == cont and bind == "0.0.0.0"
        none = "Ни по какому: запрос не дойдёт до приложения"
        correct = f"http://localhost:{host}" if ok else none
        return choice_instance(rng, f"Контейнер запущен командой `docker run -p {host}:{cont} app`. Приложение "
                                    f"внутри слушает {bind}:{app}. По какому адресу оно доступно с хоста?", correct,
                               [f"http://localhost:{cont}", f"http://localhost:{app}", f"http://localhost:{host}",
                                none],
                               explanation="-p HOST:CONTAINER пробрасывает порт контейнера; приложение должно "
                                           "слушать этот порт на 0.0.0.0, а не на loopback контейнера.")
    if tier == 2:
        fails, code = rng.randint(1, 7), rng.choice([1, 2, 3, 137])
        k = rng.randint(1, 6)
        policy, starts = rng.choice([("no", 1), (f"on-failure:{k}", min(fails, k) + 1), ("on-failure", fails + 1)])
        final = 0 if starts > fails else code
        ask = rng.randrange(3)
        question = ["Сколько всего раз запустится контейнер, включая первый запуск?",
                    "Сколько раз Docker перезапустит контейнер?",
                    "Какой код завершения покажет `docker inspect` в итоге?"][ask]
        return Instance(prompt=f"Процесс в контейнере первые {fails} запусков падает с кодом {code}, а затем "
                               f"завершается с кодом 0. Политика `--restart {policy}`. {question}", kind="number",
                        answer=[starts, starts - 1, final][ask],
                        explanation="on-failure:N перезапускает только при ненулевом коде и не более N раз.")
    if rng.random() < 0.5:
        base_name, base = rng.choice([("alpine:3.20", 8), ("gcr.io/distroless/static", 2), ("scratch", 0)])
        binary, builder, extra = rng.randint(10, 60), rng.randint(600, 900), rng.choice([0, 0, 3, 5])
        add = (f"\nRUN apk add --no-cache ca-certificates  # +{extra} МБ"
               if extra and base_name.startswith("alpine") else "")
        size = base + binary + (extra if add else 0)
        code = (f"FROM golang:1.23 AS build  # {builder} МБ\nWORKDIR /src\nCOPY . .\n"
                f"RUN go build -o /out/app .  # бинарник {binary} МБ\n\nFROM {base_name}  # {base} МБ{add}\n"
                "COPY --from=build /out/app /app\nENTRYPOINT [\"/app\"]")
    else:
        base, blob = rng.choice([45, 120, 150]), rng.randint(50, 400)
        size = base + blob
        code = (f"FROM python:3.12-slim  # {base} МБ\n"
                f"RUN curl -o /tmp/data.tar.gz https://example.org/data.tar.gz  # архив {blob} МБ\n"
                "RUN tar -xzf /tmp/data.tar.gz -C /opt && rm /tmp/data.tar.gz  # распакованные файлы ~0 МБ\n"
                "CMD [\"python\", \"-m\", \"app\"]")
    return Instance(prompt="Какого размера (МБ) будет итоговый образ? Метаданные не учитывайте.", kind="number",
                    answer=size, code=code, lang="dockerfile",
                    explanation="В итоговый образ попадают только слои последней стадии; удаление файла в следующем "
                                "слое не уменьшает предыдущий.")


@family("k8s_rollout", "Раскатка и доступность в Kubernetes", "kubernetes", "посчитай",
        {1: Tier(-0.5, 1.4, 120), 2: Tier(0.4, 1.6, 150), 3: Tier(1.1, 1.6, 180)})
def k8s_rollout(rng: random.Random, tier: int) -> Instance:
    replicas = rng.randint(3, 20)
    ask_max = rng.random() < 0.5
    question = ("Какое максимальное число подов может существовать одновременно во время раскатки?" if ask_max
                else "Какое минимальное число доступных подов гарантируется во время раскатки?")
    if tier == 1:
        surge, unavail = rng.randint(1, 4), rng.randint(0, 3)
        return Instance(prompt=f"Deployment: replicas = {replicas}, стратегия RollingUpdate с maxSurge = {surge} и "
                               f"maxUnavailable = {unavail}. {question}", kind="number",
                        answer=replicas + surge if ask_max else replicas - unavail)
    if tier == 2:
        sp, up = rng.choice([10, 20, 25, 30, 50]), rng.choice([10, 20, 25, 30, 50])
        ans = replicas + math.ceil(replicas * sp / 100) if ask_max else replicas - math.floor(replicas * up / 100)
        return Instance(prompt=f"Deployment: replicas = {replicas}, maxSurge = {sp}%, maxUnavailable = {up}%. "
                               f"{question}", kind="number", answer=ans,
                        explanation="Проценты maxSurge округляются вверх, maxUnavailable — вниз.")
    pct = rng.choice([50, 60, 70, 75, 80, 90])
    healthy = replicas - rng.randint(0, 2)
    if rng.random() < 0.5:
        min_av, rule = math.ceil(replicas * pct / 100), f"minAvailable: {pct}%"
    else:
        min_av, rule = replicas - math.ceil(replicas * (100 - pct) / 100), f"maxUnavailable: {100 - pct}%"
    return Instance(prompt=f"Deployment из {replicas} реплик, сейчас здоровы {healthy}. PodDisruptionBudget: {rule}. "
                           "Сколько подов можно вытеснить (drain ноды) прямо сейчас, не нарушив PDB?",
                    kind="number", answer=max(0, healthy - min_av),
                    explanation="Проценты в PDB округляются вверх; бюджет считается от здоровых подов.")


_CI_JOBS = ["lint", "unit", "build", "e2e", "docs", "scan", "deploy", "migrate", "package"]
_CI_PATTERNS = ["backend/**/*", "frontend/**/*", "docs/**/*", "**/*.md", "docker-compose.yml", "deploy/**/*"]
_CI_FILES = ["backend/app/main.py", "frontend/src/App.tsx", "docs/api.md", "README.md", "docker-compose.yml",
             "deploy/nginx.conf", "backend/README.md", "e2e/flow.spec.ts"]


def _glob(pattern: str, path: str) -> bool:
    if pattern.endswith("/**/*"):
        return path.startswith(pattern[:-4])
    if pattern.startswith("**/*"):
        return path.endswith(pattern[4:])
    return path == pattern


@family("ci_pipeline", "Длительность и условия запуска CI", "ci_cd", "посчитай",
        {1: Tier(-0.7, 1.4, 150), 2: Tier(0.4, 1.6, 180), 3: Tier(1.2, 1.6, 180)})
def ci_pipeline(rng: random.Random, tier: int) -> Instance:
    jobs = rng.sample(_CI_JOBS, rng.randint(5, 7))
    dur = {j: rng.randint(1, 9) for j in jobs}
    if tier == 1:
        stages = [jobs[:2], jobs[2:4], jobs[4:]]
        lines = [f"{j}: stage {i + 1}, {dur[j]} мин" for i, st in enumerate(stages) for j in st]
        return Instance(prompt="Пайплайн со стадиями: задачи одной стадии идут параллельно (раннеров хватает), "
                               "стадия начинается после завершения предыдущей. Сколько минут займёт пайплайн?",
                        kind="number", answer=sum(max(dur[j] for j in st) for st in stages),
                        code="\n".join(lines), lang="text")
    if tier == 2:
        needs = {j: sorted(rng.sample(jobs[:i], min(i, rng.randint(0, 2)))) for i, j in enumerate(jobs)}
        finish: dict[str, int] = {}
        for j in jobs:
            finish[j] = max((finish[n] for n in needs[j]), default=0) + dur[j]
        lines = [f"{j}: {dur[j]} мин, needs: [{', '.join(needs[j])}]" for j in jobs]
        return Instance(prompt="Задача запускается, как только завершены все задачи из её needs (раннеров хватает). "
                               "Сколько минут займёт пайплайн?", kind="number", answer=max(finish.values()),
                        code="\n".join(lines), lang="text",
                        explanation="Длительность — самый длинный путь в графе зависимостей.")
    rules = {j: rng.sample(_CI_PATTERNS, rng.randint(1, 2)) for j in jobs}
    files = rng.sample(_CI_FILES, rng.randint(1, 3))
    ran = sum(1 for j in jobs if any(_glob(p, f) for p in rules[j] for f in files))
    lines = [f"{j}: rules: changes: [{', '.join(rules[j])}]" for j in jobs]
    return Instance(prompt=f"В merge request изменены файлы: {', '.join(files)}. Сколько задач запустится? "
                           "(`dir/**/*` — любой файл внутри dir, `**/*.md` — любой .md в любом каталоге)",
                    kind="number", answer=ran, code="\n".join(lines), lang="yaml")


_SIGNALS = [("SIGINT (Ctrl+C)", 2), ("SIGKILL (OOM killer)", 9), ("SIGTERM", 15), ("SIGHUP", 1), ("SIGQUIT", 3),
            ("SIGABRT", 6), ("SIGSEGV", 11), ("SIGPIPE", 13), ("SIGALRM", 14), ("SIGUSR1", 10)]
_EXIT_PLACES = ["shell-скрипте", "CI-задаче", "systemd-юните", "init-контейнере пода"]


@family("linux_exit", "Коды возврата и конвейеры shell", "linux", "посчитай",
        {1: Tier(-0.6, 1.4, 120), 2: Tier(0.4, 1.6, 150), 3: Tier(1.1, 1.6, 150)})
def linux_exit(rng: random.Random, tier: int) -> Instance:
    cmds = rng.sample(["fetch", "check", "build", "upload", "notify", "migrate"], 3)
    codes = {c: rng.choice([0, 0, 1, 2, 3]) for c in cmds}
    table = "\n".join(f"# {c} завершается с кодом {codes[c]}" for c in cmds)
    a, b, c = cmds
    if tier == 1:
        r = codes[a]
        if r == 0:
            r = codes[b]
        if r != 0:
            r = codes[c]
        return Instance(prompt="Что выведет echo?", kind="number", answer=r, lang="bash",
                        code=f"{table}\n\n{a} && {b} || {c}\necho $?",
                        explanation="`a && b || c` = `(a && b) || c`; $? — код последней выполненной команды.")
    if tier == 2:
        pipefail = rng.random() < 0.5
        nonzero = [codes[x] for x in cmds if codes[x] != 0]
        r = (nonzero[-1] if nonzero else 0) if pipefail else codes[c]
        setup = "set -o pipefail\n" if pipefail else ""
        return Instance(prompt="Что выведет echo?", kind="number", answer=r, lang="bash",
                        code=f"{table}\n\n{setup}{a} | {b} | {c}\necho $?",
                        explanation="Без pipefail код конвейера — код последней команды; с pipefail — самой правой "
                                    "упавшей.")
    if rng.random() < 0.4:
        name, sig = rng.choice(_SIGNALS)
        return Instance(prompt=f"Команда в {rng.choice(_EXIT_PLACES)} завершена сигналом {name}. Какой код возврата "
                               "увидит вызывающий shell в `$?`?", kind="number", answer=128 + sig,
                        explanation="Завершение сигналом N даёт код 128 + N.")
    n = rng.choice([rng.randint(256, 700), rng.randint(-255, -1)])
    return Instance(prompt=f"Программа вызывает `exit({n})`. Какой код возврата увидит shell?", kind="number",
                    answer=n % 256, explanation="Код возврата — младший байт: N mod 256.")


_ORDER_STATES = ["Новый", "Оплачен", "Собран", "Отправлен", "Доставлен", "Отменён", "Возврат"]
_ORDER_EVENTS = ["оплатить", "собрать", "отправить", "доставить", "отменить", "вернуть"]


@family("qa_states", "Тестирование переходов состояний", "test_design", "посчитай",
        {1: Tier(-0.7, 1.4, 150), 2: Tier(0.5, 1.6, 180), 3: Tier(1.2, 1.6, 210)})
def qa_states(rng: random.Random, tier: int) -> Instance:
    states = rng.sample(_ORDER_STATES, rng.randint(4, 6))
    events = rng.sample(_ORDER_EVENTS, rng.randint(3, 5))
    trans, seen = [], set()
    for _ in range(rng.randint(5, 9)):
        a, e, b = rng.choice(states), rng.choice(events), rng.choice(states)
        if (a, e) not in seen and a != b:
            seen.add((a, e))
            trans.append((a, e, b))
    table = "\n".join(f"{a} --{e}--> {b}" for a, e, b in trans)
    if tier == 1:
        return Instance(prompt="Сколько тестов нужно для покрытия всех допустимых переходов (0-switch), если каждый "
                               "тест проверяет ровно один переход?", kind="number", answer=len(trans), code=table,
                        lang="text")
    if tier == 2:
        pairs = sum(1 for _, _, b in trans for c, _, _ in trans if c == b)
        return Instance(prompt="Сколько последовательностей из двух подряд идущих переходов (1-switch покрытие) "
                               "допускает эта диаграмма?", kind="number", answer=pairs, code=table, lang="text",
                        explanation="Для каждого состояния: (число входящих переходов) × (число исходящих).")
    return Instance(prompt=f"Таблица состояний строится для состояний {', '.join(states)} и событий "
                           f"{', '.join(events)}. Сколько в ней ячеек с недопустимыми переходами (негативных "
                           "тестов)?", kind="number", answer=len(states) * len(events) - len(trans), code=table,
                    lang="text", explanation="Ячеек всего состояния × события; допустимые — перечисленные переходы.")


@family("qa_equivalence", "Классы эквивалентности и граничные значения", "test_design", "посчитай",
        {1: Tier(-0.9, 1.3, 120), 2: Tier(0.2, 1.5, 150)})
def qa_equivalence(rng: random.Random, tier: int) -> Instance:
    bands = rng.randint(2, 5)
    cuts = [5 + sum(rng.randint(5, 40) for _ in range(i + 1)) for i in range(bands - 1)]  # boundaries >= 5 apart
    unit, scale = rng.choice([("руб.", 100), ("кг", 1), ("дней", 1), ("шт.", 1)])
    edges = [1] + [c * scale for c in cuts] + [cuts[-1] * scale * 3 if cuts else 1000]
    rules = [f"от {edges[i]} до {edges[i + 1] - 1} {unit} — тариф {i + 1}" for i in range(bands - 1)]
    rules.append(f"от {edges[-2]} до {edges[-1]} {unit} — тариф {bands}")
    text = (f"Поле принимает целые значения от {edges[0]} до {edges[-1]} {unit}; значения вне диапазона — ошибка. "
            f"Тариф: {'; '.join(rules)}.")
    if tier == 1:
        return Instance(prompt=f"{text}\n\nСколько всего классов эквивалентности, включая невалидные (меньше "
                               "минимума и больше максимума)?", kind="number", answer=bands + 2)
    per = rng.choice([2, 3])
    return Instance(prompt=f"{text}\n\nСколько различных тестовых значений даст анализ граничных значений, если на "
                           f"каждую границу берут {per} значения ({'граница и соседнее за ней' if per == 2 else 'до, на и после границы'})? "
                           "Границы — минимум, максимум и стыки тарифов.", kind="number", answer=per * (bands + 1),
                    explanation="Границ на одну больше, чем тарифов; значения разных границ не совпадают.")


@family("ml_validation", "Разбиения и подбор гиперпараметров", "ml", "посчитай",
        {1: Tier(-0.6, 1.4, 120), 2: Tier(0.3, 1.5, 150), 3: Tier(1.2, 1.6, 180)})
def ml_validation(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        k = rng.choice([3, 4, 5, 8, 10])
        n = k * rng.randint(20, 400)
        return Instance(prompt=f"Датасет из {n} объектов, KFold с k = {k}. Сколько объектов в обучающей части "
                               "каждого фолда?", kind="number", answer=n - n // k)
    if tier == 2:
        grid = {p: rng.sample(v, rng.randint(2, len(v))) for p, v in rng.sample([
            ("max_depth", [3, 5, 7, 9]), ("n_estimators", [100, 200, 500]), ("learning_rate", [0.01, 0.05, 0.1, 0.3]),
            ("min_samples_leaf", [1, 5, 10]), ("subsample", [0.7, 0.85, 1.0])], rng.randint(2, 3))}
        cv = rng.choice([3, 5, 10])
        refit = rng.random() < 0.6
        fits = math.prod(len(v) for v in grid.values()) * cv + int(refit)
        code = f"GridSearchCV(model, param_grid={grid}, cv={cv}, refit={refit})"
        return Instance(prompt="Сколько раз будет обучена модель при вызове fit?", kind="number", answer=fits,
                        code=code, lang="python", explanation="Каждая комбинация × каждый фолд, плюс refit на всех "
                                                              "данных, если он включён.")
    s = rng.randint(2, 6)
    n = rng.randint(50, 400)
    test = n // (s + 1)
    which = rng.choice(["первом", "последнем"])
    ans = n - s * test if which == "первом" else n - test
    return Instance(prompt=f"TimeSeriesSplit(n_splits={s}) на ряде из {n} точек. Сколько точек в обучающей части "
                           f"на {which} разбиении?", kind="number", answer=ans,
                    explanation="test_size = n // (n_splits + 1); обучающая часть растёт от n − n_splits·test_size "
                                "до n − test_size.")


@family("ml_trees", "Критерии разбиения деревьев", "ml", "посчитай",
        {2: Tier(0.4, 1.5, 180), 3: Tier(1.3, 1.6, 240)})
def ml_trees(rng: random.Random, tier: int) -> Instance:
    def gini(counts: list[int]) -> float:
        n = sum(counts)
        return 1 - sum((c / n) ** 2 for c in counts) if n else 0.0

    if tier == 2:
        counts = [rng.randint(1, 30) for _ in range(rng.choice([2, 3]))]
        return Instance(prompt=f"В узле дерева {len(counts)} класса с числом объектов {', '.join(map(str, counts))}. "
                               "Чему равна неоднородность Джини? До сотых.", kind="number",
                        answer=round(gini(counts), 2), tolerance=0.01, explanation="Gini = 1 − Σ p_k².")
    left = [rng.randint(0, 20), rng.randint(0, 20)]
    right = [rng.randint(0, 20), rng.randint(0, 20)]
    if sum(left) == 0:
        left[0] = 1
    if sum(right) == 0:
        right[1] = 1
    parent = [left[0] + right[0], left[1] + right[1]]
    n = sum(parent)
    gain = gini(parent) - sum(left) / n * gini(left) - sum(right) / n * gini(right)
    return Instance(prompt=f"Узел: классы 0/1 = {parent[0]}/{parent[1]}. Разбиение даёт левый узел {left[0]}/{left[1]} "
                           f"и правый {right[0]}/{right[1]}. На сколько уменьшится взвешенная неоднородность Джини? "
                           "До сотых.", kind="number", answer=round(gain, 2), tolerance=0.01,
                    explanation="Прирост = Gini(родитель) − Σ (n_i / n) · Gini(потомок_i).")


_SERVICES = ["web", "api", "worker", "db", "redis", "queue", "nginx", "migrate", "mail"]


@family("docker_compose", "Docker Compose: окружение и зависимости", "docker", "посчитай / определи",
        {1: Tier(-0.4, 1.4, 120), 2: Tier(0.5, 1.5, 150)})
def docker_compose(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        var = rng.choice(["MODE", "LOG_LEVEL", "DB_HOST", "FEATURE_X"])
        values = rng.sample(["dev", "prod", "test", "debug", "stage", "local"], 4)
        layers = [("Dockerfile: ENV", 4), ("env_file: .env", 3), ("environment в compose", 2),
                  ("docker compose run -e", 1)]
        present = [(name, prio, v) for (name, prio), v in zip(layers, values) if rng.random() < 0.7]
        if not present:
            present = [(layers[0][0], layers[0][1], values[0])]
        win = min(present, key=lambda x: x[1])
        lines = [f"{name}: {var}={v}" for name, _, v in present]
        return Instance(prompt=f"Переменная {var} задана в нескольких местах (ниже). Какое значение увидит процесс "
                               "в контейнере?", kind="text", answer=win[2], code="\n".join(lines), lang="text",
                        explanation="Приоритет: run -e > environment > env_file > ENV образа.")
    services = rng.sample(_SERVICES, rng.randint(5, 7))
    deps = {s: sorted(rng.sample(services[i + 1:], min(len(services) - i - 1, rng.randint(0, 2))))
            for i, s in enumerate(services)}
    target = services[rng.randint(0, 2)]
    need, stack = set(), [target]
    while stack:
        s = stack.pop()
        if s not in need:
            need.add(s)
            stack.extend(deps[s])
    lines = [f"{s}:\n  depends_on: [{', '.join(deps[s])}]" for s in services]
    return Instance(prompt=f"Сколько сервисов запустит `docker compose up {target}`?", kind="number",
                    answer=len(need), code="services:\n" + "\n".join("  " + ln.replace("\n", "\n  ") for ln in lines),
                    lang="yaml", explanation="Compose поднимает указанный сервис и всё его транзитивное depends_on.")
