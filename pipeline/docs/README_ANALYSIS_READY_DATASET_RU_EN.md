# Analysis-Ready Dataset Guide / Руководство по Analysis-Ready датасету

## 1. Purpose / Назначение

**RU**

Этот файл описывает итоговый curated dataset `data/final/analysis_ready_jobs.csv`, построенный поверх `data/interim/enriched_jobs_full_v1.csv`.
Его задача:

- объяснить логику всего датасета;
- показать разницу между raw/enriched и curated слоями;
- задокументировать все колонки;
- помочь безопасно использовать датасет в Streamlit, ноутбуках и аналитических витринах.

Главный принцип слоя:

- мы **не фабрикуем факты**;
- мы **не затираем исходные поля**;
- мы добавляем новые `*_clean`, `*_norm`, `*_filled`, `*_source_v2`, `*_confidence_v2`, `*_flag` поля;
- каждая новая логика по возможности traceable.

**EN**

This file documents the final curated dataset `data/final/analysis_ready_jobs.csv`, built on top of `data/interim/enriched_jobs_full_v1.csv`.
Its purpose is to:

- explain the full dataset logic;
- clarify the difference between the raw/enriched layer and the curated analytical layer;
- document every column;
- help analysts use the dataset safely in Streamlit, notebooks, and marts.

Core principle:

- we **do not fabricate facts**;
- we **do not overwrite raw source fields blindly**;
- we add new `*_clean`, `*_norm`, `*_filled`, `*_source_v2`, `*_confidence_v2`, and `*_flag` fields;
- every enrichment step should stay as traceable as possible.

---

## 2. Files / Файлы

**Main outputs / Основные выходы**

- `data/final/analysis_ready_jobs.csv`
- `data/final/analysis_ready_jobs_salary_fixed_v3.csv`
- `data/final/jobs_salary_clean_v3.csv`
- `data/final/jobs_skills_clean.csv`
- `data/final/jobs_entity_clean.csv`
- `data/final/salary_manual_review_cases_v3.csv`
- `data/reports/data_quality_report.json`
- `docs/reports/data_quality_report.md`
- `data/reports/header_parse_audit.json`
- `docs/reports/header_parse_audit.md`
- `data/reports/still_bad_rows.csv`

**Recommended usage / Рекомендуемое использование**

- Use `data/final/analysis_ready_jobs_salary_fixed_v3.csv` as the main dashboard dataset.
- Use `data/final/analysis_ready_jobs.csv` as the pre-repair curated baseline.
- Use `data/final/jobs_skills_clean.csv` for skill frequency, trend, and co-occurrence analysis.
- Use `data/final/jobs_salary_clean_v3.csv` for salary analytics after the repaired salary pipeline.
- Use `data/final/salary_manual_review_cases_v3.csv` as a manual-review queue for ambiguous salary rows.
- Use `data/final/jobs_entity_clean.csv` for employer/title/category summaries.

---

## 3. Dataset Logic / Логика датасета

**RU**

Датасет устроен как многослойная таблица:

1. `raw source fields`
   это поля, пришедшие из HH, Telegram, Kolesa, Kaspi и предыдущего LLM pipeline.

2. `enriched fields`
   это поля после первичного LLM enrichment: `title_normalized`, `category`, `level`, `requirements_clean`, `hard_skills` и др.

3. `curated analytical fields`
   это наши новые поля:
   `description_clean_v2`, `salary_*_clean`, `*_norm`, `*_filled`, `*_source_v2`, `quality_tier`, `usable_for_*`.

4. `audit and provenance fields`
   это поля, которые помогают понять происхождение и качество значений:
   `llm_confidence`, `llm_merge_status`, `review_flags`, `final_field_sources`, `header_parse_pattern` и др.

**EN**

The dataset is intentionally layered:

1. `raw source fields`
   values originally coming from HH, Telegram, Kolesa, Kaspi, and the previous LLM pipeline.

2. `enriched fields`
   values produced by the initial LLM enrichment stage:
   `title_normalized`, `category`, `level`, `requirements_clean`, `hard_skills`, etc.

