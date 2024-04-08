from joblib import delayed, Parallel
import backoff
import coloredlogs
import logging
import os
import pathlib
import psycopg
import sys
import textwrap
import time

logger = logging.getLogger(__name__)
coloredlogs.install(
    level=logging.INFO,
    fmt="%(asctime)s %(name)s [%(threadName)s] %(levelname)s: %(message)s",
)

steampipe_database_port = os.environ.get("STEAMPIPE_DATABASE_PORT")
steampipe_install_dir = os.environ.get("STEAMPIPE_INSTALL_DIR")
steampipe_install_dir = (
    pathlib.Path(steampipe_install_dir)
    if steampipe_install_dir
    else pathlib.Path.home() / ".steampipe"
)


def process_account(account, connection):
    logger.info(f"Processing account {account} ({connection})...")
    connection_name = f"aws_{account}_{connection}"
    configuration = textwrap.dedent(
        f"""\
        connection "{connection_name}" {{
            plugin              = plugin.aws
            default_region      = "eu-west-3"
            regions             = ["all"]
        }}
        """
    )
    steampipe_config_path = steampipe_install_dir / "config" / f"{connection_name}.spc"
    with open(steampipe_config_path, "w") as f:
        f.write(configuration)

    # Leave steampipe some time to pick up the configuration changes
    time.sleep(2)

    # Connect to steampipe service with psycopg client
    steampipe_conn = psycopg.connect(
        host="localhost",
        dbname="steampipe",
        user="steampipe",
        port=steampipe_database_port,
        password="steampipe",
    )

    @backoff.on_exception(
        backoff.constant,
        interval=1,
        jitter=None,
        on_backoff=lambda details: steampipe_conn.rollback(),
        exception=(
            psycopg.errors.FdwError,
            psycopg.errors.InFailedSqlTransaction,
            psycopg.errors.UndefinedTable,
        ),
        max_tries=15,
    )
    def check_connection():
        logger.info(f"Checking connection for account {account}...")
        cur = steampipe_conn.execute(f"SET search_path TO {connection_name},public")
        cur = steampipe_conn.execute(
            f"SELECT 1 FROM aws_account WHERE account_id = '{account}'"
        )
        assert cur.rowcount == 1

    check_connection()

    # Run query
    cur = steampipe_conn.cursor(row_factory=psycopg.rows.dict_row)
    cur.execute("SELECT * from aws_s3_bucket")
    records = cur.fetchall()
    logger.info(f"Found {len(records)} resources: {records}")

    # Cleanup
    steampipe_conn.close()
    os.remove(steampipe_config_path)


if __name__ == "__main__":
    accounts = [sys.argv[1]] * 10
    results = Parallel(n_jobs=6, backend="threading")(
        delayed(process_account)(accounts[i], i) for i in range(len(accounts))
    )
