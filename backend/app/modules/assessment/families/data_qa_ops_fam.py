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
        r, b = rng.randint(3, 7), rng.randint(3, 7)
        p = r / (r + b) * (r - 1) / (r + b - 1)
        return Instance(prompt=f"В урне {r} красных и {b} синих шаров. Без возвращения вынимают 2 шара. "
                               "Какова вероятность, что оба красные? Ответ в процентах, округлите до целого.",
                        kind="number", answer=round(p * 100), tolerance=1)
    prev = rng.choice([0.5, 1, 2, 5])
    sens = rng.choice([90, 95, 99])
    fpr = rng.choice([2, 5, 10])
    p = (sens / 100 * prev / 100) / (sens / 100 * prev / 100 + fpr / 100 * (1 - prev / 100))
    return Instance(prompt=f"Мошеннических транзакций {prev}%. Антифрод-модель ловит {sens}% мошеннических и "
                           f"ошибочно помечает {fpr}% честных. Транзакция помечена. Какова вероятность, что она "
                           "действительно мошенническая? В процентах, до целого.",
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
    counts = sorted([rng.randint(2, 5) for _ in range(rng.randint(3, 5))], reverse=True)
    params = ", ".join(f"{name}: {c}" for name, c in zip(["браузер", "ОС", "язык", "тариф", "роль"], counts))
    return Instance(prompt=f"Параметры и число их значений: {params}. Какое минимальное число тестов теоретически "
                           "требуется для попарного (pairwise) покрытия? (нижняя оценка)", kind="number",
                    answer=counts[0] * counts[1],
                    explanation="Каждую пару значений двух самых «широких» параметров нужно покрыть хотя бы раз.")


SEVERITY = [
    ("При оплате картой списываются деньги, но заказ не создаётся (воспроизводится у {n}% пользователей).",
     "Blocker/Critical: высокий приоритет"),
    ("В футере опечатка в названии компании.", "Trivial: низкий приоритет"),
    ("Логотип клиента на главной странице отображается неправильно перед завтрашним запуском.",
     "Minor по серьёзности, но высокий приоритет"),
    ("Отчёт за год строится {n} минут вместо 10 секунд, обходной путь — выгрузка по месяцам.",
     "Major: средний приоритет"),
]


@family("qa_severity", "Серьёзность и приоритет дефектов", "test_design", "выбери вариант",
        {1: Tier(-0.8, 1.2, 90), 2: Tier(0.3, 1.3, 90)})
def qa_severity(rng: random.Random, tier: int) -> Instance:
    text, correct = rng.choice(SEVERITY[:2] if tier == 1 else SEVERITY[2:])
    return choice_instance(rng, text.format(n=rng.randint(3, 40)) + "\n\nКак классифицировать дефект?", correct,
                           [s[1] for s in SEVERITY])


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
        files = rng.randint(2, 3)
        per = [rng.randint(2, 4) for _ in range(files)]
        scope = rng.choice(["function", "module", "session"])
        ans = {"function": sum(per), "module": files, "session": 1}[scope]
        code = (f"# conftest.py\n@pytest.fixture(scope='{scope}')\ndef db():\n    print('setup')\n    yield Db()\n\n"
                + "\n".join(f"# test_{i + 1}.py: {p} тест(а), каждый использует db" for i, p in enumerate(per)))
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
        octal = "".join(str(rng.choice([7, 6, 5, 4, 0])) for _ in range(3))
        return Instance(prompt=f"Как будут выглядеть права после `chmod {octal} app.sh` в выводе `ls -l` "
                               "(9 символов, например rwxr-x---)?", kind="text", answer=_sym(octal))
    if tier == 2:
        umask = rng.choice(["022", "027", "077", "002", "026", "007", "037", "033", "006", "023", "072", "017"])
        obj, base = rng.choice([("файл", 0o666), ("каталог", 0o777)])
        val = base & ~int(umask, 8)
        return Instance(prompt=f"umask = {umask}. С какими правами (в восьмеричном виде, 3 цифры) будет создан новый "
                               f"{obj}?", kind="text", answer=f"{val:03o}")
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
    steps[2:2] = rng.sample(["ENV TZ=Europe/Moscow", "RUN useradd -m app", "ARG BUILD_ID", "RUN mkdir -p /data"],
                            rng.randint(0, 2))
    src = steps.index("COPY . .")
    steps[src + 1:src + 1] = rng.sample(["RUN chown -R app /app", "EXPOSE 8000", "RUN rm -rf /tmp/*",
                                         "ENV MODE=prod"], rng.randint(0, 2))
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
        minute = rng.choice(["0", "30", "*/15", "*/20", "0,30"])
        hour = rng.choice(["*", "3", "9-17", "*/6"])
        expr = f"{minute} {hour} * * *"
        return Instance(prompt=f"Сколько раз в сутки запустится задача по расписанию `{expr}`?", kind="number",
                        answer=_cron_count(minute, hour, "*") // 7, code=expr, lang="text")
    minute = rng.choice(["*/10", "*/15", "0,30", "5"])
    hour = rng.choice(["9-18", "8-20/2", "*/4", "10,14,18"])
    dow = rng.choice(["1-5", "1,3,5", "6,0", "*"])
    expr = f"{minute} {hour} * * {dow}"
    return Instance(prompt=f"Сколько раз в неделю запустится CI-задача по расписанию `{expr}`?", kind="number",
                    answer=_cron_count(minute, hour, dow), code=expr, lang="text")