3. `curated analytical fields`
   new fields added in the analytical preparation stage:
   `description_clean_v2`, `salary_*_clean`, `*_norm`, `*_filled`, `*_source_v2`, `quality_tier`, `usable_for_*`.

4. `audit and provenance fields`
   fields used to understand data origin and quality:
   `llm_confidence`, `llm_merge_status`, `review_flags`, `final_field_sources`, `header_parse_pattern`, etc.

---

## 4. Recommended Dashboard Filters / Рекомендуемые фильтры для дашборда

**RU**

- Общий рынок:
  `dedup_keep_for_analytics=True`
- Категории:
  `usable_for_category_analytics=True`
- Навыки:
  `usable_for_skill_analytics=True`
- Работодатели:
  `usable_for_employer_analytics=True`
- Зарплаты:
  `usable_for_salary_analytics=True`
- Для консервативной salary analytics:
  `source in ['hh_kz', 'kaspi_jobs', 'kolesa_jobs']`
- Консервативный high-quality режим:
  `quality_tier in ['A', 'B']`

**EN**

- Market overview:
  `dedup_keep_for_analytics=True`
- Category analytics:
  `usable_for_category_analytics=True`
- Skill analytics:
  `usable_for_skill_analytics=True`
- Employer analytics:
  `usable_for_employer_analytics=True`
- Salary analytics:
  `usable_for_salary_analytics=True`
- Conservative salary analytics:
  `source in ['hh_kz', 'kaspi_jobs', 'kolesa_jobs']`
- Conservative high-quality mode:
  `quality_tier in ['A', 'B']`

---

## 5. Column Dictionary / Словарь колонок

Below, each column is documented in bilingual form.

### A. Identity and Source Metadata / Идентификация и метаданные источника

- `id`
  RU: Уникальный идентификатор строки вакансии.
  EN: Unique vacancy row identifier.

- `source`
  RU: Источник записи, например `hh_kz`, `ITcom KZ`, `Work IT KZ`.
  EN: Source system or source channel name, for example `hh_kz`, `ITcom KZ`, `Work IT KZ`.

- `source_id`
  RU: Идентификатор вакансии внутри исходного источника.
  EN: Original source-level identifier.

- `source_url`
  RU: URL вакансии или канала/поста в исходном источнике.
  EN: Original vacancy or channel/post URL.

### B. Raw Role and Employer Fields / Исходные поля роли и работодателя

- `title`
  RU: Сырое название вакансии из источника. Часто пустое для Telegram.
  EN: Raw title from the original source. Often empty for Telegram rows.

- `title_normalized`
  RU: Название вакансии после LLM enrichment. Может быть общим или неполным.
  EN: LLM-enriched normalized title. Can be broad or incomplete.

- `company`
  RU: Исходное поле компании из enriched слоя. Иногда содержит leakage из полного текста поста.
  EN: Original company field from the enriched layer. Sometimes polluted by leaked vacancy text.

- `city`
  RU: Исходное поле города из enriched слоя.
  EN: Original city field from the enriched layer.

- `category`
  RU: Исходная категория вакансии после LLM enrichment.
  EN: Original LLM-enriched vacancy category.

- `level`
  RU: Исходный seniority level после enrichment.
  EN: Original enriched seniority level.

### C. Raw Experience, Employment, Work Format / Исходные поля опыта, занятости и формата

- `experience_raw`
  RU: Сырой текст про опыт работы.
  EN: Raw experience text.

- `experience_min`
  RU: Исходная нижняя граница опыта в годах.
  EN: Original lower bound for experience in years.

- `experience_max`
  RU: Исходная верхняя граница опыта в годах.
  EN: Original upper bound for experience in years.

- `employment`
  RU: Исходный тип занятости.
  EN: Original employment type.

- `work_format`
  RU: Исходный формат работы.
  EN: Original work format.

### D. Raw Salary Fields / Исходные поля зарплаты

- `salary_from`
  RU: Исходная нижняя граница зарплаты до очистки.
  EN: Original salary lower bound before cleaning.

