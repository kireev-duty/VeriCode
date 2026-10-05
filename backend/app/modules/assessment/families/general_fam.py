"""Cross-specialization families: algorithms, SQL, HTTP/networking, system design, git."""

import ipaddress
import math
import random
import sqlite3
from collections import deque

from app.modules.assessment.families.base import FUNCS, IDENTS, NAMES, Instance, Tier, choice_instance, family

COMPLEXITIES = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)", "O(n³)", "O(2ⁿ)", "O(n + m)", "O(n·m)"]


@family("algo_complexity", "Асимптотическая сложность", "algorithms", "оцени сложность",
        {1: Tier(-1.2, 1.3, 90), 2: Tier(-0.1, 1.5, 120), 3: Tier(1.0, 1.6, 150)})
def algo_complexity(rng: random.Random, tier: int) -> Instance:
    f = rng.choice(FUNCS)
    v = rng.choice(IDENTS)
    k = rng.randint(2, 5)
    variants = {
        1: [
            (f"def {f}({v}):\n    total = 0\n    for x in {v}:\n        total += x * {k}\n    return total", "O(n)"),
            (f"def {f}({v}):\n    res = 0\n    for a in {v}:\n        for b in {v}:\n            res += a * b\n"
             f"    return res", "O(n²)"),
            (f"def {f}(n):\n    i = 1\n    while i < n:\n        i *= {k}\n    return i", "O(log n)"),
            (f"def {f}({v}):\n    return {v}[len({v}) // {k}]", "O(1)"),
        ],
        2: [
            (f"def {f}({v}):\n    n = len({v})\n    cnt = 0\n    for i in range(n):\n        for j in range(i, n):\n"
             f"            cnt += {v}[i] < {v}[j]\n    return cnt", "O(n²)"),
            (f"def {f}(n):\n    s = 0\n    for i in range(n):\n        j = 1\n        while j < n:\n"
             f"            j *= {k}\n            s += 1\n    return s", "O(n log n)"),
            (f"def {f}(a, b):\n    for x in a:\n        print(x)\n    for y in b:\n        print(y)", "O(n + m)"),
            (f"def {f}(a, b):\n    seen = set(b)\n    return [x for x in a if x in seen]", "O(n + m)"),
        ],
        3: [
            (f"def {f}(n):\n    if n <= 1:\n        return 1\n    return {f}(n - 1) + {f}(n - 2)", "O(2ⁿ)"),
            (f"def {f}({v}):\n    if len({v}) <= 1:\n        return {v}\n    mid = len({v}) // 2\n"
             f"    left, right = {f}({v}[:mid]), {f}({v}[mid:])\n    return sorted(left + right)", "O(n log n)"),
            (f"def {f}(n):\n    total = 0\n    for i in range(n):\n        j = i\n        while j > 0:\n"
             f"            j //= {k}\n            total += 1\n    return total", "O(n log n)"),
            (f"def {f}({v}, queries):\n    {v} = sorted({v})\n    return [bisect.bisect_left({v}, q) for q in queries]"
             f"\n# len(queries) == len({v})", "O(n log n)"),
        ],
    }
    code, correct = rng.choice(variants[tier])
    return choice_instance(rng, "Какова временная сложность функции (n — размер входа, m — размер второго входа)?",
                           correct, COMPLEXITIES, code=code, lang="python", n=5)


@family("algo_trace", "Трассировка алгоритма", "algorithms", "просчитай результат",
        {1: Tier(-0.9, 1.4, 120), 2: Tier(0.2, 1.6, 150), 3: Tier(1.2, 1.7, 210)})
