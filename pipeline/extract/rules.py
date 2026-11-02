"""Turn a vacancy post (e.g. from Telegram) into job fields with rules — no LLM needed.

Tuned for Kazakhstan IT channels: Russian / Kazakh / English text, hashtags,
"Label: value" lines, emoji bullets. Every field is best effort; unknown -> None / "".
"""
from __future__ import annotations

import hashlib
import re

from extract.skills import COMMON_SKILLS, base_key, find_skills

EXTRACTOR_VERSION = "rules-v1"

# ── text helpers ────────────────────────────────────────────────────────────
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿←-⇿■-◿️‍⃣]+"
)
_BULLET = re.compile(r"^[\s•·▪▫◦●○►▶➤→\-–—*✓✔|]+")
_NUMBERED = re.compile(r"^\d{1,2}[.)]\s+")
_PHONE = re.compile(r"\+?[78][\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")


def clean_line(line: str) -> str:
    line = _EMOJI.sub(" ", line)
    line = _BULLET.sub("", line)
    line = _NUMBERED.sub("", line)
    return " ".join(line.split())


def _lines(text: str) -> list[str]:
    return [clean_line(raw) for raw in text.splitlines()]


def _label(text: str, names: str) -> str | None:
    """Value of a 'Name: value' line, e.g. _label(text, 'компания|company')."""
    # also bilingual labels: "Должность/position: …", "Заработная плата/salary: …"
    m = re.search(rf"(?im)^[^\w\n]*(?:{names})(?:\s*/\s*[\w ]{{1,30}})?\s*[:：]\s*(.+)$", text)
    if not m:
        return None
    value = clean_line(m.group(1))
    return value or None


# ── is it a vacancy? ────────────────────────────────────────────────────────
_JOB_WORDS = re.compile(
    r"(?i)develop|разработ|программист|engineer|инженер|аналитик|analyst|analytics|design|дизайн|"
    r"manager|менеджер|продакт|product|специалист|specialist|тестировщ|\bqa\b|\bswe\b|\bsre\b|devops|"
    r"lead\b|лид\b|архитект|architect|оператор|operator|admin|администратор|consultant|консультант|"
    r"стаж[её]р|intern\b|head of|руководител|owner|scientist|expert|эксперт|аудитор|auditor|"
    r"маркетолог|рекрутер|recruiter|бухгалтер|accountant|преподавател|teacher|instructor|ассистент|"
    r"assistant|координатор|coordinator|мастер|әзірлеуші|маман|\bcto\b|\bcpo\b|\bpm\b|"
    r"\bios\b|android|backend|frontend|full-?stack|golang|flutter"
)
_STRONG_SIGNAL = re.compile(  # each one alone makes a post very likely a vacancy
    r"(?im)#(?:вакансия|вакансии|vacancy|jobs?|hiring)\b|^[^\w\n]*(?:вакансия|позиция|должность|position|role|vacancy)\s*[:：]"
)
_VACANCY_SIGNALS = re.compile(
    r"(?i)ваканси|vacanc|hiring|ищем|ищу\b|ищет\b|ищут\b|требуется|требуются|в поиске|приглашаем|"
    r"в команду|join (?:our|the) team|стажировк|internship|"
    r"обязанност|задачи|что предстоит|чем (?:предстоит|будешь)|what you(?:'ll| will) do|"
    r"требовани|кого (?:ищем|ищут)|мы ж[её]дем|responsibilit|requirement|"
    r"условия|мы предлагаем|we offer|\bзп\b|з/п|зарплат|заработн|salary|оклад|оплата|"
    r"откликайтесь|отклик|присылайте|пишите|apply|careers|грейд|\bопыт|years of experience|"
    r"талаптар|міндеттер|жалақы"
)
_NOT_VACANCY = re.compile(
    r"(?i)#резюме|#ищу\b|#cv\b|#resume|ищу работу|ищу вакансию|ищу позицию|рассмотрю предложения|"
    r"looking for (?:a )?(?:job|position)|open to work|"
    r"ваканси\w*\s+закрыт|позиция закрыта|#закрыт|vacancy (?:is )?closed|position (?:is )?(?:closed|filled)"
)
_EVENT = re.compile(r"(?i)конференц|meetup|митап|хакатон|hackathon|вебинар|webinar|мероприят|ивент|спикер|рубрика")