- `salary_to`
  RU: Исходная верхняя граница зарплаты до очистки.
  EN: Original salary upper bound before cleaning.

- `salary_avg`
  RU: Исходная средняя зарплата или производное поле до очистки.
  EN: Original average salary or derived salary field before cleaning.

- `currency`
  RU: Исходная валюта до нормализации.
  EN: Original currency before normalization.

- `salary_raw`
  RU: Исходная строка про зарплату.
  EN: Raw salary text snippet.

- `salary_gross`
  RU: Признак gross/net, если был извлечён ранее.
  EN: Gross/net indicator when previously extracted.

### E. Raw Description and Text Blocks / Исходное описание и текстовые блоки

- `description`
  RU: Полный текст вакансии или поста.
  EN: Full raw vacancy or post text.

- `description_clean`
  RU: Старое “очищенное” поле из предыдущего pipeline. Исторически ненадежно.
  EN: Legacy “cleaned” description from the old pipeline. Historically unreliable.

- `requirements_raw`
  RU: Сырой блок требований.
  EN: Raw requirements block.

- `requirements_clean`
  RU: Очищенный/сжатый блок требований после LLM enrichment.
  EN: LLM-cleaned requirements summary.

- `responsibilities_raw`
  RU: Сырой блок обязанностей.
  EN: Raw responsibilities block.

- `responsibilities_clean`
  RU: Очищенный/сжатый блок обязанностей после LLM enrichment.
  EN: LLM-cleaned responsibilities summary.

- `skills_raw`
  RU: Сырой текст навыков, если он был выделен раньше.
  EN: Raw skill text, when available.

### F. Enriched Skill Arrays / Обогащенные массивы навыков

- `hard_skills`
  RU: JSON-строка со списком hard skills из enriched слоя.
  EN: JSON string with hard skills from the enriched layer.

- `soft_skills`
  RU: JSON-строка со списком soft skills из enriched слоя.
  EN: JSON string with soft skills from the enriched layer.

- `tech_stack`
  RU: JSON-строка со списком технологий/стека из enriched слоя.
  EN: JSON string with technology stack items from the enriched layer.

### G. English Fields / Поля по английскому языку

- `english_mention`
  RU: Упоминается ли английский в тексте вакансии.
  EN: Whether English is mentioned in the vacancy text.

- `english_required`
  RU: Требуется ли английский явно.
  EN: Whether English is explicitly required.

- `english_level`
  RU: Исходный уровень английского до нормализации.
  EN: Original English level before normalization.

### H. Time and Status Fields / Поля времени и статуса

- `posted_at`
  RU: Дата публикации вакансии.
  EN: Vacancy publication date.

- `scraped_at`
  RU: Дата/время сбора данных.
  EN: Scraping timestamp.

- `is_active`
  RU: Исторический флаг активности из исходного pipeline.
  EN: Legacy active-status flag from the original pipeline.

### I. Legacy Enrichment Metadata / Исторические метаданные enrichment слоя

- `extraction_method`
  RU: Источник происхождения значения в старом pipeline, например `mixed` или `rule_based`.
  EN: Legacy extraction method, for example `mixed` or `rule_based`.

- `llm_confidence`
  RU: Исходная уверенность LLM в строке/merge.
  EN: Original LLM confidence score.

- `duplicate_hash`
  RU: Исходный duplicate hash из предыдущего pipeline.
  EN: Legacy duplicate hash from the previous pipeline.

- `is_duplicate`
  RU: Исходный duplicate flag из старого dedup-процесса.
  EN: Legacy duplicate flag from the older deduplication pass.

### J. Legacy Parser and Provenance Objects / Исторические parser и provenance-объекты

- `parser_hints`
  RU: JSON-объект с подсказками от Telegram parser.
  EN: JSON object with Telegram parser hints.

- `parser_quality`
  RU: JSON-объект с качеством и confidence parser-полей.
  EN: JSON object with parser confidence/quality metadata.

- `final_field_sources`
  RU: JSON-объект с происхождением полей после старого merge parser + LLM.
  EN: JSON object describing final field sources after the legacy parser + LLM merge.

