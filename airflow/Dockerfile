FROM apache/airflow:3.3.2-python3.12

# The collector's libraries, pinned to the versions this Airflow release is tested with.
# "pipeline" is a named build context (see docker-compose.yml: additional_contexts).
COPY --from=pipeline requirements.txt /tmp/seekjobs-requirements.txt
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /tmp/seekjobs-requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"
