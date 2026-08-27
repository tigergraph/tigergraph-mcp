# Copyright 2025-2026 TigerGraph Inc.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file or https://www.apache.org/licenses/LICENSE-2.0
#
# Permission is granted to use, copy, modify, and distribute this software
# under the License. The software is provided "AS IS", without warranty.

"""Registry of supported data source types and their configuration keys.

TigerGraph accepts an opaque JSON config for every data source, so the shape is
defined entirely by the ``type`` value. The conventions differ per type (dotted
lowercase for Snowflake, Hadoop-style property names for S3), which is why this
is a declarative table rather than a class hierarchy.

The type list and each type's required keys were read back from a running
TigerGraph 4.2.2 server, which rejects unknown types outright and names the
keys it is missing. Unknown *keys*, by contrast, are stored as-is, so this
module warns about them rather than rejecting them.
"""

from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode

# Key name fragments that mark a value as a credential. Kept narrow on purpose:
# a broader list would match S3's "...aws.credentials.provider", whose value is
# a class name, not a secret.
_SECRET_FRAGMENTS = ("password", "secret", "token", "private_key", "api_key", "apikey")

REDACTED = "***"

DOC_URL = (
    "https://docs.tigergraph.com/tigergraph-server/4.2/data-loading/load-from-warehouse"
)


@dataclass(frozen=True)
class DataSourceTypeSpec:
    """Describes one data source type accepted by TigerGraph."""

    type_value: str
    label: str
    family: str  # "object_store" | "warehouse" | "stream" | "filesystem"
    required_keys: Tuple[str, ...] = ()
    optional_keys: Tuple[str, ...] = ()
    secret_keys: Tuple[str, ...] = ()
    url_key: Optional[str] = None
    url_prefix: Optional[str] = None
    # Some types nest driver options one level down, e.g. BigQuery's
    # "parameters" object. Keys inside it are checked separately.
    nested_container: Optional[str] = None
    nested_known_keys: Tuple[str, ...] = ()
    # Hook for rules the flat table cannot express, e.g. keys that are only
    # required for one authentication mode. Returns (errors, warnings).
    validator: Optional[Callable[[Dict[str, Any]], Tuple[List[str], List[str]]]] = None
    example: Dict[str, Any] = field(default_factory=dict)
    notes: Tuple[str, ...] = ()

    @property
    def known_keys(self) -> Tuple[str, ...]:
        keys = self.required_keys + self.optional_keys
        if self.nested_container:
            keys += (self.nested_container,)
        return keys

    def enforces_required(self) -> bool:
        return bool(self.required_keys)


# BigQuery's OAuthType selects the credential set. Verified against
# TigerGraph 4.2.2: only 0 and 2 are accepted, type 2 needs one of two token
# keys, and type 0 needs a service account email.
_BIGQUERY_OAUTH_SERVICE_ACCOUNT = 0
_BIGQUERY_OAUTH_TOKEN = 2
_BIGQUERY_TOKEN_KEYS = ("OAuthRefreshToken", "OAuthAccessToken")
_BIGQUERY_SERVICE_ACCOUNT_KEY = "OAuthServiceAcctEmail"


