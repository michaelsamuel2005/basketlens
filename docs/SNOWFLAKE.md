# Running the SQL on Snowflake

**Status: not run on Snowflake.** The models in `src/basketlens/sql/` use CREATE TABLE AS, joins, CTEs, window functions, CASE,
COALESCE and standard aggregates, and were written to avoid DuckDB-only syntax, but they have been run only on DuckDB. Do not
describe them as "run on Snowflake" until you have done the steps below and they pass.

1. Create a trial account, a warehouse (X-Small) and a schema. Upload the eight Parquet files in `data/parquet/` to an internal stage
   (`PUT file://... @stage`) and `COPY INTO raw_<name> FROM @stage FILE_FORMAT=(TYPE=PARQUET) MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE`.
2. Replace `CAST(transaction_timestamp AS DATE)` with `TO_DATE(transaction_timestamp)` if the load keeps it as a string.
3. `01_warehouse.sql`: the `ROW_NUMBER() ... ORDER BY COUNT(*) DESC` calendar query is valid as written. Replace the boolean columns
   `is_private` and `is_sale` with `BOOLEAN` expressions (already boolean in Snowflake).
4. Run every `.sql` file with `{{parameter}}` replaced (the Python runner in `sqlrun.py` does the same replacement).
5. Compare row counts and the supplier's sales ($19,125.12 in cold cereal) with the DuckDB results in `outputs/`.
