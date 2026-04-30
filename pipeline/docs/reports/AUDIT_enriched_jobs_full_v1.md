# Audit: enriched_jobs_full_v1.csv

## Scope

- File: `enriched_jobs_full_v1.csv`
- Generated rows: `16,282`
- Columns: `53`
- Input lineage: `unified_job_database.csv` -> Groq enrichment pipeline -> `enriched_jobs_full_v1.csv`
- Related artifacts used in this audit:
  - `quality_report.json`
  - `enriched_jobs_full_v1.baseline.csv`
  - `job_integration_pipeline.py`
  - `llm/*.py`

## Executive Summary

`enriched_jobs_full_v1.csv` is the strongest dataset in the repository and is the right base for the next stage, but it is not yet analysis-ready without an additional cleanup layer.

Strengths:

- strong row-level coverage for the full corpus: `16,282` rows
- meaningful enrichment gains vs baseline
- high coverage for core analytical fields:
  - `category`: `65.88%`
  - `city`: `64.67%`
  - `employment`: `62.83%`
  - `work_format`: `70.05%`
  - `requirements_clean`: `68.18%`
  - `responsibilities_clean`: `60.29%`
  - `hard_skills`: `62.84%`
  - `salary_raw`: `50.59%`
- all JSON-like audit columns are syntactically parseable

Main risks:

- `category` still missing-like for `5,555` rows
- `level` still missing-like for `10,436` rows
- `31.24%` of rows have `llm_review_flag=True`
- salary extraction contains major Telegram parsing errors, including phone numbers parsed as salaries
- `description_clean` is identical to `description` in all rows, so the “clean” layer is not actually cleaned
- `english_level` mixes uppercase and lowercase enum variants
- some fields contain obvious extraction leakage, especially `company`
- deduplication is only partial and still leaves heavy within-source repetition in several Telegram channels

Bottom line:

- Use this file as the base for the next stage.
- Do not use it directly for final analytics, dashboards, or model training.
- First build a new curated layer: `analysis_ready_jobs.csv`.

## Pipeline Context

From `quality_report.json`:

- total rows: `16,282`
- selected for LLM: `8,912`
- processed rows: `8,798`
- merged rows: `5,648`
- review rows: `3,375`
- failed rows: `118`
- LLM called rows: `8,912`
- skipped low confidence rows: `3,150`
- validation fixes count: `193`

Run metadata:

- mode: `hybrid`
- batch size: `30`
- effective batch size: `5`
- generated at: `2026-04-18T03:35:27.544427+00:00`

## Improvement vs Baseline

Compared with `enriched_jobs_full_v1.baseline.csv`:

- changed rows: `14,569 / 16,282` = `89.48%`

Largest changed columns:

- `llm_merge_status`: `14,569`
- `llm_model`: `14,569`
- `llm_called`: `14,569`
- `llm_confidence`: `13,919`
- `parser_hints`: `11,846`
- `parser_quality`: `11,846`
- `final_field_sources`: `11,846`
- `final_field_confidence`: `11,846`
- `extraction_method`: `11,419`
- `requirements_clean`: `11,101`
- `category`: `10,727`
- `hard_skills`: `10,231`
- `responsibilities_clean`: `9,816`
- `city`: `7,768`
- `employment`: `7,557`

This confirms that `enriched_jobs_full_v1.csv` is the only truly enriched full-run dataset in the project.

## Dataset-Level Health

### Coverage snapshot

- `title_normalized`: `35.28%`
- `company`: `38.08%`
- `city`: `64.67%`
- `category`: `65.88%`
- `level`: `35.90%`
- `employment`: `62.83%`
- `work_format`: `70.05%`
- `experience_min`: `43.44%`
- `experience_max`: `22.16%`
- `requirements_clean`: `68.18%`
- `responsibilities_clean`: `60.29%`
- `hard_skills`: `62.84%`
- `soft_skills`: `30.79%`
- `tech_stack`: `38.09%`
- `salary_raw`: `50.59%`
- `salary_from`: `43.35%`
- `salary_to`: `29.11%`
- `currency`: `48.34%`

### Missingness and uncertainty

- `llm_review_flag=True`: `5,087` rows = `31.24%`
- `llm_called=True`: `14,569` rows = `89.48%`
- `llm_merge_status=auto_merged`: `6,332`
- `llm_merge_status=merged_with_review`: `5,087`
- `llm_merge_status=skipped_low_confidence`: `3,150`
- rows with no LLM call: `1,713`

