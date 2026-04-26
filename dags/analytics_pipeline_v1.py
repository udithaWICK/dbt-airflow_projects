from datetime import datetime,timedelta
#from airflow.operators.python import PythonOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
#from airflow.operators.bash import BashOperator
from airflow import DAG

def notify_success(**context):
    print(f"SUCCESS: DAG {context['dag'].dag_id} run {context['run_id']} ")

def notify_failure(**context):
    print(f"FAILURE: DAG {context['dag'].dag_id} task {context['task_instance'].task_id} ")
    
    
default_args = {
    'owner': 'uditha',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5)
}

with DAG(
    dag_id ="analytics_pipeline_v1",
    default_args=default_args,
    description="Raw to mart analytics pipeline with dbt checks",
    start_date=datetime(2026,4,20),
    schedule="0 7 * * *",
    catchup=False,
    max_active_runs=1,
    on_failure_callback=notify_failure,
    tags=["analytics","dbt","interview"],
) as dag:
    
    extract_raw_data = BashOperator(
        task_id="extract_raw_data",
        bash_command="echo 'Extract raw data step'; sleep 2",
        execution_timeout=timedelta(minutes=20),
    )

    stage_data = BashOperator(
        task_id="stage_data",
        bash_command="echo 'Stage data step'; sleep 2",
        execution_timeout=timedelta(minutes=20),
    )

    dbt_run_models = BashOperator(
    task_id="dbt_run_models",
    bash_command="source /root/.venv/dbt-airflow/bin/activate && cd /root/cl-dbt/my_dbt_project && dbt run --profiles-dir /root/.dbt",
    execution_timeout=timedelta(minutes=20),
)

    dbt_test_models = BashOperator(
    task_id="dbt_test_models",
    bash_command="source /root/.venv/dbt-airflow/bin/activate && cd /root/cl-dbt/my_dbt_project && dbt test --profiles-dir /root/.dbt",
    execution_timeout=timedelta(minutes=20),
)

    publish_mart = BashOperator(
        task_id="publish_mart",
        bash_command="echo 'Publish mart step'; sleep 2",
        execution_timeout=timedelta(minutes=20),
    )

    notify_status = PythonOperator(
        task_id="notify_operator",
        python_callable=notify_success,
       
    )

    extract_raw_data >> stage_data >> dbt_run_models >> dbt_test_models >> publish_mart >> notify_status

