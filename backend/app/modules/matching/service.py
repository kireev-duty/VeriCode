"""Shortlists for employers: category-first search, ranking with explanations, anonymised cards, contact reveal."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalog import GRADE_BY_ID, GRADE_ORDER, SKILL_BY_ID, SPEC_BY_ID
from app.models import Application, CandidateProfile, Company, HiringNeed, Invitation, Vacancy
from app.modules.fsp.scoring import DISCIPLINES, LEVELS, RESULTS, fsp_score
from app.modules.matching.scoring import CandidateView, NeedSpec, profile_strength, score


def public_code(c: CandidateProfile) -> str:
    return f"К-{c.verify_code[:5].upper()}"


def candidate_view(c: CandidateProfile) -> CandidateView:
    fsp, reasons = fsp_score(c.achievements, (c.fsp_profile or {}).get("rank", ""))
    last = max([d for d in (c.grade_confirmed_at, c.last_task_at) if d is not None], default=None)
    text = " ".join([c.headline or "", c.about or ""] + [e.get("summary", "") + " " + e.get("position", "")
                                                         for e in (c.experience or []) if isinstance(e, dict)])
    return CandidateView(
        id=c.id, specialization=c.specialization, grade=c.grade, theta=c.theta, skill_theta=c.skill_theta or {},
        declared_skills=[s["id"] for s in (c.skills or []) if isinstance(s, dict)],
        experience_years=c.experience_years or 0, work_formats=c.work_formats or [], city=c.city or "",
        relocation=bool(c.relocation), salary_expectation=c.salary_expectation, fsp=fsp, fsp_reasons=reasons,
        last_activity=last, text=text, claimed_grade=None if c.grade else c.claimed_grade,
    )


def need_spec(n: HiringNeed | Vacancy) -> NeedSpec:
    text = getattr(n, "raw_text", "") or getattr(n, "description", "") or ""
    return NeedSpec(specialization=n.specialization, grade=n.grade, must_skills=list(n.must_skills or []),
                    nice_skills=list(n.nice_skills or []), work_formats=list(n.work_formats or []), city=n.city or "",
                    salary_from=n.salary_from, salary_to=n.salary_to, text=text,
                    require_fsp=bool(getattr(n, "require_fsp", False)))


def effective_grade(c: CandidateProfile) -> str | None:
    """The confirmed grade, or the claimed one for a candidate whose grade is not confirmed yet."""
    return c.grade or c.claimed_grade


def in_bank(c: CandidateProfile) -> bool:
    """Visible to employers: took the test (confirmed or not), consented to publication, not hidden."""
    return effective_grade(c) is not None and bool(c.visible_to_employers) and c.consent_publication_at is not None


def grade_in(grades: list[str]):
    """SQL filter by the effective grade (confirmed, else claimed)."""
    return or_(CandidateProfile.grade.in_(grades),
               and_(CandidateProfile.grade.is_(None), CandidateProfile.claimed_grade.in_(grades)))


def searchable_query():
    """Candidates who took the test, gave consent to publication and are visible.

    A grade that is not confirmed does not hide the candidate (per the organisers' Q&A they must not drop out of
    circulation): such candidates are listed after all confirmed ones and marked.
    """
    return (select(CandidateProfile)
            .options(selectinload(CandidateProfile.achievements))
            .where(or_(CandidateProfile.grade.is_not(None), CandidateProfile.claimed_grade.is_not(None)),
                   CandidateProfile.visible_to_employers.is_(True),
                   CandidateProfile.consent_publication_at.is_not(None)))


def categories_overview(db: Session) -> list[dict]:
    rows = db.scalars(searchable_query()).all()
    counts: dict[tuple[str, str], dict] = {}
    for c in rows:
        key = (c.specialization, effective_grade(c))
        d = counts.setdefault(key, {"total": 0, "fsp": 0, "unconfirmed": 0})
        if c.grade:
            d["total"] += 1
            d["fsp"] += 1 if c.achievements else 0
        else:
            d["unconfirmed"] += 1
    out = []
    for spec_id, spec in SPEC_BY_ID.items():
        for g in GRADE_ORDER:
            d = counts.get((spec_id, g), {"total": 0, "fsp": 0, "unconfirmed": 0})
            out.append({"specialization": spec_id, "specialization_title": spec.short, "grade": g,
                        "grade_title": GRADE_BY_ID[g].title, "count": d["total"], "with_fsp": d["fsp"],
                        "unconfirmed": d["unconfirmed"]})
    return out


def apply_filters(views: list[tuple[CandidateProfile, CandidateView]], f: dict) -> list:
    out = []
    for c, v in views:
        if f.get("grades") and (v.grade or v.claimed_grade) not in f["grades"]:
            continue
        if f.get("skills") and not set(f["skills"]) <= (set(v.declared_skills) | set(v.skill_theta)):
            continue
        if f.get("verified_skills") and not set(f["verified_skills"]) <= set(v.skill_theta):
            continue
        if f.get("fsp_only") and not c.achievements:
            continue
        if f.get("work_formats") and v.work_formats and not set(f["work_formats"]) & set(v.work_formats):
            continue
        if f.get("city") and v.city != f["city"] and not v.relocation:
            continue
        if f.get("max_salary") and v.salary_expectation and v.salary_expectation > f["max_salary"]:
            continue
        if f.get("min_experience") and v.experience_years < f["min_experience"]:
            continue
        out.append((c, v))
    return out


def shortlist(db: Session, company: Company, need: HiringNeed, filters: dict | None = None, limit: int = 50) -> dict:
    """Recommended categories (requested grade + neighbours) and ranked candidates with explanations.

    Filters narrow the *same* shortlist (the need is stored server-side); pinned candidates stay on top even
    if a filter would hide them, hidden ones are removed.
    """
    spec = need_spec(need)
    gi = GRADE_ORDER.index(need.grade)
    grades = [g for g in GRADE_ORDER if abs(GRADE_ORDER.index(g) - gi) <= 1]
    rows = db.scalars(searchable_query().where(CandidateProfile.specialization == need.specialization,
                                               grade_in(grades))).all()
    views = [(c, candidate_view(c)) for c in rows if c.id not in (need.hidden or [])]
    if need.require_fsp:
        views = [(c, v) for c, v in views if c.achievements]
    pinned_ids = set(need.pinned or [])
    filtered = apply_filters(views, filters or {})
    keep = {c.id for c, _ in filtered} | pinned_ids
    scored = []
    for c, v in views:
        if c.id not in keep:
            continue
        s = score(v, spec, company.ranking_weights or {})
        scored.append((c, v, s))
    # pinned first, then all confirmed grades, then the unconfirmed tail
    scored.sort(key=lambda x: (x[0].id not in pinned_ids, x[0].grade is None, -x[2]["score"]))
    invited = invitation_status_map(db, company.id, [c.id for c, _, _ in scored])

    categories = []
    for g in grades:
        in_cat = [x for x in scored if x[1].grade == g]
        categories.append({"specialization": need.specialization, "grade": g, "grade_title": GRADE_BY_ID[g].title,
                           "is_target": g == need.grade, "count": len(in_cat),
                           "unconfirmed": sum(1 for x in scored if x[1].claimed_grade == g),
                           "avg_score": round(sum(x[2]["score"] for x in in_cat) / len(in_cat), 3) if in_cat else 0})
    return {
        "need_id": need.id,
        "total_in_categories": len(views),
        "after_filters": len(scored),
        "categories": categories,
        "candidates": [card(c, v, s, pinned=c.id in pinned_ids, invitation=invited.get(c.id))
                       for c, v, s in scored[:limit]],
    }


def browse_category(db: Session, specialization: str, grade: str, filters: dict | None = None,
                    limit: int = 50) -> list[dict]:
    rows = db.scalars(searchable_query().where(CandidateProfile.specialization == specialization,
                                               grade_in([grade]))).all()
    views = apply_filters([(c, candidate_view(c)) for c in rows], filters or {})
    ranked = sorted(views, key=lambda x: (x[0].grade is None, -profile_strength(x[1])))
    return [card(c, v, None, strength=profile_strength(v)) for c, v in ranked[:limit]]


def search_bank(db: Session, q: str = "", filters: dict | None = None, limit: int = 50) -> list[dict]:
    """Free search across the whole bank: specialization/grade/category/stack/FSP filters, ranked by strength."""
    f = filters or {}
    query = searchable_query()
    if f.get("specializations"):
        query = query.where(CandidateProfile.specialization.in_(f["specializations"]))
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(CandidateProfile.headline.ilike(like), CandidateProfile.about.ilike(like)))
    views = apply_filters([(c, candidate_view(c)) for c in db.scalars(query).all()], f)
    ranked = sorted(views, key=lambda x: (x[0].grade is None, -profile_strength(x[1])))
    return [card(c, v, None, strength=profile_strength(v)) for c, v in ranked[:limit]]


def invitation_status_map(db: Session, company_id: int, candidate_ids: list[int]) -> dict[int, str]:
    if not candidate_ids:
        return {}
    rows = db.execute(select(Invitation.candidate_id, Invitation.status).where(
        Invitation.company_id == company_id, Invitation.candidate_id.in_(candidate_ids))
        .order_by(Invitation.created_at)).all()
    return {cid: st for cid, st in rows}


def contacts_open(db: Session, company_id: int, candidate_id: int) -> bool:
    """Contacts are revealed only after the candidate accepted an invitation or applied to this company."""
    accepted = db.scalar(select(Invitation.id).where(Invitation.company_id == company_id,
                                                     Invitation.candidate_id == candidate_id,
                                                     Invitation.status == "accepted"))
    if accepted:
        return True
    applied = db.scalar(select(Application.id).join(Vacancy).where(
        Vacancy.company_id == company_id, Application.candidate_id == candidate_id,
        Application.status != "withdrawn"))
    return bool(applied)


def achievements_public(c: CandidateProfile) -> list[dict]:
    return [{"event_name": a.event_name, "level": LEVELS.get(a.event_level, (a.event_level,))[0],
             "discipline": DISCIPLINES.get(a.discipline, a.discipline), "year": a.date.year,
             "result": RESULTS.get(a.result_type, (a.result_type,))[0], "place": a.place,
             "participants": a.participants, "team_role": a.team_role, "verified": True}
            for a in c.achievements]


def card(c: CandidateProfile, v: CandidateView, s: dict | None, *, pinned: bool = False,
         invitation: str | None = None, strength: float | None = None) -> dict:
    """Anonymised card: no name, photo, age, contacts or employer names - only the verified skill passport."""
    privacy = c.privacy or {}
    skills = []
    for sk in c.skills or []:
        sid = sk.get("id") if isinstance(sk, dict) else None
        if sid in SKILL_BY_ID:
            skills.append({"id": sid, "title": SKILL_BY_ID[sid].title, "years": sk.get("years"),
                           "verified": sid in (c.skill_theta or {})})
    for sid in c.skill_theta or {}:
        if sid in SKILL_BY_ID and sid not in {x["id"] for x in skills}:
            skills.append({"id": sid, "title": SKILL_BY_ID[sid].title, "years": None, "verified": True})
    return {
        "id": c.id,
        "code": public_code(c),
        "headline": c.headline,
        "specialization": c.specialization,
        "specialization_title": SPEC_BY_ID[c.specialization].short if c.specialization else None,
        "grade": c.grade,
        "grade_title": GRADE_BY_ID[c.grade].title if c.grade else None,
        "grade_confirmed": c.grade is not None,
        "claimed_grade": None if c.grade else c.claimed_grade,
        "claimed_grade_title": GRADE_BY_ID[c.claimed_grade].title if not c.grade and c.claimed_grade else None,
        "theta": c.theta,
        "skill_theta": c.skill_theta or {},
        "grade_confirmed_at": c.grade_confirmed_at.isoformat() if c.grade_confirmed_at else None,
        "experience_years": round(c.experience_years or 0),
        "skills": skills,
        "work_formats": c.work_formats or [],
        "city": c.city if privacy.get("show_city", True) else "",
        "relocation": c.relocation,
        "team_roles": c.team_roles or [],
        "soft_skills": c.soft_skills or [],
        "has_fsp": bool(c.achievements),
        "fsp_linked": bool(c.fsp_id),
        "fsp_rank": (c.fsp_profile or {}).get("rank", ""),
        "achievements": achievements_public(c) if privacy.get("show_fsp", True) else [],
        "fsp_score": v.fsp,
        "open_to_offers": c.open_to_offers,
        "match": s,
        "strength": strength,
        "pinned": pinned,
        "invitation_status": invitation,
    }


def experience_public(c: CandidateProfile) -> list[dict]:
    show_companies = (c.privacy or {}).get("show_companies", False)
    return [{"position": e.get("position", ""), "company": e.get("company", "") if show_companies else "скрыто",
             "from": e.get("from", ""), "to": e.get("to", ""), "summary": e.get("summary", "")}
            for e in (c.experience or []) if isinstance(e, dict)]