- `final_field_confidence`
  RU: JSON-объект с confidence по полям после старого merge.
  EN: JSON object with field-level confidence after the legacy merge.

- `review_flags`
  RU: JSON-массив флагов, указывающих на поля, требующие review.
  EN: JSON array of field-level review flags.

- `conflict_flags`
  RU: JSON-массив конфликтующих полей parser vs LLM.
  EN: JSON array of parser-vs-LLM conflict flags.

- `validation_fixes`
  RU: JSON-массив исправлений, примененных старым validation stage.
  EN: JSON array of fixes applied by the legacy validation stage.

### K. Legacy LLM Execution Metadata / Исторические LLM execution-метаданные

- `llm_merge_status`
  RU: Статус merge в старом LLM pipeline.
  EN: Merge status from the old LLM pipeline.

- `llm_model`
  RU: Модель LLM, использованная в старом enrichment run.
  EN: LLM model used in the previous enrichment run.

- `llm_review_flag`
  RU: Флаг, что строка требует review после старого pipeline.
  EN: Flag indicating the row required review in the legacy pipeline.

- `llm_called`
  RU: Вызывался ли LLM для этой строки в старом pipeline.
  EN: Whether an LLM call was made for this row in the legacy pipeline.

- `parser_only`
  RU: Исторический флаг parser-only обработки.
  EN: Legacy parser-only processing flag.

### L. Source Family Flags / Флаги семейства источников

- `is_telegram_source`
  RU: Булев флаг, что строка пришла из Telegram-подобного источника.
  EN: Boolean flag showing that the row comes from a Telegram-like source.

- `is_structured_source`
  RU: Булев флаг, что строка пришла из structured source (`hh_kz`, `kaspi_jobs`, `kolesa_jobs`).
  EN: Boolean flag showing that the row comes from a structured source (`hh_kz`, `kaspi_jobs`, `kolesa_jobs`).

### M. Real Description Cleaning v2 / Настоящая очистка описания v2

- `description_clean_v2`
  RU: Новый очищенный текст вакансии, пригодный для аналитики.
  EN: New cleaned vacancy text intended for analytics.

- `description_clean_changed`
  RU: Было ли описание реально изменено относительно исходного текста.
  EN: Whether the description was actually changed during cleaning.

- `description_clean_len`
  RU: Длина `description_clean_v2`.
  EN: Length of `description_clean_v2`.

- `description_clean_removed_chars`
  RU: Сколько символов было удалено в процессе очистки.
  EN: Number of characters removed during text cleaning.

### N. Header Parsing for Telegram-like Posts / Header parsing для Telegram-подобных постов

- `header_extracted_title`
  RU: Заголовок вакансии, извлеченный специальным header parser.
  EN: Title extracted by the dedicated header parser.

- `header_extracted_company`
  RU: Компания, извлеченная из header-like части поста.
  EN: Company extracted from the header-like part of the post.

- `header_extracted_city`
  RU: Город, извлеченный из header-like части поста.
  EN: City extracted from the header-like part of the post.

- `header_parse_pattern`
  RU: Имя сработавшего шаблона header parser.
  EN: Name of the header parser pattern that matched.

- `header_parse_confidence`
  RU: Confidence header parsing logic.
  EN: Confidence score of the header parsing logic.

### O. Salary Cleaning v2 / Очистка зарплаты v2

- `salary_from_clean`
  RU: Очищенная нижняя граница зарплаты.
  EN: Cleaned lower salary bound.

- `salary_to_clean`
  RU: Очищенная верхняя граница зарплаты.
  EN: Cleaned upper salary bound.

- `salary_avg_clean`
  RU: Очищенная средняя зарплата, вычисляемая только из валидных значений.
  EN: Cleaned average salary calculated only from valid salary bounds.

- `currency_clean`
  RU: Нормализованная валюта после salary cleaning.
  EN: Normalized currency after salary cleaning.

- `salary_parse_quality`
  RU: Качество/режим salary parsing, например `existing_numeric`, `contact_leak`, `parsed_range`.
  EN: Salary parsing quality/mode such as `existing_numeric`, `contact_leak`, or `parsed_range`.

