"""Python and asyncio families. Answers are obtained by executing the generated program."""

import math
import random

from app.modules.assessment.families.base import IDENTS, NAMES, Instance, Tier, family, run_python


def _ints(rng: random.Random, n: int, lo: int = 1, hi: int = 30) -> list[int]:
    return rng.sample(range(lo, hi), n)


@family("py_slicing", "Срезы и списковые выражения", "python", "предскажи вывод",
        {1: Tier(-1.4, 1.5, 90), 2: Tier(-0.3, 1.6, 120), 3: Tier(0.8, 1.7, 150)})
def py_slicing(rng: random.Random, tier: int) -> Instance:
    name = rng.choice(IDENTS)
    xs = _ints(rng, rng.randint(6, 8))
    if tier == 1:
        i, j = sorted(rng.sample(range(len(xs)), 2))
        expr = rng.choice([f"{name}[{i}:{j}]", f"{name}[-{len(xs) - i}:]", f"{name}[:{j}]"])
    elif tier == 2:
        k, m = rng.randint(2, 4), rng.randint(2, 3)
        r = rng.randint(0, m - 1)
        expr = rng.choice([f"{name}[::-{m}]", f"[x * {k} for x in {name} if x % {m} == {r}]",
                           f"{name}[{rng.randint(1, 3)}::{m}]"])
    else:
        k = rng.randint(3, 5)
        expr = rng.choice([
            f"[{name}[i] for i in range(len({name})) if {name}[i] > {name}[i - 1]]",
            f"sorted({name}, key=lambda x: (x % {k}, -x))[:3]",
            f"[a - b for a, b in zip({name}, {name}[1:]) if a > b]",
        ])
    code = f"{name} = {xs}\nprint({expr})"
    return Instance(prompt="Что выведет программа?", kind="text", answer=run_python(code), code=code,
                    lang="python", explanation="Ответ получен выполнением программы.")


@family("py_mutability", "Изменяемость и ссылки", "python", "предскажи вывод",
        {1: Tier(-1.0, 1.4, 90), 2: Tier(0.1, 1.6, 120), 3: Tier(1.1, 1.8, 150)})
def py_mutability(rng: random.Random, tier: int) -> Instance:
    a, b = rng.sample(IDENTS, 2)
    vals = _ints(rng, 3, 1, 10)
    x = rng.randint(10, 99)
    if tier == 1:
        bind = rng.choice([f"{b} = {a}", f"{b} = {a}[:]", f"{b} = list({a})"])
        op = rng.choice([f"{b}.append({x})", f"{b}[0] = {x}"])
        code = f"{a} = {vals}\n{bind}\n{op}\nprint({a})"
    elif tier == 2:
        op = rng.choice([f"{b} += [{x}]", f"{b} = {b} + [{x}]"])
        code = f"{a} = {vals}\n{b} = {a}\n{op}\nprint(len({a}), len({b}))"
    else:
        fn = rng.choice(["add", "push", "track", "collect", "remember"])
        calls = rng.randint(2, 5)
        if rng.random() < 0.5:
            code = (f"def {fn}(x, acc=[]):\n    acc.append(x)\n    return acc\n\n"
                    + "".join(f"{fn}({rng.randint(1, 9)})\n" for _ in range(calls - 1))
                    + f"print({fn}({x}))")
        else:
            n, k, m = rng.randint(3, 5), rng.randint(2, 7), rng.randint(0, 3)
            late = rng.random() < 0.5  # the classic late binding vs. the default-argument fix
            lam = f"lambda i=i: i * {k} + {m}" if not late else f"lambda: i * {k} + {m}"
            code = (f"fs = [{lam} for i in range({n})]\n"
                    f"print([f() for f in fs])")
    return Instance(prompt="Что выведет программа?", kind="text", answer=run_python(code), code=code,
                    lang="python")


@family("py_dicts", "Словари и подсчёт", "python", "предскажи вывод",
        {1: Tier(-0.8, 1.3, 120), 2: Tier(0.3, 1.5, 150)})
def py_dicts(rng: random.Random, tier: int) -> Instance:
    words = [rng.choice(NAMES[:5]) for _ in range(rng.randint(7, 10))]
    if tier == 1:
        target = rng.choice(words)
        code = (f"words = {words}\ncounts = {{}}\nfor w in words:\n    counts[w] = counts.get(w, 0) + 1\n"
                f"print(counts['{target}'], len(counts))")
    else:
        k = rng.randint(3, 5)
        code = (f"words = {words}\ngroups = {{}}\nfor i, w in enumerate(words):\n"
                f"    groups.setdefault(len(w), []).append(i % {k})\n"
                f"print(sorted((key, sum(v)) for key, v in groups.items()))")
    return Instance(prompt="Что выведет программа?", kind="text", answer=run_python(code), code=code,
                    lang="python")


