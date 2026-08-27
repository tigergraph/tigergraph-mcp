# Loading from a data warehouse

TigerGraph can read directly from a data warehouse over JDBC. Instead of
pointing a loading job at a file, you point it at a SQL query, and TigerGraph
loads the result set into vertices and edges.

Snowflake, BigQuery, and PostgreSQL are supported. See
[Load from a Data Warehouse](https://docs.tigergraph.com/tigergraph-server/4.2/data-loading/load-from-warehouse)
for the server-side reference.

## 1. Look up the configuration keys

Every data source type takes a different config shape. Ask the server-side
registry rather than guessing:

```
get_data_source_types(family="warehouse")
```

This answers locally, without contacting TigerGraph, and returns the required
keys, optional keys, and an example config for each type.

## 2. Create the data source

### Snowflake

```
create_data_source(
    data_source_name="sf1",
    data_source_type="snowflake",
    config={
        "connection.url": "jdbc:snowflake:/https:/ab12345.snowflakecomputing.com/?db=MYDB&schema=PUBLIC&role=LOADER",
        "connection.user": "tg_loader",
        "connection.password": "<password>",
    },
)
```

Notes:

- The database, schema, and role are **query parameters on `connection.url`**,
  not separate config keys.
- For key-pair authentication, add `private_key_file` to `connection.url`
  instead of supplying `connection.password`.
- The password is sent to TigerGraph but masked in the tool's response, so it
  does not appear in a conversation transcript.

### BigQuery

BigQuery puts its OAuth credentials in a nested `parameters` object rather than
at the top level:

```
create_data_source(
    data_source_name="bq1",
    data_source_type="bigquery",
    config={
        "ProjectId": "my-gcp-project",
        "OAuthType": 2,
        "parameters": {
            "OAuthRefreshToken": "<refresh token>",
            "OAuthClientId": "<client id>.apps.googleusercontent.com",
            "OAuthClientSecret": "<client secret>",
        },
    },
)
```

`OAuthType` 2 selects refresh-token authentication and is the documented path;
the three `parameters` keys are required for it. For large result sets, add
`EnableHighThroughputAPI`, `AllowLargeResults`, and `LargeResultDataset` to
`parameters`.

### PostgreSQL

PostgreSQL takes discrete connection keys instead of a JDBC URL:

```
create_data_source(
    data_source_name="pg1",
    data_source_type="postgresql",
    config={
        "host": "pg.internal",
        "port": 5432,
        "connection.user": "postgres",
        "connection.password": "<password>",
        "db.name": "postgres",
    },
)
```

## 3. Preview the data

```
preview_sample_data(
    data_source_name="sf1",
    file_path="SELECT * FROM MYDB.PUBLIC.PERSON",
    num_rows=10,
)
```

## 4. Create the loading job

A file entry names the data source and the query instead of a path:

```
create_loading_job(
    job_name="load_person",
    files=[{
        "file_alias": "f_person",
        "data_source": "sf1",
        "query": "SELECT id, name, age FROM MYDB.PUBLIC.PERSON",
        "separator": "|",
        "node_mappings": [{
            "vertex_type": "Person",
            "attribute_mappings": {"id": 0, "name": 1, "age": 2},
        }],
    }],
    run_job=True,
)
```

This generates:

```gsql
CREATE LOADING JOB load_person FOR GRAPH MyGraph {
  DEFINE FILENAME f_person = "$sf1:SELECT id, name, age FROM MYDB.PUBLIC.PERSON";

  LOAD f_person
    TO VERTEX Person VALUES($0, $1, $2)
    USING SEPARATOR="|";
}
```

### Columns are positional

`$0`, `$1`, … refer to the columns of the SELECT list in order, so
`attribute_mappings` must use integer indices. Mapping by column name is
rejected for warehouse-backed entries.

Because the mapping is positional, list the columns explicitly rather than
using `SELECT *` — otherwise a schema change in the warehouse silently shifts
every mapping.

## Databricks

TigerGraph has no Databricks data source type. Asked to create one, a 4.2.2
server answers:

```
"type" must be one of following: KAFKA, KAFKA_V2, S3, GCS, ABS, BIGQUERY,
SNOWFLAKE, POSTGRESQL, MIRRORMAKER, ICEBERG
```

There is no generic `jdbc` type either. `create_data_source` still forwards
whatever type you give it — the server decides — so asking for `databricks`
returns the message above along with the keys a known type would need.

Two routes work instead.

### Through the Iceberg catalog (preferred)

Databricks Unity Catalog exposes an Iceberg REST catalog endpoint, and
TigerGraph has an `iceberg` data source type:

```
create_data_source(
    data_source_name="dbx",
    data_source_type="iceberg",
    config={
        "iceberg.catalog.type": "rest",
        "iceberg.catalog.uri": "<Unity Catalog Iceberg REST endpoint>",
    },
)
```

This keeps the table in place rather than copying it. Confirm the catalog
endpoint and any additional authentication keys your server build expects —
the required pair above is what a 4.2.2 server enforces at creation time.

### Through an object store export

Otherwise, write the table to cloud storage the TigerGraph server can read and
use an object store data source:

```sql
-- Databricks
CREATE TABLE main.default.person_export
USING CSV LOCATION 's3://my-bucket/exports/person/'
AS SELECT id, name, age FROM main.default.person;
```

```
create_data_source(
    data_source_name="dbx_export",
    data_source_type="s3",
    config={"access.key": "<key>", "secret.key": "<secret>"},
)
```

Then load from `s3a://my-bucket/exports/person/` as a normal file-backed job.
