from app.services.execution_service import ExecutionService


class _DummySession:
    def __init__(self):
        self.add_all_payloads = []

    def add_all(self, items):
        self.add_all_payloads.append(items)

    def get(self, _model, pk):
        class _Case:
            def __init__(self, testcase_id):
                self.id = testcase_id
                self.name = f"case_{testcase_id}"

        return _Case(pk)


class _DummyDetail:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.request_data = {}
        self.response_data = {}
        self.assertion_data = []
        self.extract_data = {}


class _Execution:
    def __init__(self, execution_id):
        self.id = execution_id


def test_add_details_batch_adds_all_and_commits_once(monkeypatch):
    dummy_session = _DummySession()
    commit_calls = {"count": 0}

    monkeypatch.setattr("app.services.execution_service.db.session", dummy_session)
    monkeypatch.setattr("app.services.execution_service.ExecutionDetail", _DummyDetail)
    monkeypatch.setattr(
        "app.services.execution_service.ExecutionService.get_by_id",
        staticmethod(lambda execution_id: _Execution(execution_id)),
    )
    monkeypatch.setattr(
        "app.services.execution_service.commit_session",
        lambda: commit_calls.__setitem__("count", commit_calls["count"] + 1),
    )

    items = [
        {
            "testcase_id": 1,
            "testcase_name": "case_a",
            "status": "passed",
            "request_data": {"url": "/a"},
            "response_data": {"status_code": 200},
            "assertion_data": [{"passed": True}],
            "extract_data": {"token": "abc"},
            "error_message": "",
            "duration_ms": 10,
        },
        {
            "testcase_id": 2,
            "testcase_name": "case_b",
            "status": "failed",
            "request_data": {"url": "/b"},
            "response_data": {"status_code": 500},
            "assertion_data": [{"passed": False}],
            "extract_data": {},
            "error_message": "boom",
            "duration_ms": 20,
        },
    ]

    result = ExecutionService.add_details_batch(execution_id=99, detail_items=items)

    assert len(result) == 2
    assert len(dummy_session.add_all_payloads) == 1
    assert len(dummy_session.add_all_payloads[0]) == 2
    assert commit_calls["count"] == 1
