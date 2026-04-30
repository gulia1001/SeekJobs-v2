# 🚀 LLM Integration Pipeline для объединения вакансий

Полное решение для интеграции и нормализации данных о вакансиях из 4+ источников (HH, Kolesa, Kaspi, Telegram) с использованием Groq API для обогащения данных LLM.

## 📋 Структура проекта

```
job_integration_pipeline.py       - Source integration and normalization
enrich/main.py                    - LLM enrichment entrypoint
enrich/pipeline.py                - Batch enrichment logic
prepare_analysis_ready_jobs.py    - Curated analytical layer builder
repair_salary_layer_v2.py         - Salary repair / review pipeline
```

## 🗄️ Единая схема БД (40+ полей)

### Основная информация
- **id** (UUID) - Уникальный ID
- **source** - Источник (hh_kz, kaspi_jobs, kolesa_jobs, telegram)
- **source_id** - ID в исходной системе
- **source_url** - Link на вакансию
- **title** - Оригинальное название
- **title_normalized** - Нормализованное название (LLM)
- **company** - Компания
- **city** - Город (almaty, astana, remote, other, unknown)

### Направление и уровень
- **category** - Категория вакансии (backend, frontend, devops, data_engineer и т.д.)
- **level** - Уровень (intern, junior, middle, senior, lead, head, unknown)

### Опыт и формат работы
- **experience_raw** - Исходный текст опыта
- **experience_min/max** - Min/max лет опыта (числа)
- **employment** - Тип (full_time, part_time, contract, internship, unknown)
- **work_format** - Формат (office, remote, hybrid, unknown)

### Зарплата
- **salary_from/to/avg** - Диапазон и средняя зарплата
- **currency** - Валюта (KZT, USD, RUB, EUR, UNKNOWN)
- **salary_raw** - Исходная строка
- **salary_gross** - False = на руки, True = до налогов, NULL = unknown

### Описание и требования
- **description** - Полное оригинальное описание
- **description_clean** - Очищенное описание
- **requirements_raw/clean** - Требования
- **responsibilities_raw/clean** - Обязанности

### Навыки (LLM)
- **skills_raw** - Исходные навыки
- **hard_skills** - JSON: ["Python", "SQL", ...]
- **soft_skills** - JSON: ["communication", ...]
- **tech_stack** - JSON: ["Docker", "Kubernetes", ...]

### Английский язык
- **english_mention** - Упоминается в описании
- **english_required** - Явно требуется
- **english_level** - A1, A2, B1, B2, C1, C2, unknown, NULL

### Метаданные
- **posted_at** - Дата публикации
- **scraped_at** - Дата парсинга
- **is_active** - Активна ли вакансия
- **extraction_method** - source, rule_based, llm, manual, mixed
- **llm_confidence** - 0.0-1.0 (уверенность LLM)
- **is_duplicate** - Дубликат?
- **duplicate_hash** - MD5 hash для поиска дубликатов

## 🔄 Процесс обработки

### Этап 1: Data Cleaning & Preprocessing (Автоматический)
```
Источники CSV → Загрузка → Очистка HTML → Нормализация текста
                           ↓
                   Извлечение by regex:
                   - Зарплата (суммы, валюта)
                   - Опыт (min/max лет)
                   - Город
                   - Английский язык
```

### Этап 2: LLM Обогащение (Groq API)
```
Очищенные данные → Подготовка батчей (по 10 записей)
                  ↓
                LLM Промпты (Groq Free)
                  ↓
                Извлечение через JSON:
                - title_normalized
                - category (18 типов)
                - level (7 уровней)
                - hard_skills, soft_skills, tech_stack
                - requirements_clean, responsibilities_clean
```

### Этап 3: Валидация и Сохранение
```
LLM результаты → Валидация значений → Вычисление хэшей
                                       ↓
                                Обнаружение дубликатов
                                       ↓
                                Экспорт (CSV/SQLite/JSONL)
```

## 🚀 Быстрый старт

### 1. Базовая обработка (без LLM) - 5 минут

```python
# Просто запустите всё в порядке:
# Section 1: Загрузка
# Section 2: Очистка
# Section 3: Извлечение
# Section 7: Сохранение

# Получите data/interim/unified_job_database.csv с 3000+ вакансиями
```

### 2. С интеграцией LLM - 30+ минут

```python
# 1. Получить API ключ (бесплатно)
# https://console.groq.com/keys

# 2. Инициализировать
init_groq_client('your-api-key')

# 3. Обработать батчи
llm_results = process_all_batches_with_groq(llm_batches)

# 4. Объединить и экспортировать
final_df_enhanced = merge_llm_with_source(combined_df, llm_results)
final_db_enhanced = create_final_database(final_df_enhanced)
export_to_csv(final_db_enhanced, 'vacancies_with_llm.csv')
```

