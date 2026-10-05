"""Parametric item families.

A family is a task *template*: the structure (and therefore the difficulty) is fixed, the surface - data,
names, constants, branch choices - is drawn from a seeded RNG. The correct answer is *computed* (by running
the generated code, a SQL engine or an exact model of the semantics), never typed by hand and never produced
by an LLM. Two candidates practically never see the same instance, so a leaked answer key is useless,
while every instance of a tier keeps comparable difficulty.

A family exposes several difficulty tiers; each (family, tier) is one calibrated IRT item "slot".
"""

import contextlib
import io
import random
from collections.abc import Callable
from dataclasses import dataclass, field

NAMES = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi", "ivan", "judy", "kate", "leo",
         "mike", "nina", "oleg", "pavel", "rita", "sara", "tom", "vera"]
IDENTS = ["items", "data", "values", "nums", "xs", "arr", "buf", "acc", "res", "out", "seq", "pool", "batch",
          "queue", "stack", "cache", "parts", "chunks"]
FUNCS = ["process", "handle", "build", "collect", "update", "merge", "transform", "apply", "visit", "compute"]


@dataclass
class Instance:
    prompt: str
    kind: str  # single | text | number
    answer: object  # option index for single, canonical string for text, float for number
    code: str = ""
    lang: str = ""
    options: list[str] = field(default_factory=list)
    explanation: str = ""
    tolerance: float = 0.0  # for numeric answers

    def payload(self) -> dict:
        return {"prompt": self.prompt, "kind": self.kind, "code": self.code, "lang": self.lang,
                "options": self.options}

    def answer_key(self) -> dict:
        return {"answer": self.answer, "explanation": self.explanation, "tolerance": self.tolerance}


@dataclass(frozen=True)
class Tier:
    b: float  # expert prior difficulty, re-estimated by calibration
    a: float = 1.4
    time_s: int = 120


@dataclass(frozen=True)
class Family:
    id: str
    title: str
    skill: str
    fmt: str  # human description of the format: "предскажи вывод", "найди ошибку", ...
    tiers: dict[int, Tier]
    generate: Callable[[random.Random, int], Instance]

    def item_key(self, tier: int) -> str:
        return f"{self.id}:{tier}"


REGISTRY: dict[str, Family] = {}


def family(id: str, title: str, skill: str, fmt: str, tiers: dict[int, Tier]):
    def deco(fn: Callable[[random.Random, int], Instance]):
        REGISTRY[id] = Family(id, title, skill, fmt, tiers, fn)
        return fn

    return deco


def guess_floor(kind: str, n_options: int) -> float:
    return 1.0 / n_options if kind == "single" and n_options else 0.0


# ------------------------------------------------------------------------------------------------ helpers


def run_python(code: str) -> str:
    """Executes *generated* (trusted, template-built) code and captures stdout. Never used on user input."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<item>", "exec"), {"__name__": "__item__"})
    return buf.getvalue().strip()


def choice_instance(rng: random.Random, prompt: str, correct: str, distractors: list[str], *, code: str = "",
                    lang: str = "", explanation: str = "", n: int = 4) -> Instance:
    """Builds a shuffled single-choice item; distractors equal to the correct answer are dropped."""
    seen = {correct}
    pool = []
    for d in distractors:
        if d not in seen:
            seen.add(d)
            pool.append(d)
    rng.shuffle(pool)
    options = [correct] + pool[: n - 1]
    rng.shuffle(options)
    return Instance(prompt=prompt, kind="single", answer=options.index(correct), code=code, lang=lang,
                    options=options, explanation=explanation)


def normalize_text(s: str) -> str:
    """Whitespace-insensitive, quote-insensitive comparison: "[1,'a']" == "[1, \"a\"]"."""
    return "".join(str(s).split()).replace('"', "'").lower()


def check(instance_kind: str, key: dict, response) -> bool:
    answer = key["answer"]
    if response is None:
        return False
    if instance_kind == "single":
        try:
            return int(response) == int(answer)
        except (TypeError, ValueError):
            return False
    if instance_kind == "number":
        try:
            value = float(str(response).replace(",", ".").strip())
        except ValueError:
            return False
        return abs(value - float(answer)) <= float(key.get("tolerance") or 0) + 1e-9
    return normalize_text(response) == normalize_text(answer)
