from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True)
class PageDefinition:
    key: str
    label: str
    icon: str
    filename: str


PAGE_DEFINITIONS = [
    PageDefinition("market_overview", "Market Overview", "🏠", "1_market_overview.py"),
    PageDefinition("salary_analytics", "Salary Analytics", "💰", "2_salary_analytics.py"),
    PageDefinition("skills_demand", "Skills Demand", "🛠️", "3_skills_demand.py"),
    PageDefinition("companies", "Companies", "🏢", "4_companies.py"),
]


def load_page_module(page: PageDefinition) -> ModuleType:
    pages_dir = Path(__file__).resolve().parent
    file_path = pages_dir / page.filename
    module_name = f"app.pages.{page.key}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load page module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