def algo_trace(rng: random.Random, tier: int) -> Instance:
    if tier == 1:
        ops, stack, lines = [], [], []
        for _ in range(rng.randint(7, 9)):
            if stack and rng.random() < 0.4:
                stack.pop()
                lines.append("s.pop()")
            else:
                x = rng.randint(1, 50)
                stack.append(x)
                lines.append(f"s.append({x})")
        ops = "\n".join(lines)
        return Instance(prompt="Чему равна сумма элементов стека s после выполнения операций?", kind="number",
                        answer=sum(stack), code="s = []\n" + ops, lang="python")
    if tier == 2:
        arr = sorted(rng.sample(range(1, 200), rng.randint(12, 20)))
        target = rng.choice(arr)
        lo, hi, steps = 0, len(arr) - 1, 0
        while lo <= hi:
            steps += 1
            mid = (lo + hi) // 2
            if arr[mid] == target:
                break
            if arr[mid] < target:
                lo = mid + 1
            else:
                hi = mid - 1
        code = (f"arr = {arr}\nlo, hi, steps = 0, len(arr) - 1, 0\nwhile lo <= hi:\n    steps += 1\n"
                f"    mid = (lo + hi) // 2\n    if arr[mid] == {target}:\n        break\n"
                f"    if arr[mid] < {target}:\n        lo = mid + 1\n    else:\n        hi = mid - 1\nprint(steps)")
        return Instance(prompt="Что выведет программа?", kind="number", answer=steps, code=code, lang="python")
    n = rng.randint(7, 9)
    nodes = rng.sample(NAMES, n)
    edges = set()
    for i in range(1, n):  # random spanning tree keeps the graph connected
        edges.add(tuple(sorted((nodes[i], nodes[rng.randint(0, i - 1)]))))
    for _ in range(rng.randint(1, 3)):
        u, w = rng.sample(nodes, 2)
        edges.add(tuple(sorted((u, w))))
    edges = sorted(edges)
    adj = {x: [] for x in nodes}
    for u, w in edges:
        adj[u].append(w)
        adj[w].append(u)
    src, dst = rng.sample(nodes, 2)
    dist = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        for w in adj[u]:
            if w not in dist:
                dist[w] = dist[u] + 1
                q.append(w)
    edge_txt = ", ".join(f"{u}–{w}" for u, w in edges)
    return Instance(prompt=f"Неориентированный граф задан рёбрами: {edge_txt}.\n\n"
                           f"Какова длина кратчайшего пути (в рёбрах) от **{src}** до **{dst}**?",
                    kind="number", answer=dist[dst])


# ------------------------------------------------------------------------------------------------ SQL

DEPTS = ["dev", "qa", "ops", "sales", "hr"]


def _sql_fixture(rng: random.Random) -> tuple[str, list[tuple]]:
    rows = []
    depts = rng.sample(DEPTS, 3)
    for i, name in enumerate(rng.sample(NAMES, rng.randint(7, 9)), start=1):
        rows.append((i, name, rng.choice(depts), rng.choice(range(60, 260, 10)) * 1000,
                     rng.choice([None, None, rng.randint(1, 3)])))
    lines = [f"({r[0]}, '{r[1]}', '{r[2]}', {r[3]}, {'NULL' if r[4] is None else r[4]})" for r in rows]
    ddl = ("CREATE TABLE emp (id INT, name TEXT, dept TEXT, salary INT, manager_id INT);\n"
           "INSERT INTO emp VALUES\n  " + ",\n  ".join(lines) + ";")
    return ddl, rows


def _sql_eval(ddl: str, query: str):
    con = sqlite3.connect(":memory:")
    con.executescript(ddl)
    res = con.execute(query).fetchall()
    con.close()
    return res


@family("sql_query", "Результат SQL-запроса", "sql", "выполни запрос в уме",
        {1: Tier(-1.0, 1.4, 150), 2: Tier(0.2, 1.6, 180), 3: Tier(1.2, 1.8, 210)})
