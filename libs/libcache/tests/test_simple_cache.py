from http import HTTPStatus

import pytest
from pymongo.errors import DocumentTooLarge

from libcache.simple_cache import (
    DoesNotExist,
    InvalidCursor,
    InvalidLimit,
    _clean_database,
    connect_to_cache,
    delete_first_rows_responses,
    delete_splits_responses,
    get_cache_reports_first_rows,
    get_cache_reports_splits_next,
    get_datasets_with_some_error,
    get_first_rows_response,
    get_first_rows_responses_count_by_status,
    get_splits_response,
    get_splits_responses_count_by_status,
    get_valid_dataset_names,
    mark_first_rows_responses_as_stale,
    mark_splits_responses_as_stale,
    upsert_first_rows_response,
    upsert_splits_response,
)

from ._utils import MONGO_CACHE_DATABASE, MONGO_URL


@pytest.fixture(autouse=True, scope="module")
def safe_guard() -> None:
    if "test" not in MONGO_CACHE_DATABASE:
        raise ValueError("Test must be launched on a test mongo database")


@pytest.fixture(autouse=True, scope="module")
def client() -> None:
    connect_to_cache(database=MONGO_CACHE_DATABASE, host=MONGO_URL)


@pytest.fixture(autouse=True)
def clean_mongo_database() -> None:
    _clean_database()


def test_upsert_splits_response() -> None:
    dataset_name = "test_dataset"
    response = {"splits": [{"dataset_name": dataset_name, "config_name": "test_config", "split_name": "test_split"}]}
    upsert_splits_response(dataset_name, response, HTTPStatus.OK)
    response1, http_status, error_code = get_splits_response(dataset_name)
    assert http_status == HTTPStatus.OK
    assert response1 == response
    assert error_code is None

    # ensure it's idempotent
    upsert_splits_response(dataset_name, response, HTTPStatus.OK)
    (response2, _, _) = get_splits_response(dataset_name)
    assert response2 == response1

    mark_splits_responses_as_stale(dataset_name)
    # we don't have access to the stale field
    # we also don't have access to the updated_at field

    delete_splits_responses(dataset_name)
    with pytest.raises(DoesNotExist):
        get_splits_response(dataset_name)

    mark_splits_responses_as_stale(dataset_name)
    with pytest.raises(DoesNotExist):
        get_splits_response(dataset_name)

    upsert_splits_response(dataset_name, response, HTTPStatus.BAD_REQUEST, "error_code")
    response3, http_status, error_code = get_splits_response(dataset_name)
    assert response3 == response
    assert http_status == HTTPStatus.BAD_REQUEST
    assert error_code == "error_code"


def test_upsert_first_rows_response() -> None:
    dataset_name = "test_dataset"
    config_name = "test_config"
    split_name = "test_split"
    response = {"key": "value"}
    upsert_first_rows_response(dataset_name, config_name, split_name, response, HTTPStatus.OK)
    response1, http_status, _ = get_first_rows_response(dataset_name, config_name, split_name)
    assert http_status == HTTPStatus.OK
    assert response1 == response

    # ensure it's idempotent
    upsert_first_rows_response(dataset_name, config_name, split_name, response, HTTPStatus.OK)
    (response2, _, _) = get_first_rows_response(dataset_name, config_name, split_name)
    assert response2 == response1

    mark_first_rows_responses_as_stale(dataset_name)
    mark_first_rows_responses_as_stale(dataset_name, config_name, split_name)
    # we don't have access to the stale field
    # we also don't have access to the updated_at field

    upsert_first_rows_response(dataset_name, config_name, "test_split2", response, HTTPStatus.OK)
    delete_first_rows_responses(dataset_name, config_name, "test_split2")
    get_first_rows_response(dataset_name, config_name, split_name)

    delete_first_rows_responses(dataset_name)
    with pytest.raises(DoesNotExist):
        get_first_rows_response(dataset_name, config_name, split_name)

    mark_first_rows_responses_as_stale(dataset_name)
    mark_first_rows_responses_as_stale(dataset_name, config_name, split_name)
    with pytest.raises(DoesNotExist):
        get_first_rows_response(dataset_name, config_name, split_name)


def test_big_row() -> None:
    # https://github.com/huggingface/datasets-server/issues/197
    dataset_name = "test_dataset"
    config_name = "test_config"
    split_name = "test_split"
    big_response = {"content": "a" * 100_000_000}
    with pytest.raises(DocumentTooLarge):
        upsert_first_rows_response(dataset_name, config_name, split_name, big_response, HTTPStatus.OK)


def test_valid() -> None:
    assert get_valid_dataset_names() == []
    assert get_datasets_with_some_error() == []

    upsert_splits_response(
        "test_dataset",
        {"key": "value"},
        HTTPStatus.OK,
    )

    assert get_valid_dataset_names() == []
    assert get_datasets_with_some_error() == []

    upsert_first_rows_response(
        "test_dataset",
        "test_config",
        "test_split",
        {
            "key": "value",
        },
        HTTPStatus.OK,
    )

    assert get_valid_dataset_names() == ["test_dataset"]
    assert get_datasets_with_some_error() == []

    upsert_splits_response(
        "test_dataset2",
        {"key": "value"},
        HTTPStatus.OK,
    )

    assert get_valid_dataset_names() == ["test_dataset"]
    assert get_datasets_with_some_error() == []

    upsert_first_rows_response(
        "test_dataset2",
        "test_config2",
        "test_split2",
        {
            "key": "value",
        },
        HTTPStatus.BAD_REQUEST,
    )

    assert get_valid_dataset_names() == ["test_dataset"]
    assert get_datasets_with_some_error() == ["test_dataset2"]

    upsert_first_rows_response(
        "test_dataset2",
        "test_config2",
        "test_split3",
        {
            "key": "value",
        },
        HTTPStatus.OK,
    )

    assert get_valid_dataset_names() == ["test_dataset", "test_dataset2"]
    assert get_datasets_with_some_error() == ["test_dataset2"]

    upsert_splits_response(
        "test_dataset3",
        {"key": "value"},
        HTTPStatus.BAD_REQUEST,
    )

    assert get_valid_dataset_names() == ["test_dataset", "test_dataset2"]
    assert get_datasets_with_some_error() == ["test_dataset2", "test_dataset3"]