def is_vacancy(text: str) -> bool:
    """Points for hiring signals; not a job seeker's CV, a closed vacancy, or an event announcement."""
    if len(text) < 60 or _NOT_VACANCY.search(text):
        return False
    score = 2 * bool(_STRONG_SIGNAL.search(text))
    score += len({m.group(0).lower()[:6] for m in _VACANCY_SIGNALS.finditer(text)})
    head = "\n".join(text.splitlines()[:4])
    score += bool(_JOB_WORDS.search(head))
    if _EVENT.search(head) and not _STRONG_SIGNAL.search(text):  # event is the headline, not a perk
        score -= 2
    return score >= 3


# ── city ────────────────────────────────────────────────────────────────────
_CITIES = {
    "Almaty": r"алмат\w*|алма-ат\w*|almaty",
    "Astana": r"астан\w*|нур-султан\w*|нурсултан\w*|astana|nur-sultan",
    "Shymkent": r"шымкент\w*|shymkent",
    "Karaganda": r"караганд\w*|қарағанд\w*|karagand\w*",
    "Aktobe": r"актобе|ақтөбе|aktobe",
    "Atyrau": r"атырау|atyrau",
    "Aktau": r"актау|ақтау|aktau",
    "Pavlodar": r"павлодар\w*|pavlodar",
    "Ust-Kamenogorsk": r"усть-каменогорск\w*|өскемен|оскемен|oskemen|ust-kamenogorsk",
    "Semey": r"семей|семипалатинск\w*|semey",
    "Kostanay": r"костанай|қостанай|kostanay",
    "Taraz": r"тараз\w*|taraz",
    "Kyzylorda": r"кызылорд\w*|қызылорд\w*|kyzylorda",
    "Petropavl": r"петропавл\w*|petropavl\w*",
    "Oral": r"уральск\w*|орал|oral",
    "Taldykorgan": r"талдыкорган\w*|талдықорған|taldykorgan",
    "Turkestan": r"туркестан\w*|түркістан|turkestan",
    "Kokshetau": r"кокшетау|көкшетау|kokshetau",
    "Ekibastuz": r"экибастуз\w*|ekibastuz",
    "Tashkent": r"ташкент\w*|tashkent",
    "Bishkek": r"бишкек\w*|bishkek",
}
_CITY_RE = {name: re.compile(rf"(?i)(?<![\w-])(?:{pattern})(?![\w-])") for name, pattern in _CITIES.items()}


def find_city(text: str) -> str | None:
    """Earliest city mentioned in the text."""
    best: tuple[int, str] | None = None
    for name, rx in _CITY_RE.items():
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


# ── salary ──────────────────────────────────────────────────────────────────
_SALARY_LABEL = (r"зп|з/п|зарплата|заработная плата|оклад|оплата|оплата труда|доход|вознаграждение|бюджет|"
                 r"ставка|salary|compensation|pay|жалақы")
