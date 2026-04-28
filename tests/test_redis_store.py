"""Unit tests for RedisStore — the Redis implementation of DataStore."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fakeredis
import pytest

from data_access.interface import DataStore
from data_access.redis_store import RedisStore


@pytest.fixture
def store() -> RedisStore:
    """Fresh in-memory RedisStore for each test."""
    return RedisStore(fakeredis.FakeRedis(decode_responses=True))


# ---------------------------------------------------------------------------
# Contract check
# ---------------------------------------------------------------------------

def test_redis_store_implements_data_store(store: RedisStore) -> None:
    assert isinstance(store, DataStore)


# ---------------------------------------------------------------------------
# get / set
# ---------------------------------------------------------------------------

def test_set_and_get(store: RedisStore) -> None:
    store.set("key", "value")
    assert store.get("key") == "value"


def test_get_missing_key_returns_none(store: RedisStore) -> None:
    assert store.get("no-such-key") is None


def test_set_overwrites_existing_value(store: RedisStore) -> None:
    store.set("k", "first")
    store.set("k", "second")
    assert store.get("k") == "second"


# ---------------------------------------------------------------------------
# exists
# ---------------------------------------------------------------------------

def test_exists_false_when_key_absent(store: RedisStore) -> None:
    assert store.exists("missing") is False


def test_exists_true_after_set(store: RedisStore) -> None:
    store.set("present", "1")
    assert store.exists("present") is True


def test_exists_returns_bool_type(store: RedisStore) -> None:
    store.set("x", "y")
    result = store.exists("x")
    assert type(result) is bool


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_single_key(store: RedisStore) -> None:
    store.set("a", "1")
    store.delete("a")
    assert store.get("a") is None


def test_delete_multiple_keys(store: RedisStore) -> None:
    store.set("a", "1")
    store.set("b", "2")
    store.delete("a", "b")
    assert store.get("a") is None
    assert store.get("b") is None


def test_delete_missing_key_does_not_raise(store: RedisStore) -> None:
    store.delete("never-stored")  # must not raise


def test_delete_with_no_args_does_not_raise(store: RedisStore) -> None:
    store.delete()  # must not raise


def test_delete_removes_only_specified_key(store: RedisStore) -> None:
    store.set("keep", "yes")
    store.set("drop", "no")
    store.delete("drop")
    assert store.get("keep") == "yes"


# ---------------------------------------------------------------------------
# add_object / get_objects
# ---------------------------------------------------------------------------

def test_add_object_and_get_objects_full(store: RedisStore) -> None:
    store.add_object("zs", {"a": 1.0, "b": 2.0, "c": 3.0})
    assert store.get_objects("zs", 0, -1) == ["a", "b", "c"]


def test_get_objects_respects_score_order(store: RedisStore) -> None:
    store.add_object("zs", {"z": 10.0, "a": 1.0, "m": 5.0})
    assert store.get_objects("zs", 0, -1) == ["a", "m", "z"]


def test_get_objects_with_positive_stop(store: RedisStore) -> None:
    store.add_object("zs", {"a": 1.0, "b": 2.0, "c": 3.0})
    assert store.get_objects("zs", 0, 1) == ["a", "b"]


def test_get_objects_empty_set_returns_empty_list(store: RedisStore) -> None:
    assert store.get_objects("empty", 0, -1) == []


def test_add_object_updates_score_of_existing_member(store: RedisStore) -> None:
    store.add_object("zs", {"a": 10.0})
    store.add_object("zs", {"a": 1.0})  # lower score — should re-sort
    store.add_object("zs", {"b": 5.0})
    assert store.get_objects("zs", 0, -1) == ["a", "b"]


# ---------------------------------------------------------------------------
# delete_object
# ---------------------------------------------------------------------------

def test_delete_object_removes_member(store: RedisStore) -> None:
    store.add_object("zs", {"a": 1.0, "b": 2.0})
    store.delete_object("zs", "a")
    assert store.get_objects("zs", 0, -1) == ["b"]


def test_delete_object_multiple_members(store: RedisStore) -> None:
    store.add_object("zs", {"a": 1.0, "b": 2.0, "c": 3.0})
    store.delete_object("zs", "a", "c")
    assert store.get_objects("zs", 0, -1) == ["b"]


def test_delete_object_missing_member_does_not_raise(store: RedisStore) -> None:
    store.add_object("zs", {"a": 1.0})
    store.delete_object("zs", "no-such-member")  # must not raise
    assert store.get_objects("zs", 0, -1) == ["a"]


def test_delete_object_with_no_members_does_not_raise(store: RedisStore) -> None:
    store.add_object("zs", {"a": 1.0})
    store.delete_object("zs")  # must not raise
    assert store.get_objects("zs", 0, -1) == ["a"]
