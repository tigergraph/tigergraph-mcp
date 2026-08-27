"""Tests for tigergraph_mcp.tools.datasource_types."""

import unittest

from tigergraph_mcp.tools.datasource_types import (
    DATA_SOURCE_TYPES,
    REDACTED,
    TYPE_ALIASES,
    describe_all,
    find_spec,
    get_spec,
    guidance,
    normalize_type,
    redact,
    resolve_type,
    validate_config,
)

SNOWFLAKE_URL = (
    "jdbc:snowflake:/https:/ab12345.snowflakecomputing.com/"
    "?db=MYDB&schema=PUBLIC&role=LOADER"
)
SNOWFLAKE_CONFIG = {
    "connection.url": SNOWFLAKE_URL,
    "connection.user": "tg_loader",
    "connection.password": "s3cr3t",
}


class TestRegistryIntegrity(unittest.TestCase):

    def test_every_alias_points_at_a_real_type(self):
        for alias, target in TYPE_ALIASES.items():
            self.assertIn(target, DATA_SOURCE_TYPES, f"alias '{alias}' is dangling")

    def test_type_value_matches_registry_key(self):
        for key, spec in DATA_SOURCE_TYPES.items():
            self.assertEqual(key, spec.type_value)

    def test_secret_keys_are_declared_keys(self):
        for spec in DATA_SOURCE_TYPES.values():
            for secret in spec.secret_keys:
                self.assertIn(secret, spec.known_keys, f"{spec.type_value}/{secret}")

    def test_examples_satisfy_their_own_required_keys(self):
        for spec in DATA_SOURCE_TYPES.values():
            if not spec.required_keys:
                continue
            errors, _ = validate_config(spec.type_value, spec.example)
            self.assertEqual(errors, [], f"{spec.type_value} example is invalid")

    def test_registry_matches_the_server_type_list(self):
        # Read back from TigerGraph 4.2.2, which rejects anything else:
        # "type" must be one of KAFKA, KAFKA_V2, S3, GCS, ABS, BIGQUERY,
        # SNOWFLAKE, POSTGRESQL, MIRRORMAKER, ICEBERG.
        self.assertEqual(
            sorted(DATA_SOURCE_TYPES),
            sorted(["kafka", "kafka_v2", "s3", "gcs", "abs", "bigquery",
                    "snowflake", "postgresql", "mirrormaker", "iceberg"]),
        )

    def test_local_is_not_a_data_source_type(self):
        # The server rejects it; local files are loaded with
        # run_loading_job_with_file instead.
        self.assertNotIn("local", DATA_SOURCE_TYPES)
        self.assertNotIn("local", TYPE_ALIASES)

    def test_databricks_is_not_advertised(self):
        # TigerGraph 4.2 does not document a Databricks data source type;
        # advertising one would produce a server-side failure at create time.
        self.assertNotIn("databricks", DATA_SOURCE_TYPES)
        self.assertNotIn("databricks", TYPE_ALIASES)