_SALARY_WORDS = re.compile(rf"(?i)(?<!\w)(?:{_SALARY_LABEL}|на руки|\bnet\b|gross|гросс)(?!\w)")
_NUM = r"\d[\d  .,]*\s*(?:тыс\.?|млн|mln|k|к)?"
# an amount (or range) written right next to a currency: "500 000 ₸", "$2000-3000", "от 900к тенге"
_MONEY = re.compile(
    rf"(?i)(?:(?:от|до|from|up to)\s*)?(?:"
    rf"[$€₸]\s*{_NUM}(?:\s*[-–—]\s*[$€₸]?\s*{_NUM})?"
    rf"|{_NUM}(?:\s*[-–—]\s*(?:до\s*)?{_NUM})?\s*(?:₸|тг\b|тенге|kzt|\$|usd|долл\w*|€|eur|евро|₽|руб\w*|rub)"
    rf")"
)
_AMOUNT = re.compile(
    r"(?i)(?P<prefix>\bот|\bдо|\bfrom|\bup to|\bto)?\s*[$€]?\s*"
    r"(?P<num>\d{1,3}(?:[ \u00a0.,]\d{3})+|\d+(?:[.,]\d+)?)\s*"
    r"(?P<mult>тыс\.?|млн|mln|млрд|bn\b|k\b|к\b|к(?=[\s\-–—])|m\b|b\b)?"
)
# lines about the company's money, not the salary ("Инвестиции — $940", "$700M revenue")
_NOT_SALARY = re.compile(
    r"(?i)инвестиц|оценк\w* компании|valuation|revenue|выручк|оборот|раунд|\barr\b|капитализац|"
    r"размер команды|пользовател|users"
)
_YEARLY = re.compile(r"(?i)в год|/\s*год|годов\w*|per year|/\s*y(?:ea)?r\b|a year|annual\w*|per annum")
_LIMITS = {"KZT": (50_000, 30_000_000), "USD": (200, 50_000), "EUR": (200, 50_000), "RUB": (10_000, 5_000_000)}


def _currency(text: str) -> str | None:
    t = text.lower()
    if "$" in t or "usd" in t or "долл" in t:
        return "USD"
    if "€" in t or "eur" in t or "евро" in t:
        return "EUR"
    if "₽" in t or "руб" in t or "rub" in t:
        return "RUB"
    if "₸" in t or re.search(r"\bтг\b|тенге|kzt", t):
        return "KZT"
    return None


def parse_salary(text: str) -> tuple[float | None, float | None, str | None]:
    """'от 700 000 на руки' -> (700000, None, 'KZT'); '900к-1млн тенге' -> (900000, 1000000, 'KZT').
    Returns (None, None, None) when there is no believable monthly salary."""
    text = _PHONE.sub(" ", text)
    # "400-500 тыс" -> "400 тыс - 500 тыс": the unit belongs to both ends of the range
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*([-–—])\s*(\d+(?:[.,]\d+)?)\s*(тыс\.?|млн|k|к)(?![а-яa-z])",
                  r"\1 \4 \2 \3 \4", text, flags=re.IGNORECASE)
    amounts: list[tuple[str, float]] = []
    for m in _AMOUNT.finditer(text):
        raw = m.group("num")
        if re.fullmatch(r"\d{1,3}(?:[ \u00a0.,]\d{3})+", raw):
            value = float(re.sub(r"[ \u00a0.,]", "", raw))
        else:
            value = float(raw.replace(",", "."))
        mult = (m.group("mult") or "").lower()
        if mult.startswith(("тыс", "k", "к")):
            value *= 1_000
        elif mult in ("млн", "mln", "m"):
            value *= 1_000_000
        elif mult in ("млрд", "bn", "b"):
            value *= 1_000_000_000  # company money, never a salary — dropped by the limits below
        amounts.append(((m.group("prefix") or "").lower(), value))

    currency = _currency(text)
    if currency is None and amounts and max(v for _, v in amounts) >= 30_000:
        currency = "KZT"
    if currency is None:
        return None, None, None
    low, high = _LIMITS[currency]
    # yearly salaries -> monthly ("в год", "per year", or US-style "$100,000 - $350,000")
    yearly = _YEARLY.search(text) or (
        currency in ("USD", "EUR") and amounts and all(high < v <= 1_200_000 for _, v in amounts))
    if yearly:
        amounts = [(p, round(v / 12)) for p, v in amounts]
    amounts = [(p, v) for p, v in amounts if low <= v <= high]
    if not amounts:
        return None, None, None
    if len(amounts) >= 2:
        values = sorted(v for _, v in amounts[:2])
        return values[0], values[1], currency
    prefix, value = amounts[0]
    if prefix in ("до", "up to", "to"):
        return None, value, currency
    if prefix in ("от", "from"):
        return value, None, currency
    return value, value, currency


