"""Frontend families: JavaScript, TypeScript, HTML/CSS, React, browser. JS semantics are reproduced by exact
Python models (event-loop simulator, coercion rules, specificity calculator), so answers stay computed."""

import random
from collections import deque

from app.modules.assessment.families.base import IDENTS, Instance, Tier, choice_instance, family

# ------------------------------------------------------------------------------------------------ event loop
# Action = ("log", label) | ("micro", [actions]) | ("timer", delay, [actions])


def _simulate(main: list) -> list[str]:
    out: list[str] = []
    micro: deque = deque()
    timers: list = []
    seq = 0

    def run(actions):
        nonlocal seq
        for act in actions:
            if act[0] == "log":
                out.append(act[1])
            elif act[0] == "micro":
                micro.append(act[1])
            elif act[0] == "timer":
                timers.append((act[1], seq, act[2]))
                seq += 1

    def drain():
        while micro:
            run(micro.popleft())

    run(main)
    drain()
    while timers:
        timers.sort(key=lambda t: (t[0], t[1]))
        _, _, actions = timers.pop(0)
        run(actions)
        drain()
    return out


def _render(actions: list, indent: str = "") -> list[str]:
    lines = []
    for act in actions:
        if act[0] == "log":
            lines.append(f"{indent}console.log('{act[1]}');")
        elif act[0] == "micro":
            inner = act[1]
            if len(inner) == 1 and inner[0][0] == "log":
                lines.append(f"{indent}Promise.resolve().then(() => console.log('{inner[0][1]}'));")
            elif len(inner) == 2 and inner[0][0] == "log" and inner[1][0] == "micro":
                lines.append(f"{indent}Promise.resolve()\n{indent}  .then(() => console.log('{inner[0][1]}'))\n"
                             f"{indent}  .then(() => console.log('{inner[1][1][0][1]}'));")
            else:
                lines.append(f"{indent}queueMicrotask(() => {{")
                lines += _render(inner, indent + "  ")
                lines.append(f"{indent}}});")
        elif act[0] == "timer":
            delay, inner = act[1], act[2]
            if len(inner) == 1 and inner[0][0] == "log":
                lines.append(f"{indent}setTimeout(() => console.log('{inner[0][1]}'), {delay});")
            else:
                lines.append(f"{indent}setTimeout(() => {{")
                lines += _render(inner, indent + "  ")
                lines.append(f"{indent}}}, {delay});")
    return lines


@family("js_event_loop", "Event loop: микро- и макрозадачи", "javascript", "предскажи порядок вывода",
        {1: Tier(-0.6, 1.5, 120), 2: Tier(0.4, 1.7, 150), 3: Tier(1.3, 1.8, 210)})
def js_event_loop(rng: random.Random, tier: int) -> Instance:
    labels = iter("123456789ABCDEF")
    n = {1: rng.randint(4, 5), 2: 5, 3: 6}[tier]
    main: list = []
    while len(main) < n:
        r = rng.random()
        if r < 0.3:
            main.append(("log", next(labels)))
        elif r < 0.6:
            if tier >= 2 and rng.random() < 0.5:
                a, b = next(labels), next(labels)
                main.append(("micro", [("log", a), ("micro", [("log", b)])]))
            else:
                main.append(("micro", [("log", next(labels))]))
        else:
            delay = rng.choice([0, 0, 10]) if tier >= 2 else 0
            if tier == 3 and rng.random() < 0.6:
                a, b = next(labels), next(labels)
                main.append(("timer", delay, [("log", a), ("micro", [("log", b)])]))
            else:
                main.append(("timer", delay, [("log", next(labels))]))
    code = "\n".join(_render(main))
    return Instance(prompt="В каком порядке будут выведены значения? Запишите через пробел.", kind="text",
                    answer=" ".join(_simulate(main)), code=code, lang="javascript",
                    explanation="Синхронный код → все микрозадачи → по одной макрозадаче, после каждой снова "
                                "очередь микрозадач.")


