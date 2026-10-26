"""
Module  : tests/db/test_database_operations.py
Author  : Anil Kalisetti
Purpose : CRUD, transactions, constraints, safety and streaming on the DatabaseClient.

Real-life scenario: a bank-style ``accounts`` table where integrity matters more than speed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from framework.db.client import DatabaseClient, safe_identifier


@pytest.fixture
def accounts(scratch_db: DatabaseClient) -> DatabaseClient:
    scratch_db.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, "
        "email TEXT UNIQUE, balance TEXT NOT NULL DEFAULT '0.00')"
    )
    scratch_db.execute_many(
        "INSERT INTO accounts (id, owner, email, balance) VALUES (:id, :owner, :email, :balance)",
        [
            {"id": 1, "owner": "Priya Nair", "email": "priya@example.com", "balance": "100.00"},
            {"id": 2, "owner": "Tom O'Brien", "email": "tom@example.com", "balance": "50.00"},
        ],
    )
    return scratch_db


# --- create / read / update / delete ---------------------------------------------------------------
def test_read_variants(accounts):
    assert accounts.fetch_one("SELECT owner FROM accounts WHERE id = :id", {"id": 1}) == {"owner": "Priya Nair"}
    assert accounts.fetch_one("SELECT * FROM accounts WHERE id = :id", {"id": 404}) is None
    assert accounts.scalar("SELECT COUNT(*) FROM accounts") == 2
    assert accounts.scalar("SELECT balance FROM accounts WHERE id = 404") is None
    assert [r["id"] for r in accounts.fetch_all("SELECT id FROM accounts ORDER BY id DESC")] == [2, 1]


def test_update_and_delete_report_affected_rows(accounts):
    assert accounts.execute("UPDATE accounts SET balance = :b WHERE id = :id", {"b": "75.00", "id": 2}) == 1
    assert accounts.execute("UPDATE accounts SET balance = '0.00' WHERE id = 999") == 0
    assert accounts.execute("DELETE FROM accounts WHERE id = 2") == 1
    assert accounts.row_count("accounts") == 1


def test_decimal_values_round_trip_without_float_error(accounts):
    accounts.execute("UPDATE accounts SET balance = :b WHERE id = 1", {"b": Decimal("0.10") + Decimal("0.20")})
    assert accounts.scalar("SELECT balance FROM accounts WHERE id = 1") == "0.30"  # float would give 0.30000000000000004


def test_unicode_and_emoji_round_trip(accounts):
    accounts.execute("INSERT INTO accounts (id, owner) VALUES (3, :o)", {"o": "José 张伟 🙂"})
    assert accounts.scalar("SELECT owner FROM accounts WHERE id = 3") == "José 张伟 🙂"


def test_null_handling(accounts):
    accounts.execute("INSERT INTO accounts (id, owner, email) VALUES (3, 'No Email', NULL)")
    accounts.execute("INSERT INTO accounts (id, owner, email) VALUES (4, 'Also None', NULL)")  # UNIQUE allows many NULLs
    assert accounts.scalar("SELECT COUNT(*) FROM accounts WHERE email IS NULL") == 2
    assert accounts.scalar("SELECT COUNT(*) FROM accounts WHERE email = NULL") == 0  # classic SQL trap


# --- constraints -------------------------------------------------------------------------------------------
def test_unique_constraint_is_enforced(accounts):
    with pytest.raises(IntegrityError):
        accounts.execute("INSERT INTO accounts (id, owner, email) VALUES (3, 'Dup', 'priya@example.com')")


def test_not_null_constraint_is_enforced(accounts):
    with pytest.raises(IntegrityError):
        accounts.execute("INSERT INTO accounts (id, owner) VALUES (3, NULL)")


def test_primary_key_constraint_is_enforced(accounts):
    with pytest.raises(IntegrityError):
        accounts.execute("INSERT INTO accounts (id, owner) VALUES (1, 'Same id')")


# --- transactions ---------------------------------------------------------------------------------------------
def test_transaction_commits_all_statements_together(accounts):
    from sqlalchemy import text

    with accounts.transaction() as conn:  # money transfer: both legs or neither
        conn.execute(text("UPDATE accounts SET balance = '60.00' WHERE id = 1"))
        conn.execute(text("UPDATE accounts SET balance = '90.00' WHERE id = 2"))
    assert accounts.fetch_all("SELECT balance FROM accounts ORDER BY id") == [{"balance": "60.00"}, {"balance": "90.00"}]


def test_transaction_rolls_back_everything_on_error(accounts):
    from sqlalchemy import text

    with pytest.raises(RuntimeError), accounts.transaction() as conn:
        conn.execute(text("UPDATE accounts SET balance = '0.00' WHERE id = 1"))
        raise RuntimeError("bank system unavailable mid-transfer")
    assert accounts.scalar("SELECT balance FROM accounts WHERE id = 1") == "100.00"


# --- security -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "hostile",
    ["Robert'); DROP TABLE accounts;--", "' OR '1'='1", "x'; UPDATE accounts SET balance='999999' WHERE '1'='1"],
    ids=["drop-table", "always-true", "stacked-update"],
)
def test_values_are_bound_never_interpolated(accounts, hostile):
    accounts.execute("INSERT INTO accounts (id, owner) VALUES (3, :owner)", {"owner": hostile})
    assert accounts.scalar("SELECT owner FROM accounts WHERE id = 3") == hostile  # stored as inert text
    assert accounts.table_exists("accounts")
    assert accounts.scalar("SELECT COUNT(*) FROM accounts WHERE balance = '999999'") == 0  # no injected UPDATE ran
    assert accounts.row_count("accounts") == 3  # nothing deleted, nothing extra inserted


@pytest.mark.parametrize(
    "name", ["accounts; DROP TABLE accounts", "a b", "1abc", "", "a.b.c", "tab-le", "x'--"],
)
def test_unsafe_identifiers_are_rejected(name):
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        safe_identifier(name)


@pytest.mark.parametrize("name", ["accounts", "_staging", "dbo.accounts", "Sales2026"])
def test_safe_identifiers_are_accepted(name):
    assert safe_identifier(name) == name


# --- metadata, bulk, streaming -----------------------------------------------------------------------------------
def test_metadata_helpers(accounts):
    assert accounts.table_exists("accounts")
    assert not accounts.table_exists("missing")
    assert [c["name"] for c in accounts.columns("accounts")] == ["id", "owner", "email", "balance"]


def test_execute_many_with_empty_list_is_a_noop(accounts):
    assert accounts.execute_many("INSERT INTO accounts (id, owner) VALUES (:id, :owner)", []) == 0


def test_stream_yields_every_row_across_chunk_boundaries(scratch_db):
    scratch_db.execute("CREATE TABLE big (n INTEGER)")
    scratch_db.execute_many("INSERT INTO big VALUES (:n)", [{"n": i} for i in range(2_501)])
    streamed = [row["n"] for row in scratch_db.stream("SELECT n FROM big ORDER BY n", chunk_size=1_000)]
    assert streamed == list(range(2_501))  # 1000 + 1000 + 501: no row lost or repeated at the seams


def test_stream_of_empty_result_is_empty(accounts):
    assert list(accounts.stream("SELECT * FROM accounts WHERE id = 404")) == []