def find_salary(text: str) -> tuple[float | None, float | None, str | None]:
    """Salary from (1) a 'ЗП: …' line, (2) a line with a pay word ('на руки', 'оклад'),
    (3) an amount written next to a currency anywhere — never from random numbers."""
    labelled = _label(text, _SALARY_LABEL)
    if labelled:
        result = parse_salary(labelled)
        if result[2]:
            return result
    lines = [ln for ln in text.splitlines() if not _NOT_SALARY.search(ln)]
    for line in lines:
        if _SALARY_WORDS.search(line):
            result = parse_salary(line)
            if result[2]:
                return result
    for m in _MONEY.finditer(_PHONE.sub(" ", "\n".join(lines))):
        result = parse_salary(m.group(0))
        if result[2]:
            return result
    return None, None, None


# ── level ───────────────────────────────────────────────────────────────────
_LEVELS = [
    ("intern", r"intern\w*|стаж[её]р\w*|стажировк\w*|trainee|практикант\w*"),
    ("junior", r"junior|джун\w*|младш\w*|кіші"),
    ("middle", r"middle|мидл\w*|mid"),
    ("senior", r"senior|сеньор\w*|синьор\w*|старш\w*|ведущ\w*|аға"),
    ("lead", r"lead|лид|тимлид\w*|техлид\w*|head of|principal|architect|архитектор\w*"),
    ("manager", r"cto|cpo|cio|director|директор\w*"),
]
_LEVEL_RE = [(lvl, re.compile(rf"(?i)(?<![\w-])(?:{p})(?![\w-])")) for lvl, p in _LEVELS]
_EXPERIENCE = re.compile(
    r"(?i)(?:опыт\w*|experience|стаж)[^\n]{0,40}?(?:от|from|не менее|min(?:imum)?|more than|более)?\s*"
    r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:[-–—]\s*\d+\s*)?(?:год|года|лет|years?|yrs?)"
    r"|(?:от|from)\s*(\d+(?:[.,]\d+)?)\s*\+?\s*(?:год|года|лет|years?)"
)


def find_level(text: str) -> str | None:
    best: tuple[int, str] | None = None
    for level, rx in _LEVEL_RE:
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), level)
    return best[1] if best else None


def find_experience_years(text: str) -> float | None:
    m = _EXPERIENCE.search(text)
    if not m:
        return None
    return float((m.group(1) or m.group(2)).replace(",", "."))


def level_from_experience(years: float | None) -> str | None:
    if years is None:
        return None
    if years >= 5:
        return "senior"
    if years >= 3:
        return "middle"
    return "junior"


# ── category ────────────────────────────────────────────────────────────────
_CATEGORIES = [
    ("qa", r"\bqa\b|\baqa\b|тестировщ|tester|test(?:ing)? engineer|sdet|quality assurance"),
    ("security", r"secur|безопасн|\bиб\b|кибер|pentest|пентест|\bsoc\b|siem|red team|blue team"),
    ("devops", r"devops|\bsre\b|site reliability|platform engineer|системн\w* администратор|сисадмин|"
               r"system administrator|cloud engineer|инфраструктур|database administrator|\bdba\b|"
               r"администратор баз"),
    ("data", r"data scien|data engineer|дата[- ]?сайен|\bml\b|machine learning|машинн\w* обуч|"
             r"\bai\b[- ]?(?:engineer|инженер|developer|разработчик)|mlops|\bnlp\b|computer vision|deep learning|"
             r"big data|\bllm\b|scientist"),
    ("analytics", r"analyst|analytics|аналитик|\bbi\b|power bi|tableau"),
    ("design", r"design|дизайн|\bui\b|\bux\b"),
    ("product", r"product manager|product owner|продакт|продуктов\w* менеджер|\bcpo\b"),
    ("software_engineering", r"develop|разработчик|разработк|программист|backend|frontend|front-end|back-end|"
                             r"full-?stack|фулстек|mobile|\bios\b|android|flutter|\b1[сc]\b|golang|\bjava\b|python|"
                             r"\bphp\b|\.net|react|\bvue\b|node|software engineer|\bswe\b|инженер-программист|"
                             r"әзірлеуші"),
    ("management", r"project manager|project\s+менеджер|проджект|проектн\w* менеджер|менеджер проект|руководител\w* проект|"
                   r"delivery manager|scrum master|agile|\bcto\b|head of|руководител\w*|team ?lead|тимлид|\bpm\b"),
    ("support", r"support|поддержк|оператор|call-?центр|helpdesk|service desk|қолдау"),
    ("marketing", r"marketing|маркетолог|маркетинг|\bsmm\b|\bseo\b|контент|content"),
    ("sales", r"sales|продаж|relationship manager|account manager|business development|по работе с клиентами"),
    ("hr", r"\bhr\b|recruit|рекрут|подбор персонала|talent"),
    ("finance", r"accountant|бухгалтер|финанс|finance|экономист|аудит"),
]
_CATEGORY_RE = [(cat, re.compile(rf"(?i){p}")) for cat, p in _CATEGORIES]


