from __future__ import annotations

from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from enrich.config import (
    CATEGORY_VALUES,
    CURRENCY_VALUES,
    EMPLOYMENT_VALUES,
    ENGLISH_LEVEL_VALUES,
    LEVEL_VALUES,
    WORK_FORMAT_VALUES,
)


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value if str(item).strip())
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    if text.lower() in {"unknown", "null", "none", "n/a", "not specified"}:
        return None
    return text


def _normalize_category_label(value) -> str:
    if value is None:
        return CategoryEnum.UNKNOWN.value

    normalized = str(value).strip().lower().replace("&", " and ")
    normalized = normalized.replace("/", " ").replace("-", " ").replace(".", " ")
    normalized = "_".join(part for part in normalized.split() if part)
    if not normalized:
        return CategoryEnum.UNKNOWN.value
    if normalized in CATEGORY_VALUES:
        return normalized

    alias_map = {
        "backend": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "backend_developer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "backend_engineer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "frontend": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "frontend_developer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "frontend_engineer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "fullstack": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "full_stack": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "fullstack_developer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "mobile": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "android": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "ios": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "software": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "software_engineer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "software_developer": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "web_development": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "web": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "engineering": CategoryEnum.SOFTWARE_ENGINEERING.value,
        "data_engineer": CategoryEnum.DATA.value,
        "data_analyst": CategoryEnum.DATA.value,
        "data_scientist": CategoryEnum.DATA.value,
        "ml": CategoryEnum.DATA.value,
        "ai": CategoryEnum.DATA.value,
        "ml_engineer": CategoryEnum.DATA.value,
        "machine_learning": CategoryEnum.DATA.value,
        "machine_learning_engineer": CategoryEnum.DATA.value,
        "artificial_intelligence": CategoryEnum.DATA.value,
        "bi": CategoryEnum.DATA.value,
        "bi_analyst": CategoryEnum.DATA.value,
        "business_intelligence": CategoryEnum.DATA.value,
        "test": CategoryEnum.QA.value,
        "testing": CategoryEnum.QA.value,
        "quality_assurance": CategoryEnum.QA.value,
        "test_automation": CategoryEnum.QA.value,
        "sdet": CategoryEnum.QA.value,
        "sre": CategoryEnum.DEVOPS.value,
        "platform": CategoryEnum.DEVOPS.value,
        "platform_engineering": CategoryEnum.DEVOPS.value,
        "cloud": CategoryEnum.DEVOPS.value,
        "cloud_engineering": CategoryEnum.DEVOPS.value,
        "infrastructure": CategoryEnum.DEVOPS.value,
        "infra": CategoryEnum.DEVOPS.value,
        "product_manager": CategoryEnum.PRODUCT.value,
        "product_owner": CategoryEnum.PRODUCT.value,
        "project_management": CategoryEnum.MANAGEMENT.value,
        "project_manager": CategoryEnum.MANAGEMENT.value,
        "engineering_manager": CategoryEnum.MANAGEMENT.value,
        "delivery_manager": CategoryEnum.MANAGEMENT.value,
        "team_lead": CategoryEnum.MANAGEMENT.value,
        "leadership": CategoryEnum.MANAGEMENT.value,
        "business_analyst": CategoryEnum.ANALYTICS.value,
        "system_analyst": CategoryEnum.ANALYTICS.value,
        "systems_analyst": CategoryEnum.ANALYTICS.value,
        "product_analyst": CategoryEnum.ANALYTICS.value,
        "analyst": CategoryEnum.ANALYTICS.value,
        "ux": CategoryEnum.DESIGN.value,
        "ui": CategoryEnum.DESIGN.value,
        "ui_ux": CategoryEnum.DESIGN.value,
        "ux_ui": CategoryEnum.DESIGN.value,
        "product_design": CategoryEnum.DESIGN.value,
        "product_designer": CategoryEnum.DESIGN.value,
        "graphic_design": CategoryEnum.DESIGN.value,
        "motion_design": CategoryEnum.DESIGN.value,
        "cybersecurity": CategoryEnum.SECURITY.value,
        "information_security": CategoryEnum.SECURITY.value,
        "infosec": CategoryEnum.SECURITY.value,
        "soc": CategoryEnum.SECURITY.value,
        "customer_support": CategoryEnum.SUPPORT.value,
        "technical_support": CategoryEnum.SUPPORT.value,
        "helpdesk": CategoryEnum.SUPPORT.value,
        "service_desk": CategoryEnum.SUPPORT.value,
        "smm": CategoryEnum.MARKETING.value,
        "performance_marketing": CategoryEnum.MARKETING.value,
        "digital_marketing": CategoryEnum.MARKETING.value,
        "growth": CategoryEnum.MARKETING.value,
        "sales_manager": CategoryEnum.SALES.value,
        "business_development": CategoryEnum.SALES.value,
        "account_executive": CategoryEnum.SALES.value,
        "recruiting": CategoryEnum.HR.value,
        "recruiter": CategoryEnum.HR.value,
        "talent_acquisition": CategoryEnum.HR.value,
        "accounting": CategoryEnum.FINANCE.value,
        "accountant": CategoryEnum.FINANCE.value,
        "financial_analyst": CategoryEnum.FINANCE.value,
        "finops": CategoryEnum.FINANCE.value,
    }
    if normalized in alias_map:
        return alias_map[normalized]

    contains_map = [
        (["backend", "frontend", "fullstack", "mobile", "software", "developer", "programmer", "java", "python", "golang", "php", "dotnet", "csharp", "react", "angular", "vue"], CategoryEnum.SOFTWARE_ENGINEERING.value),
        (["data", "ml", "machine_learning", "ai", "analytics_engineer", "bi"], CategoryEnum.DATA.value),
        (["qa", "test", "testing", "sdet"], CategoryEnum.QA.value),
        (["devops", "sre", "platform", "cloud", "infra", "infrastructure"], CategoryEnum.DEVOPS.value),
        (["product"], CategoryEnum.PRODUCT.value),
        (["manager", "lead", "delivery"], CategoryEnum.MANAGEMENT.value),
        (["analyst", "analysis"], CategoryEnum.ANALYTICS.value),
        (["design", "designer", "ux", "ui"], CategoryEnum.DESIGN.value),
        (["security", "cyber", "infosec"], CategoryEnum.SECURITY.value),
        (["support", "helpdesk", "service_desk"], CategoryEnum.SUPPORT.value),
        (["marketing", "smm", "growth"], CategoryEnum.MARKETING.value),
        (["sales", "business_development"], CategoryEnum.SALES.value),
        (["hr", "recruit"], CategoryEnum.HR.value),
        (["finance", "account", "finops"], CategoryEnum.FINANCE.value),
    ]
    for terms, canonical in contains_map:
        if any(term in normalized for term in terms):
            return canonical

    return CategoryEnum.OTHER.value