def sql_query(rng: random.Random, tier: int) -> Instance:
    ddl, rows = _sql_fixture(rng)
    dept = rng.choice([r[2] for r in rows])
    sal = rng.choice(range(100, 200, 20)) * 1000
    if tier == 1:
        query = f"SELECT COUNT(*) FROM emp WHERE dept = '{dept}' AND salary >= {sal};"
        q_text = "Какое число вернёт запрос?"
    elif tier == 2:
        k = rng.randint(2, 3)
        query = (f"SELECT dept, AVG(salary) FROM emp\nWHERE salary > {sal - 60000}\nGROUP BY dept\n"
                 f"HAVING COUNT(*) >= {k};")
        q_text = "Сколько строк вернёт запрос?"
    else:
        m = rng.randint(1, 3)
        query = rng.choice([
            f"SELECT COUNT(*) FROM emp WHERE manager_id <> {m};",
            f"SELECT COUNT(manager_id) + COUNT(DISTINCT dept) FROM emp WHERE salary < {sal + 40000};",
            f"SELECT COUNT(*) FROM emp WHERE manager_id NOT IN (SELECT id FROM emp WHERE dept = '{dept}');",
        ])
        q_text = "Какое число вернёт запрос? (обратите внимание на NULL)"
    res = _sql_eval(ddl, query)
    answer = len(res) if tier == 2 else res[0][0]
    return Instance(prompt=q_text, kind="number", answer=answer, code=f"{ddl}\n\n{query}", lang="sql",
                    explanation="Ответ вычислен выполнением запроса в SQLite.")


@family("sql_join", "Соединения таблиц", "sql", "выполни запрос в уме",
        {2: Tier(0.4, 1.6, 180), 3: Tier(1.3, 1.7, 210)})
def sql_join(rng: random.Random, tier: int) -> Instance:
    users = rng.sample(NAMES, rng.randint(4, 6))
    orders = [(i, rng.randint(1, len(users) + 1), rng.randint(1, 9) * 100) for i in range(1, rng.randint(5, 8))]
    ddl = ("CREATE TABLE users (id INT, name TEXT);\nINSERT INTO users VALUES "
           + ", ".join(f"({i}, '{n}')" for i, n in enumerate(users, start=1)) + ";\n"
           + "CREATE TABLE orders (id INT, user_id INT, amount INT);\nINSERT INTO orders VALUES "
           + ", ".join(f"({o[0]}, {o[1]}, {o[2]})" for o in orders) + ";")
    if tier == 2:
        join = rng.choice(["JOIN", "LEFT JOIN"])
        query = f"SELECT u.name, o.amount\nFROM users u {join} orders o ON o.user_id = u.id;"
        answer = len(_sql_eval(ddl, query))
        q_text = "Сколько строк вернёт запрос?"
    else:
        query = ("SELECT COUNT(*) FROM (\n  SELECT u.id, COUNT(o.id) AS n\n  FROM users u LEFT JOIN orders o "
                 "ON o.user_id = u.id\n  GROUP BY u.id\n) t WHERE n = 0;")
        answer = _sql_eval(ddl, query)[0][0]
        q_text = "Какое число вернёт запрос?"
    return Instance(prompt=q_text, kind="number", answer=answer, code=f"{ddl}\n\n{query}", lang="sql")


# ------------------------------------------------------------------------------------------------ HTTP

