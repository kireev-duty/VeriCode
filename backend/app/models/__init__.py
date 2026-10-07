"""ORM models. Generic JSON columns keep the schema portable (PostgreSQL in prod, SQLite in unit tests)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime, utcnow

# ----------------------------------------------------------------------------------------------- users & auth


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # candidate | employer
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    candidate: Mapped["CandidateProfile | None"] = relationship(back_populates="user", uselist=False)
    company: Mapped["Company | None"] = relationship(back_populates="owner", uselist=False)


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20), default="verify")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


# ----------------------------------------------------------------------------------------------- candidate


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # personal data: hidden from employers until an invitation is accepted or the candidate applies
    full_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    telegram: Mapped[str] = mapped_column(String(100), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    birth_year: Mapped[int | None] = mapped_column(Integer)

    # professional profile (self-described; does NOT define the category)
    headline: Mapped[str] = mapped_column(String(200), default="")
    about: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    work_formats: Mapped[list] = mapped_column(JSON, default=list)  # office/hybrid/remote
    relocation: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_expectation: Mapped[int | None] = mapped_column(Integer)  # RUB/month, never shown to employers directly
    experience_years: Mapped[float] = mapped_column(Float, default=0)
    skills: Mapped[list] = mapped_column(JSON, default=list)  # [{"id": "python", "years": 3}]
    team_roles: Mapped[list] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)  # [{"company","position","from","to","summary"}]
    education: Mapped[list] = mapped_column(JSON, default=list)

    # onboarding survey
    industries: Mapped[list] = mapped_column(JSON, default=list)
    specialization: Mapped[str | None] = mapped_column(String(30))
    declared_grade: Mapped[str | None] = mapped_column(String(20))
    survey: Mapped[dict] = mapped_column(JSON, default=dict)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)

    # category assigned by the test (the only thing employers search by)
    grade: Mapped[str | None] = mapped_column(String(20), index=True)
    # the grade of the last attempt that was not confirmed while no grade is confirmed yet: such candidates are
    # shown to employers below the confirmed ones, marked "не подтверждён" (they do not drop out of circulation)
    claimed_grade: Mapped[str | None] = mapped_column(String(20))
    theta: Mapped[float | None] = mapped_column(Float)
    theta_se: Mapped[float | None] = mapped_column(Float)
    skill_theta: Mapped[dict] = mapped_column(JSON, default=dict)  # per-skill ability estimates from the test
    grade_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    grade_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # freshness of the profile, fed by regular tasks
    last_task_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    task_score: Mapped[float] = mapped_column(Float, default=0)

    # FSP
    fsp_id: Mapped[str | None] = mapped_column(String(64), index=True)
    fsp_linked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fsp_profile: Mapped[dict] = mapped_column(JSON, default=dict)  # rank, rating, region (cached from registry)

    # privacy & consents (152-FZ)
    consent_processing_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    consent_publication_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    visible_to_employers: Mapped[bool] = mapped_column(Boolean, default=True)
    privacy: Mapped[dict] = mapped_column(JSON, default=dict)  # {"show_city": true, "show_experience": true, ...}
    open_to_offers: Mapped[bool] = mapped_column(Boolean, default=True)
    min_salary_for_invites: Mapped[int | None] = mapped_column(Integer)

    resume_file: Mapped[str | None] = mapped_column(String(255))
    verify_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # public verification page

    user: Mapped[User] = relationship(back_populates="candidate")
    achievements: Mapped[list["FspAchievement"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="FspAchievement.date.desc()"
    )


class FspAchievement(Base):
    """Our proposed data model for an FSP registry record (see docs/fsp-integration.md)."""

    __tablename__ = "fsp_achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))
    event_name: Mapped[str] = mapped_column(String(300))
    event_level: Mapped[str] = mapped_column(String(30))  # regional | federal | international
    discipline: Mapped[str] = mapped_column(String(40))  # product | algorithmic | security | drones | robotics
    date: Mapped[datetime] = mapped_column(UTCDateTime())
    place: Mapped[int | None] = mapped_column(Integer)
    participants: Mapped[int | None] = mapped_column(Integer)
    team_name: Mapped[str] = mapped_column(String(200), default="")
    team_role: Mapped[str] = mapped_column(String(50), default="")
    result_type: Mapped[str] = mapped_column(String(30), default="participant")  # winner|prize|finalist|participant
    skills: Mapped[list] = mapped_column(JSON, default=list)
    certificate_url: Mapped[str] = mapped_column(String(500), default="")

    candidate: Mapped[CandidateProfile] = relationship(back_populates="achievements")


# ----------------------------------------------------------------------------------------------- assessment


class ItemFamilyStat(Base):
    """Calibration and exposure state of an item family (a parametric task template at a difficulty tier)."""

    __tablename__ = "item_family_stats"

    item_key: Mapped[str] = mapped_column(String(80), primary_key=True)  # "<family>:<tier>"
    a: Mapped[float] = mapped_column(Float)
    b: Mapped[float] = mapped_column(Float)
    exposures: Mapped[int] = mapped_column(Integer, default=0)
    responses: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    residual_cusum: Mapped[float] = mapped_column(Float, default=0)  # leak detector state (see assessment/leak.py)
    residual_baseline: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | flagged | retired
    flagged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AssessmentSession(TimestampMixin, Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(30))
    target_grade: Mapped[str] = mapped_column(String(20))
    blueprint: Mapped[dict] = mapped_column(JSON, default=dict)  # skill -> weight
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id", ondelete="SET NULL"))
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | finished | abandoned
    theta: Mapped[float] = mapped_column(Float, default=0)
    se: Mapped[float] = mapped_column(Float, default=1)
    prior_mean: Mapped[float] = mapped_column(Float, default=0)
    result_grade: Mapped[str | None] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(30))  # confirmed | upgrade_available | not_confirmed
    p_target: Mapped[float | None] = mapped_column(Float)  # posterior P(theta >= target threshold)
    skill_theta: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[dict] = mapped_column(JSON, default=dict)  # integrity signals summary
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    items: Mapped[list["AssessmentItem"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="AssessmentItem.position"
    )


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    item_key: Mapped[str] = mapped_column(String(80))
    skill: Mapped[str] = mapped_column(String(40))
    seed: Mapped[int] = mapped_column(Integer)
    a: Mapped[float] = mapped_column(Float)
    b: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)  # what the candidate sees (no answer)
    answer: Mapped[dict] = mapped_column(JSON)  # server-side only
    response: Mapped[dict | None] = mapped_column(JSON)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    time_limit_s: Mapped[int] = mapped_column(Integer, default=120)
    shown_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    signals: Mapped[dict] = mapped_column(JSON, default=dict)  # paste, blur count, client time

    session: Mapped[AssessmentSession] = relationship(back_populates="items")


class GradeHistory(Base):
    __tablename__ = "grade_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str | None] = mapped_column(String(20))
    previous_grade: Mapped[str | None] = mapped_column(String(20))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)



class PilotSurvey(Base):
    """Optional questionnaire after a test: the pilot compares the test result with experience, self-assessment and
    a team lead's opinion (validation/pilot.py). Item complaints live in AssessmentItem.signals["report"]."""

    __tablename__ = "pilot_surveys"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), unique=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    experience_years: Mapped[float | None] = mapped_column(Float)
    position: Mapped[str] = mapped_column(String(120), default="")
    self_grade: Mapped[str | None] = mapped_column(String(20))
    lead_grade: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

