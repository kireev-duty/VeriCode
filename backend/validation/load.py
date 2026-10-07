"""Load test against a running stand: `uv run python -m validation.load --url http://localhost:8080 --users 50`.

N virtual users work at the same time for --seconds: 70% employers (shortlist for a need, search in the bank with
filters, a candidate card, a category page), 30% candidates (dashboard, vacancies with match scores, profile) and
everyone occasionally asks for a test blueprint with generated items (the CPU-heavy path of the test engine).
Each user waits 0.5-2 s between actions, like a person. The result (p50/p95/p99 per operation, error share, RPS)
goes to docs/validation/load.json; validation.run quotes it in the report.
Needs the demo data (SEED_DEMO=true): users log in through /api/auth/demo-login.
"""

import argparse
import asyncio
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

OUT = Path(__file__).resolve().parents[2] / "docs" / "validation" / "load.json"
SPECS = ["backend", "frontend", "data", "qa", "devops"]
GRADES = ["junior", "middle", "senior"]
SKILLS = ["python", "react", "sql", "docker", "kubernetes", "typescript", "go", "java"]


class Stats:
    def __init__(self) -> None:
        self.times: dict[str, list[float]] = {}
        self.errors: dict[str, int] = {}

    def add(self, op: str, seconds: float, ok: bool) -> None:
        self.times.setdefault(op, []).append(seconds)
        if not ok:
            self.errors[op] = self.errors.get(op, 0) + 1


async def call(client: httpx.AsyncClient, stats: Stats, op: str, method: str, url: str, **kw):
    t0 = time.perf_counter()
    try:
        r = await client.request(method, url, **kw)
        ok = r.status_code < 400
    except httpx.HTTPError:
        r, ok = None, False
    stats.add(op, time.perf_counter() - t0, ok)
    return r.json() if (r is not None and ok and r.headers.get("content-type", "").startswith("application/json")) \
        else None


async def employer(client: httpx.AsyncClient, stats: Stats, rng: random.Random, until: float) -> None:
    needs = await call(client, stats, "needs list", "GET", "/api/employer/needs") or []
    need_ids = [n["id"] for n in needs] if isinstance(needs, list) else []
    seen: list[int] = []
    while time.perf_counter() < until:
        op = rng.random()
        if op < 0.35 and need_ids:
            res = await call(client, stats, "shortlist", "POST", f"/api/employer/needs/{rng.choice(need_ids)}/shortlist",
                             json={"grades": rng.sample(GRADES, rng.randint(0, 2))})
            for c in (res or {}).get("candidates", [])[:5]:
                seen.append(c["id"])
        elif op < 0.65:
            await call(client, stats, "search", "POST", "/api/employer/search",
                       json={"q": rng.choice(["", "python", "react", "kubernetes"]),
                             "filters": {"specializations": [rng.choice(SPECS)], "grades": [rng.choice(GRADES)],
                                         "skills": rng.sample(SKILLS, rng.randint(0, 2)),
                                         "fsp_only": rng.random() < 0.2}})
        elif op < 0.85 and seen:
            await call(client, stats, "candidate card", "GET", f"/api/employer/candidates/{rng.choice(seen)}")
        elif op < 0.95:
            await call(client, stats, "category", "POST", f"/api/employer/categories/{rng.choice(SPECS)}/"
                                                         f"{rng.choice(GRADES)}", json={})
        else:
            await call(client, stats, "test blueprint", "POST", "/api/assessment/blueprint-preview",
                       json={"specialization": rng.choice(SPECS), "samples": 4})
        await asyncio.sleep(rng.uniform(0.5, 2.0))


async def candidate(client: httpx.AsyncClient, stats: Stats, rng: random.Random, until: float) -> None:
    while time.perf_counter() < until:
        op = rng.random()
        if op < 0.35:
            await call(client, stats, "dashboard", "GET", "/api/candidate/dashboard")
        elif op < 0.7:
            await call(client, stats, "vacancies", "GET", "/api/candidate/vacancies")
        elif op < 0.9:
            await call(client, stats, "profile", "GET", "/api/candidate/profile")
        else:
            await call(client, stats, "test blueprint", "POST", "/api/assessment/blueprint-preview",
                       json={"specialization": rng.choice(SPECS), "samples": 4})
        await asyncio.sleep(rng.uniform(0.5, 2.0))


async def run(url: str, users: int, seconds: int) -> dict:
    stats = Stats()
    limits = httpx.Limits(max_connections=users * 2)
    async with httpx.AsyncClient(base_url=url, timeout=30, limits=limits) as anon:
        tokens = {}
        for role in ("employer", "candidate"):
            r = await anon.post("/api/auth/demo-login", params={"role": role})
            r.raise_for_status()
            tokens[role] = r.json()["access_token"]
    clients, tasks = [], []
    until = time.perf_counter() + seconds
    t0 = time.perf_counter()
    for i in range(users):
        role = "employer" if i < round(users * 0.7) else "candidate"
        c = httpx.AsyncClient(base_url=url, timeout=30, headers={"Authorization": f"Bearer {tokens[role]}"})
        clients.append(c)
        fn = employer if role == "employer" else candidate
        tasks.append(fn(c, stats, random.Random(i), until))
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - t0
    for c in clients:
        await c.aclose()
    ops = {}
    total = sum(len(v) for v in stats.times.values())
    for op, ts in sorted(stats.times.items()):
        arr = np.array(ts) * 1000
        ops[op] = {"requests": len(ts), "p50_ms": round(float(np.percentile(arr, 50))),
                   "p95_ms": round(float(np.percentile(arr, 95))), "p99_ms": round(float(np.percentile(arr, 99))),
                   "errors": stats.errors.get(op, 0)}
    return {"generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "url": url, "users": users,
            "seconds": round(elapsed), "requests": total, "rps": round(total / elapsed, 1),
            "error_share": round(sum(stats.errors.values()) / max(1, total), 4), "operations": ops}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=180)
    args = ap.parse_args()
    result = asyncio.run(run(args.url, args.users, args.seconds))
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