def find_category(title: str, text: str) -> str:
    """Rules on the title first (most reliable), then the start of the post."""
    for scope in (title, text[:400]):
        for cat, rx in _CATEGORY_RE:
            if scope and rx.search(scope):
                return cat
    return "other"


# ── work format & employment ────────────────────────────────────────────────
def find_work_format(text: str) -> str:
    t = text.lower()
    if re.search(r"гибрид|hybrid", t):
        return "hybrid"
    if re.search(r"удал[её]н|удаленк|удалёнк|remote|дистанц|из дома|work from home", t):
        return "remote"
    if re.search(r"\bофис|в офисе|office|on-?site|оффлайн", t):
        return "office"
    return ""


def find_employment(text: str) -> str:
    t = text.lower()
    if re.search(r"стажировк|internship", t):
        return "internship"
    if re.search(r"частичн\w* занятост|part[- ]?time|неполн\w* (?:день|занятост)", t):
        return "part_time"
    if re.search(r"проектн|контракт|contract|freelance|фриланс|гпх", t):
        return "contract"
    if re.search(r"полн\w* занятост|full[- ]?time|полный день|5/2", t):
        return "full_time"
    return ""


# ── title & company ─────────────────────────────────────────────────────────
_TITLE_LABEL = r"вакансия|позиция|должность|position|role|vacancy|job title"
_OTHER_LABELS = re.compile(
    r"(?i)^(?:компания|company|работодатель|город|city|локация|location|зп|з/п|зарплата|salary|оклад|"
    r"оплата|формат|format|грейд|grade|уровень|level|опыт|experience|занятость|employment|график|schedule|"
    r"контакты|contacts?|telegram|тг|резюме|cv|откликайтесь|отклик|пишите|писать|стек|stack|"
    r"требования|обязанности|условия|описание)\b\s*[:：]?"
)
_GENERIC_LINE = re.compile(
    r"(?i)^(?:#\S+\s*)+$"                                       # only hashtags
    r"|^(?:новая |открыта |горящая |срочная |активная )?ваканси[яи]\W*$"
    r"|^vacancy\W*$|^we(?:'|’)?(?:re| are)\s+(?:actively\s+)?hiring\W*$|^hiring\W*$|^job\W*$|^работа\W*$"
    r"|^актуальн|^(?:мы\s+)?ищем\W*$|^всем привет|^привет|^здравствуйте|^добрый день"
    r"|^https?://|^@\w+$"
)
# "ТОО Fourmi LAB в поисках iOS Senior", "Kaspi ищет Python-разработчика"
_COMPANY_SEEKS = re.compile(
    r"(?i)^(?P<company>.{2,50}?)\s+(?:в поисках|ищет|ищут|нанимает|is looking for|is hiring|looking for)\s+(?P<title>.+)$"
)
_SEEK_PREFIX = re.compile(
    r"(?i)^(?:ищем|ищу|ищут|ищет|требуется|требуются|(?:нам\s+)?нужен|(?:нам\s+)?нужна|(?:нам\s+)?нужны|"
    r"в поиске|открыта вакансия|вакансия|"
    r"we(?:'|’)?re looking for|we are looking for|looking for|hiring|we(?:'|’)?re hiring)\s*[:\-–—]?\s+"
)
_TITLE_COMPANY = re.compile(r"^(?P<title>.+?)\s+(?:в|at|@)\s+(?P<rest>.+?)[.!]?$")
_COMPANY_AT_END = re.compile(r"((?:[«\"“]?[A-ZА-ЯЁ0-9][\w&.\-«»\"“”']*)(?:\s+[A-ZА-ЯЁ0-9][\w&.\-«»\"“”']*){0,3})\s*$")
_HIDDEN = re.compile(r"(?i)^(?:скрыт\w*|не указан\w*|конфиденциальн\w*|hidden|confidential|n/?a|-)$")
_TRAILING_HASHTAGS = re.compile(r"(?:(?:^|\s)#\w+)+\s*$")


