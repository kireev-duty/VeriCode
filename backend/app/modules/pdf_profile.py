"""Standardised PDF profile ("skill passport") with a QR code to the public verification page."""

import io
from pathlib import Path

import qrcode
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.catalog import GRADE_BY_ID, SKILL_BY_ID, SPEC_BY_ID, WORK_FORMATS
from app.core.config import settings
from app.models import CandidateProfile
from app.modules.fsp.scoring import DISCIPLINES, LEVELS, RESULTS

ASSETS = Path(__file__).resolve().parent.parent / "assets"
BLUE = HexColor("#402FFF")
RED = HexColor("#EC1D35")
DARK = HexColor("#1B1C21")
GREY = HexColor("#6B6C72")
LIGHT = HexColor("#EDEDED")

_fonts_ready = False


def _fonts():
    global _fonts_ready
    if not _fonts_ready:
        pdfmetrics.registerFont(TTFont("Sans", str(ASSETS / "fonts" / "PTSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Sans-Bold", str(ASSETS / "fonts" / "PTSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Mono", str(ASSETS / "fonts" / "JetBrainsMono-Regular.ttf")))
        _fonts_ready = True


def verify_url(c: CandidateProfile) -> str:
    return f"{settings.public_url}/verify/{c.verify_code}"


def _qr(url: str) -> ImageReader:
    img = qrcode.make(url, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def render(c: CandidateProfile, include_contacts: bool = True) -> bytes:
    _fonts()
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    left, right = 18 * mm, W - 18 * mm
    pdf.setTitle(f"Профиль кандидата — {c.full_name or 'ФСП Талант'}")

    # header band
    pdf.setFillColor(BLUE)
    pdf.rect(0, H - 38 * mm, W, 38 * mm, stroke=0, fill=1)
    pdf.drawImage(ImageReader(str(ASSETS / "logo.png")), left, H - 31 * mm, 22 * mm, 23 * mm, mask="auto")
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont("Sans-Bold", 20)
    pdf.drawString(left + 28 * mm, H - 17 * mm, c.full_name or "Кандидат")
    pdf.setFont("Sans", 11)
    spec = SPEC_BY_ID[c.specialization].title if c.specialization else "Специализация не выбрана"
    grade = GRADE_BY_ID[c.grade].title if c.grade else "грейд не подтверждён"
    pdf.drawString(left + 28 * mm, H - 24 * mm, f"{spec} · {grade}")
    pdf.setFont("Mono", 8)
    pdf.drawString(left + 28 * mm, H - 30 * mm, "СТАНДАРТИЗИРОВАННЫЙ ПРОФИЛЬ · ФСП ТАЛАНТ")
    pdf.drawImage(_qr(verify_url(c)), right - 26 * mm, H - 34 * mm, 26 * mm, 26 * mm)

    y = H - 48 * mm

    def section(title: str):
        nonlocal y
        if y < 40 * mm:
            pdf.showPage()
            y = H - 20 * mm
        pdf.setFillColor(BLUE)
        pdf.setFont("Mono", 9)
        pdf.drawString(left, y, title.upper())
        pdf.setStrokeColor(LIGHT)
        pdf.line(left, y - 2 * mm, right, y - 2 * mm)
        y -= 8 * mm

    def text(line: str, font: str = "Sans", size: int = 10, color=DARK, gap: float = 5.2):
        nonlocal y
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        for ln in simpleSplit(line, font, size, right - left):
            if y < 18 * mm:
                pdf.showPage()
                y = H - 20 * mm
                pdf.setFont(font, size)
                pdf.setFillColor(color)
            pdf.drawString(left, y, ln)
            y -= gap * mm

    section("Категория, подтверждённая тестом")
    if c.grade:
        date = c.grade_confirmed_at.strftime("%d.%m.%Y") if c.grade_confirmed_at else ""
        text(f"{spec} · {grade} — подтверждено адаптивным тестом {date}", "Sans-Bold", 11)
        if c.skill_theta:
            parts = [f"{SKILL_BY_ID[s].title if s in SKILL_BY_ID else s}: {_level(v)}"
                     for s, v in sorted(c.skill_theta.items(), key=lambda x: -x[1])]
            text("Навыки по результатам теста: " + "; ".join(parts), color=GREY, size=9)
    else:
        text("Грейд ещё не подтверждён тестом.", color=GREY)
    y -= 2 * mm

    section("Профиль")
    if c.headline:
        text(c.headline, "Sans-Bold", 11)
    meta = [f"Опыт: {c.experience_years:g} лет" if c.experience_years else "",
            f"Город: {c.city}" if c.city else "",
            "Формат: " + ", ".join(WORK_FORMATS.get(f, f) for f in c.work_formats) if c.work_formats else "",
            "Готов к релокации" if c.relocation else ""]
    text(" · ".join(m for m in meta if m), color=GREY, size=9)
    if c.about:
        text(c.about, size=10)
    y -= 2 * mm

    if c.skills:
        section("Стек")
        skills = []
        for s in c.skills:
            if isinstance(s, dict) and s.get("id") in SKILL_BY_ID:
                mark = " •" if s["id"] in (c.skill_theta or {}) else ""
                years = f" ({s['years']} г.)" if s.get("years") else ""
                skills.append(f"{SKILL_BY_ID[s['id']].title}{years}{mark}")
        text(", ".join(skills))
        text("• — навык проверен тестом", size=8, color=GREY)
        y -= 2 * mm

    if c.experience:
        section("Опыт работы")
        for e in c.experience:
            if not isinstance(e, dict):
                continue
            text(f"{e.get('position', '')} — {e.get('company', '')}", "Sans-Bold", 10)
            text(f"{e.get('from', '')} — {e.get('to', '') or 'по н. в.'}", size=9, color=GREY)
            if e.get("summary"):
                text(e["summary"], size=9)
            y -= 1 * mm

    section("Достижения ФСП")
    if c.achievements:
        for a in c.achievements:
            res = RESULTS.get(a.result_type, (a.result_type,))[0]
            place = f", {a.place} место" if a.place else ""
            text(f"{res}{place} — {a.event_name} ({a.date.year})", "Sans-Bold", 10)
            text(f"{LEVELS.get(a.event_level, (a.event_level,))[0]} уровень · "
                 f"{DISCIPLINES.get(a.discipline, a.discipline)}" + (f" · роль: {a.team_role}" if a.team_role else ""),
                 size=9, color=GREY)
        if (c.fsp_profile or {}).get("rank"):
            text(f"Спортивный разряд: {c.fsp_profile['rank']}", size=9)
        text("Данные получены из реестра ФСП по ФСП ID и не редактируются кандидатом.", size=8, color=GREY)
    else:
        text("История участия в соревнованиях ФСП отсутствует.", size=9, color=GREY)
    y -= 2 * mm

    if c.team_roles or c.soft_skills:
        section("Роли в команде и soft skills")
        text(", ".join((c.team_roles or []) + (c.soft_skills or [])), size=10)

    if include_contacts:
        section("Контакты")
        text(" · ".join(x for x in (c.contact_email, c.phone, c.telegram) if x) or "—")

    pdf.setFont("Mono", 7)
    pdf.setFillColor(GREY)
    pdf.drawString(left, 10 * mm, f"Проверить подлинность: {verify_url(c)}")
    pdf.setFillColor(RED)
    pdf.rect(right - 12 * mm, 9 * mm, 12 * mm, 1.2 * mm, stroke=0, fill=1)
    pdf.save()
    return buf.getvalue()


def _level(theta: float) -> str:
    if theta >= 1.1:
        return "высокий"
    if theta >= 0.1:
        return "уверенный"
    if theta >= -0.9:
        return "базовый"
    return "начальный"