def _js_coercion_cases(rng: random.Random) -> list[tuple[str, str, list[str]]]:
    a, b = rng.randint(2, 9), rng.randint(2, 9)
    c = rng.choice(["px", "1", "a"])
    return [
        (f"'{a}' + {b}", f"{a}{b}", [str(a + b), "NaN", "TypeError"]),
        (f"'{a}' - {b}", str(a - b), [f"{a}-{b}", "NaN", f"{a}{b}"]),
        (f"'{a}' * '{b}'", str(a * b), [f"{a}{b}", "NaN", f"'{a}{b}'"]),
        (f"{a} + {b} + '{c}'", f"{a + b}{c}", [f"{a}{b}{c}", "NaN", f"{a + b}"]),
        (f"'{c}' + {a} + {b}", f"{c}{a}{b}", [f"{c}{a + b}", "NaN", f"{a + b}{c}"]),
        (f"true + {a}", str(a + 1), [f"true{a}", "NaN", str(a)]),
        (f"[{a}] + [{b}]", f"{a}{b}", [str(a + b), f"[{a}, {b}]", "NaN"]),
        (f"null + {a}", str(a), ["NaN", f"null{a}", "TypeError"]),
        (f"undefined + {a}", "NaN", [str(a), f"undefined{a}", "TypeError"]),
        (f"{a} / 0", "Infinity", ["NaN", "0", "ZeroDivisionError"]),
        ("typeof null", "object", ["null", "undefined", "NaN"]),
        (f"'{b}' == {b} && '{b}' === {b}", "false", ["true", "TypeError", "NaN"]),
    ]


@family("js_coercion", "Приведение типов в JS", "javascript", "выбери вывод",
        {1: Tier(-0.9, 1.3, 75), 2: Tier(0.1, 1.4, 90)})
def js_coercion(rng: random.Random, tier: int) -> Instance:
    cases = _js_coercion_cases(rng)
    expr, correct, wrong = rng.choice(cases[:6] if tier == 1 else cases[6:])
    return choice_instance(rng, "Что выведет `console.log`?", correct, wrong, code=f"console.log({expr});",
                           lang="javascript")


def _js_parse_int(s: str, radix: int) -> str:
    if radix == 0:
        radix = 10
    if radix == 1 or radix > 36:
        return "NaN"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"[:radix]
    val, ok = 0, False
    for ch in s.lower():
        if ch not in digits:
            break
        val, ok = val * radix + digits.index(ch), True
    return str(val) if ok else "NaN"


@family("js_arrays", "Методы массивов", "javascript", "предскажи вывод",
        {1: Tier(-1.1, 1.4, 120), 2: Tier(0.3, 1.6, 120), 3: Tier(1.2, 1.7, 150)})
def js_arrays(rng: random.Random, tier: int) -> Instance:
    name = rng.choice(IDENTS)
    if tier == 1:
        arr = rng.sample(range(1, 30), rng.randint(5, 7))
        m, r, k, s = rng.randint(2, 3), 0, rng.randint(2, 4), rng.randint(0, 10)
        r = rng.randint(0, m - 1)
        code = (f"const {name} = {arr};\nconsole.log(\n  {name}.filter(x => x % {m} === {r})\n"
                f"    .map(x => x * {k})\n    .reduce((a, b) => a + b, {s})\n);")
        ans = str(sum(x * k for x in arr if x % m == r) + s)
    elif tier == 2:
        arr = rng.sample([1, 2, 5, 9, 10, 15, 21, 100, 25, 3, 30, 200], rng.randint(4, 6))
        code = f"const {name} = {arr};\n{name}.sort();\nconsole.log({name}.join(' '));"
        ans = " ".join(sorted(map(str, arr)))
    else:
        strs = [str(rng.randint(1, 20)) for _ in range(rng.randint(3, 5))]
        code = f"console.log({strs}.map(parseInt).join(' '));".replace('"', "'")
        ans = " ".join(_js_parse_int(s, i) for i, s in enumerate(strs))
    return Instance(prompt="Что выведет программа?", kind="text", answer=ans, code=code, lang="javascript",
                    explanation="sort() без компаратора сравнивает строки; map передаёт индекс вторым аргументом.")