- `salary_is_suspicious`
  RU: Общий флаг подозрительности зарплаты.
  EN: Overall suspicious-salary flag.

- `salary_outlier_flag`
  RU: Флаг зарплатного outlier.
  EN: Salary outlier flag.

- `salary_contact_leak_flag`
  RU: Флаг, что зарплата была загрязнена телефоном/контактами.
  EN: Flag showing that salary was contaminated by phone/contact data.

- `salary_zero_flag`
  RU: Флаг нулевого salary value.
  EN: Flag for zero salary values.

- `salary_usable_for_analytics`
  RU: Можно ли использовать salary block для аналитики в принципе.
  EN: Whether the salary block is analytically usable at the row level.

- `salary_fix_flags`
  RU: JSON-массив примененных salary-fix правил.
  EN: JSON array of salary-fix rules applied to the row.

- `salary_parse_source`
  RU: Из какого источника/блока был прочитан salary candidate.
  EN: Source block from which the salary candidate was parsed.

**Additional salary review fields in `analysis_ready_jobs_salary_fixed_v3.csv` / Дополнительные salary review поля в `analysis_ready_jobs_salary_fixed_v3.csv`**

- `salary_period`
  RU: Определенный период зарплаты: `hour`, `day`, `month`, `year` или `null`.
  EN: Detected salary period: `hour`, `day`, `month`, `year`, or `null`.

- `salary_source_basis_v2`
  RU: Какой источник был выбран для финальной salary логики: `text_parsed`, `existing_numeric_fallback`, `manual_review_queue`, `missing`.
  EN: Which source won in the final salary logic: `text_parsed`, `existing_numeric_fallback`, `manual_review_queue`, or `missing`.

- `salary_source_conflict_flag`
  RU: Флаг сильного конфликта между legacy numeric salary и новым text parsing.
  EN: Flag for a strong conflict between legacy numeric salary fields and the new text parsing result.

- `salary_manual_review_flag`
  RU: Флаг, что строка вынесена в ручной salary review.
  EN: Flag showing that the row was moved into manual salary review.

- `salary_manual_review_category`
  RU: Причина ручного review, например `too_many_amounts`, `source_conflict_major`, `multi_variant_compensation`.
  EN: Reason for manual review, for example `too_many_amounts`, `source_conflict_major`, or `multi_variant_compensation`.

- `salary_from_candidate_v2`
  RU: Кандидат на нижнюю границу зарплаты, найденный новым parser до финального решения.
  EN: Candidate lower salary bound found by the new parser before the final decision step.

- `salary_to_candidate_v2`
  RU: Кандидат на верхнюю границу зарплаты, найденный новым parser до финального решения.
  EN: Candidate upper salary bound found by the new parser before the final decision step.

### P. Normalized Categorical Fields / Нормализованные категориальные поля

- `english_level_norm`
  RU: Нормализованный уровень английского (`a1`...`c2`, `not_required`).
  EN: Normalized English level (`a1`...`c2`, `not_required`).

- `english_level_invalid_flag`
  RU: Флаг, что исходное значение `english_level` было вне допустимого enum.
  EN: Flag showing that the original `english_level` value was outside the expected enum.

- `category_norm`
  RU: Нормализованная версия исходного `category`.
  EN: Normalized version of the original `category`.

- `level_norm`
  RU: Нормализованная версия исходного `level`.
  EN: Normalized version of the original `level`.

- `employment_norm`
  RU: Нормализованная версия исходного `employment`.
  EN: Normalized version of the original `employment`.

- `work_format_norm`
  RU: Нормализованная версия исходного `work_format`.
  EN: Normalized version of the original `work_format`.

- `city_norm`
  RU: Нормализованный город/локация.
  EN: Normalized city/location field.

- `city_source_v2`
  RU: Источник `city_norm`: существующее значение или backfill из header parser.
  EN: Source of `city_norm`: existing value or header-parser backfill.

### Q. Title Finalization / Финализация title

- `title_clean`
  RU: Базовая очистка исходного `title`.
  EN: Basic cleanup of the original `title`.

