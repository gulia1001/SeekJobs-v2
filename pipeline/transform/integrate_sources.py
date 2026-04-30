"""
Data Processing and LLM Integration Pipeline
Объединение вакансий из разных источников (HH, Kolesa, Kaspi, Telegram) в единую БД с LLM обогащением через Groq API

Usage:
    python job_integration_pipeline.py --mode clean  # Data cleaning only
    python job_integration_pipeline.py --mode llm    # With LLM processing
"""

import argparse
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# Setup paths
BASE_PATH = Path(__file__).resolve().parents[1]  # pipeline/
DATA_DIR = BASE_PATH / 'data'
DATASETS_PATH = DATA_DIR / 'raw'  # raw source exports (was 'datasets IT Jobs/')

# Constants
VALID_CATEGORIES = [
    'backend', 'frontend', 'fullstack', 'mobile', 'devops', 
    'data_analyst', 'data_engineer', 'data_scientist', 'ml_engineer',
    'qa', 'product_analyst', 'business_analyst', 'system_analyst',
    'project_manager', 'product_manager', 'ui_ux_designer', 'support',
    'other', 'unknown'
]

VALID_LEVELS = ['intern', 'junior', 'middle', 'senior', 'lead', 'head', 'unknown']
VALID_ENGLISH = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'unknown']
DEFAULT_GROQ_MODEL = 'openai/gpt-oss-20b'

TELEGRAM_CHANNELS = {
    '-1001746243221': {
        'slug': 'itcom_kz',
        'display_name': 'ITcom KZ',
        'handle': 'itcom_kz',
    },
    '-1001218364404': {
        'slug': 'zhumysbarit',
        'display_name': 'Zhumys Bar IT',
        'handle': 'zhumysbarit',
    },
    '-1001446132226': {
        'slug': 'workitkz',
        'display_name': 'Work IT KZ',
        'handle': 'workitkz',
    },
    '-1001651093004': {
        'slug': 'halyk_jumys',
        'display_name': 'Halyk Jumys',
        'handle': 'halyk_jumys',
    },
    '-1002321256587': {
        'slug': 'itvacancykz',
        'display_name': 'IT Vacancy KZ',
        'handle': 'itvacancykz',
    },
    '-1003217256724': {
        'slug': 'insferaforyou',
        'display_name': 'Insfera For You',
        'handle': 'insferaforyou',
    },
    '-1003882138113': {
        'slug': 'no_username',
        'display_name': 'Freedom Broker',
        'handle': 'freedom_broker',
    },
}


def clean_html(text: Optional[str]) -> Optional[str]:
    if not isinstance(text, str):
        return None
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#039;', "'").replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text or None


def normalize_whitespace(text: Optional[str]) -> str:
    if not isinstance(text, str):
        return ''
    return re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()


def normalize_currency(currency: Optional[str]) -> str:
    if not isinstance(currency, str) or not currency.strip():
        return 'UNKNOWN'
    normalized = currency.strip().upper()
    currency_map = {
        'KZT': 'KZT',
        'ТГ': 'KZT',
        'ТЕНГЕ': 'KZT',
        'KGS': 'KGS',
        'USD': 'USD',
        '$': 'USD',
        'EUR': 'EUR',
        '€': 'EUR',
        'RUR': 'RUB',
        'RUB': 'RUB',
        'РУБ': 'RUB',
    }
    return currency_map.get(normalized, normalized)


def compute_salary_avg(salary_from: Optional[float], salary_to: Optional[float]) -> Optional[float]:
    if pd.notna(salary_from) and pd.notna(salary_to):
        return float((salary_from + salary_to) / 2)
    if pd.notna(salary_from):
        return float(salary_from)
    if pd.notna(salary_to):
        return float(salary_to)
    return None


def parse_salary_text(salary_text: Optional[str]) -> Tuple[Optional[int], Optional[int], Optional[float], str]:
    text = normalize_whitespace(salary_text).lower()
    if not text or text in {'не указана', 'not specified', 'n/a'}:
        return None, None, None, 'UNKNOWN'

    currency = 'UNKNOWN'
    if any(token in text for token in ['тенге', 'тг', '₸']):
        currency = 'KZT'
    elif any(token in text for token in ['usd', '$']):
        currency = 'USD'
    elif any(token in text for token in ['eur', '€']):
        currency = 'EUR'
    elif any(token in text for token in ['rub', 'rur', 'руб']):
        currency = 'RUB'

    numbers = [
        int(match.replace(' ', ''))
        for match in re.findall(r'(\d[\d ]+)', text)
        if match.replace(' ', '').isdigit()
    ]
    if not numbers:
        return None, None, None, currency

    if ('от' in text or 'from' in text) and len(numbers) == 1:
        salary_from = numbers[0]
        return salary_from, None, float(salary_from), currency
    if ('до' in text or 'to' in text) and len(numbers) == 1:
        salary_to = numbers[0]
        return None, salary_to, float(salary_to), currency
    if len(numbers) >= 2:
        salary_from = min(numbers[0], numbers[1])
        salary_to = max(numbers[0], numbers[1])
        return salary_from, salary_to, compute_salary_avg(salary_from, salary_to), currency

    salary_from = numbers[0]
    return salary_from, None, float(salary_from), currency