_RES = ["заказ", "пользователь", "платёж", "статья", "тикет", "проект"]
HTTP_SCENARIOS = [
    (1, "Клиент запросил {r} с id={n}, такого объекта нет.", "404 Not Found"),
    (1, "Клиент успешно создал новый {r} через POST.", "201 Created"),
    (1, "Запрос к защищённому эндпоинту пришёл без токена авторизации.", "401 Unauthorized"),
    (1, "Пользователь авторизован, но пытается удалить чужой {r}.", "403 Forbidden"),
    (2, "Тело POST-запроса — валидный JSON, но поле amount отрицательное и не проходит бизнес-валидацию.",
     "422 Unprocessable Content"),
    (2, "Клиент превысил лимит в {n} запросов в минуту.", "429 Too Many Requests"),
    (2, "Попытка создать {r} с уже занятым уникальным кодом.", "409 Conflict"),
    (2, "Запрос с If-None-Match, ETag ресурса не изменился.", "304 Not Modified"),
    (2, "Успешный DELETE, тело ответа не возвращается.", "204 No Content"),
    (3, "Шлюз (nginx) не дождался ответа от upstream-сервиса за {n} секунд.", "504 Gateway Timeout"),
    (3, "Шлюз получил от upstream некорректный ответ (соединение сброшено).", "502 Bad Gateway"),
    (3, "PUT с If-Match, но ETag на сервере уже другой (кто-то изменил {r}).", "412 Precondition Failed"),
]
HTTP_CODES = sorted({s[2] for s in HTTP_SCENARIOS} | {"400 Bad Request", "500 Internal Server Error",
                                                      "200 OK", "405 Method Not Allowed"})


@family("http_status", "Коды ответа HTTP", "http", "выбери вариант",
        {1: Tier(-1.3, 1.2, 60), 2: Tier(-0.2, 1.4, 75), 3: Tier(0.8, 1.5, 90)})
def http_status(rng: random.Random, tier: int) -> Instance:
    pool = [s for s in HTTP_SCENARIOS if s[0] == tier]
    _, text, code = rng.choice(pool)
    text = text.format(r=rng.choice(_RES), n=rng.randint(10, 999))
    near = [c for c in HTTP_CODES if c[0] == code[0] and c != code]
    other = [c for c in HTTP_CODES if c[0] != code[0]]
    return choice_instance(rng, f"{text}\n\nКакой код ответа наиболее корректен?", code,
                           rng.sample(near, min(2, len(near))) + rng.sample(other, 2))


@family("net_cidr", "Адресация и подсети", "http", "посчитай",
        {2: Tier(0.3, 1.5, 120), 3: Tier(1.2, 1.6, 150)})