### Deduplication state

- `is_duplicate=True`: `1,371` rows = `8.42%`
- duplicate groups with `rows > 1`: `919`
- rows participating in duplicate groups: `2,290`
- extra rows beyond first per duplicate group: `1,371`
- cross-source duplicate groups: `307`
- same-source duplicate groups: `612`

This means the duplicate problem is real but not catastrophic. However, it is uneven by source.

## Source Audit

### Source mix

- `Work IT KZ`: `6,898`
- `ITcom KZ`: `3,248`
- `hh_kz`: `2,748`
- `IT Vacancy KZ`: `1,288`
- `Zhumys Bar IT`: `1,208`
- `Halyk Jumys`: `716`
- `kaspi_jobs`: `53`
- `Insfera For You`: `47`
- `kolesa_jobs`: `41`
- `Freedom Broker`: `35`

### Best sources for structured quality

Best:

- `hh_kz`
- `kaspi_jobs`
- `kolesa_jobs`

Why:

- source-native title/company/city data is stronger
- lower duplicate pressure
- fewer raw Telegram artifacts

### Best Telegram sources

Relatively strongest:

- `Work IT KZ`
- `Zhumys Bar IT`
- `IT Vacancy KZ`

### Weakest sources

Weakest:

- `Halyk Jumys`
- `Insfera For You`
- part of `ITcom KZ`

Why:

- high `unknown`
- poor enrichment retention
- more repeated/non-standard posts

### Duplicate rate by source

- `Halyk Jumys`: `42.46%`
- `Zhumys Bar IT`: `18.87%`
- `Work IT KZ`: `9.08%`
- `IT Vacancy KZ`: `7.38%`
- `Insfera For You`: `4.26%`
- `ITcom KZ`: `3.33%`
- `hh_kz`: `0.29%`
- `Freedom Broker`: `0.00%`
- `kaspi_jobs`: `0.00%`
- `kolesa_jobs`: `0.00%`

### Review rate by source

- `hh_kz`: `47.74%`
- `kaspi_jobs`: `41.51%`
- `kolesa_jobs`: `36.59%`
- `IT Vacancy KZ`: `36.02%`
- `Work IT KZ`: `29.33%`
- `Freedom Broker`: `28.57%`
- `Insfera For You`: `27.66%`
- `ITcom KZ`: `24.66%`
- `Zhumys Bar IT`: `23.59%`
- `Halyk Jumys`: `19.83%`

Interpretation:

- high review rate in `hh_kz` is not necessarily bad data; it often means parser and LLM disagree on structured fields
- for Telegram, review flags mostly indicate salary/employment/work-format ambiguity

## Column-by-Column Audit

### 1. Identity and Provenance

#### `id`

- coverage: `100%`
- uniqueness: `100%`
- status: good
- use as primary row key: yes

#### `source`

- coverage: `100%`
- unique values: `10`
- status: good
- note: mixes structured sources and channel-like Telegram sources in one field

#### `source_id`

- coverage: `100%`
- unique non-missing: `16,267`
- duplicate rows by `source_id`: `29`
- status: acceptable but not unique
- issue: source IDs collide across sources, especially HH/Kolesa cases

#### `source_url`

- coverage: `100%`
- unique non-missing: `2,848`
- Telegram rows use channel handles like `@workitkz`
- status: not reliable as a row identifier
- issue: `13,440` Telegram rows reuse channel-level URLs, so uniqueness is very low

### 2. Titles and Company

#### `title`

- coverage: `17.45%`
- missing-like: `13,440`
- status: weak for Telegram-heavy corpus
- issue: most Telegram rows still have `title='unknown'`

#### `title_normalized`

- coverage: `35.28%`
- unique non-missing: `3,056`
- top values:
  - `frontend developer`
  - `java developer`
  - `backend developer`
  - `devops engineer`
  - `qa engineer`
- status: useful but incomplete
- issue: `2,903` rows have `title='unknown'` while `title_normalized` is present, showing the raw title field was not backfilled

#### `company`

- coverage: `38.08%`
- unique non-missing: `3,047`
- top employers:
  - `Kaspi.kz`
  - `Tele2/Altel`
  - `Andersen`
  - `Ptolemay`
- status: medium quality
- issue: `45` rows have suspicious company strings longer than `120` chars
- issue type: extraction leakage from Telegram post body into the company field

### 3. Location and Classification

#### `city`