def infer_work_format(*texts: Optional[str]) -> str:
    combined = ' '.join(normalize_whitespace(text).lower() for text in texts if isinstance(text, str))
    if not combined:
        return 'unknown'

    hybrid_terms = ['гибрид', 'hybrid']
    remote_terms = ['удален', 'remote', 'дистанцион', 'home office', 'work from home']
    office_terms = ['офис', 'office', 'onsite', 'on-site', 'в офисе', 'на месте']

    if any(term in combined for term in hybrid_terms):
        return 'hybrid'
    if any(term in combined for term in remote_terms):
        return 'remote'
    if any(term in combined for term in office_terms):
        return 'office'
    return 'unknown'


def extract_id_from_url(url: Optional[str], fallback_prefix: str) -> Optional[str]:
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    digits_match = re.search(r'-(\d+)(?:[/?#]|$)', url)
    if digits_match:
        return digits_match.group(1)
    slug_match = re.search(r'/vacancy/([^/?#]+)', url)
    if slug_match:
        return slug_match.group(1)
    return f"{fallback_prefix}_{hashlib.md5(url.lower().encode()).hexdigest()[:12]}"


def normalize_string_list(value) -> List[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r'[|;,/\n]+', str(value))
    cleaned = []
    seen = set()
    for item in raw_items:
        item = normalize_whitespace(str(item)).strip(' -')
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(item)
    return cleaned


def normalize_telegram_title(channel_title: Optional[str]) -> str:
    if not isinstance(channel_title, str) or not channel_title.strip():
        return 'Telegram Channel'
    return normalize_whitespace(channel_title)


def make_telegram_source_id(channel_id: Optional[str], message_id) -> Optional[str]:
    if pd.isna(message_id):
        return None
    return f"{channel_id}_{int(message_id)}"


