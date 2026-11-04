"""DAG integrity test — needs Airflow installed (runs in CI, or inside the Airflow container:
`docker compose exec airflow-scheduler python -m pytest /opt/airflow/tests`)."""
import os
import warnings
from pathlib import Path

import pytest

pytest.importorskip("airflow")

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("SEEKJOBS_PIPELINE_DIR", str(ROOT / "pipeline"))
DAGS = Path(os.environ.get("SEEKJOBS_DAGS_DIR", ROOT / "airflow" / "dags"))


@pytest.fixture(scope="module")
def dag():
    from airflow.dag_processing.dagbag import DagBag

    warnings.simplefilter("ignore")
    bag = DagBag(dag_folder=str(DAGS))
    assert bag.import_errors == {}
    return bag.get_dag("seekjobs_daily_vacancies")


def test_one_extract_task_per_channel(dag):
    import sys

    sys.path.insert(0, os.environ["SEEKJOBS_PIPELINE_DIR"])
    from scrapers.telegram import load_channels

    extracts = {t for t in dag.task_ids if t.startswith("extract_")}
    assert extracts == {f"extract_{c.handle}" for c in load_channels()}
    assert {"extract_devkz_jobs", "extract_itvacancykz", "extract_halyk_jumys"} <= extracts


def test_order_of_steps(dag):
    extracts = {t for t in dag.task_ids if t.startswith("extract_")}
    assert set(dag.get_task("prepare_database").downstream_task_ids) == extracts
    assert set(dag.get_task("transform_load").upstream_task_ids) == extracts
    assert dag.get_task("expire_old_jobs").upstream_task_ids == {"transform_load"}
    assert dag.get_task("quality_check").upstream_task_ids == {"expire_old_jobs"}


def test_daily_schedule_and_politeness(dag):
    assert str(dag.schedule) == "0 8 * * *"
    assert str(dag.timezone) == "Asia/Almaty"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.max_active_tasks == 3  # at most 3 channels fetched at once


def test_failure_handling(dag):
    assert dag.get_task("extract_devkz_jobs").retries == 2
    rule = dag.get_task("transform_load").trigger_rule
    assert getattr(rule, "value", rule) == "all_done"  # one broken channel doesn't block the rest
    assert dag.get_task("quality_check").retries == 0  # a data problem is reported, not retried