- coverage: `64.67%`
- values:
  - `almaty`: `7,136`
  - `astana`: `2,782`
  - `other`: `609`
  - `remote`: `3`
- status: good coverage, weak granularity
- issue: `remote` is severely underdetected
- issue: only 4 categories means non-Almaty/non-Astana geography is collapsed too aggressively

#### `category`

- coverage: `65.88%`
- missing-like: `5,555`
- top values:
  - `software_engineering`: `5,590`
  - `analytics`: `770`
  - `data`: `672`
  - `devops`: `636`
  - `management`: `611`
  - `qa`: `550`
- status: strong relative to baseline, still incomplete
- issue: `625` rows have `category='unknown'` while `hard_skills` are present
- issue: new category scheme differs from older pipeline/docs

#### `level`

- coverage: `35.90%`
- missing-like: `10,436`
- values:
  - `middle`: `2,338`
  - `senior`: `2,079`
  - `junior`: `1,208`
  - `intern`: `134`
  - `lead`: `77`
  - `manager`: `10`
- status: weak
- issue: too much `unknown`
- issue: schema drift vs older docs and code, which used `head` instead of `manager`

### 4. Experience

#### `experience_raw`

- coverage: `17.31%`
- top values:
  - `От 3 до 6 лет`
  - `От 1 года до 3 лет`
  - `Более 6 лет`
  - `Нет опыта`
- status: good for structured sources, mostly absent elsewhere

#### `experience_min`

- coverage: `43.44%`
- median: `3`
- p95: `6`
- max: `20`
- status: useful
- issue: one outlier above `15`

#### `experience_max`

- coverage: `22.16%`
- median: `3`
- p95: `6`
- max: `24`
- status: weaker than `experience_min`
- issue: one outlier above `20`
- issue: `12` rows still have invalid min/max ordering even after validation

### 5. Employment and Work Format

#### `employment`

- coverage: `62.83%`
- values:
  - `full_time`: `7,579`
  - `temporary`: `1,265`
  - `internship`: `582`
  - `contract`: `576`
  - `part_time`: `228`
- status: decent
- issue: suspiciously high `temporary`
- issue: employment is one of the most conflict-heavy fields

#### `work_format`

- coverage: `70.05%`
- values:
  - `office`: `5,817`
  - `remote`: `3,406`
  - `hybrid`: `2,182`
- status: one of the strongest fields
- issue: still conflict-heavy in Telegram rows

### 6. Salary Block

#### `salary_from`

- coverage: `43.35%`
- median: `400,000`
- p95: `1,000,000`
- max: `77,783,686,819`
- status: useful but contaminated
- issue: `10` values above `10,000,000`
- issue: `461` zero values

#### `salary_to`

- coverage: `29.11%`
- median: `600,000`
- p95: `1,500,000`
- max: `87,772,596,017`
- status: useful but contaminated
- issue: `25` values above `10,000,000`
- issue: `11` zero values

#### `salary_avg`

- coverage: `46.44%`
- median: `450,000`
- p95: `1,250,000`
- max: `87,770,788,710`
- status: usable only after outlier cleaning
- issue: `31` rows above `10,000,000`

#### `currency`

- coverage: `48.34%`
- values:
  - `KZT`: `6,714`
  - `USD`: `963`
  - `RUB`: `110`
  - `EUR`: `83`
  - `KGS`: `1`
- status: mostly fine
- issue: unexpected `KGS:1`

#### `salary_raw`

- coverage: `50.59%`
- unique non-missing: `4,481`
- status: important but noisy
- issue: phone numbers are frequently parsed as salary
- issue: examples include numbers like `87770788710` and `77783686819`
- issue: top recurring malformed forms include `000 тг`, `000 тенге`, `000тг`

#### `salary_gross`

- coverage: `7.92%`
- values:
  - `False`: `762`
  - `True`: `528`
- status: too sparse for serious use

#### Salary consistency verdict

Good:

- `salary_avg` arithmetic is mostly internally consistent
- almost no `salary_from > salary_to` after validation

Bad:

- Telegram contact phones are polluting salary extraction
- salary columns need a strict cleaning pass before any compensation analytics

### 7. Descriptions and Text Fields

#### `description`

- coverage: `99.98%`
- median length: `1,209`
- p95 length: `2,741`
- max length: `8,762`
- status: excellent coverage

#### `description_clean`

- coverage: `99.98%`
- status: structurally present but functionally broken
- critical issue: `description == description_clean` for all `16,282` rows

