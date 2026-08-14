from app.services.ui_automation_service import UiAutomationService


class _Artifact:
    def __init__(self, run_id, created_at):
        self.run_id = run_id
        self.created_at = created_at


def test_list_artifacts_by_run_ids_groups_records(monkeypatch):
    class _Column:
        def in_(self, _):
            return self

        def asc(self):
            return self

    class _Query:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return self._rows

    class _ArtifactModel:
        run_id = _Column()
        created_at = _Column()

    rows = [
        _Artifact(run_id=1, created_at=1),
        _Artifact(run_id=1, created_at=2),
        _Artifact(run_id=3, created_at=1),
    ]
    _ArtifactModel.query = _Query(rows)
    monkeypatch.setattr("app.services.ui_automation_service.UiAutomationArtifact", _ArtifactModel)

    result = UiAutomationService.list_artifacts_by_run_ids([1, "2", 3, "x", 3])

    assert sorted(result.keys()) == [1, 2, 3]
    assert len(result[1]) == 2
    assert len(result[2]) == 0
    assert len(result[3]) == 1