@family("js_closures", "Замыкания и области видимости", "javascript", "предскажи вывод",
        {2: Tier(0.2, 1.6, 120), 3: Tier(1.1, 1.6, 120)})
def js_closures(rng: random.Random, tier: int) -> Instance:
    if tier == 2:
        n, k, b = rng.randint(2, 5), rng.randint(1, 4), rng.randint(0, 3)
        kw = rng.choice(["var", "let"])
        code = f"for ({kw} i = {b}; i < {b + n}; i++) {{\n  setTimeout(() => console.log(i * {k}), 0);\n}}"
        vals = [(b + n) * k] * n if kw == "var" else [i * k for i in range(b, b + n)]
        return Instance(prompt="Что будет выведено? Запишите значения через пробел.", kind="text",
                        answer=" ".join(map(str, vals)), code=code, lang="javascript")
    v = rng.choice(["count", "total", "user"])
    x = rng.randint(1, 99)
    kw = rng.choice(["var", "let", "const"])
    code = f"function f() {{\n  console.log({v});\n  {kw} {v} = {x};\n}}\nf();"
    correct = "undefined" if kw == "var" else "ReferenceError"
    return choice_instance(rng, "Что произойдёт при вызове f()?", correct,
                           ["undefined", "ReferenceError", str(x), "null"], code=code, lang="javascript")


# ------------------------------------------------------------------------------------------------ TypeScript

FIELDS = ["id", "name", "email", "age", "role", "phone", "city", "avatar", "createdAt", "status"]


@family("ts_utility", "Утилитарные типы TypeScript", "typescript", "посчитай",
        {1: Tier(-0.3, 1.4, 120), 2: Tier(0.9, 1.6, 180)})
def ts_utility(rng: random.Random, tier: int) -> Instance:
    user = rng.sample(FIELDS, rng.randint(5, 7))
    decl = "type User = {\n" + "".join(f"  {f}: string;\n" for f in user) + "};"
    if tier == 1:
        k = rng.sample(user, rng.randint(1, 3))
        op = rng.choice(["Omit", "Pick"])
        keys = " | ".join(f"'{x}'" for x in k)
        code = f"{decl}\ntype T = {op}<User, {keys}>;"
        n = len(user) - len(k) if op == "Omit" else len(k)
    else:
        admin = rng.sample(FIELDS, rng.randint(4, 6))
        code = (decl + "\ntype Admin = {\n" + "".join(f"  {f}: string;\n" for f in admin) + "};\n"
                "type T = Exclude<keyof User, keyof Admin> | Extract<keyof Admin, 'id' | 'role' | 'status'>;")
        n = len((set(user) - set(admin)) | (set(admin) & {"id", "role", "status"}))
    return Instance(prompt="Сколько членов (ключей) содержит тип T?", kind="number", answer=n, code=code,
                    lang="typescript")


# ------------------------------------------------------------------------------------------------ CSS

COLORS = ["red", "green", "blue", "orange", "purple", "teal", "gold", "navy"]
_ANCESTORS = [  # (selector variants, (ids, classes, types))
    [("nav", (0, 0, 1)), (".menu", (0, 1, 0)), ("#top", (1, 0, 0)), ("nav.menu", (0, 1, 1))],
    [("ul", (0, 0, 1)), ("ul.list", (0, 1, 1))],
    [("li", (0, 0, 1)), (".item", (0, 1, 0)), ("li.active", (0, 1, 1)), (".item.active", (0, 2, 0)),
     ("li:first-child", (0, 1, 1))],
]
_TARGET = [("a", (0, 0, 1)), (".link", (0, 1, 0)), ("a.link", (0, 1, 1)), ("a[href]", (0, 1, 1)),
           ("#cta", (1, 0, 0)), ("a.link.primary", (0, 2, 1))]
HTML = ('<nav id="top" class="menu">\n  <ul class="list">\n    <li class="item active">\n'
        '      <a id="cta" class="link primary" href="/join">Join</a>\n    </li>\n  </ul>\n</nav>')


@family("css_specificity", "Специфичность CSS", "html_css", "определи результат",
        {1: Tier(-0.7, 1.4, 150), 2: Tier(0.4, 1.6, 180), 3: Tier(1.2, 1.7, 210)})
