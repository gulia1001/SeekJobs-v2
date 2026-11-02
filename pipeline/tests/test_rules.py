"""Rule-based extraction on posts written in the styles of real Kazakhstan IT channels
(company names and contacts are made up)."""
import pytest

from extract.rules import dedup_key, extract_job, find_city, is_vacancy, parse_salary

LABELLED = """Компания: Rocket Labs
Локация: Алматы, удаленка
Вакансия: QA Manual
Грейд: Senior
ЗП: 900к-1млн тенге
Требования:
• от 5 лет опыта
• опыт с Postman и SQL

Откликайтесь @recruiter_demo
#QA #Almaty"""

HASHTAGS = """#астана #cpp

Middle C/C++ developer / Senior C/C++ developer
от 700 000 на руки
г. Астана
TelecomDemo, https://telecom-demo.kz/

Обязанности
- Разработка на C++ под Linux

Требования
- Опыт с Git и Docker"""

EMPLOYER_CHANNEL = """📞 Оператор call-центра | Павлодар

📌 Основные обязанности:
🔹 Консультировать клиентов по продуктам банка

✅ Основные требования:
🎓 Среднее или высшее образование
🗣️ Грамотная речь"""

KAZAKH = """💬 Чат-қолдау операторы | Шымкент

📌 Негізгі міндеттері:
🔹 Клиенттерге кеңес беру

📌 Негізгі талаптар:
🔹 Орта немесе жоғары білім"""

TITLE_WITH_COMPANY = """#алматы #ui #ux

UI/UX Designer в BelesDemo

Работа над интерфейсами цифровых продуктов.
Что предстоит делать:
• Проектировать интерфейсы в Figma
Требования: опыт от 2 лет"""

MULTI = """Открыты позиции в Aitas Demo.

🔹 Системный аналитик 1С (Senior)
Обязателен опыт работы с 1С.

Условия:
удалённо, ГПХ"""

BILINGUAL = """#jobs #Алматы

📍 Формат/working arrangement: офис в Алматы
✔️ Должность/position: Data Engineer
🏢 Место работы/workplace: ТОО «Demo Capital»
💸 Заработная плата/salary: 600 000–800 000 ₸ в месяц, на руки

📈 Обязанности/responsibilities:
— Разрабатывать ETL-пайплайны на Python и SQL"""

COMPANY_SEEKS = """ТОО Fourmi Demo (Алматы) в поисках iOS Senior разработчика

Требования: Swift, SwiftUI, UIKit
Условия: офис, полная занятость"""

COMPANY_MONEY_NOT_SALARY = """Analytics Engineer в Mollie Demo

📍Амстердам
Размер команды — 1k-5k | Инвестиции — $940, оценка компании — $6,5B
Требования: SQL, Python. Откликайтесь в личку"""


def test_labelled_post():
    job = extract_job(LABELLED)
    assert job["title"] == "QA Manual"
    assert job["company"] == "Rocket Labs"
    assert job["city"] == "Almaty"
    assert job["work_format"] == "remote"
    assert job["level"] == "senior"
    assert (job["salary_from"], job["salary_to"], job["currency"]) == (900_000, 1_000_000, "KZT")
    assert job["salary_avg"] == 950_000
    assert job["category"] == "qa"
    assert {"Postman", "SQL"} <= set(job["skills"])


def test_hashtag_post():
    job = extract_job(HASHTAGS)
    assert job["title"] == "Middle C/C++ developer / Senior C/C++ developer"
    assert job["company"] == "TelecomDemo"
    assert job["city"] == "Astana"
    assert job["level"] == "middle"
    assert (job["salary_from"], job["salary_to"]) == (700_000, None)
    assert job["category"] == "software_engineering"
    assert {"C++", "Linux", "Git", "Docker"} <= set(job["skills"])


def test_employer_channel_uses_default_company():
    job = extract_job(EMPLOYER_CHANNEL, default_company="Halyk Bank")
    assert (job["title"], job["company"], job["city"], job["category"]) == (
        "Оператор call-центра", "Halyk Bank", "Pavlodar", "support")


def test_kazakh_language_post():
    assert is_vacancy(KAZAKH)
    job = extract_job(KAZAKH)
    assert (job["title"], job["city"], job["category"]) == ("Чат-қолдау операторы", "Shymkent", "support")