def test_count_by_status() -> None:
    assert "OK" not in get_splits_responses_count_by_status()

    upsert_splits_response(
        "test_dataset2",
        {"key": "value"},
        HTTPStatus.OK,
    )

    assert get_splits_responses_count_by_status()["OK"] == 1
    assert "OK" not in get_first_rows_responses_count_by_status()

    upsert_first_rows_response(
        "test_dataset",
        "test_config",
        "test_split",
        {
            "key": "value",
        },
        HTTPStatus.OK,
    )

    assert get_splits_responses_count_by_status()["OK"] == 1


def test_get_cache_reports_splits_next() -> None:
    assert get_cache_reports_splits_next("", 2) == {"cache_reports": [], "next_cursor": ""}
    upsert_splits_response(
        "a",
        {"key": "value"},
        HTTPStatus.OK,
    )
    b_details = {
        "error": "error B",
        "cause_exception": "ExceptionB",
        "cause_message": "Cause message B",
        "cause_traceback": ["B"],
    }
    upsert_splits_response(
        "b",
        b_details,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "ErrorCodeB",
        b_details,
    )
    c_details = {
        "error": "error C",
        "cause_exception": "ExceptionC",
        "cause_message": "Cause message C",
        "cause_traceback": ["C"],
    }
    upsert_splits_response(
        "c",
        {
            "error": c_details["error"],
        },
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "ErrorCodeC",
        c_details,
    )
    response = get_cache_reports_splits_next("", 2)
    assert response["cache_reports"] == [
        {"dataset": "a", "http_status": HTTPStatus.OK.value},
        {
            "dataset": "b",
            "http_status": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "error": {
                "cause_exception": "ExceptionB",
                "cause_message": "Cause message B",
                "cause_traceback": ["B"],
                "error_code": "ErrorCodeB",
                "message": "error B",
            },
        },
    ]
    assert response["next_cursor"] != ""
    next_cursor = response["next_cursor"]

    response = get_cache_reports_splits_next(next_cursor, 2)
    assert response == {
        "cache_reports": [
            {
                "dataset": "c",
                "http_status": HTTPStatus.INTERNAL_SERVER_ERROR.value,
                "error": {
                    "cause_exception": "ExceptionC",
                    "cause_message": "Cause message C",
                    "cause_traceback": ["C"],
                    "error_code": "ErrorCodeC",
                    "message": "error C",
                },
            },
        ],
        "next_cursor": "",
    }

    with pytest.raises(InvalidCursor):
        get_cache_reports_splits_next("not an objectid", 2)
    with pytest.raises(InvalidLimit):
        get_cache_reports_splits_next(next_cursor, -1)
    with pytest.raises(InvalidLimit):
        get_cache_reports_splits_next(next_cursor, 0)


def test_get_cache_reports_first_rows() -> None:
    assert get_cache_reports_first_rows("", 2) == {"cache_reports": [], "next_cursor": ""}
    upsert_first_rows_response(
        "a",
        "config",
        "split",
        {"key": "value"},
        HTTPStatus.OK,
    )
    b_details = {
        "error": "error B",
        "cause_exception": "ExceptionB",
        "cause_message": "Cause message B",
        "cause_traceback": ["B"],
    }
    upsert_first_rows_response(
        "b",
        "config",
        "split",
        b_details,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "ErrorCodeB",
        b_details,
    )
    c_details = {
        "error": "error C",
        "cause_exception": "ExceptionC",
        "cause_message": "Cause message C",
        "cause_traceback": ["C"],
    }
    upsert_first_rows_response(
        "c",
        "config",
        "split",
        {
            "error": c_details["error"],
        },
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "ErrorCodeC",
        c_details,
    )
    response = get_cache_reports_first_rows(None, 2)
    assert response["cache_reports"] == [
        {"dataset": "a", "config": "config", "split": "split", "http_status": HTTPStatus.OK.value},
        {
            "dataset": "b",
            "config": "config",
            "split": "split",
            "http_status": HTTPStatus.INTERNAL_SERVER_ERROR.value,
            "error": {
                "cause_exception": "ExceptionB",
                "cause_message": "Cause message B",
                "cause_traceback": ["B"],
                "error_code": "ErrorCodeB",
                "message": "error B",
            },
        },
    ]
    assert response["next_cursor"] != ""
    next_cursor = response["next_cursor"]

    response = get_cache_reports_first_rows(next_cursor, 2)
    assert response == {
        "cache_reports": [
            {
                "dataset": "c",
                "config": "config",
                "split": "split",
                "http_status": HTTPStatus.INTERNAL_SERVER_ERROR.value,
                "error": {
                    "cause_exception": "ExceptionC",
                    "cause_message": "Cause message C",
                    "cause_traceback": ["C"],
                    "error_code": "ErrorCodeC",
                    "message": "error C",
                },
            },
        ],
        "next_cursor": "",
    }

    with pytest.raises(InvalidCursor):
        get_cache_reports_first_rows("not an objectid", 2)
    with pytest.raises(InvalidLimit):
        get_cache_reports_first_rows(next_cursor, -1)
    with pytest.raises(InvalidLimit):
        get_cache_reports_first_rows(next_cursor, 0)