- `title_final`
  RU: Итоговое поле title для аналитики.
  EN: Final title field recommended for analytics.

- `title_is_inferred`
  RU: Был ли title получен не напрямую из исходного `title`, а через fallback/backfill.
  EN: Whether the title was inferred via fallback/backfill rather than copied directly from the original `title`.

- `title_source_v2`
  RU: Источник `title_final`: `raw_title`, `title_normalized`, `header_parse`, `description_rule`, `missing`.
  EN: Source of `title_final`: `raw_title`, `title_normalized`, `header_parse`, `description_rule`, `missing`.

### R. Company Finalization / Финализация company

- `company_clean`
  RU: Итоговое очищенное название компании для аналитики.
  EN: Final cleaned company name for analytics.

- `company_is_suspicious`
  RU: Флаг, что компания выглядит как текстовый leakage, promo-блок или невалидная сущность.
  EN: Flag showing that the company value looks like leaked text, promo content, or an invalid entity.

- `company_source_v2`
  RU: Источник `company_clean`: existing cleaned field, `header_parse`, `missing`, `dropped_suspicious`.
  EN: Source of `company_clean`: existing cleaned field, `header_parse`, `missing`, or `dropped_suspicious`.

### S. Clean Skill and Stack Fields / Очищенные поля навыков и стека

- `hard_skills_clean`
  RU: JSON-строка с canonicalized hard skills.
  EN: JSON string with canonicalized hard skills.

- `soft_skills_clean`
  RU: JSON-строка с canonicalized soft skills.
  EN: JSON string with canonicalized soft skills.

- `tech_stack_clean`
  RU: JSON-строка с canonicalized tech stack.
  EN: JSON string with canonicalized tech stack.

- `skills_all_clean`
  RU: Объединенный JSON-список всех очищенных skills и stack items.
  EN: Combined JSON list of all cleaned skills and stack items.

- `skills_count`
  RU: Количество уникальных очищенных skills в строке.
  EN: Number of unique cleaned skills in the row.

- `top_skill_family`
  RU: Главная skill family для строки, например `data_and_backend`, `frontend_and_web`, `devops_and_cloud`.
  EN: Top skill family for the row, for example `data_and_backend`, `frontend_and_web`, or `devops_and_cloud`.

### T. Category and Level Backfill / Backfill категорий и уровней

- `category_filled`
  RU: Итоговая категория для аналитики после использования исходного значения и rule-based backfill.
  EN: Final category for analytics after combining original values with rule-based backfill.

- `category_source_v2`
  RU: Источник `category_filled`: `existing_valid`, `rule_based_high`, `rule_based_medium`, `unresolved`.
  EN: Source of `category_filled`: `existing_valid`, `rule_based_high`, `rule_based_medium`, or `unresolved`.

- `category_confidence_v2`
  RU: Confidence итоговой category логики.
  EN: Confidence score for the final category logic.

- `level_filled`
  RU: Итоговый seniority level для аналитики.
  EN: Final seniority level for analytics.

- `level_source_v2`
  RU: Источник `level_filled`: `existing_valid`, `title_rule_high`, `text_rule_medium`, `experience_rule_medium`, `unresolved`.
  EN: Source of `level_filled`: `existing_valid`, `title_rule_high`, `text_rule_medium`, `experience_rule_medium`, or `unresolved`.

- `level_confidence_v2`
  RU: Confidence итоговой level логики.
  EN: Confidence score for the final level logic.

### U. Internship Logic / Логика internship

- `internship_flag_v2`
  RU: Общий флаг, что строка выглядит internship-like.
  EN: General flag indicating that the row looks internship-like.

- `internship_consistency_flag`
  RU: Проверка согласованности между `employment_norm` и `level_filled` для internship кейсов.
  EN: Consistency check between `employment_norm` and `level_filled` for internship-like rows.

### V. Second-Pass Deduplication / Dedup второго прохода

- `dedup_key_v2`
  RU: Новый аналитический dedup key.
  EN: New analytical deduplication key.