def css_specificity(rng: random.Random, tier: int) -> Instance:
    n_rules = {1: 3, 2: 4, 3: 4}[tier]
    rules, used = [], set()
    while len(rules) < n_rules:
        spec = [0, 0, 0]
        parts = []
        for level in _ANCESTORS:
            if rng.random() < (0.3 if tier == 1 else 0.6):
                sel, s = rng.choice(level)
                parts.append(sel)
                spec = [x + y for x, y in zip(spec, s)]
        tsel, ts = rng.choice(_TARGET if tier > 1 else _TARGET[:4])
        parts.append(tsel)
        spec = tuple(x + y for x, y in zip(spec, ts))
        selector = " ".join(parts)
        if selector in used:
            continue
        used.add(selector)
        rules.append([selector, spec, False])
    if tier == 3:
        rules[rng.randint(0, len(rules) - 2)][2] = True  # an !important on a weaker rule
    colors = rng.sample(COLORS, len(rules))
    best = max(range(len(rules)), key=lambda i: (rules[i][2], rules[i][1], i))
    css = "\n".join(f"{r[0]} {{ color: {c}{' !important' if r[2] else ''}; }}" for r, c in zip(rules, colors))
    return choice_instance(rng, "Какого цвета будет текст ссылки «Join»?", colors[best], colors,
                           code=f"<!-- HTML -->\n{HTML}\n\n/* CSS */\n{css}", lang="html",
                           explanation="Сравниваются (id, классы/атрибуты/псевдоклассы, теги), затем порядок; "
                                       "!important перекрывает обычные объявления.")


@family("css_box", "Блочная модель CSS", "html_css", "посчитай",
        {1: Tier(-0.9, 1.4, 120), 2: Tier(0.2, 1.5, 150)})
def css_box(rng: random.Random, tier: int) -> Instance:
    w = rng.choice(range(100, 401, 20))
    py, px = rng.choice(range(4, 33, 4)), rng.choice(range(4, 33, 4))
    border = rng.randint(1, 5)
    margin = rng.choice(range(0, 41, 5))
    sizing = rng.choice(["content-box", "border-box"])
    pad = f"{px}px" if tier == 1 else f"{py}px {px}px"
    css = (f".card {{\n  box-sizing: {sizing};\n  width: {w}px;\n  padding: {pad};\n"
           f"  border: {border}px solid #ccc;\n  margin: {margin}px;\n}}")
    total = w if sizing == "border-box" else w + 2 * px + 2 * border
    return Instance(prompt="Какова итоговая ширина элемента .card на странице (по внешнему краю рамки, без margin), "
                           "в пикселях?", kind="number", answer=total, code=css, lang="css")


# ------------------------------------------------------------------------------------------------ React


@family("react_state", "Состояние и эффекты React", "react", "предскажи результат",
        {1: Tier(-0.4, 1.5, 150), 2: Tier(0.6, 1.7, 180), 3: Tier(1.4, 1.6, 180)})