# ----------------------------------------------------------------------------------------------- employer


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(100), default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    size: Mapped[str] = mapped_column(String(30), default="")
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    contact_phone: Mapped[str] = mapped_column(String(50), default="")
    contact_telegram: Mapped[str] = mapped_column(String(100), default="")
    inn: Mapped[str] = mapped_column(String(12), default="")
    domain_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_url: Mapped[str] = mapped_column(String(500), default="")
    webhook_secret: Mapped[str] = mapped_column(String(64), default="")
    logo_color: Mapped[str] = mapped_column(String(9), default="#5B4CF5")
    # per-company adjustments of matching weights learned from candidates' decline reasons
    ranking_weights: Mapped[dict] = mapped_column(JSON, default=dict)

    owner: Mapped[User] = relationship(back_populates="company")


class HiringNeed(TimestampMixin, Base):
    """What the employer is looking for. A need produces a shortlist (saved, refinable without loss)."""

    __tablename__ = "hiring_needs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    team_description: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(20))
    must_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_skills: Mapped[list] = mapped_column(JSON, default=list)
    work_formats: Mapped[list] = mapped_column(JSON, default=list)
    city: Mapped[str] = mapped_column(String(100), default="")
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    require_fsp: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned: Mapped[list] = mapped_column(JSON, default=list)  # candidate ids kept on top of the shortlist
    hidden: Mapped[list] = mapped_column(JSON, default=list)  # candidate ids removed by the employer
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Vacancy(TimestampMixin, Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(20))
    must_skills: Mapped[list] = mapped_column(JSON, default=list)
    nice_skills: Mapped[list] = mapped_column(JSON, default=list)
    work_formats: Mapped[list] = mapped_column(JSON, default=list)
    city: Mapped[str] = mapped_column(String(100), default="")
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="published")  # draft | published | closed

    company: Mapped[Company] = relationship()


