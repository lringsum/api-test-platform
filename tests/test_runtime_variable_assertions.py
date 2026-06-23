from app.utils.assertion_engine import run_assertions
from app.utils.extractor import extract_variables
from app.utils.variable_resolver import resolve_variables


def test_exact_variable_keeps_native_type():
    resolved = resolve_variables(
        {
            "folder_id": "${folder_id}",
            "enabled": "${enabled}",
            "ids": "${ids}",
        },
        {"folder_id": 199, "enabled": True, "ids": [1, 2, 3]},
    )

    assert resolved == {
        "folder_id": 199,
        "enabled": True,
        "ids": [1, 2, 3],
    }


def test_embedded_variable_is_interpolated_as_text():
    resolved = resolve_variables(
        "SCN_Folder_${folder_id}",
        {"folder_id": 199},
    )

    assert resolved == "SCN_Folder_199"


def test_assertion_expected_value_supports_runtime_variable():
    passed, results = run_assertions(
        assertions=[
            {
                "type": "json_path",
                "path": "data.folder_id",
                "expected": "${folder_id}",
            },
            {
                "type": "json_path",
                "path": "data.is_favorite",
                "expected": "${is_favorite}",
            },
        ],
        response_snapshot={
            "status_code": 200,
            "text": "",
            "json": {
                "data": {
                    "folder_id": 199,
                    "is_favorite": True,
                }
            },
        },
        duration_ms=20,
        runtime_variables={"folder_id": 199, "is_favorite": True},
    )

    assert passed is True
    assert all(item["passed"] for item in results)


def test_json_array_contains_supports_item_path_and_runtime_variable():
    passed, results = run_assertions(
        assertions=[
            {
                "type": "json_array_contains",
                "path": "data.tags",
                "item_path": "id",
                "expected": "${tag_id}",
            }
        ],
        response_snapshot={
            "status_code": 200,
            "text": "",
            "json": {
                "data": {
                    "tags": [
                        {"id": 3003, "name": "tag-a"},
                        {"id": 3270, "name": "tag-b"},
                    ]
                }
            },
        },
        duration_ms=20,
        runtime_variables={"tag_id": 3270},
    )

    assert passed is True
    assert results[0]["actual"] == [
        {"id": 3003, "name": "tag-a"},
        {"id": 3270, "name": "tag-b"},
    ]


def test_extracted_value_can_be_used_by_same_response_assertion():
    response_json = {"data": {"folder_id": 199}}
    extracted_values, _ = extract_variables(
        {"folder_id": "data.folder_id"},
        response_json,
    )

    passed, _ = run_assertions(
        assertions=[
            {
                "type": "json_path",
                "path": "data.folder_id",
                "expected": "${folder_id}",
            }
        ],
        response_snapshot={
            "status_code": 200,
            "text": "",
            "json": response_json,
        },
        duration_ms=20,
        runtime_variables=extracted_values,
    )

    assert passed is True