def react_state(rng: random.Random, tier: int) -> Instance:
    start = rng.randint(0, 5)
    if tier in (1, 2):
        n = rng.randint(2, 4)
        updates, value, lines = [], start, []
        for _ in range(n):
            k = rng.randint(1, 3)
            functional = tier == 2 and rng.random() < 0.5
            if functional:
                value += k
                lines.append(f"    setCount(c => c + {k});")
            else:
                value = start + k
                lines.append(f"    setCount(count + {k});")
            updates.append(functional)
        code = (f"function Counter() {{\n  const [count, setCount] = useState({start});\n"
                f"  const onClick = () => {{\n" + "\n".join(lines) + "\n  };\n"
                "  return <button onClick={onClick}>{count}</button>;\n}")
        return Instance(prompt="Что покажет кнопка после одного клика?", kind="number", answer=value, code=code,
                        lang="jsx", explanation="count внутри обработчика — значение из текущего рендера; "
                                                "функциональные обновления применяются к результату предыдущих.")
    renders = rng.randint(2, 9)
    changes = rng.randint(0, renders - 1)
    deps = rng.choice(["[]", "[userId]", "none"])
    runs = {"[]": 1, "[userId]": 1 + changes, "none": 1 + renders}[deps]
    dep_code = "" if deps == "none" else f", {deps}"
    unmount = rng.random() < 0.5
    ask_cleanup = rng.random() < 0.5
    fn = rng.choice(["load", "subscribe", "track", "connect"])
    code = (f"function Profile({{ userId }}) {{\n  useEffect(() => {{\n    {fn}(userId);\n"
            f"    return () => cleanup(userId);\n  }}{dep_code});\n  return <Card id={{userId}} />;\n}}")
    tail = " и затем размонтировали" if unmount else ""
    if ask_cleanup:
        question, answer = "Сколько раз будет вызвана cleanup?", runs - 1 + int(unmount)
    else:
        question, answer = f"Сколько раз будет вызвана {fn}?", runs
    return Instance(prompt=f"Компонент смонтировали, затем он перерисовался ещё {renders} раз(а){tail}; userId при "
                           f"этом менялся {changes} раз(а). {question} (production-сборка, без StrictMode)",
                    kind="number", answer=answer, code=code, lang="jsx",
                    explanation="cleanup вызывается перед каждым повторным запуском эффекта и при размонтировании.")


# ------------------------------------------------------------------------------------------------ browser


@family("dom_events", "Всплытие и перехват событий", "browser", "предскажи порядок",
        {2: Tier(0.3, 1.6, 150), 3: Tier(1.2, 1.7, 180)})
def dom_events(rng: random.Random, tier: int) -> Instance:
    chain = ["outer", "inner", "btn"] if rng.random() < 0.5 else ["page", "outer", "inner", "btn"]
    listeners = []  # (node, capture, label, stops)
    labels = iter("ABCDEFGHIJ")
    for node in chain:
        for _ in range(rng.randint(1, 2)):
            capture = node != "btn" and rng.random() < 0.5
            listeners.append((node, capture, next(labels), False))
    if tier == 3:
        i = rng.randrange(len(listeners))
        node, capture, label, _ = listeners[i]
        listeners[i] = (node, capture, label, True)
    order, stopped_at = [], None
    phases = [(n, True) for n in chain[:-1]] + [("btn", None)] + [(n, False) for n in reversed(chain[:-1])]
    for node, cap in phases:
        if stopped_at is not None and stopped_at != node:
            break
        for ln in listeners:
            if ln[0] == node and (cap is None or ln[1] == cap):
                order.append(ln[2])
                if ln[3]:
                    stopped_at = node
    markup = '<div id="outer">\n  <div id="inner">\n    <button id="btn">OK</button>\n  </div>\n</div>'
    if chain[0] == "page":
        markup = '<main id="page">\n' + "\n".join("  " + ln for ln in markup.splitlines()) + "\n</main>"
    lines = [markup, "<script>"]
    for node, capture, label, stops in listeners:
        body = f"console.log('{label}')" + ("; e.stopPropagation()" if stops else "")
        cap = ", true" if capture else ""
        lines.append(f"{node}.addEventListener('click', e => {{ {body}; }}{cap});")
    lines.append("</script>")
    return Instance(prompt="Пользователь кликнул по кнопке. Что выведется? Буквы через пробел.", kind="text",
                    answer=" ".join(order), code="\n".join(lines), lang="html",
                    explanation="Сначала перехват (capture) сверху вниз, затем цель, затем всплытие; "
                                "stopPropagation не отменяет остальные обработчики на том же элементе.")


# ------------------------------------------------------------------------------------------------ bank extension

# union member -> (typeof result, is array)
_TS_MEMBERS = {"string": "string", "number": "number", "boolean": "boolean", "null": "object",
               "undefined": "undefined", "string[]": "object", "Date": "object"}