Interpretation:

- the cleaning layer is not actually producing a cleaned description
- downstream NLP/embedding tasks will still receive hashtags, emojis, contacts and promo noise

#### `requirements_raw`

- coverage: `17.26%`
- status: sparse, mostly structured-source field

#### `requirements_clean`

- coverage: `68.18%`
- status: one of the best LLM-derived fields
- note: this is much more useful than `requirements_raw`

#### `responsibilities_raw`

- coverage: `17.29%`
- status: sparse, mostly structured-source field

#### `responsibilities_clean`

- coverage: `60.29%`
- status: strong
- note: useful for role clustering and task analysis

### 8. Skills

#### `skills_raw`

- coverage: `11.39%`
- status: too sparse for standalone use

#### `hard_skills`

- coverage: `62.84%`
- parseable JSON arrays: `100%`
- avg list length: `7.12`
- top items:
  - `PostgreSQL`
  - `SQL`
  - `Python`
  - `Git`
  - `Docker`
- status: strong, high value
- issue: weak canonicalization remains
- examples:
  - `Git` and `git`
  - `Python` and `python`
  - `1С`, `1C`, `1c`

#### `soft_skills`

- coverage: `30.79%`
- parseable JSON arrays: `100%`
- avg list length: `2.81`
- status: moderate
- issue: strong duplication by case and language variant
- examples:
  - `communication`, `коммуникация`, `Коммуникация`
  - `teamwork`, `командная работа`, `Умение работать в команде`

#### `tech_stack`

- coverage: `38.09%`
- parseable JSON arrays: `100%`
- avg list length: `4.98`
- status: helpful, but less complete than `hard_skills`
- issue: same normalization problem as hard skills

### 9. English

#### `english_mention`

- coverage: `100%`
- `True`: `4,276`
- status: fine

#### `english_required`

- coverage: `100%`
- `True`: `486`
- status: usable

#### `english_level`

- coverage: `15.74%`
- values include:
  - `B2`, `b2`
  - `B1`, `b1`
  - `C1`, `c2`
  - `A1`, `A2`
  - `not_required`
- status: inconsistent enum formatting
- issue: `1,701` rows use uppercase variants
- issue: mix of uppercase and lowercase breaks clean categorical analysis
- validation fixes mention:
  - `english_level_out_of_enum`
  - `english_level_reset_without_mention`

### 10. Temporal and Status Columns

#### `posted_at`

- coverage: `99.42%`
- status: good
- note: no future leakage relative to `scraped_at`
- note: no dates before 2024 in this file

#### `scraped_at`

- coverage: `100%`
- unique values: `1`
- value: `2026-04-14 22:57:12.700409+00:00`
- status: good as batch metadata, not event-level metadata

#### `is_active`

- coverage: `100%`
- only value: `True`
- status: unusable for analysis in current form

### 11. Enrichment Metadata

#### `extraction_method`

- values:
  - `mixed`: `11,419`
  - `rule_based`: `4,863`
- status: useful provenance signal

#### `llm_confidence`

- coverage: `100%`
- median: `0.78`
- p95: `1.0`
- status: useful ranking signal
- caution: confidence is not calibrated ground truth

#### `duplicate_hash`

- coverage: `100%`
- unique values: `14,911`
- status: useful for dedup workflows

#### `is_duplicate`

- coverage: `100%`
- status: useful but incomplete for final business analysis

### 12. Parser/LLM Provenance Objects

#### `parser_hints`

- coverage: `72.76%`
- valid JSON objects: `100%`
- status: good diagnostic field

#### `parser_quality`

- coverage: `72.76%`
- valid JSON objects: `100%`
- status: strong for audit/debug use

#### `final_field_sources`

- coverage: `72.76%`
- valid JSON objects: `100%`
- status: one of the most valuable audit columns

#### `final_field_confidence`

- coverage: `72.76%`
- valid JSON objects: `100%`
- status: strong provenance metadata

### 13. Review and Validation Columns

#### `review_flags`

- coverage: `18.54%`
- valid JSON arrays: `100%`
- top items:
  - `salary_raw`
  - `employment`
  - `salary_from`
  - `work_format`
- status: highly useful

#### `conflict_flags`

- coverage: `18.48%`
- valid JSON arrays: `100%`
- top items mirror review flags
- status: useful

#### `validation_fixes`