class JobIntegrationPipeline:
    """Main pipeline for job vacancy data integration and LLM enrichment"""
    
    def __init__(self):
        self.sources_data = {}
        self.cleaned_data = {}
        self.combined_df = None
        self.final_df = None
        self.final_db = None
        self.llm_batches = []
        self.llm_results = {}
        
    def load_all_sources(self) -> Dict[str, pd.DataFrame]:
        """Load data from all sources"""
        sources = {}
        
        # HH.kz
        try:
            hh_files = [
                DATASETS_PATH / 'hh_almaty_astana_it_20260414_014547.csv',
            ]
            hh_dfs = []
            for file in hh_files:
                if file.exists():
                    df = pd.read_csv(file)
                    hh_dfs.append(df)
                    print(f"✅ Loaded HH: {file.name} ({len(df)} rows)")
            if hh_dfs:
                sources['hh_kz'] = pd.concat(hh_dfs, ignore_index=True)
        except Exception as e:
            print(f"❌ Error loading HH: {e}")
        
        # Kolesa
        try:
            kolesa_files = [
                DATASETS_PATH / 'kolesa_vacancies.csv',
                DATASETS_PATH / 'kolesa_vacancies_smart.csv'
            ]
            kolesa_dfs = []
            for file in kolesa_files:
                if file.exists():
                    df = pd.read_csv(file)
                    kolesa_dfs.append(df)
                    print(f"✅ Loaded Kolesa: {file.name} ({len(df)} rows)")
            if kolesa_dfs:
                sources['kolesa_jobs'] = pd.concat(kolesa_dfs, ignore_index=True)
        except Exception as e:
            print(f"❌ Error loading Kolesa: {e}")
        
        # Kaspi
        try:
            kaspi_file = DATASETS_PATH / 'kaspi_it_vacancies_2024.csv'
            if kaspi_file.exists():
                sources['kaspi_jobs'] = pd.read_csv(kaspi_file)
                print(f"✅ Loaded Kaspi: {len(sources['kaspi_jobs'])} rows")
        except Exception as e:
            print(f"❌ Error loading Kaspi: {e}")
        
        # Telegram channels
        telegram_dfs = []
        for channel_id, channel_meta in TELEGRAM_CHANNELS.items():
            try:
                csv_file = DATASETS_PATH / f"{channel_id}_{channel_meta['slug']}.csv"
                if csv_file.exists():
                    df = pd.read_csv(csv_file)
                    df['channel_id'] = channel_id
                    df['channel_name'] = channel_meta['slug']
                    df['channel_title'] = channel_meta['display_name']
                    df['channel_handle'] = channel_meta['handle']
                    telegram_dfs.append(df)
                    print(f"✅ Loaded Telegram {channel_meta['display_name']}: {len(df)} messages")
            except Exception as e:
                print(f"⚠️  Skipping {channel_id}: {e}")
        
        if telegram_dfs:
            sources['telegram'] = pd.concat(telegram_dfs, ignore_index=True)
        
        self.sources_data = sources
        print(f"\n✅ Total sources loaded: {len(sources)}")
        for source, df in sources.items():
            print(f"  • {source}: {len(df)} records")
        
        return sources
    
    def clean_data(self) -> Dict[str, pd.DataFrame]:
        """Clean all source data"""

        # HH cleaning
        if 'hh_kz' in self.sources_data:
            df = self.sources_data['hh_kz'].copy()
            df['title'] = df['title'].fillna('unknown')
            df['description_raw'] = df['description'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['requirements_raw'] = df['requirement'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['responsibilities_raw'] = df['responsibility'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['skills_raw'] = df['skills'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['salary_raw'] = df.apply(
                lambda x: (
                    f"{int(x['salary_from']) if pd.notna(x['salary_from']) else ''}"
                    f"{' - ' + str(int(x['salary_to'])) if pd.notna(x['salary_to']) else ''}"
                    f" {normalize_currency(x['currency'])}"
                ).strip() if pd.notna(x['salary_from']) or pd.notna(x['salary_to']) else None,
                axis=1
            )
            df['source_url'] = df['url']
            df['source_id'] = df['id'].astype(str)
            df['posted_at'] = pd.to_datetime(df['published_at'], errors='coerce')
            df['company'] = df['company'].fillna('unknown')
            df['city'] = df['vacancy_city'].apply(lambda x: 'almaty' if x == 'Алматы' else ('astana' if x == 'Астана' else 'unknown'))
            
            employ_map = {
                'Полная занятость': 'full_time',
                'Неполная занятость': 'part_time',
                'Стажировка': 'internship'
            }
            df['employment'] = df['employment'].map(employ_map).fillna('unknown')
            df['work_format'] = df.apply(
                lambda row: infer_work_format(
                    row.get('schedule'),
                    row.get('description'),
                    row.get('requirement'),
                    row.get('responsibility'),
                ),
                axis=1,
            )
            df['experience_raw'] = df['experience']
            df['salary_from'] = pd.to_numeric(df['salary_from'], errors='coerce')
            df['salary_to'] = pd.to_numeric(df['salary_to'], errors='coerce')
            df['salary_avg'] = df.apply(lambda row: compute_salary_avg(row['salary_from'], row['salary_to']), axis=1)
            df['currency'] = df['currency'].apply(normalize_currency)
            df['salary_gross'] = df['salary_gross'].apply(
                lambda value: None if pd.isna(value) else bool(value)
            ) if 'salary_gross' in df.columns else None
            
            self.cleaned_data['hh_kz'] = df[['source_id', 'title', 'company', 'city', 'source_url', 'employment', 'work_format',
                                              'salary_from', 'salary_to', 'salary_avg', 'currency', 'salary_raw', 'salary_gross',
                                              'description_raw', 'requirements_raw', 'responsibilities_raw', 'skills_raw',
                                              'posted_at', 'experience_raw']]
            print(f"✅ HH cleaned: {len(self.cleaned_data['hh_kz'])} records")
        
        # Kolesa cleaning
        if 'kolesa_jobs' in self.sources_data:
            df = self.sources_data['kolesa_jobs'].copy()
            df['title'] = df['title'].fillna('unknown')
            df['description_raw'] = df.apply(
                lambda row: clean_html(' '.join(
                    part for part in [
                        row.get('responsibilities'),
                        row.get('requirements'),
                        row.get('nice_to_have'),
                    ]
                    if isinstance(part, str) and part.strip()
                )) if any(isinstance(row.get(col), str) and row.get(col).strip() for col in ['responsibilities', 'requirements', 'nice_to_have']) else None,
                axis=1,
            )
            df['requirements_raw'] = df['requirements'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['responsibilities_raw'] = df['responsibilities'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['skills_raw'] = df['tech_stack'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['salary_raw'] = df['salary']
            df['source_url'] = df['url']
            df['source_id'] = df['url'].apply(lambda value: extract_id_from_url(value, 'kolesa'))
            df['company'] = df['company'].fillna('unknown')
            df['city'] = df['location'].apply(lambda x: 'almaty' if x == 'Алматы' else ('astana' if x == 'Астана' else 'unknown'))
            df['employment'] = 'unknown'
            df['work_format'] = df.apply(
                lambda row: infer_work_format(
                    row.get('title'),
                    row.get('responsibilities'),
                    row.get('requirements'),
                    row.get('nice_to_have'),
                ),
                axis=1,
            )
            df['experience_raw'] = df['experience']
            df['salary_from'] = pd.to_numeric(df['salary_from'], errors='coerce')
            df['salary_to'] = pd.to_numeric(df['salary_to'], errors='coerce')
            df['salary_avg'] = df.apply(lambda row: compute_salary_avg(row['salary_from'], row['salary_to']), axis=1)
            df['currency'] = 'KZT'
            df['salary_gross'] = None
            df['posted_at'] = None
            
            self.cleaned_data['kolesa_jobs'] = df[['source_id', 'title', 'company', 'city', 'source_url', 'employment', 'work_format',
                                                    'salary_from', 'salary_to', 'salary_avg', 'currency', 'salary_raw', 'salary_gross',
                                                    'description_raw', 'requirements_raw', 'responsibilities_raw', 'skills_raw',
                                                    'posted_at', 'experience_raw']]
            print(f"✅ Kolesa cleaned: {len(self.cleaned_data['kolesa_jobs'])} records")
        
        # Kaspi cleaning
        if 'kaspi_jobs' in self.sources_data:
            df = self.sources_data['kaspi_jobs'].copy()
            df['title'] = df['Position'].fillna('unknown')
            df['description_raw'] = df['Full_Description'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['requirements_raw'] = df['Skills_List'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['responsibilities_raw'] = df['Skills_List'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['skills_raw'] = df['Skills_List'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['salary_raw'] = df['Salary']
            df['source_url'] = df['URL']
            df['source_id'] = df['URL'].apply(lambda value: extract_id_from_url(value, 'kaspi'))
            df['company'] = 'Kaspi.kz'
            df['city'] = df['City'].apply(lambda x: 'almaty' if x == 'Алматы' else ('astana' if x == 'Астана' else 'unknown'))
            df['employment'] = 'unknown'
            df['work_format'] = df.apply(
                lambda row: infer_work_format(row.get('Schedule'), row.get('Full_Description')),
                axis=1,
            )
            df['experience_raw'] = df['Experience']
            parsed_salary = df['salary_raw'].apply(parse_salary_text)
            df['salary_from'] = [salary[0] for salary in parsed_salary]
            df['salary_to'] = [salary[1] for salary in parsed_salary]
            df['salary_avg'] = [salary[2] for salary in parsed_salary]
            df['currency'] = [salary[3] for salary in parsed_salary]
            df['salary_gross'] = None
            df['posted_at'] = None
            
            self.cleaned_data['kaspi_jobs'] = df[['source_id', 'title', 'company', 'city', 'source_url', 'employment', 'work_format',
                                                   'salary_from', 'salary_to', 'salary_avg', 'currency', 'salary_raw', 'salary_gross',
                                                   'description_raw', 'requirements_raw', 'responsibilities_raw', 'skills_raw',
                                                   'posted_at', 'experience_raw']]
            print(f"✅ Kaspi cleaned: {len(self.cleaned_data['kaspi_jobs'])} records")
        
        # Telegram cleaning
        if 'telegram' in self.sources_data:
            df = self.sources_data['telegram'].copy()
            df = df.dropna(subset=['message'])
            df = df[df['message'].str.len() > 50]
            
            vacancy_keywords = ['вакансия', 'требуется', 'нужен', 'опыт', 'зарплата', 'job', 'developer', 'engineer']
            df = df[df['message'].apply(lambda x: any(kw in x.lower() for kw in vacancy_keywords))]
            
            df['title'] = 'unknown'
            df['description_raw'] = df['message'].apply(lambda x: clean_html(x) if pd.notna(x) else None)
            df['requirements_raw'] = None
            df['responsibilities_raw'] = None
            df['skills_raw'] = None
            df['salary_raw'] = None
            df['source_url'] = df['channel_handle'].apply(lambda value: f"@{value}" if isinstance(value, str) and value else None)
            df['source_id'] = df.apply(lambda row: make_telegram_source_id(row['channel_id'], row['message_id']), axis=1)
            df['source'] = df['channel_title'].apply(normalize_telegram_title)
            df['company'] = 'unknown'
            df['city'] = 'unknown'
            df['employment'] = 'unknown'
            df['work_format'] = df['message'].apply(infer_work_format)
            df['salary_from'] = None
            df['salary_to'] = None
            df['salary_avg'] = None
            df['currency'] = 'UNKNOWN'
            df['salary_gross'] = None
            df['posted_at'] = pd.to_datetime(df['date'], errors='coerce')
            df['experience_raw'] = None
            
            self.cleaned_data['telegram'] = df[['source', 'source_id', 'title', 'company', 'city', 'source_url', 'employment', 'work_format',
                                               'salary_from', 'salary_to', 'salary_avg', 'currency', 'salary_raw', 'salary_gross',
                                               'description_raw', 'requirements_raw', 'responsibilities_raw', 'skills_raw',
                                               'posted_at', 'experience_raw']]
            print(f"✅ Telegram cleaned: {len(self.cleaned_data['telegram'])} records")
        
        return self.cleaned_data
    
    def extract_fields(self) -> pd.DataFrame:
        """Extract structured fields using regex rules"""
        
        combined_frames = []
        for source, df in self.cleaned_data.items():
            source_df = df.copy()
            if 'source' not in source_df.columns:
                source_df['source'] = source
            combined_frames.append(source_df)
        self.combined_df = pd.concat(combined_frames, ignore_index=True)
        
        # Extract experience
        def extract_experience(text):
            if not isinstance(text, str) or len(text) < 2:
                return None, None
            text_lower = normalize_whitespace(text).lower()
            if 'нет опыта' in text_lower or 'no experience' in text_lower:
                return 0, 0
            more_than_match = re.search(r'(?:более|more than|from)\s*(\d+)\s*(?:года|года|лет|years?)', text_lower)
            if more_than_match:
                return int(more_than_match.group(1)), None
            from_to_match = re.search(
                r'от\s*(\d+)\s*(?:года|лет)?\s*до\s*(\d+)\s*(?:года|лет|years?)',
                text_lower
            )
            if from_to_match:
                start_years = int(from_to_match.group(1))
                end_years = int(from_to_match.group(2))
                if start_years <= 50 and end_years <= 50:
                    return min(start_years, end_years), max(start_years, end_years)
            range_match = re.search(
                r'(\d+)\s*(?:[-–—]|до)\s*(\d+)\s*(?:года|лет|years?)',
                text_lower
            )
            if range_match:
                start_years = int(range_match.group(1))
                end_years = int(range_match.group(2))
                if start_years <= 50 and end_years <= 50:
                    return min(start_years, end_years), max(start_years, end_years)
            to_match = re.search(r'(?<!от\s)до\s*(\d+)\s*(?:года|лет|years?)', text_lower)
            if to_match:
                return 0, int(to_match.group(1))
            single_match = re.search(r'(\d+)\s*(?:года|лет|years?)', text_lower)
            if single_match:
                years = int(single_match.group(1))
                if years <= 50:
                    if 'от' in text_lower or 'from' in text_lower:
                        return years, None
                    if 'до' in text_lower or 'up to' in text_lower:
                        return 0, years
                    return years, years
            bare_range_match = re.search(r'(\d+)\s*[-–—]\s*(\d+)', text_lower)
            if bare_range_match:
                start_years = int(bare_range_match.group(1))
                end_years = int(bare_range_match.group(2))
                if start_years <= 50 and end_years <= 50:
                    return min(start_years, end_years), max(start_years, end_years)
            return None, None
        
        self.combined_df['experience_min'], self.combined_df['experience_max'] = zip(*self.combined_df['experience_raw'].apply(extract_experience))
        
        # Extract English level
        def extract_english(text):
            if not isinstance(text, str):
                return None, False, False
            text_lower = normalize_whitespace(text).lower()
            english_mentioned = any(w in text_lower for w in ['english', 'англий'])
            english_required = english_mentioned and any(w in text_lower for w in ['required', 'требуется', 'must have', 'обязательно'])
            level = None
            for pattern, lvl in [('c2', 'C2'), ('c1', 'C1'), ('b2', 'B2'), ('b1', 'B1'), ('a2', 'A2'), ('a1', 'A1')]:
                if pattern in text_lower:
                    level = lvl
                    break
            return level, english_mentioned, english_required
        
        english_text = self.combined_df.apply(
            lambda row: ' '.join(
                part for part in [
                    row.get('description_raw'),
                    row.get('requirements_raw'),
                    row.get('skills_raw'),
                ]
                if isinstance(part, str) and part.strip()
            ),
            axis=1,
        )
        english_data = english_text.apply(extract_english)
        self.combined_df['english_level'], self.combined_df['english_mention'], self.combined_df['english_required'] = zip(*english_data)
        
        print(f"✅ Extracted fields from {len(self.combined_df)} records")
        
        return self.combined_df
    
    def prepare_for_llm(self, batch_size: int = 10, limit: Optional[int] = None) -> List[List[Dict]]:
        """Prepare batches for LLM processing"""

        if self.combined_df is None:
            raise ValueError("Run extract_fields() before prepare_for_llm().")

        to_process = self.combined_df[self.combined_df['description_raw'].notna()].copy()
        if limit is not None:
            to_process = to_process.head(limit)

        def create_prompt(row):
            context_parts = [
                f"SOURCE: {row['source']}",
                f"TITLE: {row['title']}",
                f"COMPANY: {row['company']}",
                f"DESCRIPTION: {row['description_raw'] or 'N/A'}",
                f"REQUIREMENTS: {row['requirements_raw'] or 'N/A'}",
                f"RESPONSIBILITIES: {row['responsibilities_raw'] or 'N/A'}",
                f"SKILLS_RAW: {row['skills_raw'] or 'N/A'}",
            ]
            return '\n'.join(context_parts)
        
        batches = []
        current_batch = []
        
        for idx, row in to_process.iterrows():
            record = {
                'idx': idx,
                'title': row['title'],
                'prompt': create_prompt(row)
            }
            current_batch.append(record)
            if len(current_batch) >= batch_size:
                batches.append(current_batch)
                current_batch = []
        
        if current_batch:
            batches.append(current_batch)
        
        self.llm_batches = batches
        print(f"✅ Created {len(batches)} LLM batches (batch_size={batch_size})")
        
        return batches

    def _llm_json_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "title_normalized": {"type": "string"},
                "category": {"type": "string", "enum": VALID_CATEGORIES},
                "level": {"type": "string", "enum": VALID_LEVELS},
                "hard_skills": {"type": "array", "items": {"type": "string"}},
                "soft_skills": {"type": "array", "items": {"type": "string"}},
                "tech_stack": {"type": "array", "items": {"type": "string"}},
                "requirements_clean": {"type": ["string", "null"]},
                "responsibilities_clean": {"type": ["string", "null"]},
                "english_mention": {"type": "boolean"},
                "english_required": {"type": ["boolean", "null"]},
                "english_level": {"type": ["string", "null"], "enum": VALID_ENGLISH + [None]},
                "llm_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": [
                "title_normalized",
                "category",
                "level",
                "hard_skills",
                "soft_skills",
                "tech_stack",
                "requirements_clean",
                "responsibilities_clean",
                "english_mention",
                "english_required",
                "english_level",
                "llm_confidence",
            ],
            "additionalProperties": False,
        }

    def _normalize_llm_result(self, row: pd.Series, payload: Dict) -> Dict:
        title_normalized = normalize_whitespace(payload.get('title_normalized')) or row['title']
        category = payload.get('category')
        if category not in VALID_CATEGORIES:
            category = 'unknown'
        level = payload.get('level')
        if level not in VALID_LEVELS:
            level = 'unknown'

        english_level = payload.get('english_level')
        if english_level not in VALID_ENGLISH and english_level is not None:
            english_level = 'unknown'

        llm_confidence = payload.get('llm_confidence', 0.0)
        try:
            llm_confidence = max(0.0, min(float(llm_confidence), 1.0))
        except (TypeError, ValueError):
            llm_confidence = 0.0

        return {
            'title_normalized': title_normalized,
            'category': category,
            'level': level,
            'hard_skills': normalize_string_list(payload.get('hard_skills')),
            'soft_skills': normalize_string_list(payload.get('soft_skills')),
            'tech_stack': normalize_string_list(payload.get('tech_stack')),
            'requirements_clean': clean_html(payload.get('requirements_clean')) if payload.get('requirements_clean') else None,
            'responsibilities_clean': clean_html(payload.get('responsibilities_clean')) if payload.get('responsibilities_clean') else None,
            'english_mention': bool(payload.get('english_mention', False)),
            'english_required': payload.get('english_required'),
            'english_level': english_level,
            'llm_confidence': llm_confidence,
        }

    def process_with_groq(
        self,
        model: str = DEFAULT_GROQ_MODEL,
        batch_size: int = 10,
        limit: Optional[int] = None,
        delay_seconds: float = 0.5,
        max_retries: int = 3,
    ) -> Dict[int, Dict]:
        """Enrich records with Groq structured outputs."""

        if self.combined_df is None:
            raise ValueError("Run extract_fields() before process_with_groq().")
        if self.final_db is None:
            self.create_final_database()

        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set. Export it before running --mode llm.")

        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError("Package 'groq' is not installed. Run: pip install groq") from exc

        client = Groq(api_key=api_key)
        schema = self._llm_json_schema()
        strict_mode = model.startswith('openai/gpt-oss-')

        system_prompt = (
            "You extract structured job-vacancy data for a Kazakhstan IT jobs warehouse. "
            "Return a single JSON object only. "
            "Use the allowed enums exactly. "
            "If evidence is weak, use category='unknown', level='unknown', empty arrays, "
            "and null for missing cleaned text or unknown English level."
        )

        batches = self.prepare_for_llm(batch_size=batch_size, limit=limit)
        flat_records = [record for batch in batches for record in batch]
        results = {}
        failures = 0

        for position, record in enumerate(flat_records, start=1):
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = client.chat.completions.create(
                        model=model,
                        temperature=0,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": record['prompt']},
                        ],
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "job_extraction",
                                "strict": strict_mode,
                                "schema": schema,
                            },
                        },
                    )
                    content = response.choices[0].message.content or "{}"
                    parsed = json.loads(content)
                    normalized = self._normalize_llm_result(self.combined_df.loc[record['idx']], parsed)
                    results[record['idx']] = normalized
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < max_retries:
                        time.sleep(delay_seconds * attempt)
            else:
                failures += 1
                print(f"⚠️  LLM failed for idx={record['idx']}: {last_error}")

            if position % 25 == 0 or position == len(flat_records):
                print(f"   Processed {position}/{len(flat_records)} records with Groq")
            time.sleep(delay_seconds)

        self.llm_results = results
        self.apply_llm_results(results)
        print(f"✅ Groq enrichment complete: {len(results)} records updated, {failures} failures")
        return results

    def apply_llm_results(self, llm_results: Dict[int, Dict]) -> pd.DataFrame:
        """Merge LLM outputs back into the final database."""

        if self.final_db is None:
            self.create_final_database()

        for idx, result in llm_results.items():
            self.final_db.at[idx, 'title_normalized'] = result['title_normalized']
            self.final_db.at[idx, 'category'] = result['category']
            self.final_db.at[idx, 'level'] = result['level']
            self.final_db.at[idx, 'hard_skills'] = json.dumps(result['hard_skills'], ensure_ascii=False)
            self.final_db.at[idx, 'soft_skills'] = json.dumps(result['soft_skills'], ensure_ascii=False)
            self.final_db.at[idx, 'tech_stack'] = json.dumps(result['tech_stack'], ensure_ascii=False)
            self.final_db.at[idx, 'requirements_clean'] = result['requirements_clean'] or self.final_db.at[idx, 'requirements_raw']
            self.final_db.at[idx, 'responsibilities_clean'] = result['responsibilities_clean'] or self.final_db.at[idx, 'responsibilities_raw']
            self.final_db.at[idx, 'english_mention'] = result['english_mention']
            self.final_db.at[idx, 'english_required'] = result['english_required']
            self.final_db.at[idx, 'english_level'] = result['english_level']
            self.final_db.at[idx, 'llm_confidence'] = result['llm_confidence']
            self.final_db.at[idx, 'extraction_method'] = 'mixed'

        self.final_db = self._refresh_duplicate_flags(self.final_db)
        return self.final_db
    
    def create_final_database(self) -> pd.DataFrame:
        """Create final unified database"""
        
        if self.combined_df is None:
            return None
        
        db = pd.DataFrame()
        
        # Add all required fields
        db['id'] = [str(uuid.uuid4()) for _ in range(len(self.combined_df))]
        db['source'] = self.combined_df['source']
        db['source_id'] = self.combined_df['source_id']
        db['source_url'] = self.combined_df['source_url']
        db['title'] = self.combined_df['title']
        db['title_normalized'] = self.combined_df['title']  # Will be updated by LLM
        db['company'] = self.combined_df['company']
        db['city'] = self.combined_df['city']
        db['category'] = 'unknown'  # Will be updated by LLM
        db['level'] = 'unknown'  # Will be updated by LLM
        
        db['experience_raw'] = self.combined_df['experience_raw']
        db['experience_min'] = self.combined_df['experience_min'].astype('Int64')
        db['experience_max'] = self.combined_df['experience_max'].astype('Int64')
        db['employment'] = self.combined_df['employment']
        db['work_format'] = self.combined_df['work_format']
        
        db['salary_from'] = self.combined_df['salary_from'].astype('Int64')
        db['salary_to'] = self.combined_df['salary_to'].astype('Int64')
        db['salary_avg'] = self.combined_df['salary_avg']
        db['currency'] = self.combined_df['currency']
        db['salary_raw'] = self.combined_df['salary_raw']
        db['salary_gross'] = self.combined_df['salary_gross']
        
        db['description'] = self.combined_df['description_raw']
        db['description_clean'] = self.combined_df['description_raw']
        db['requirements_raw'] = self.combined_df['requirements_raw']
        db['requirements_clean'] = ''  # Will be updated by LLM
        db['responsibilities_raw'] = self.combined_df['responsibilities_raw']
        db['responsibilities_clean'] = ''  # Will be updated by LLM
        
        db['skills_raw'] = self.combined_df['skills_raw']
        db['hard_skills'] = None
        db['soft_skills'] = None
        db['tech_stack'] = None
        
        db['english_mention'] = self.combined_df['english_mention']
        db['english_required'] = self.combined_df['english_required']
        db['english_level'] = self.combined_df['english_level']
        
        db['posted_at'] = self.combined_df['posted_at']
        db['scraped_at'] = datetime.now(timezone.utc)
        db['is_active'] = True
        
        db['extraction_method'] = 'rule_based'
        db['llm_confidence'] = 0.0

        db = self._refresh_duplicate_flags(db)
        
        self.final_db = db
        print(f"✅ Created final database: {len(db)} records, {len(db.columns)} columns")
        print(f"   Duplicates: {db['is_duplicate'].sum()}")
        
        return db

    def _refresh_duplicate_flags(self, db: pd.DataFrame) -> pd.DataFrame:
        """Recompute duplicate hashes and flags using source-aware logic."""

        def normalized_hash_text(text: Optional[str]) -> str:
            cleaned = normalize_whitespace(text).lower()
            cleaned = re.sub(r'[^a-zа-я0-9\s]+', ' ', cleaned, flags=re.IGNORECASE)
            return re.sub(r'\s+', ' ', cleaned).strip()

        def gen_hash(row):
            if row['source'] == 'telegram':
                content_fingerprint = normalized_hash_text(row['description_clean'] or row['description'] or '')
                base = content_fingerprint or normalized_hash_text(row['source_id'])
            else:
                description_text = row['description_clean'] or row['description'] or ''
                description_fingerprint = normalized_hash_text(description_text[:400])
                base = ' | '.join([
                    normalized_hash_text(row['title_normalized'] or row['title']),
                    normalized_hash_text(row['company']),
                    normalized_hash_text(row['city']),
                    description_fingerprint,
                ])
            return hashlib.md5(base.encode()).hexdigest()

        refreshed = db.copy()
        refreshed['duplicate_hash'] = refreshed.apply(gen_hash, axis=1)
        refreshed['is_duplicate'] = refreshed.duplicated(subset=['duplicate_hash'], keep='first')
        return refreshed
    
    def export(self):
        """Export to multiple formats"""
        
        if self.final_db is None:
            print("❌ No data to export. Run create_final_database first.")
            return
        
        # CSV
        csv_path = DATA_DIR / 'interim' / 'unified_job_database.csv'
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.final_db.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"✅ CSV: {csv_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        # SQLite
        import sqlite3
        
        # Prepare data for SQLite (convert timestamps to strings)
        db_sqlite = self.final_db.copy()
        if 'posted_at' in db_sqlite.columns:
            db_sqlite['posted_at'] = db_sqlite['posted_at'].astype(str)
        if 'scraped_at' in db_sqlite.columns:
            db_sqlite['scraped_at'] = db_sqlite['scraped_at'].astype(str)
        
        sqlite_path = DATA_DIR / 'interim' / 'job_vacancies.db'
        conn = sqlite3.connect(sqlite_path)
        db_sqlite.to_sql('vacancies', conn, if_exists='replace', index=False)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_source ON vacancies(source)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_category ON vacancies(category)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_level ON vacancies(level)')
        conn.commit()
        conn.close()
        print(f"✅ SQLite: {sqlite_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        print(f"\n✅ Exported to:")
        print(f"   • {csv_path.name}")
        print(f"   • {sqlite_path.name}")


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description='Job vacancy integration pipeline')
    parser.add_argument('--mode', choices=['clean', 'llm'], default='clean', help='Run data cleaning only or run Groq enrichment too')
    parser.add_argument('--model', default=DEFAULT_GROQ_MODEL, help='Groq model for --mode llm')
    parser.add_argument('--batch-size', type=int, default=10, help='Number of records grouped for LLM prep')
    parser.add_argument('--limit', type=int, default=None, help='Optional limit for LLM processing')
    parser.add_argument('--delay-seconds', type=float, default=0.5, help='Delay between Groq requests')
    args = parser.parse_args()
    
    print("🚀 Job Integration Pipeline Starting...\n")
    
    pipeline = JobIntegrationPipeline()
    
    # Step 1: Load
    print("Step 1: Loading data from all sources...")
    pipeline.load_all_sources()
    
    # Step 2: Clean
    print("\nStep 2: Cleaning and normalizing data...")
    pipeline.clean_data()
    
    # Step 3: Extract
    print("\nStep 3: Extracting structured fields...")
    pipeline.extract_fields()
    
    # Step 4: Create database
    print("\nStep 4: Creating final database...")
    pipeline.create_final_database()

    if args.mode == 'llm':
        print("\nStep 5: Processing with Groq...")
        try:
            pipeline.process_with_groq(
                model=args.model,
                batch_size=args.batch_size,
                limit=args.limit,
                delay_seconds=args.delay_seconds,
            )
        except RuntimeError as exc:
            print(f"❌ {exc}")
            return
    else:
        print("\nStep 5: Preparing batches for future LLM processing...")
        pipeline.prepare_for_llm(batch_size=args.batch_size)
    
    # Step 6: Export
    print("\nStep 6: Exporting data...")
    pipeline.export()
    
    print("\n✅ Pipeline complete!")
    print(f"\nTotal records: {len(pipeline.final_db)}")
    print(f"Sources: {pipeline.final_db['source'].value_counts().to_dict()}")


if __name__ == '__main__':
    main()