# guard text -> predicate "this member is removed by the early return"
_TS_GUARDS = {
    'typeof x === "string"': lambda m: _TS_MEMBERS[m] == "string",
    'typeof x === "number"': lambda m: _TS_MEMBERS[m] == "number",
    'typeof x === "boolean"': lambda m: _TS_MEMBERS[m] == "boolean",
    'typeof x === "object"': lambda m: _TS_MEMBERS[m] == "object",
    "x === null": lambda m: m == "null",
    "x === undefined": lambda m: m == "undefined",
    "x == null": lambda m: m in ("null", "undefined"),
    "Array.isArray(x)": lambda m: m == "string[]",
    "x instanceof Date": lambda m: m == "Date",
}
_TS_KINDS = ["circle", "square", "rect", "triangle", "ellipse", "polygon"]


@family("ts_narrowing", "Сужение типов TypeScript", "typescript", "определи тип",
        {1: Tier(-0.4, 1.4, 120), 2: Tier(0.5, 1.6, 150), 3: Tier(1.2, 1.6, 180)})
def ts_narrowing(rng: random.Random, tier: int) -> Instance:
    if tier in (1, 2):
        members = rng.sample(list(_TS_MEMBERS), rng.randint(4, 5))
        if tier == 2 and not {"null", "undefined", "string[]"} & set(members):
            members[-1] = "null"
        if tier == 1:
            guard_pool = [g for g in _TS_GUARDS if "object" not in g and "== null" not in g]
        else:
            guard_pool = list(_TS_GUARDS)
        guards = rng.sample(guard_pool, 2)
        left = [m for m in members if not any(_TS_GUARDS[g](m) for g in guards)]
        correct = " | ".join(left) or "never"
        # distractors: typical mistakes - typeof "object" not covering null/arrays, == null as === null
        wrong = set()
        for drop in members:
            alt = [m for m in left if m != drop] if drop in left else left + [drop]
            alt = [m for m in members if m in alt]
            wrong.add(" | ".join(alt) or "never")
        code = (f"function f(x: {' | '.join(members)}) {{\n"
                + "".join(f"  if ({g}) return;\n" for g in guards) + "  x; // <- тип здесь?\n}")
        return choice_instance(rng, "Какой тип у x в отмеченной строке?", correct, sorted(wrong - {correct}),
                               code=code, lang="typescript",
                               explanation="typeof null === \"object\", массивы тоже object; == null отсекает и null, "
                                           "и undefined.")
    kinds = rng.sample(_TS_KINDS, rng.randint(4, 6))
    early = rng.sample(kinds, rng.randint(0, 1))
    cases = rng.sample([k for k in kinds if k not in early], rng.randint(1, len(kinds) - len(early)))
    left = [k for k in kinds if k not in early and k not in cases]
    union = " | ".join(f"{{ kind: '{k}' }}" for k in kinds)
    lines = [f"type Shape = {union};", "", "function area(s: Shape) {"]
    lines += [f"  if (s.kind === '{k}') return 0;" for k in early]
    lines += ["  switch (s.kind) {"] + [f"    case '{k}':" for k in cases] + ["      return 1;", "    default:",
                                                                               "      const n: never = s;",
                                                                               "  }", "}"]
    return Instance(prompt="Сколько вариантов Shape компилятор назовёт в ошибке у строки `const n: never = s`? "
                           "(0 — ошибки нет)", kind="number", answer=len(left), code="\n".join(lines),
                    lang="typescript",
                    explanation="В default остаются варианты, не отсечённые ни ранним return, ни case.")


_PROP_KINDS = {  # prop expression, stable between renders of Parent
    "const": ('label="title"', True),
    "count": ("value={count}", False),
    "inline_obj": ("style={{ margin: 8 }}", False),
    "inline_fn": ("onSave={() => save(id)}", False),
    "cb_stable": ("onSave={saveCb}", True),
    "cb_count": ("onPick={pickCb}", False),
    "memo_obj": ("options={opts}", True),
}


@family("react_render", "Лишние перерисовки и memo", "react", "посчитай",
        {2: Tier(0.5, 1.6, 180), 3: Tier(1.3, 1.7, 210)})