- coverage: `3.89%`
- valid JSON arrays: `100%`
- top items:
  - `english_level_out_of_enum`
  - `english_level_reset_without_mention`
  - `internship_level_review`
  - `currency_normalized_from_salary_raw`
  - `salary_range_swapped`
- status: useful quality-control signal

#### `llm_merge_status`

- coverage: `89.48%`
- values:
  - `auto_merged`: `6,332`
  - `merged_with_review`: `5,087`
  - `skipped_low_confidence`: `3,150`
- status: essential field for next-stage filtering

#### `llm_model`

- coverage: `89.48%`
- values:
  - `llama-3.3-70b-versatile`: `9,587`
  - `llama-3.1-8b-instant`: `4,982`
- status: useful for experiment traceability

#### `llm_review_flag`

- coverage: `100%`
- `True`: `5,087`
- status: must be used as a quality filter

#### `llm_called`

- coverage: `100%`
- `True`: `14,569`
- status: useful

#### `parser_only`

- coverage: `100%`
- only value: `False`
- status: currently not useful
- issue: parser-only branch appears unused in the final dataset

## Provenance Audit by Final Field

Key pattern:

- `category`, `requirements_clean`, `responsibilities_clean`, `hard_skills`, `soft_skills`, `tech_stack` are mostly LLM-semantic fields
- `city`, `employment`, `work_format`, `salary_*`, `currency`, `experience_*` are mixed parser + LLM fields

Examples:

- `category`: mostly `llm_semantic`
- `city`: mostly `parser_confirmed_by_llm`
- `work_format`: mostly `parser_confirmed_by_llm`
- `salary_raw`: mixed between `llm_semantic`, `parser_confirmed_by_llm`, `regex_in_text`, and `missing`
- `currency`: strong parser contribution

Confidence pattern:

- many semantic fields are only `medium_confidence`
- `city` and `work_format` have more `high_confidence`
- salary fields remain medium-confidence heavy

## Major Data Quality Problems

### 1. Salary contamination from contact data

Critical.

Telegram posts often contain phone numbers near “salary” wording. Regex/LLM logic is capturing phones as compensation.

Examples in file:

- `87770788710`
- `87757386747`
- `77783686819`

Impact:

- salary analytics are unsafe without hard cleaning
- compensation distributions are badly skewed by outliers

### 2. Fake cleaned description field

Critical.

`description_clean` is identical to `description` for all rows.

Impact:

- text analysis still contains hashtags, contact blocks, emojis, promo text
- NLP quality will be worse than expected
- downstream users may wrongly trust the cleaned field

### 3. Too many `unknown` values in strategic analytical fields

High.

- `category`: `34.12%` unknown-like
- `level`: `64.10%` unknown-like
- `company`: `61.92%` missing-like

Impact:

- segmentation quality is limited
- role seniority analysis is weak
- company-level market mapping is incomplete

### 4. Enum inconsistency

High.

`english_level` uses mixed case and mixed label variants.

Impact:

- categorical stats are unreliable until normalized

### 5. Weak skill canonicalization

Medium-high.

Examples:

- `Git` vs `git`
- `Python` vs `python`
- `1С` vs `1C` vs `1c`

Impact:

- skill frequency stats are fragmented
- embeddings/feature engineering will be noisier

### 6. Company field leakage

Medium-high.

Some Telegram rows store huge chunks of vacancy text in `company`.

Impact:

- employer analytics become unreliable
- organization dedup becomes harder

### 7. Incomplete internship consistency

Medium.

- `level='intern'` but `employment!='internship'`: `33` rows
- `employment='internship'` but `level!='intern'`: `481` rows

Impact:

- junior/intern funnel analysis will be noisy

### 8. Dedup remains incomplete for Telegram-heavy sources

Medium.

Strong duplicate concentration remains in:

- `Halyk Jumys`
- `Zhumys Bar IT`
- `Work IT KZ`

Impact:

- job volume trends can be overstated
- skill frequency can be overcounted

## What Is Good Enough Already

These parts are already valuable and can be reused with light cleanup:

- `id`
- `source`
- `posted_at`
- `description`
- `requirements_clean`
- `responsibilities_clean`
- `hard_skills`
- `city`
- `work_format`
- `llm_review_flag`
- `llm_merge_status`
- `duplicate_hash`
- `is_duplicate`
- provenance JSON columns

## Recommended Next Stages

## Stage 1. Build an analysis-ready layer

Create a new file:

- `analysis_ready_jobs.csv`

Recommended filters:

- exclude or separately tag `is_duplicate=True`
- exclude salary outliers above a hard threshold
- keep `llm_review_flag` as a separate quality feature
- normalize all enums and skills

Recommended new fields:

- `quality_tier`
- `salary_is_suspicious`
- `title_is_inferred`
- `company_is_suspicious`
- `is_telegram_source`
- `is_structured_source`
- `english_level_norm`
- `category_norm`
- `level_norm`

## Stage 2. Fix the text-cleaning layer

Need:

- true `description_clean`
- remove:
  - hashtags
  - Telegram handles
  - contact phones
  - email blocks
  - emoji noise
  - “send CV / write in direct” promo fragments

Expected effect:

- better title extraction
- better company extraction
- better salary parsing
- stronger downstream embeddings and clustering

## Stage 3. Rebuild salary extraction

Must do before any salary dashboard or salary model.

Add rules:

- ignore 10-11 digit phone patterns
- ignore contact blocks after keywords like `контакты`, `whatsapp`, `telegram`, `резюме`
- support shorthand:
  - `900К`
  - `1.5 млн`
  - `500k`
- mark ambiguous salary rows instead of forcing numeric parse

Output fields to add:

- `salary_parse_quality`
- `salary_outlier_flag`
- `salary_contact_leak_flag`

## Stage 4. Canonicalize titles, skills, and companies

Need normalization dictionaries for:

- titles:
  - `frontend developer`, `front-end developer`, `react developer`
- skills:
  - `Git/git`
  - `Python/python`
  - `1С/1C/1c`
- companies:
  - strip long leaked text
  - normalize common naming variants

## Stage 5. Improve categorical completeness

Priority targets:

- `category`
- `level`
- `company`
- `city`

Best strategy:

- use cleaned description
- backfill title from title_normalized if raw title is unknown
- rerun targeted enrichment only on rows with:
  - `category='unknown'`
  - `level='unknown'`
  - suspicious company

## Stage 6. Strengthen deduplication

Need a second-pass dedup key using:

- normalized title
- normalized company
- city
- source-family
- time window

Create:

- `cross_source_duplicate_group`
- `same_role_duplicate_group`

## Stage 7. Define quality tiers for downstream usage

Suggested:

- `A`: structured source, no duplicate, no review flag, no suspicious salary/company
- `B`: enriched row, medium confidence, no critical anomaly
- `C`: review-needed row but still analyzable for text tasks
- `D`: unsafe for salary/entity analytics

## Recommended Uses by Current Dataset State

Safe now:

- vacancy volume analysis by source
- high-level category analysis after excluding `unknown`
- work format trends
- city split between `almaty` and `astana`
- skills exploration after canonicalization
- text clustering/topic modeling using cleaned replacement field

Unsafe now without cleanup:

- salary benchmarking
- employer ranking
- seniority market sizing
- remote job market estimates
- training production ML models directly from this file

## Concrete Action Plan

### Immediate

1. Freeze `enriched_jobs_full_v1.csv` as the current raw enriched snapshot.
2. Create `analysis_ready_jobs.csv`.
3. Normalize `english_level`, `category`, `level`.
4. Remove salary outliers and phone-derived salary values.
5. Create true `description_clean_v2`.

### Short-term

1. Canonicalize `hard_skills`, `soft_skills`, `tech_stack`.
2. Clean leaked `company` values.
3. Backfill better titles for Telegram rows.
4. Run targeted re-enrichment on `unknown` category/level/company rows.

### Mid-term

1. Build quality tiers.
2. Build second-pass dedup.
3. Produce domain marts:
   - `jobs_salary_clean.csv`
   - `jobs_skills_clean.csv`
   - `jobs_entity_clean.csv`

### Before dashboards or modeling

1. Recompute all descriptive statistics on the cleaned layer.
2. Validate salary distributions by source.
3. Validate top employers after company normalization.
4. Validate skill frequencies after canonicalization.

## Final Verdict

`enriched_jobs_full_v1.csv` is a strong intermediate dataset and the correct foundation for the next phase, but it is not a final analytical dataset yet.

Readiness assessment:

- source consolidation: good
- enrichment coverage: good
- auditability/provenance: very good
- salary trustworthiness: poor
- entity normalization: medium-poor
- categorical completeness: medium
- dedup quality: medium
- analytics-readiness overall: medium

Recommended next move:

- do not replace this file
- build a curated derivative layer from it
- treat this file as the enriched master snapshot