class CategoryEnum(StrEnum):
    DATA = "data"
    SOFTWARE_ENGINEERING = "software_engineering"
    QA = "qa"
    DEVOPS = "devops"
    PRODUCT = "product"
    DESIGN = "design"
    ANALYTICS = "analytics"
    SECURITY = "security"
    MANAGEMENT = "management"
    SUPPORT = "support"
    MARKETING = "marketing"
    SALES = "sales"
    HR = "hr"
    FINANCE = "finance"
    OTHER = "other"
    UNKNOWN = "unknown"


class LevelEnum(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    UNKNOWN = "unknown"


class EmploymentEnum(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class WorkFormatEnum(StrEnum):
    OFFICE = "office"
    REMOTE = "remote"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class EnglishLevelEnum(StrEnum):
    NOT_REQUIRED = "not_required"
    A1 = "a1"
    A2 = "a2"
    B1 = "b1"
    B2 = "b2"
    C1 = "c1"
    C2 = "c2"
    UNKNOWN = "unknown"


class CurrencyEnum(StrEnum):
    KZT = "KZT"
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"
    UNKNOWN = "unknown"


class SalaryPeriodEnum(StrEnum):
    HOUR = "hour"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class VacancyLLMInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    title: Optional[str] = None
    description_clean: str
    parser_hints: Optional[dict] = None


class VacancyExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title_normalized: Optional[str] = None
    company: Optional[str] = None
    city: Optional[str] = None
    category: CategoryEnum = CategoryEnum.UNKNOWN
    level: LevelEnum = LevelEnum.UNKNOWN
    employment: EmploymentEnum = EmploymentEnum.UNKNOWN
    work_format: WorkFormatEnum = WorkFormatEnum.UNKNOWN
    experience_min: Optional[float] = Field(default=None, ge=0)
    experience_max: Optional[float] = Field(default=None, ge=0)
    english_mention: Optional[bool] = None
    english_required: Optional[bool] = None
    english_level: EnglishLevelEnum = EnglishLevelEnum.UNKNOWN
    requirements_clean: Optional[str] = None
    responsibilities_clean: Optional[str] = None
    hard_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    salary_raw: Optional[str] = None
    salary_from: Optional[int] = Field(default=None, ge=0)
    salary_to: Optional[int] = Field(default=None, ge=0)
    currency: CurrencyEnum = CurrencyEnum.UNKNOWN
    salary_period: SalaryPeriodEnum = SalaryPeriodEnum.UNKNOWN
    salary_gross: Optional[bool] = None
    llm_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "title_normalized",
        "company",
        "city",
        "requirements_clean",
        "responsibilities_clean",
        "salary_raw",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_text(value)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value) -> str:
        return _normalize_category_label(value)

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value) -> str:
        if value is None:
            return LevelEnum.UNKNOWN.value
        normalized = str(value).strip().lower().replace(" ", "_")
        return normalized if normalized in LEVEL_VALUES else LevelEnum.UNKNOWN.value

    @field_validator("employment", mode="before")
    @classmethod
    def normalize_employment(cls, value) -> str:
        if value is None:
            return EmploymentEnum.UNKNOWN.value
        normalized = str(value).strip().lower().replace(" ", "_")
        return normalized if normalized in EMPLOYMENT_VALUES else EmploymentEnum.UNKNOWN.value

    @field_validator("work_format", mode="before")
    @classmethod
    def normalize_work_format(cls, value) -> str:
        if value is None:
            return WorkFormatEnum.UNKNOWN.value
        normalized = str(value).strip().lower().replace(" ", "_")
        return normalized if normalized in WORK_FORMAT_VALUES else WorkFormatEnum.UNKNOWN.value

    @field_validator("english_level", mode="before")
    @classmethod
    def normalize_english_level(cls, value) -> str:
        if value is None:
            return EnglishLevelEnum.UNKNOWN.value
        normalized = str(value).strip().lower().replace(" ", "_")
        normalized = {
            "upper-intermediate": "b2",
            "upper_intermediate": "b2",
            "intermediate": "b1",
            "pre-intermediate": "a2",
            "pre_intermediate": "a2",
            "advanced": "c1",
            "elementary": "a2",
            "beginner": "a1",
        }.get(normalized, normalized)
        return normalized if normalized in ENGLISH_LEVEL_VALUES else EnglishLevelEnum.UNKNOWN.value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value) -> str:
        if value is None:
            return CurrencyEnum.UNKNOWN.value
        normalized = str(value).strip().upper()
        normalized = {"POSTGRES": "POSTGRESQL"}.get(normalized, normalized)
        return normalized if normalized in CURRENCY_VALUES else CurrencyEnum.UNKNOWN.value

    @field_validator("hard_skills", "soft_skills", "tech_stack", mode="before")
    @classmethod
    def normalize_list_field(cls, value) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            items = value
        else:
            items = [value]
        cleaned = []
        seen = set()
        for item in items:
            text = _normalize_text(item)
            if not text:
                continue
            key = text.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(text)
        return cleaned

    @field_validator("experience_min", "experience_max", mode="before")
    @classmethod
    def normalize_experience(cls, value):
        if value in (None, "", "null", "None"):
            return None
        return float(value)

    @field_validator("salary_from", "salary_to", mode="before")
    @classmethod
    def normalize_salary(cls, value):
        if value in (None, "", "null", "None"):
            return None
        return int(float(value))

    @field_validator("salary_period", mode="before")
    @classmethod
    def normalize_salary_period(cls, value):
        if value is None:
            return SalaryPeriodEnum.UNKNOWN.value
        normalized = str(value).strip().lower().replace(" ", "_")
        mapping = {
            "час": SalaryPeriodEnum.HOUR.value,
            "в_час": SalaryPeriodEnum.HOUR.value,
            "hour": SalaryPeriodEnum.HOUR.value,
            "hourly": SalaryPeriodEnum.HOUR.value,
            "week": SalaryPeriodEnum.WEEK.value,
            "weekly": SalaryPeriodEnum.WEEK.value,
            "weekend": SalaryPeriodEnum.WEEK.value,
            "month": SalaryPeriodEnum.MONTH.value,
            "monthly": SalaryPeriodEnum.MONTH.value,
            "месяц": SalaryPeriodEnum.MONTH.value,
            "m": SalaryPeriodEnum.MONTH.value,
            "year": SalaryPeriodEnum.YEAR.value,
            "annual": SalaryPeriodEnum.YEAR.value,
            "yearly": SalaryPeriodEnum.YEAR.value,
            "год": SalaryPeriodEnum.YEAR.value,
        }
        return mapping.get(normalized, SalaryPeriodEnum.UNKNOWN.value)

    @field_validator("llm_confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value):
        if value in (None, "", "null", "None"):
            return 0.0
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.0

    @model_validator(mode="after")
    def validate_ranges(self) -> "VacancyExtraction":
        if self.experience_min is not None and self.experience_max is not None:
            if self.experience_min > self.experience_max:
                self.experience_min, self.experience_max = self.experience_max, self.experience_min
        if self.salary_from is not None and self.salary_to is not None:
            if self.salary_from > self.salary_to:
                self.salary_from, self.salary_to = self.salary_to, self.salary_from
        return self


class BatchExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[VacancyExtraction]