def react_render(rng: random.Random, tier: int) -> Instance:
    kinds = ["const", "count", "inline_obj"] if tier == 2 else list(_PROP_KINDS)
    names = rng.sample(["Header", "List", "Chart", "Footer", "Sidebar", "Card", "Badge"], rng.randint(3, 5))
    children = [(n, rng.random() < 0.7, rng.choice(kinds), rng.random() < 0.4) for n in names]
    total = 1  # Parent itself
    decl = []
    for name, memo, kind, has_child in children:
        prop = _PROP_KINDS[kind][0].split("=")[0]
        inner = "<Icon />" if has_child else "<div />"
        body = f"function {name}({{ {prop} }}) {{ return {inner}; }}"
        decl.append(f"const {name} = memo({body});" if memo else body)
        if not memo or not _PROP_KINDS[kind][1]:
            total += 1 + int(has_child)
    hooks = []
    if any(k == "cb_stable" for _, _, k, _ in children):
        hooks.append("  const saveCb = useCallback(() => save(id), [id]);")
    if any(k == "cb_count" for _, _, k, _ in children):
        hooks.append("  const pickCb = useCallback(() => pick(count), [count]);")
    if any(k == "memo_obj" for _, _, k, _ in children):
        hooks.append("  const opts = useMemo(() => ({ dense: true }), []);")
    jsx = [f"      <{n} {_PROP_KINDS[k][0]} />" for n, _, k, _ in children]
    code = ("function Icon() { return <svg />; }\n" + "\n".join(decl) + "\n\nfunction Parent({ id }) {\n"
            "  const [count, setCount] = useState(0);\n" + "\n".join(hooks) + ("\n" if hooks else "")
            + "  return (\n    <>\n      <button onClick={() => setCount(count + 1)}>+</button>\n"
            + "\n".join(jsx) + "\n    </>\n  );\n}")
    return Instance(prompt="Пользователь нажал «+» (id не меняется). Сколько компонентов перерисуется, включая "
                           "Parent? Icon тоже считается компонентом.", kind="number", answer=total, code=code,
                    lang="jsx",
                    explanation="memo пропускает рендер, только если все пропсы равны по ссылке; inline-объекты и "
                                "функции, а также useCallback с изменившимися deps — новые ссылки.")


_COOKIE_HOSTS = ["shop.example.com", "api.example.com", "example.com", "pay.example.com"]


@family("browser_cookies", "Отправка cookie", "browser", "посчитай",
        {1: Tier(-0.6, 1.4, 150), 2: Tier(0.4, 1.6, 180), 3: Tier(1.2, 1.7, 210)})
def browser_cookies(rng: random.Random, tier: int) -> Instance:
    cookies = []
    for name in rng.sample(["sid", "cart", "lang", "theme", "ab", "csrf", "ref"], rng.randint(4, 5)):
        domain = rng.choice([None, "example.com"])
        path = rng.choice(["/", "/", "/account", "/api"])
        secure = tier >= 2 and rng.random() < 0.5
        samesite = rng.choice(["Strict", "Lax", "None"]) if tier == 3 else None
        cookies.append((name, domain, path, secure, samesite))
    scheme = rng.choice(["https", "http"]) if tier >= 2 else "https"
    host = rng.choice(_COOKIE_HOSTS)
    req_path = rng.choice(["/", "/account/orders", "/api/v1/cart", "/catalog"])
    context, cross, top_get = ("переход по ссылке внутри сайта", False, True)
    if tier == 3:
        context, cross, top_get = rng.choice([
            ("переход по ссылке внутри сайта", False, True),
            ("переход по ссылке с другого сайта (GET, верхний уровень)", True, True),
            ("fetch-запрос со страницы другого сайта", True, False),
        ])

    def sent(c) -> bool:
        _, domain, path, secure, samesite = c
        if domain is None and host != "shop.example.com":
            return False
        if path != "/" and not (req_path == path or req_path.startswith(path + "/")):
            return False
        if secure and scheme != "https":
            return False
        if samesite == "None" and not secure:
            return False  # rejected by the browser at Set-Cookie time
        if cross and (samesite == "Strict" or (samesite == "Lax" and not top_get)):
            return False
        return True

    lines = []
    for name, domain, path, secure, samesite in cookies:
        attrs = [f"{name}=1", f"Path={path}"] + ([f"Domain={domain}"] if domain else [])
        attrs += (["Secure"] if secure else []) + ([f"SameSite={samesite}"] if samesite else [])
        lines.append("Set-Cookie: " + "; ".join(attrs))
    return Instance(prompt=f"Сайт https://shop.example.com установил cookie (ответы ниже). Затем браузер выполняет "
                           f"запрос {scheme}://{host}{req_path} ({context}). Сколько cookie уйдёт с запросом?",
                    kind="number", answer=sum(1 for c in cookies if sent(c)), code="\n".join(lines), lang="http",
                    explanation="Без Domain cookie привязана к хосту; Path — префикс пути; Secure — только https; "
                                "SameSite=None требует Secure; Lax пропускает кросс-сайтовые только для навигации "
                                "верхнего уровня.")