def _validate_bigquery(config: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    oauth_type = config.get("OAuthType")
    if oauth_type is None:
        return errors, warnings
    if isinstance(oauth_type, bool) or not isinstance(oauth_type, int):
        errors.append(
            f"'OAuthType' must be the number 0 or 2, not a string (got {oauth_type!r})."
        )
        return errors, warnings
    if oauth_type not in (_BIGQUERY_OAUTH_SERVICE_ACCOUNT, _BIGQUERY_OAUTH_TOKEN):
        errors.append(f"'OAuthType' must be 0 or 2 (got {oauth_type}).")
        return errors, warnings

    parameters = config.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    if oauth_type == _BIGQUERY_OAUTH_TOKEN:
        if not any(parameters.get(k) for k in _BIGQUERY_TOKEN_KEYS):
            errors.append(
                "OAuthType 2 requires one of "
                f"{' or '.join('parameters.' + k for k in _BIGQUERY_TOKEN_KEYS)}."
            )
    elif not parameters.get(_BIGQUERY_SERVICE_ACCOUNT_KEY):
        errors.append(
            f"OAuthType 0 requires 'parameters.{_BIGQUERY_SERVICE_ACCOUNT_KEY}'."
        )

    return errors, warnings


# Types and required keys below were read back from a TigerGraph 4.2.2 server,
# which rejects any type outside this list and names the keys it needs.
DATA_SOURCE_TYPES: Dict[str, DataSourceTypeSpec] = {
    "s3": DataSourceTypeSpec(
        type_value="s3",
        label="Amazon S3",
        family="object_store",
        required_keys=("access.key", "secret.key"),
        optional_keys=("file.reader.settings.fs.s3a.aws.credentials.provider",),
        secret_keys=("access.key", "secret.key"),
        example={"access.key": "<aws access key>", "secret.key": "<aws secret key>"},
        notes=(
            "Both keys are required and must be non-empty, including for public "
            "buckets.",
            "File paths use the s3a:// scheme.",
        ),
    ),
    "gcs": DataSourceTypeSpec(
        type_value="gcs",
        label="Google Cloud Storage",
        family="object_store",
        required_keys=("project.id", "client.email", "private.key.id", "private.key"),
        secret_keys=("private.key", "private.key.id"),
        example={
            "project.id": "<gcp project>",
            "client.email": "<service account email>",
            "private.key.id": "<key id>",
            "private.key": "<service account private key>",
        },
        notes=(
            "Key names are dot-separated, not the underscored names used in a "
            "service account JSON file.",
        ),
    ),
    "abs": DataSourceTypeSpec(
        type_value="abs",
        label="Azure Blob Storage",
        family="object_store",
        required_keys=("client.id", "client.secret", "tenant.id"),
        secret_keys=("client.secret",),
        example={
            "client.id": "<application id>",
            "client.secret": "<client secret>",
            "tenant.id": "<tenant id>",
        },
        notes=("Also accepted as 'azure_blob'; the server's type value is 'abs'.",),
    ),
    "kafka": DataSourceTypeSpec(
        type_value="kafka",
        label="External Kafka",
        family="stream",
        required_keys=("bootstrap.servers",),
        example={"bootstrap.servers": "<host:9092>"},
    ),
    "kafka_v2": DataSourceTypeSpec(
        type_value="kafka_v2",
        label="External Kafka (v2 connector)",
        family="stream",
        required_keys=("bootstrap.servers",),
        example={"bootstrap.servers": "<host:9092>"},
    ),
    "mirrormaker": DataSourceTypeSpec(
        type_value="mirrormaker",
        label="Kafka MirrorMaker",
        family="stream",
        required_keys=("source.cluster.bootstrap.servers",),
        example={"source.cluster.bootstrap.servers": "<host:9092>"},
    ),
    "iceberg": DataSourceTypeSpec(
        type_value="iceberg",
        label="Apache Iceberg",
        family="lakehouse",
        required_keys=("iceberg.catalog.type", "iceberg.catalog.uri"),
        example={
            "iceberg.catalog.type": "rest",
            "iceberg.catalog.uri": "<catalog endpoint>",
        },
        notes=(
            "Reads Iceberg tables through a catalog endpoint. Warehouses that "
            "expose an Iceberg REST catalog, such as Databricks Unity Catalog, "
            "can be reached this way.",
        ),
    ),
    "snowflake": DataSourceTypeSpec(
        type_value="snowflake",
        label="Snowflake",
        family="warehouse",
        required_keys=("connection.url", "connection.user", "connection.password"),
        secret_keys=("connection.password",),
        url_key="connection.url",
        url_prefix="jdbc:snowflake:",
        example={
            "connection.url": (
                "jdbc:snowflake:/https:/<account_id>.snowflakecomputing.com/"
                "?db=<db>&schema=<schema>&role=<role>"
            ),
            "connection.user": "<username>",
            "connection.password": "<password>",
        },
        notes=(
            "Database, schema, and role are query parameters on connection.url, "
            "not separate keys.",
            "For key-pair authentication add private_key_file to connection.url "
            "instead of using connection.password.",
            "Loading jobs read from this source with "
            "'$<data_source>:SELECT ... FROM <db>.<schema>.<table>'.",
        ),
    ),
    "bigquery": DataSourceTypeSpec(
        type_value="bigquery",
        label="Google BigQuery",
        family="warehouse",
        required_keys=("ProjectId", "OAuthType"),
        nested_container="parameters",
        nested_known_keys=(
            "OAuthRefreshToken",
            "OAuthAccessToken",
            "OAuthClientId",
            "OAuthClientSecret",
            "OAuthServiceAcctEmail",
            "EnableHighThroughputAPI",
            "AllowLargeResults",
            "LargeResultDataset",
        ),
        validator=_validate_bigquery,
        example={
            "ProjectId": "<gcp project>",
            "OAuthType": 2,
            "parameters": {"OAuthRefreshToken": "<refresh token>"},
        },
        notes=(
            "Credentials go inside the nested 'parameters' object, not at the "
            "top level.",
            "OAuthType 2 uses a token and needs OAuthRefreshToken or "
            "OAuthAccessToken; OAuthType 0 uses a service account and needs "
            "OAuthServiceAcctEmail.",
            "For large result sets add EnableHighThroughputAPI, AllowLargeResults, "
            "and LargeResultDataset to 'parameters'.",
            "Loading jobs read from this source with "
            "'$<data_source>:SELECT ... FROM <project>.<dataset>.<table>'.",
        ),
    ),
    "postgresql": DataSourceTypeSpec(
        type_value="postgresql",
        label="PostgreSQL",
        family="warehouse",
        required_keys=("host", "connection.user", "connection.password"),
        optional_keys=("port", "db.name"),
        secret_keys=("connection.password",),
        example={
            "host": "<hostname>",
            "port": 5432,
            "connection.user": "<username>",
            "connection.password": "<password>",
            "db.name": "<database>",
        },
        notes=(
            "Connection details are separate keys here; there is no JDBC URL.",
            "Loading jobs read from this source with "
            "'$<data_source>:SELECT ... FROM <schema>.<table>'.",
        ),
    ),
}

# Alternate spellings accepted from callers, mapped to the server's type value.
TYPE_ALIASES: Dict[str, str] = {
    "azure_blob": "abs",
    "azure": "abs",
    "azureblob": "abs",
    "blob": "abs",
    "s3a": "s3",
    "google_cloud_storage": "gcs",
    "kafka2": "kafka_v2",
    "kafkav2": "kafka_v2",
    "snowflakedb": "snowflake",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "pg": "postgresql",
    "bq": "bigquery",
    "google_bigquery": "bigquery",
}

SUPPORTED_TYPE_NAMES: Tuple[str, ...] = tuple(DATA_SOURCE_TYPES) + tuple(TYPE_ALIASES)


def normalize_type(name: str) -> str:
    """Normalize a caller-supplied type name to the server's type value.

    Unknown names pass through lowercased rather than raising: TigerGraph is
    the authority on which types it accepts, and this table can lag a newer
    server. Only known aliases are rewritten.
    """
    key = (name or "").strip().lower()
    return TYPE_ALIASES.get(key, key)


def resolve_type(name: str) -> str:
    """Normalize a name, requiring it to be one this table knows.

    Raises:
        ValueError: if the name is not a known type or alias.
    """
    key = normalize_type(name)
    if key in DATA_SOURCE_TYPES:
        return key

    close = get_close_matches(key, SUPPORTED_TYPE_NAMES, n=3, cutoff=0.5)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ValueError(
        f"Unknown data source type '{name}'. "
        f"Supported types: {', '.join(DATA_SOURCE_TYPES)}.{hint}"
    )


def find_spec(name: str) -> Optional[DataSourceTypeSpec]:
    """Return the spec for a type name or alias, or None if unrecognized."""
    return DATA_SOURCE_TYPES.get(normalize_type(name))


def get_spec(name: str) -> DataSourceTypeSpec:
    """Return the spec for a type name or alias."""
    return DATA_SOURCE_TYPES[resolve_type(name)]


def guidance(type_value: str, config: Dict[str, Any]) -> List[str]:
    """Hints to attach to a failed create/update, based on what we know.

    The server has already given its own reason by this point; these add the
    key names and a worked example it does not include.
    """
    spec = find_spec(type_value)
    if spec is None:
        close = get_close_matches(
            normalize_type(type_value), SUPPORTED_TYPE_NAMES, n=3, cutoff=0.5
        )
        hints = [
            f"'{type_value}' is not a type this client knows about. If the server "
            "rejected the type, it lists the ones it accepts in the message above.",
            "List the types this client knows: get_data_source_types()",
        ]
        if close:
            hints.insert(0, f"Did you mean: {', '.join(close)}?")
        return hints

    errors, warnings = validate_config(spec.type_value, config)
    hints = []
    if errors:
        hints.append("Likely cause: " + " ".join(errors))
    hints.extend(f"Note: {w}" for w in warnings)
    if spec.required_keys:
        hints.append(
            f"Required keys for {spec.label}: {', '.join(spec.required_keys)}"
        )
    hints.append(f"Example config: {spec.example}")
    hints.extend(spec.notes)
    hints.append(f"Reference: {DOC_URL}")
    return hints


def validate_config(
    type_value: str, config: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """Check a config dict against its type's spec.

    Returns:
        (errors, warnings). Errors are conditions the server will certainly
        reject. Warnings cover keys this table does not recognize, which may
        still be valid on a newer server, so callers should proceed.
    """
    spec = get_spec(type_value)
    errors: List[str] = []
    warnings: List[str] = []

    supplied = {k for k in config if k != "type"}

    for key in spec.required_keys:
        if key not in supplied or config[key] in (None, ""):
            errors.append(f"Missing required key '{key}' for {spec.label} data sources.")

    if spec.url_key and spec.url_prefix:
        url = config.get(spec.url_key)
        if isinstance(url, str) and url and not url.startswith(spec.url_prefix):
            errors.append(
                f"'{spec.url_key}' must start with '{spec.url_prefix}' "
                f"for {spec.label} data sources (got '{url.split('?')[0]}')."
            )

    if spec.validator:
        extra_errors, extra_warnings = spec.validator(config)
        errors.extend(extra_errors)
        warnings.extend(extra_warnings)

    if spec.nested_container and spec.nested_known_keys:
        nested = config.get(spec.nested_container)
        if nested is not None and not isinstance(nested, dict):
            errors.append(
                f"'{spec.nested_container}' must be an object for {spec.label} "
                "data sources."
            )
        elif isinstance(nested, dict):
            for key in sorted(set(nested) - set(spec.nested_known_keys)):
                close = get_close_matches(key, spec.nested_known_keys, n=1, cutoff=0.6)
                if close:
                    warnings.append(
                        f"Unrecognized key '{spec.nested_container}.{key}' — "
                        f"did you mean '{close[0]}'?"
                    )
                else:
                    warnings.append(
                        f"Key '{spec.nested_container}.{key}' is not in the known key "
                        f"list for {spec.label}; passing it through unchanged."
                    )

    if spec.known_keys:
        for key in sorted(supplied - set(spec.known_keys)):
            close = get_close_matches(key, spec.known_keys, n=1, cutoff=0.6)
            if close:
                warnings.append(f"Unrecognized key '{key}' — did you mean '{close[0]}'?")
            else:
                warnings.append(
                    f"Key '{key}' is not in the known key list for {spec.label}; "
                    "passing it through unchanged."
                )

    return errors, warnings


def _is_secret_key(key: str, spec_secrets: Tuple[str, ...]) -> bool:
    if key in spec_secrets:
        return True
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SECRET_FRAGMENTS)


def _redact_url(url: str) -> str:
    """Mask credential-looking query parameters inside a JDBC URL."""
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    params = parse_qsl(query, keep_blank_values=True)
    if not params:
        return url
    masked = [
        (k, REDACTED if _is_secret_key(k, ()) else v) for k, v in params
    ]
    return f"{base}?{urlencode(masked, safe='<>')}"


def redact(type_value: Optional[str], config: Any) -> Any:
    """Return a copy of a config with credential values masked.

    Applied to every data source read so passwords never reach a transcript.
    Unknown types still get the name-based masking.
    """
    try:
        spec_secrets = get_spec(type_value).secret_keys if type_value else ()
        url_key = get_spec(type_value).url_key if type_value else None
    except (ValueError, KeyError):
        spec_secrets, url_key = (), None

    def _walk(value: Any, key: Optional[str] = None) -> Any:
        if isinstance(value, dict):
            inner_type = value.get("type")
            inner_secrets = spec_secrets
            inner_url_key = url_key
            if isinstance(inner_type, str) and inner_type.lower() in DATA_SOURCE_TYPES:
                inner_spec = DATA_SOURCE_TYPES[inner_type.lower()]
                inner_secrets = inner_spec.secret_keys
                inner_url_key = inner_spec.url_key
            return {
                k: (
                    REDACTED
                    if _is_secret_key(k, inner_secrets)
                    else _redact_url(v)
                    if k == inner_url_key and isinstance(v, str)
                    else _walk(v, k)
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_walk(item, key) for item in value]
        return value

    return _walk(config)


def describe_type(spec: DataSourceTypeSpec) -> Dict[str, Any]:
    """Render one spec for the get_data_source_types tool."""
    return {
        "type": spec.type_value,
        "label": spec.label,
        "family": spec.family,
        "required_keys": list(spec.required_keys),
        "optional_keys": list(spec.optional_keys),
        "aliases": sorted(k for k, v in TYPE_ALIASES.items() if v == spec.type_value),
        "example_config": spec.example,
        "notes": list(spec.notes),
    }


def describe_all(family: Optional[str] = None) -> List[Dict[str, Any]]:
    """Render the registry, optionally filtered to one family."""
    return [
        describe_type(spec)
        for spec in DATA_SOURCE_TYPES.values()
        if family is None or spec.family == family
    ]
