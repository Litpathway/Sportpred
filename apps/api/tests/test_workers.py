from contextlib import nullcontext

from sqlalchemy import select

from app.models.entities import JobRun
from app.providers.api_football import RequestBudgetExceeded
from app.workers import tasks


class FakeLock:
    def acquire(self, **kwargs): return True
    def owned(self): return True
    def release(self): pass


class FakeRedis:
    def lock(self, *args, **kwargs): return FakeLock()


def configure(monkeypatch, db):
    monkeypatch.setattr(tasks.redis.Redis, "from_url", lambda *a, **k: FakeRedis())
    monkeypatch.setattr(tasks, "SessionLocal", lambda: nullcontext(db))


def test_job_success_is_persisted_and_retries_are_idempotent(db, monkeypatch):
    configure(monkeypatch, db)
    calls = []
    monkeypatch.setattr(tasks, "execute_job", lambda name, session: calls.append(name) or {"done": True})
    first = tasks.run_job.apply(args=["sync"], task_id="stable-task-id", throw=True)
    again = tasks.run_job.apply(args=["sync"], task_id="stable-task-id", throw=True)
    assert first.result == {"done": True} and again.result == {"status": "already_completed"}
    assert calls == ["sync"]
    assert db.scalar(select(JobRun)).status == "succeeded"


def test_successful_run_supersedes_older_dead_letters_for_same_job(db, monkeypatch):
    configure(monkeypatch, db)
    previous = JobRun(key="sync:old-task", name="sync", status="dead_letter", attempts=4, error="old provider error")
    other = JobRun(key="train:old-task", name="train", status="dead_letter", attempts=4, error="training error")
    db.add_all([previous, other])
    db.commit()
    monkeypatch.setattr(tasks, "execute_job", lambda name, session: {"done": True})

    tasks.run_job.apply(args=["sync"], task_id="recovered-sync", throw=True)

    db.refresh(previous)
    db.refresh(other)
    assert previous.status == "superseded" and previous.error == "old provider error"
    assert other.status == "dead_letter"


def test_failed_job_retries_then_records_dead_letter(db, monkeypatch):
    configure(monkeypatch, db)
    def failing(name, session): raise ConnectionError("provider unavailable")
    monkeypatch.setattr(tasks, "execute_job", failing)
    result = tasks.run_job.apply(args=["sync"], task_id="failing-task", throw=False)
    assert result.failed()
    job = db.scalar(select(JobRun))
    assert job.status == "dead_letter" and job.attempts == 4 and job.error == "ConnectionError"


def test_request_budget_defers_job_without_retries(db, monkeypatch):
    configure(monkeypatch, db)
    monkeypatch.setattr(tasks, "execute_job", lambda name, session: (_ for _ in ()).throw(
        RequestBudgetExceeded("API-Football request budget reached; fixture sync deferred until quota resets")))

    result = tasks.run_job.apply(args=["pipeline"], task_id="budget-deferred-task", throw=True)

    job = db.scalar(select(JobRun))
    assert result.result["status"] == "deferred"
    assert job.status == "deferred" and job.attempts == 1
    assert "quota resets" in job.error


def test_concurrent_pipeline_job_declines_without_lock(db, monkeypatch):
    configure(monkeypatch, db)
    monkeypatch.setattr(FakeLock, "acquire", lambda *a, **k: False)
    result = tasks.run_job.apply(args=["pipeline"], throw=True)
    assert result.result == {"status": "busy"}