- `same_role_duplicate_group`
  RU: Идентификатор duplicate group, если строка входит в повторяющуюся роль/вакансию.
  EN: Duplicate group identifier if the row belongs to a repeated role/vacancy cluster.

- `is_duplicate_v2`
  RU: Расширенный duplicate flag после второго прохода dedup.
  EN: Extended duplicate flag after the second-pass deduplication logic.

- `dedup_keep_for_analytics`
  RU: Следует ли оставлять строку для аналитики после второго прохода dedup.
  EN: Whether the row should be kept for analytics after second-pass deduplication.

### W. Quality and Usability Layer / Слой качества и аналитической пригодности

- `quality_tier`
  RU: Итоговый tier качества строки: `A`, `B`, `C`, `D`.
  EN: Final row quality tier: `A`, `B`, `C`, or `D`.

- `usable_for_salary_analytics`
  RU: Можно ли использовать строку в salary dashboards.
  EN: Whether the row is safe to use in salary dashboards.

- `usable_for_employer_analytics`
  RU: Можно ли использовать строку в employer/company analytics.
  EN: Whether the row is safe to use in employer/company analytics.

- `usable_for_skill_analytics`
  RU: Можно ли использовать строку в skill analytics.
  EN: Whether the row is safe to use in skill analytics.

- `usable_for_category_analytics`
  RU: Можно ли использовать строку в category analytics.
  EN: Whether the row is safe to use in category analytics.

---

## 6. What Is Safe to Analyze / Что уже безопасно анализировать

**RU**

Уже можно:

- объем вакансий по источникам;
- распределение по городам;
- распределение по `work_format_norm`;
- broad category analytics по `category_filled`;
- skill analytics по `jobs_skills_clean.csv`;
- employer analytics по `company_clean` с фильтром `usable_for_employer_analytics=True`;
- salary analytics по `data/final/jobs_salary_clean_v3.csv` или `usable_for_salary_analytics=True`.

Пока осторожно:

- английский язык как отдельный рынок-сигнал;
- очень точный salary benchmarking на маленьких срезах;
- fine-grained seniority benchmarking по редким категориям.

**EN**

Safe enough now:

- vacancy volume by source;
- city distribution;
- `work_format_norm` analysis;
- broad category analysis using `category_filled`;
- skill analytics using `jobs_skills_clean.csv`;
- employer analytics using `company_clean` with `usable_for_employer_analytics=True`;
- salary analytics using `data/final/jobs_salary_clean_v3.csv` or `usable_for_salary_analytics=True`.

Still use caution for:

- English-level market analysis;
- highly precise salary benchmarking on small slices;
- fine-grained seniority benchmarking for rare role groups.

---

## 7. Should We Keep a README? / Нужен ли README?

**RU**

Да, отдельный README для curated dataset полезен.
Почему:

- аналитик быстрее понимает, какие колонки использовать;
- Streamlit app легче документировать;
- уменьшается риск, что кто-то возьмет raw поле вместо curated;
- provenance and quality logic становятся прозрачными.

Лучше держать структуру так:

- `README_LLM_INTEGRATION.md` — про старый enrichment pipeline;
- `README_ANALYSIS_READY_DATASET_RU_EN.md` — про финальный аналитический слой.

**EN**

Yes, a dedicated README for the curated dataset is useful.
It helps because:

- analysts quickly understand which columns to use;
- the Streamlit app becomes easier to document;
- it reduces the risk of using raw fields instead of curated ones;
- provenance and quality logic remain transparent.

Recommended split:

- `README_LLM_INTEGRATION.md` — for the legacy enrichment pipeline;
- `README_ANALYSIS_READY_DATASET_RU_EN.md` — for the final analytical layer.

---

## 8. Final Recommendation / Финальная рекомендация

Use `data/final/analysis_ready_jobs_salary_fixed_v3.csv` as the main analytical source, but always apply the use-case-specific flags:

- `dedup_keep_for_analytics`
- `usable_for_salary_analytics`
- `usable_for_employer_analytics`
- `usable_for_skill_analytics`
- `usable_for_category_analytics`
- `quality_tier`

Это лучший способ сохранить максимум аналитической пользы без фабрикации данных.