class TestResolveType(unittest.TestCase):

    def test_canonical_and_case_insensitive(self):
        self.assertEqual(resolve_type("snowflake"), "snowflake")
        self.assertEqual(resolve_type("SnowFlake"), "snowflake")
        self.assertEqual(resolve_type("  s3 "), "s3")

    def test_azure_blob_alias_maps_to_abs(self):
        self.assertEqual(resolve_type("azure_blob"), "abs")

    def test_unknown_type_suggests_close_match(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_type("snowflak")
        self.assertIn("snowflake", str(ctx.exception))

    def test_unknown_type_lists_supported(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_type("redshift")
        self.assertIn("Supported types", str(ctx.exception))


class TestValidateConfig(unittest.TestCase):

    def test_valid_snowflake_config(self):
        errors, warnings = validate_config("snowflake", SNOWFLAKE_CONFIG)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_required_key_is_an_error(self):
        config = dict(SNOWFLAKE_CONFIG)
        del config["connection.password"]
        errors, _ = validate_config("snowflake", config)
        self.assertEqual(len(errors), 1)
        self.assertIn("connection.password", errors[0])

    def test_empty_required_value_is_an_error(self):
        config = {**SNOWFLAKE_CONFIG, "connection.user": ""}
        errors, _ = validate_config("snowflake", config)
        self.assertTrue(any("connection.user" in e for e in errors))

    def test_wrong_jdbc_prefix_is_an_error(self):
        config = {**SNOWFLAKE_CONFIG, "connection.url": "jdbc:postgresql://host/db"}
        errors, _ = validate_config("snowflake", config)
        self.assertTrue(any("jdbc:snowflake:" in e for e in errors))

    def test_error_message_does_not_leak_url_query_string(self):
        config = {**SNOWFLAKE_CONFIG, "connection.url": "jdbc:mysql://h/?password=leak"}
        errors, _ = validate_config("snowflake", config)
        self.assertTrue(errors)
        self.assertNotIn("leak", " ".join(errors))

    def test_typo_key_warns_with_suggestion(self):
        config = {**SNOWFLAKE_CONFIG, "connection.usr": "x"}
        errors, warnings = validate_config("snowflake", config)
        self.assertEqual(errors, [])
        self.assertTrue(any("connection.user" in w for w in warnings))

    def test_unknown_key_warns_but_does_not_error(self):
        config = {**SNOWFLAKE_CONFIG, "some.future.option": "1"}
        errors, warnings = validate_config("snowflake", config)
        self.assertEqual(errors, [])
        self.assertTrue(any("some.future.option" in w for w in warnings))

    def test_s3_requires_both_credential_keys(self):
        # Verified against TigerGraph 4.2.2: both keys are required and must be
        # non-empty, even when an anonymous credentials provider is supplied.
        errors, _ = validate_config("s3", {})
        self.assertTrue(any("access.key" in e for e in errors))
        self.assertTrue(any("secret.key" in e for e in errors))

    def test_s3_anonymous_provider_alone_is_rejected(self):
        provider = "file.reader.settings.fs.s3a.aws.credentials.provider"
        errors, _ = validate_config("s3", {provider: "org.apache.hadoop..."})
        self.assertTrue(errors)

    def test_gcs_keys_are_dot_separated(self):
        errors, _ = validate_config("gcs", {
            "project.id": "p", "client.email": "e",
            "private.key.id": "i", "private.key": "k",
        })
        self.assertEqual(errors, [])

    def test_gcs_underscored_keys_are_rejected(self):
        errors, _ = validate_config("gcs", {
            "project_id": "p", "client_email": "e",
            "private_key_id": "i", "private_key": "k",
        })
        self.assertTrue(any("project.id" in e for e in errors))

    def test_type_key_in_config_is_ignored_by_validation(self):
        errors, warnings = validate_config(
            "snowflake", {**SNOWFLAKE_CONFIG, "type": "snowflake"}
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class TestRedact(unittest.TestCase):

    def test_password_is_masked(self):
        out = redact("snowflake", {"type": "snowflake", **SNOWFLAKE_CONFIG})
        self.assertEqual(out["connection.password"], REDACTED)
        self.assertEqual(out["connection.user"], "tg_loader")

    def test_url_is_preserved_when_it_holds_no_secret(self):
        out = redact("snowflake", SNOWFLAKE_CONFIG)
        self.assertIn("db=MYDB", out["connection.url"])

    def test_secret_url_parameter_is_masked(self):
        config = {
            **SNOWFLAKE_CONFIG,
            "connection.url": SNOWFLAKE_URL + "&private_key_file_pwd=abc",
        }
        out = redact("snowflake", config)
        self.assertNotIn("abc", out["connection.url"])
        self.assertIn("db=MYDB", out["connection.url"])

    def test_s3_provider_class_is_not_mistaken_for_a_secret(self):
        key = "file.reader.settings.fs.s3a.aws.credentials.provider"
        value = "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider"
        out = redact("s3", {"type": "s3", key: value})
        self.assertEqual(out[key], value)

    def test_s3_access_keys_are_masked(self):
        out = redact("s3", {"type": "s3", "access.key": "AKIA", "secret.key": "shh"})
        self.assertEqual(out["access.key"], REDACTED)
        self.assertEqual(out["secret.key"], REDACTED)

    def test_masks_a_list_of_sources_using_each_entry_type(self):
        out = redact(None, [
            {"name": "sf", "type": "snowflake", **SNOWFLAKE_CONFIG},
            {"name": "s3", "type": "s3", "access.key": "AKIA"},
        ])
        self.assertEqual(out[0]["connection.password"], REDACTED)
        self.assertEqual(out[1]["access.key"], REDACTED)

    def test_masks_nested_parameters_by_name(self):
        out = redact(None, {"type": "custom", "parameters": {"OAuthToken": "abc"}})
        self.assertEqual(out["parameters"]["OAuthToken"], REDACTED)

    def test_unknown_type_still_masks_by_name(self):
        out = redact("not_a_real_type", {"password": "abc", "host": "h"})
        self.assertEqual(out["password"], REDACTED)
        self.assertEqual(out["host"], "h")

    def test_input_is_not_mutated(self):
        config = {"type": "snowflake", **SNOWFLAKE_CONFIG}
        redact("snowflake", config)
        self.assertEqual(config["connection.password"], "s3cr3t")


class TestDescribeAll(unittest.TestCase):

    def test_lists_every_type(self):
        self.assertEqual(len(describe_all()), len(DATA_SOURCE_TYPES))

    def test_family_filter(self):
        warehouses = describe_all("warehouse")
        self.assertEqual(
            [t["type"] for t in warehouses], ["snowflake", "bigquery", "postgresql"]
        )

    def test_snowflake_entry_carries_keys_and_aliases(self):
        entry = next(t for t in describe_all() if t["type"] == "snowflake")
        self.assertEqual(
            entry["required_keys"],
            ["connection.url", "connection.user", "connection.password"],
        )
        self.assertTrue(entry["notes"])

    def test_abs_entry_lists_azure_blob_alias(self):
        entry = next(t for t in describe_all() if t["type"] == "abs")
        self.assertIn("azure_blob", entry["aliases"])

    def test_example_config_omits_the_type_key(self):
        for entry in describe_all():
            self.assertNotIn("type", entry["example_config"])

    def test_spec_lookup_accepts_alias(self):
        self.assertEqual(get_spec("azure_blob").type_value, "abs")


class TestBigQuery(unittest.TestCase):

    VALID = {
        "ProjectId": "tigergraph-dev",
        "OAuthType": 2,
        "parameters": {
            "OAuthRefreshToken": "rt",
            "OAuthClientId": "cid.apps.googleusercontent.com",
            "OAuthClientSecret": "cs",
        },
    }

    def test_valid_config(self):
        errors, warnings = validate_config("bigquery", self.VALID)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_top_level_key(self):
        config = {k: v for k, v in self.VALID.items() if k != "ProjectId"}
        errors, _ = validate_config("bigquery", config)
        self.assertTrue(any("ProjectId" in e for e in errors))

    def test_oauth_type_2_requires_parameters(self):
        errors, _ = validate_config("bigquery", {"ProjectId": "p", "OAuthType": 2})
        self.assertTrue(any("parameters" in e for e in errors))

    def test_oauth_type_2_accepts_a_refresh_token_alone(self):
        # The server needs only one of the two token keys.
        config = {**self.VALID, "parameters": {"OAuthRefreshToken": "rt"}}
        errors, _ = validate_config("bigquery", config)
        self.assertEqual(errors, [])

    def test_oauth_type_2_accepts_an_access_token_alone(self):
        config = {**self.VALID, "parameters": {"OAuthAccessToken": "at"}}
        errors, _ = validate_config("bigquery", config)
        self.assertEqual(errors, [])

    def test_oauth_type_0_requires_a_service_account_email(self):
        errors, _ = validate_config("bigquery", {"ProjectId": "p", "OAuthType": 0})
        self.assertTrue(any("OAuthServiceAcctEmail" in e for e in errors))

    def test_oauth_type_0_with_service_account_is_valid(self):
        errors, _ = validate_config("bigquery", {
            "ProjectId": "p", "OAuthType": 0,
            "parameters": {"OAuthServiceAcctEmail": "sa@example.com"},
        })
        self.assertEqual(errors, [])

    def test_unsupported_oauth_type_is_rejected(self):
        # The server accepts only 0 and 2.
        errors, _ = validate_config("bigquery", {"ProjectId": "p", "OAuthType": 3})
        self.assertTrue(any("0 or 2" in e for e in errors))

    def test_string_oauth_type_is_an_error(self):
        errors, _ = validate_config("bigquery", {"ProjectId": "p", "OAuthType": "2"})
        self.assertTrue(any("OAuthType" in e for e in errors))

    def test_non_object_parameters_is_an_error(self):
        config = {**self.VALID, "parameters": "OAuthRefreshToken=rt"}
        errors, _ = validate_config("bigquery", config)
        self.assertTrue(errors)

    def test_tuning_parameters_do_not_warn(self):
        config = {
            **self.VALID,
            "parameters": {**self.VALID["parameters"], "AllowLargeResults": "1"},
        }
        _, warnings = validate_config("bigquery", config)
        self.assertEqual(warnings, [])

    def test_unknown_nested_key_warns(self):
        config = {
            **self.VALID,
            "parameters": {**self.VALID["parameters"], "OAuthClientID": "x"},
        }
        errors, warnings = validate_config("bigquery", config)
        self.assertEqual(errors, [])
        self.assertTrue(any("OAuthClientId" in w for w in warnings))

    def test_nested_credentials_are_masked(self):
        out = redact("bigquery", {"type": "bigquery", **self.VALID})
        self.assertEqual(out["parameters"]["OAuthRefreshToken"], REDACTED)
        self.assertEqual(out["parameters"]["OAuthClientSecret"], REDACTED)

    def test_client_id_is_not_masked(self):
        out = redact("bigquery", {"type": "bigquery", **self.VALID})
        self.assertEqual(
            out["parameters"]["OAuthClientId"], "cid.apps.googleusercontent.com"
        )

    def test_alias(self):
        self.assertEqual(resolve_type("bq"), "bigquery")


class TestPostgreSQL(unittest.TestCase):

    VALID = {
        "host": "pg.internal",
        "port": 5432,
        "connection.user": "postgres",
        "connection.password": "postgres",
        "db.name": "postgres",
    }

    def test_valid_config(self):
        errors, warnings = validate_config("postgresql", self.VALID)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_connection_keys_are_required(self):
        for key in ("host", "connection.user", "connection.password"):
            config = {k: v for k, v in self.VALID.items() if k != key}
            errors, _ = validate_config("postgresql", config)
            self.assertTrue(any(key in e for e in errors), f"{key} not enforced")

    def test_port_and_db_name_are_optional(self):
        # Verified against TigerGraph 4.2.2: both may be omitted.
        config = {k: v for k, v in self.VALID.items() if k not in ("port", "db.name")}
        errors, warnings = validate_config("postgresql", config)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_password_is_masked(self):
        out = redact("postgresql", {"type": "postgresql", **self.VALID})
        self.assertEqual(out["connection.password"], REDACTED)
        self.assertEqual(out["host"], "pg.internal")

    def test_postgres_alias(self):
        self.assertEqual(resolve_type("postgres"), "postgresql")

    def test_no_jdbc_url_expected(self):
        # PostgreSQL uses discrete host/port keys, so no url prefix rule applies.
        self.assertIsNone(get_spec("postgresql").url_key)


class TestPassthroughNormalization(unittest.TestCase):
    """TigerGraph is the authority on valid types; this table must never
    block a type it happens not to know."""

    def test_known_alias_is_rewritten(self):
        self.assertEqual(normalize_type("azure_blob"), "abs")

    def test_unknown_type_passes_through_lowercased(self):
        self.assertEqual(normalize_type("Redshift"), "redshift")

    def test_unknown_type_never_raises(self):
        for name in ("databricks", "local", "", "  ", "something_new"):
            self.assertIsInstance(normalize_type(name), str)

    def test_find_spec_returns_none_for_unknown(self):
        self.assertIsNone(find_spec("databricks"))
        self.assertIsNotNone(find_spec("snowflake"))


class TestGuidance(unittest.TestCase):

    def test_known_type_lists_required_keys_and_example(self):
        hints = " ".join(guidance("snowflake", {}))
        self.assertIn("Required keys for Snowflake", hints)
        self.assertIn("connection.url", hints)

    def test_known_type_names_the_specific_missing_key(self):
        hints = " ".join(guidance("snowflake", {"connection.user": "u"}))
        self.assertIn("Likely cause", hints)
        self.assertIn("connection.url", hints)

    def test_unknown_type_defers_to_the_server_message(self):
        hints = " ".join(guidance("databricks", {}))
        self.assertIn("not a type this client knows", hints)
        self.assertIn("get_data_source_types", hints)

    def test_unknown_type_suggests_a_close_match(self):
        hints = " ".join(guidance("snowflak", {}))
        self.assertIn("snowflake", hints)

    def test_guidance_never_raises_on_any_input(self):
        for name in ("", "databricks", "s3", "SNOWFLAKE"):
            self.assertIsInstance(guidance(name, {}), list)


if __name__ == "__main__":
    unittest.main()