@family("py_exceptions", "Поток выполнения try/except/finally", "python", "предскажи вывод",
        {2: Tier(0.0, 1.5, 150), 3: Tier(1.0, 1.7, 180)})
def py_exceptions(rng: random.Random, tier: int) -> Instance:
    fn = rng.choice(["parse", "load", "run", "step"])
    raise_at = rng.randint(0, 3)
    exc = rng.choice(["ValueError", "KeyError", "ZeroDivisionError"])
    catch = exc if rng.random() < 0.7 else rng.choice(["TypeError", "IndexError"])
    body = (f"def {fn}(n):\n    out = []\n    try:\n        out.append('t')\n"
            f"        if n == {raise_at}:\n            raise {exc}()\n        out.append('t2')\n")
    body += f"    except {catch}:\n        out.append('e')\n"
    if tier == 3:
        body += "        return ''.join(out)\n"
    body += "    else:\n        out.append('l')\n    finally:\n        out.append('f')\n    return ''.join(out)\n\n"
    rng_n = rng.sample(range(4), 2)
    body += "res = []\n"
    body += f"for n in {rng_n}:\n    try:\n        res.append({fn}(n))\n    except Exception:\n        res.append('!')\n"
    body += "print(res)"
    return Instance(prompt="Что выведет программа?", kind="text", answer=run_python(body), code=body,
                    lang="python", explanation="finally выполняется всегда, даже после return.")


@family("py_iterators", "Генераторы и итераторы", "python", "предскажи вывод",
        {2: Tier(0.4, 1.5, 120), 3: Tier(1.3, 1.6, 150)})
def py_iterators(rng: random.Random, tier: int) -> Instance:
    n, k = rng.randint(3, 12), rng.randint(2, 5)
    if tier == 2:
        m = rng.randint(1, 4)
        code = rng.choice([
            f"g = (x * {k} for x in range({n}))\nprint(sum(g), sum(g))",
            f"g = (x + {m} for x in range({n}) if x % {k})\nfirst = list(g)\nprint(len(first), list(g))",
            f"it = map(lambda x: x * {k}, range({n}))\nprint(max(it), sum(it))",
        ])
    else:
        xs = _ints(rng, rng.choice([5, 6, 7]), 1, 20)
        code = rng.choice([
            f"it = iter({xs})\nprint(list(zip(it, it)))",
            f"it = iter({xs})\nfirst = next(it)\nprint(first, sum(it), list(it))",
        ])
    return Instance(prompt="Что выведет программа?", kind="text", answer=run_python(code), code=code,
                    lang="python")


@family("py_classes", "Классы, атрибуты и MRO", "python", "предскажи вывод",
        {2: Tier(0.6, 1.5, 150), 3: Tier(1.5, 1.6, 180)})
def py_classes(rng: random.Random, tier: int) -> Instance:
    if tier == 2:
        cls = rng.choice(["Cart", "Team", "Queue"])
        n = rng.randint(2, 3)
        shared = rng.random() < 0.6
        init = "" if shared else "    def __init__(self):\n        self.items = []\n"
        attr = "    items = []\n" if shared else ""
        n = rng.randint(2, 5)
        k = rng.randint(1, 4)
        idx = rng.randrange(n)
        what = rng.choice([f"len(objs[{idx}].items)", f"sum(objs[{idx}].items)", f"objs[{idx}].items[-1]"])
        code = (f"class {cls}:\n{attr}{init}    def add(self, x):\n        self.items.append(x)\n\n"
                f"objs = [{cls}() for _ in range({n})]\nfor i, o in enumerate(objs):\n    o.add(i * {k})\n"
                f"print({what})")
    else:
        # diamond: which sides delegate to super() and the order of bases vary -> 4! x 2 x 2 x 2 structures
        base, left, right, child = rng.sample(["A", "B", "C", "D"], 4)

        def body(name: str, delegates: bool) -> str:
            return f"'{name}' + super().who()" if delegates else f"'{name}'"

        bases = f"{left}, {right}" if rng.random() < 0.5 else f"{right}, {left}"
        code = (f"class {base}:\n    def who(self):\n        return '{base}'\n\n"
                f"class {left}({base}):\n    def who(self):\n        return {body(left, rng.random() < 0.7)}\n\n"
                f"class {right}({base}):\n    def who(self):\n        return {body(right, rng.random() < 0.7)}\n\n"
                f"class {child}({bases}):\n    pass\n\nprint({child}().who())")
    return Instance(prompt="Что выведет программа?", kind="text", answer=run_python(code), code=code,
                    lang="python")


@family("py_async", "Конкурентность в asyncio", "asyncio", "предскажи вывод / время",
        {1: Tier(-0.4, 1.4, 150), 2: Tier(0.5, 1.6, 180), 3: Tier(1.4, 1.7, 210)})