def _settle(promises: list[tuple[str, int, int | str]], combinator: str) -> str:
    """Exact model of Promise combinators. promise = (status, delay, value); ties are broken by array order."""
    by_time = sorted(range(len(promises)), key=lambda i: (promises[i][1], i))
    if combinator == "all":
        rejected = [i for i in by_time if promises[i][0] == "rejected"]
        if rejected:
            return f"error {promises[rejected[0]][2]}"
        return "[" + ", ".join(str(p[2]) for p in promises) + "]"
    if combinator == "allSettled":
        return str(sum(1 for p in promises if p[0] == "fulfilled"))
    if combinator == "race":
        first = promises[by_time[0]]
        return str(first[2]) if first[0] == "fulfilled" else f"error {first[2]}"
    fulfilled = [i for i in by_time if promises[i][0] == "fulfilled"]  # any
    return str(promises[fulfilled[0]][2]) if fulfilled else "error AggregateError"


@family("js_promises", "Комбинаторы промисов", "javascript", "предскажи вывод",
        {1: Tier(-0.3, 1.5, 150), 2: Tier(0.6, 1.6, 180), 3: Tier(1.3, 1.7, 210)})
def js_promises(rng: random.Random, tier: int) -> Instance:
    n = rng.randint(3, 4)
    promises = []
    for i in range(n):
        ok = rng.random() < 0.65
        promises.append(("fulfilled" if ok else "rejected", rng.choice(range(10, 101, 10)),
                         rng.randint(1, 99) if ok else f"E{i + 1}"))
    combinator = {1: rng.choice(["all", "allSettled"]), 2: rng.choice(["race", "any"]),
                  3: "all"}[tier]
    rescued = set()
    if tier == 3:
        rescued = {i for i, p in enumerate(promises) if p[0] == "rejected" and rng.random() < 0.6}
    effective = [("fulfilled", d, 0) if i in rescued else (s, d, v) for i, (s, d, v) in enumerate(promises)]
    defs = []
    for i, (status, delay, value) in enumerate(promises):
        body = f"resolve({value})" if status == "fulfilled" else f"reject('{value}')"
        fn = "resolve" if status == "fulfilled" else "_, reject"
        tail = ".catch(() => 0)" if i in rescued else ""
        defs.append(f"const p{i + 1} = new Promise(({fn}) => setTimeout(() => {body}, {delay})){tail};")
    if combinator == "allSettled":
        call = (f"Promise.allSettled([{', '.join(f'p{i + 1}' for i in range(n))}])\n"
                "  .then(rs => console.log(rs.filter(r => r.status === 'fulfilled').length));")
    else:
        err = "e.errors ? 'AggregateError' : e" if combinator == "any" else "e"
        call = (f"Promise.{combinator}([{', '.join(f'p{i + 1}' for i in range(n))}])\n"
                f"  .then(v => console.log(v))\n  .catch(e => console.log('error', {err}));")
    return Instance(prompt="Что выведет код? Запишите как в консоли: массив в виде [1, 2], число или «error E1».",
                    kind="text", answer=_settle(effective, combinator), code="\n".join(defs) + "\n\n" + call,
                    lang="javascript",
                    explanation="all падает на первом (по времени) отказе, allSettled ждёт всех, race берёт первый "
                                "завершившийся, any — первый успешный; .catch на промисе превращает отказ в значение.")
