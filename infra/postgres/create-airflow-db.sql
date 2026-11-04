-- Runs once, when the Postgres volume is first created: a separate database for
-- Airflow's own metadata, next to the "seekjobs" database with the jobs.
CREATE DATABASE airflow;