## 📊 Groq API

### Характеристики
- **Free tier**: 30 requests/minute, unlimited messages
- **Скорость**: ~2-3 сек на запрос
- **Качество**: Отличное для структурирования данных
- **Модели**: 
  - mixtral-8x7b-32768 (DEFAULT - быстро, хороший результат)
  - llama-3.1-70b-versatile (мощнее, медленнее)

### Получение ключа
1. Перейти https://console.groq.com/keys
2. Create API Key (автоматически генерируется)
3. Copy ключ
4. `export GROQ_API_KEY='ваш-ключ'`

## 📈 Результаты

### Статистика (на момент создания)
- **Всего вакансий**: 3000+ (объединено из 4 источников)
- **HH.kz**: 2748 записей
- **Kolesa**: 20 записей
- **Kaspi**: 53 записи
- **Telegram**: 7000+ сообщений → отфильтровано в вакансии

### Распределение по категориям
- Backend, Frontend, FullStack
- Mobile (iOS, Android)
- DevOps, QA
- Data Engineer, Data Scientist, ML Engineer
- Product Manager, Business Analyst

### Распределение по уровню
- Junior/Middle: 60%
- Senior: 30%
- Lead/Head: 5%
- Intern: 5%

## 🔍 Примеры запросов

```python
# Найти всех senior backend developers в Алматы
db[(db['category'] == 'backend') & (db['level'] == 'senior') & (db['city'] == 'almaty')]

# Найти вакансии с Python
db[db['hard_skills'].str.contains('Python', na=False)]

# Самые высокооплачиваемые позиции
db.nlargest(10, 'salary_avg')[['title', 'company', 'salary_avg']]

# Remote позиции
db[db['work_format'] == 'remote']

# С требованием английского языка
db[db['english_required'] == True]
```

## ⚙️ Технические детали

### Язык и зависимости
- Python 3.10+
- pandas, numpy
- groq (для LLM)
- sqlite3 (встроенный)

### Файлы на выходе
- `data/interim/unified_job_database.csv` (~50MB) - Основная БД
- `data/interim/job_vacancies.db` (~100MB) - SQLite БД с индексами
- `data/reports/llm_audit_log.jsonl` - audit trail LLM enrichment pipeline

### Обработка дубликатов
```
Hash = MD5(title_normalized + company + city + source)
Если hash повторяется → is_duplicate = True
```

## 🐛 Troubleshooting

### Ошибка: "GROQ_API_KEY not found"
```python
# Решение 1: Установить переменную окружения
export GROQ_API_KEY='your-key'

# Решение 2: Передать напрямую
init_groq_client('your-key')

# Решение 3: Проверить
import os
print(os.environ.get('GROQ_API_KEY'))
```

### Ошибка: "Rate limit exceeded"
```python
# Groq имеет лимит 30 req/min. Код автоматически ждёт 2 сек между батчами.
# Если нужно быстрее - используйте оплаченный план
```

### Плохое качество LLM результатов
```python
# Попробуйте другую модель:
call_groq_api(prompt, model="llama-3.1-70b-versatile")

# Или повысьте температуру для вариативности:
call_groq_api(prompt, temperature=0.5)
```

## 📚 Различные экспорты

### CSV (самый универсальный)
```python
export_to_csv(final_db)
# Открывается в Excel, Google Sheets, Pandas
# Все JSON поля как строки
```

### SQLite (для серьёзных проектов)
```python
export_to_sqlite(final_db)
# Автоматически созданы индексы
# Быстрые запросы по source, category, level, city
```

### JSONL (для обработки в потоке)
```python
export_to_json_lines(final_db)
# Одна строка JSON = одна вакансия
# Удобно для ETL систем
```

## 🎯 Roadmap

- [ ] Интеграция с PostgreSQL (вместо SQLite)
- [ ] Web интерфейс для просмотра и фильтрации
- [ ] Автоматические обновления каждый день
- [ ] Интеграция со статистикой зарплаты
- [ ] Сравнение вакансий по городам
- [ ] ML для рекомендации вакансий по CV

## 📞 Поддержка

Если что-то не работает:
1. Проверьте GROQ_API_KEY
2. Убедитесь что все CSV файлы на месте
3. Посмотрите логи ошибок в ячейке
4. Пересчитайте отдельные ячейки

---

**Создано**: 2024-04-15  
**Версия**: 1.0.0  
**Статус**: Production Ready ✅