def _shorten(title: str, limit: int = 90) -> str:
    title = title.strip(" .,:;!-–—")
    if len(title) > 45:  # "ML Engineer — описание компании …" -> "ML Engineer"
        title = re.split(r"\s+[—–-]\s+|\.\s", title, maxsplit=1)[0]
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,(-–—") + "…"


def _clean_company(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"https?://\S+|@\w+|\([^)]*\)", "", value)
    value = re.split(r"\s+[·|•]\s+", value)[0]  # "arqa · Алматы" -> "arqa"
    value = value.strip(" .,:;!()-–—|·")
    # quotes: keep a matched pair (ТОО «Demo»), unwrap «Demo», drop unmatched leftovers
    if len(value) > 2 and value[0] in "«\"“'" and value[-1] in "»\"”'":
        value = value[1:-1]
    if value.count("«") != value.count("»"):
        value = value.replace("«", "").replace("»", "")
    if value.count('"') % 2:
        value = value.replace('"', "")
    value = value.strip()
    if (not value or len(value) > 60 or _HIDDEN.match(value) or find_city(value) == value
            or _JOB_WORDS.search(value)):
        return None
    return value


def split_title_company(line: str) -> tuple[str, str | None]:
    """'UI/UX Designer в BelesAI' -> ('UI/UX Designer', 'BelesAI'). City names are not companies."""
    m = _TITLE_COMPANY.match(line)
    if not m:
        return line, None
    rest = m.group("rest")
    if find_city(rest):  # "Python-разработчик в Алматы" — drop the city, keep the title
        return (m.group("title"), None) if len(rest.split()) <= 2 else (line, None)
    name = _COMPANY_AT_END.search(rest)
    company = _clean_company(name.group(1)) if name else None
    return (m.group("title"), company) if company else (line, None)


def _candidate_lines(text: str) -> list[str]:
    out = []
    for line in _lines(text):
        if not line or len(line) < 3 or _GENERIC_LINE.search(line) or _OTHER_LABELS.search(line):
            continue
        if line.endswith(":"):  # section headers like "Требования:" or "...ищут специалистов:"
            continue
        line = _TRAILING_HASHTAGS.sub("", re.sub(r"^(?:#\w+[\s,]+)+", "", line)).strip()
        if line:
            out.append(line)
        if len(out) == 6:
            break
    return out


def _title_from_line(line: str) -> tuple[str, str | None]:
    """Title and (maybe) company from one line."""
    company = None
    m = _COMPANY_SEEKS.match(line)
    if m and _JOB_WORDS.search(m.group("title")):
        company = _clean_company(m.group("company"))
        line = m.group("title")
    line = _SEEK_PREFIX.sub("", line).lstrip(" |:·•-–—")
    # "Company · Title", "Title | City": keep the part that names a job
    parts = [p.strip() for p in re.split(r"\s+[|·•]\s+", line) if p.strip()]
    if len(parts) > 1:
        job_parts = [p for p in parts if _JOB_WORDS.search(p)]
        if job_parts:
            others = [p for p in parts if p is not job_parts[0]]
            line = job_parts[0]
            if company is None and others and not find_city(others[0]):
                company = _clean_company(others[0])
        else:
            line = parts[0]
    title, in_title_company = split_title_company(line)
    return title, company or in_title_company


def find_title(text: str) -> tuple[str | None, str | None]:
    """(title, company found next to the title). Prefers the first early line that names a job."""
    labelled = _label(text, _TITLE_LABEL)
    if labelled:
        return _shorten(labelled), None
    lines = _candidate_lines(text)
    if not lines:
        return None, None
    best = next((ln for ln in lines if _JOB_WORDS.search(ln)), lines[0])
    title, company = _title_from_line(best)
    title = re.sub(r"\s*\((?:[^)]*(?:алмат|астан|almaty|astana|remote|удал)[^)]*)\)", "", title, flags=re.I)
    if not title.strip() or (find_city(title) and len(title.split()) <= 2):
        return None, None
    return _shorten(title), company


_COMPANY_LABEL = r"компания|company|работодатель|employer|место работы|workplace"
_COMPANY_IN_TEXT = re.compile(
    r"(?:позици\w*|ваканси\w*|команд\w*|стажировк\w*|internship)\s+(?:в|at)\s+(?:компани\w+\s+)?"
    r"([«\"“]?[A-ZА-ЯЁ][\w&.\-«»\"“” ]{1,40}?)(?=[.,!:\n|]|\s+[—–-]|$)"
)
_COMPANY_WITH_SITE = re.compile(r"(?m)^\W*([^\n,:]{2,40}),\s*https?://\S+")


def find_company(text: str, title_company: str | None, default: str = "") -> str | None:
    if default:  # channel of a single employer: only an explicit "Компания:" label overrides it
        return _clean_company(clean_line(_label(text, _COMPANY_LABEL) or "")) or default
    head = "\n".join(text.splitlines()[:8])
    for candidate in (
        _label(text, _COMPANY_LABEL),
        title_company,
        (m.group(1) if (m := _COMPANY_IN_TEXT.search(head)) else None),
        (m.group(1) if (m := _COMPANY_WITH_SITE.search(head)) else None),
    ):
        company = _clean_company(clean_line(candidate)) if candidate else None
        if company:
            return company
    return default or None


# ── put it together ─────────────────────────────────────────────────────────
_LEVEL_WORDS = re.compile(rf"(?i)(?<![\w-])(?:{'|'.join(p for _, p in _LEVELS)})\+?(?![\w-])")


def dedup_key(title: str, company: str | None, text: str) -> str:
    """Same company + same core title = same job, even when reposted in several channels with
    small title changes ('Middle C/C++ developer' vs 'Middle/Senior C/C++ developer').
    Without a company, the post text itself is compared."""
    if company:
        core = [w for w in re.split(r"[\s/,()|]+", _LEVEL_WORDS.sub(" ", title)) if base_key(w)][:2]
        basis = base_key(company)[:40] + "|" + "".join(base_key(w) for w in core)
    else:
        basis = "text:" + base_key(text)[:200]
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def extract_job(text: str, default_company: str = "") -> dict | None:
    """Structured job fields from a vacancy post, or None if no title could be found."""
    title, title_company = find_title(text)
    if not title:
        return None
    city_source = _label(text, r"город|city|локация|location|местоположение") or ""
    city = find_city(city_source) or find_city(title) or find_city(text)
    work_format = find_work_format(_label(text, r"формат|format|формат работы") or "") or find_work_format(text)
    salary_from, salary_to, currency = find_salary(text)
    grade = _label(text, r"грейд|grade|уровень|level") or ""
    experience = find_experience_years(text)
    level = find_level(title) or find_level(grade) or level_from_experience(experience) or find_level(text[:600])
    company = find_company(text, title_company, default_company)

    if salary_from is not None and salary_to is not None:
        salary_avg = (salary_from + salary_to) / 2
    else:
        salary_avg = salary_from if salary_from is not None else salary_to

    return {
        "title": title,
        "company": company,
        "city": city or ("Remote" if work_format == "remote" else None),
        "category": find_category(title, text),
        "level": level or "unknown",
        "work_format": work_format,
        "employment": find_employment(text),
        "salary_from": salary_from,
        "salary_to": salary_to,
        "salary_avg": salary_avg,
        "currency": currency,
        "experience_min": experience,
        "skills": find_skills(text, COMMON_SKILLS, max_skills=25),
        "description": re.sub(r"\n{3,}", "\n\n", text.strip())[:4000],
        "dedup_key": dedup_key(title, company, text),
    }