def py_async(rng: random.Random, tier: int) -> Instance:
    if tier in (1, 2):
        names = rng.sample(["a", "b", "c", "d", "e"], 3 if tier == 1 else 4)
        delays = rng.sample(range(1, 9), len(names))
        jobs = ", ".join(f"job('{n}', {d})" for n, d in zip(names, delays))
        code = ("import asyncio\n\nasync def job(name, delay):\n    await asyncio.sleep(delay)\n"
                "    print(name, end=' ')\n\nasync def main():\n")
        if tier == 1:
            code += f"    await asyncio.gather({jobs})\n"
            order = [n for _, n in sorted(zip(delays, names))]
        else:
            first = f"job('{names[0]}', {delays[0]})"
            rest = ", ".join(f"job('{n}', {d})" for n, d in zip(names[1:], delays[1:]))
            code += f"    await {first}\n    await asyncio.gather({rest})\n"
            order = [names[0]] + [n for _, n in sorted(zip(delays[1:], names[1:]))]
        code += "\nasyncio.run(main())"
        return Instance(prompt="В каком порядке будут напечатаны имена? (sleep в секундах)", kind="text",
                        answer=" ".join(order), code=code, lang="python",
                        explanation="gather запускает корутины конкурентно, await — последовательно.")
    d = [rng.randint(1, 5) for _ in range(6)]
    code = ("import asyncio\n\nasync def job(s):\n    await asyncio.sleep(s)\n\nasync def main():\n"
            f"    await job({d[0]})\n"
            f"    await asyncio.gather(job({d[1]}), job({d[2]}))\n"
            f"    t = asyncio.create_task(job({d[3]}))\n"
            f"    await job({d[4]})\n"
            f"    await t\n"
            f"    await asyncio.wait_for(job({d[5]}), timeout=10)\n\nasyncio.run(main())")
    total = d[0] + max(d[1], d[2]) + max(d[3], d[4]) + d[5]
    return Instance(prompt="Сколько секунд (примерно) будет выполняться программа?", kind="number",
                    answer=total, code=code, lang="python",
                    explanation="create_task запускает задачу сразу, она идёт параллельно со следующим await.")


def _fifo_slots(durations: list[int], slots: int) -> int:
    """Finish time of jobs started in order whenever one of `slots` permits is free (asyncio.Semaphore is FIFO)."""
    free = [0] * slots
    for d in durations:
        i = free.index(min(free))
        free[i] += d
    return max(free)


@family("asyncio_limits", "Семафоры и таймауты asyncio", "asyncio", "посчитай",
        {2: Tier(0.6, 1.6, 180), 3: Tier(1.3, 1.7, 210)})
def asyncio_limits(rng: random.Random, tier: int) -> Instance:
    k = rng.randint(2, 4)
    if tier == 2:
        n, d = rng.randint(5, 12), rng.randint(1, 4)
        # a half-second offset keeps every finish time strictly before or after the timeout
        timeout = rng.choice([None, None, d * rng.randint(1, 3) + 0.5, d - 0.5])
        code = (f"import asyncio\n\nsem = asyncio.Semaphore({k})\n\nasync def job():\n    async with sem:\n"
                f"        await asyncio.sleep({d})\n\nasync def main():\n")
        if timeout is None:
            code += f"    await asyncio.gather(*(job() for _ in range({n})))\n"
            prompt, ans = "Сколько секунд (примерно) будет выполняться программа?", math.ceil(n / k) * d
        else:
            code += (f"    res = await asyncio.gather(*(asyncio.wait_for(job(), timeout={timeout}) for _ in "
                     f"range({n})), return_exceptions=True)\n"
                     "    print(sum(isinstance(r, TimeoutError) for r in res))\n")
            # wait_for starts every wrapper at once: the timeout also counts time spent waiting for the semaphore
            ok = sum(1 for i in range(n) if (i // k + 1) * d <= timeout)
            prompt, ans = "Что выведет программа?", n - ok
        return Instance(prompt=prompt, kind="number", answer=ans, code=code + "\nasyncio.run(main())",
                        lang="python", explanation="Семафор пропускает не больше k корутин одновременно; таймаут "
                                                   "wait_for включает и ожидание семафора.")
    durations = [rng.randint(1, 6) for _ in range(rng.randint(5, 8))]
    code = (f"import asyncio\n\nsem = asyncio.Semaphore({k})\n\nasync def job(s):\n    async with sem:\n"
            "        await asyncio.sleep(s)\n\nasync def main():\n"
            f"    await asyncio.gather(*(job(s) for s in {durations}))\n\nasyncio.run(main())")
    return Instance(prompt="Сколько секунд (примерно) будет выполняться программа? Задачи захватывают семафор в "
                           "порядке создания.", kind="number", answer=_fifo_slots(durations, k), code=code,
                    lang="python", explanation="Каждая следующая задача занимает первый освободившийся слот.")