def net_cidr(rng: random.Random, tier: int) -> Instance:
    prefix = rng.randint(22, 29)
    net = ipaddress.ip_network(f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.0/{prefix}", strict=False)
    if tier == 2:
        return Instance(prompt=f"Сколько адресов можно назначить хостам в сети **{net}** "
                               f"(без адреса сети и широковещательного)?", kind="number",
                        answer=net.num_addresses - 2)
    host = rng.choice(list(net.hosts()))
    return Instance(prompt=f"Хосту назначен адрес **{host}/{prefix}**. Какой широковещательный адрес у его сети?",
                    kind="text", answer=str(net.broadcast_address))


# ------------------------------------------------------------------------------------------------ system design


@family("sd_capacity", "Оценка мощностей", "system_design", "посчитай",
        {2: Tier(0.5, 1.4, 180), 3: Tier(1.4, 1.6, 240)})
def sd_capacity(rng: random.Random, tier: int) -> Instance:
    rps = rng.choice(range(2000, 20001, 500))
    per = rng.choice(range(300, 1501, 100))
    util = rng.choice([0.6, 0.7, 0.75, 0.8])
    servers = math.ceil(rps / (per * util))
    if tier == 2:
        return Instance(prompt=f"Пиковая нагрузка — {rps} RPS. Один инстанс выдерживает {per} RPS, но держать его "
                               f"нагрузку выше {int(util * 100)}% нельзя. Сколько инстансов нужно минимум "
                               f"(без резерва)?", kind="number", answer=servers)
    size_kb = rng.choice([2, 4, 8, 16])
    daily = rng.choice(range(1, 21)) * 1_000_000
    years = rng.choice([1, 2, 3])
    repl = rng.choice([2, 3])
    tb = daily * size_kb * 365 * years * repl / 1024**3
    return Instance(prompt=f"Сервис сохраняет {daily:,} событий в сутки, каждое ≈ {size_kb} КБ. Данные хранятся "
                           f"{years} г. с репликацией ×{repl}. Сколько ТБ потребуется? Округлите до целого "
                           f"(1 ТБ = 1024³ КБ).".replace(",", " "), kind="number", answer=round(tb), tolerance=1)


SD_SCENARIOS = [
    (2, "Каталог товаров читают в 200 раз чаще, чем изменяют; допустима задержка обновления до минуты.",
     "Кэш (например, Redis) с TTL перед БД", ["Шардирование БД по id товара", "Синхронная репликация в 3 ДЦ",
                                              "Перенос каталога в очередь сообщений"]),
    (2, "Сервис заказов должен отправить письмо и начислить бонусы, но не ждать их ответа и не терять события.",
     "Публиковать событие в брокер (Kafka/RabbitMQ) с подтверждением", [
         "Синхронно вызвать оба сервиса по HTTP", "Записать в лог-файл и обработать cron-ом раз в сутки",
         "Держать события в памяти процесса до отправки"]),
    (3, "Нужно атомарно записать заказ в БД и опубликовать событие в брокер, без двухфазного коммита.",
     "Transactional outbox: событие пишется в ту же транзакцию, отдельный процесс публикует",
     ["Сначала опубликовать событие, затем записать в БД", "Обернуть оба действия в try/except",
      "Увеличить таймауты брокера"]),
    (3, "Повторная доставка сообщения о списании денег не должна приводить к двойному списанию.",
     "Идемпотентный обработчик с ключом идемпотентности", [
         "Exactly-once в настройках HTTP-клиента", "Увеличить число партиций", "Отключить ретраи у брокера"]),
    (3, "Таблица событий растёт на 500 млн строк в месяц, запросы почти всегда за последние 7 дней.",
     "Партиционирование по времени и удаление старых партиций", [
         "Добавить индекс на каждый столбец", "Вертикально масштабировать сервер БД", "Перейти на SQLite"]),
]


@family("sd_choice", "Архитектурные решения", "system_design", "выбери решение",
        {2: Tier(0.2, 1.3, 120), 3: Tier(1.1, 1.5, 150)})
def sd_choice(rng: random.Random, tier: int) -> Instance:
    _, text, correct, wrong = rng.choice([s for s in SD_SCENARIOS if s[0] == tier])
    return choice_instance(rng, f"{text}\n\nКакое решение подходит лучше всего?", correct, wrong)


# ------------------------------------------------------------------------------------------------ git


@family("git_history", "История коммитов git", "git", "просчитай результат",
        {1: Tier(-0.8, 1.3, 120), 2: Tier(0.4, 1.5, 150)})
def git_history(rng: random.Random, tier: int) -> Instance:
    base = rng.randint(2, 5)
    feat = rng.randint(1, 4)
    main_after = rng.choice([0, rng.randint(1, 3)]) if tier == 2 else 0
    branch = rng.choice(["feature", "fix-login", "api-v2", "hotfix"])
    cmds = [f"# в ветке main {base} коммитов", f"git switch -c {branch}"]
    cmds += [f"git commit -am 'step {i + 1}'" for i in range(feat)]
    cmds.append("git switch main")
    cmds += [f"git commit -am 'main {i + 1}'" for i in range(main_after)]
    cmds.append(f"git merge {branch}")
    total = base + feat + main_after + (1 if main_after else 0)
    if tier == 2 and rng.random() < 0.5:
        k = rng.randint(1, 2)
        cmds.append(f"git reset --soft HEAD~{k}")
        total -= k
        note = " (reset --soft отбрасывает коммиты из истории, но оставляет изменения в индексе)"
    else:
        note = ""
    return Instance(prompt="Сколько коммитов покажет `git log --oneline` в ветке main после команд?", kind="number",
                    answer=total, code="\n".join(cmds), lang="bash",
                    explanation="Если main не ушла вперёд, merge — fast-forward без merge-коммита." + note)