class Invitation(TimestampMixin, Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[int | None] = mapped_column(ForeignKey("hiring_needs.id", ondelete="SET NULL"))
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("vacancies.id", ondelete="SET NULL"))
    position_title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    work_format: Mapped[str] = mapped_column(String(20), default="")
    contact_method: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent|viewed|accepted|declined|expired|withdrawn
    decline_reason: Mapped[str | None] = mapped_column(String(30))
    decline_comment: Mapped[str] = mapped_column(Text, default="")
    below_expectation: Mapped[bool] = mapped_column(Boolean, default=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    match_explanation: Mapped[list] = mapped_column(JSON, default=list)
    challenge_task_id: Mapped[int | None] = mapped_column(ForeignKey("regular_tasks.id", ondelete="SET NULL"))
    viewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())

    company: Mapped[Company] = relationship()
    candidate: Mapped[CandidateProfile] = relationship()


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("vacancy_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent|viewed|invited|rejected|withdrawn
    employer_comment: Mapped[str] = mapped_column(Text, default="")

    vacancy: Mapped[Vacancy] = relationship()
    candidate: Mapped[CandidateProfile] = relationship()


# ----------------------------------------------------------------------------------------------- regular tasks


class RegularTask(TimestampMixin, Base):
    """A short task from an employer, offered periodically to candidates of matching categories."""

    __tablename__ = "regular_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="approach")  # approach | quiz
    specialization: Mapped[str] = mapped_column(String(30))
    min_grade: Mapped[str] = mapped_column(String(20), default="intern")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    rubric: Mapped[list] = mapped_column(JSON, default=list)  # [{"point": "...", "keywords": [...], "weight": 1}]
    quiz: Mapped[dict] = mapped_column(JSON, default=dict)  # for kind=quiz: {"options": [...], "correct": i}
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped[Company | None] = relationship()


class TaskSubmission(TimestampMixin, Base):
    __tablename__ = "task_submissions"
    __table_args__ = (UniqueConstraint("task_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("regular_tasks.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    answer: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="offered")  # offered | submitted | skipped

    task: Mapped[RegularTask] = relationship()


# ----------------------------------------------------------------------------------------------- misc


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    link: Mapped[str] = mapped_column(String(300), default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    invitation_id: Mapped[int | None] = mapped_column(ForeignKey("invitations.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