def test_company_after_v():
    job = extract_job(TITLE_WITH_COMPANY)
    assert (job["title"], job["company"], job["category"]) == ("UI/UX Designer", "BelesDemo", "design")
    assert {"Figma", "UI/UX"} <= set(job["skills"])


def test_post_listing_positions():
    job = extract_job(MULTI)
    assert job["title"] == "Системный аналитик 1С (Senior)"
    assert job["company"] == "Aitas Demo"
    assert (job["category"], job["level"], job["work_format"]) == ("analytics", "senior", "remote")
    assert job["employment"] == "contract"


def test_bilingual_labels():
    job = extract_job(BILINGUAL)
    assert job["title"] == "Data Engineer"
    assert job["company"] == "ТОО «Demo Capital»"
    assert (job["salary_from"], job["salary_to"]) == (600_000, 800_000)
    assert job["category"] == "data"


def test_company_looking_for():
    job = extract_job(COMPANY_SEEKS)
    assert job["company"] == "ТОО Fourmi Demo"
    assert job["title"].startswith("iOS Senior")
    assert job["level"] == "senior"


def test_company_money_is_not_a_salary():
    job = extract_job(COMPANY_MONEY_NOT_SALARY)
    assert job["salary_avg"] is None
    assert job["company"] == "Mollie Demo"


@pytest.mark.parametrize("text", [LABELLED, HASHTAGS, EMPLOYER_CHANNEL, KAZAKH, TITLE_WITH_COMPANY, MULTI,
                                  BILINGUAL, COMPANY_SEEKS])
def test_vacancies_are_recognized(text):
    assert is_vacancy(text)


@pytest.mark.parametrize("text", [
    "#резюме\nИщу работу Python-разработчиком, опыт 2 года, Алматы. Пишите в личку!",
    "#вакансия закрыта\nДолжность: Java Developer\nКомпания: Demo\nТребования: Java, Spring",
    "29 октября пройдет технологическая конференция Demo Tech. Регистрация открыта, ждем всех!",
    "Подписывайтесь на наш канал — лучшие вакансии каждый день!",
    "кто бы мог подумать, 10к",
])
def test_non_vacancies_are_skipped(text):
    assert not is_vacancy(text)


@pytest.mark.parametrize("text, expected", [
    ("от 700 000 на руки", (700_000, None, "KZT")),
    ("900к-1млн тенге", (900_000, 1_000_000, "KZT")),
    ("$2000-3000", (2_000, 3_000, "USD")),
    ("до 1.5 млн ₸", (None, 1_500_000, "KZT")),
    ("400-500 тыс. тг. на руки", (400_000, 500_000, "KZT")),
    ("500 000 - 800 000 тг gross", (500_000, 800_000, "KZT")),
    ("по договоренности", (None, None, None)),
    ("+7 701 123 45 67", (None, None, None)),
    ("$700M revenue", (None, None, None)),
    ("$100,000 - $350,000", (8_333, 29_167, "USD")),        # US-style yearly salary -> per month
    ("24 000 000 тг в год", (2_000_000, 2_000_000, "KZT")),  # yearly -> per month
    ("1,5 млн тг", (1_500_000, 1_500_000, "KZT")),           # comma as decimal point
    ("$120000/yr", (10_000, 10_000, "USD")),
])
def test_parse_salary(text, expected):
    assert parse_salary(text) == expected


@pytest.mark.parametrize("text, city", [
    ("г. Астана", "Astana"), ("Нур-Султан", "Astana"), ("Алматы, удаленка", "Almaty"),
    ("#алматы", "Almaty"), ("Өскемен", "Ust-Kamenogorsk"), ("Москва", None),
])
def test_find_city(text, city):
    assert find_city(text) == city


def test_level_from_experience_when_title_has_none():
    post = "Python developer\nТребования: опыт работы от 5 лет, Django\nЗП: 1 200 000 ₸"
    assert extract_job(post)["level"] == "senior"


def test_reposts_with_small_title_changes_share_a_dedup_key():
    a = dedup_key("Middle C/C++ developer", "Cuman", "text a")
    b = dedup_key("Middle/Senior C/C++ developer", "Cuman", "text b")
    c = dedup_key("Middle C/C++ developer", "Other Co", "text a")
    assert a == b != c
