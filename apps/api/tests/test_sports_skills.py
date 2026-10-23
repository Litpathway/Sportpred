from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models.entities import Fixture, Team
from app.providers.fixtures import ProviderFailure, fixture_provider
from app.providers.sports_skills import RIGHTS, UPSTREAM_COMMIT, SportsSkillsFixtureProvider
from app.services.ingestion import sync_fixtures
from app.ml.features import features_for


def settings(**kwargs):
    defaults = dict(jwt_secret="test-" + "x"*48,environment="test",demo_mode=False,fixture_provider="sports_skills",
                    sports_skills_personal_use=True,sports_skills_days_ahead=1,sports_skills_enrich_limit=0)
    return Settings(**{**defaults, **kwargs})


def event(*, status="not_started", event_id="700001", season="premier-league-current"):
    return {"id":event_id,"status":status,"start_time":(datetime.now(UTC)+timedelta(days=1)).isoformat(),
            "competition":{"id":"premier-league","name":"Premier League"},"season":{"id":season},
            "competitors":[{"qualifier":"home","team":{"id":"101","name":"Test United"},"score":2},
                           {"qualifier":"away","team":{"id":"202","name":"Test City"},"score":1}]}


class FakeFootball:
    def __init__(self, events=None, source="espn"):
        self.events = [event()] if events is None else events
        self.calls = []
        self.source = source
    def get_current_season(self, **kwargs):
        self.calls.append(("get_current_season",kwargs))
        return {"status":True,"data":{"season":{"id":"premier-league-current"}}}
    def get_daily_schedule(self, **kwargs):
        self.calls.append(("get_daily_schedule",kwargs))
        return {"status":True,"data":{"events":self.events,"source":self.source}}
    def get_season_schedule(self, **kwargs):
        self.calls.append(("get_season_schedule",kwargs))
        return {"status":True,"data":{"schedules":self.events}}
    def get_event_lineups(self, **kwargs):
        self.calls.append(("get_event_lineups",kwargs))
        return {"status":True,"data":{"lineups":[{"team":{"id":id},"starting":[{"name":f"Player {n}"} for n in range(11)]} for id in ("101","202")]}}


def test_production_rights_gate_precedes_import_or_network():
    config=settings();config.environment="production"  # Deliberately bypass other production settings checks.
    sdk=FakeFootball()
    with pytest.raises(ProviderFailure,match="cannot run in production"):
        SportsSkillsFixtureProvider(config,sdk)
    assert sdk.calls==[]


def test_explicit_personal_use_opt_in_and_demo_separation():
    config=settings();config.sports_skills_personal_use=False
    with pytest.raises(ProviderFailure,match="opt-in"): SportsSkillsFixtureProvider(config,FakeFootball())
    config.sports_skills_personal_use=True;config.demo_mode=True
    with pytest.raises(ProviderFailure,match="DEMO_MODE=false"): SportsSkillsFixtureProvider(config,FakeFootball())


def test_current_season_is_discovered_and_history_is_opt_in():
    sdk=FakeFootball();provider=SportsSkillsFixtureProvider(settings(),sdk)
    rows=provider.fetch()
    assert sdk.calls[0]==("get_current_season",{"competition_id":"premier-league"})
    assert not any(c[0]=="get_season_schedule" for c in sdk.calls)
    assert len(rows)==1 and rows[0].home_external_id=="101" and rows[0].id_namespace=="espn"
    assert rows[0].odds=={} and not rows[0].simulated
    provenance=rows[0].enrichment["provenance"]
    assert provenance["rights"]==RIGHTS and provenance["upstream_commit"]==UPSTREAM_COMMIT
    assert provenance["provider_updated_at"] is None


def test_season_schedule_receives_discovered_id():
    sdk=FakeFootball();provider=SportsSkillsFixtureProvider(settings(sports_skills_history=True),sdk)
    assert len(provider.fetch())==1
    assert ("get_season_schedule",{"season_id":"premier-league-current"}) in sdk.calls


def test_date_only_or_wrong_season_records_are_rejected():
    bad=event();bad["start_time"]="2026-10-23"
    provider=SportsSkillsFixtureProvider(settings(),FakeFootball([bad,event(season="old-season")]))
    assert provider.fetch()==[]
    assert len(provider.warnings)==2


def test_estimated_season_is_not_used():
    sdk=FakeFootball()
    sdk.get_current_season=lambda **kw:{"status":True,"data":{"estimated":True,"season":{"id":"guessed"}}}
    provider=SportsSkillsFixtureProvider(settings(),sdk)
    assert provider.fetch()==[]
    assert any(w["reason"]=="season_or_history_unavailable" for w in provider.warnings)


def test_openfootball_fallback_does_not_masquerade_as_espn():
    provider=SportsSkillsFixtureProvider(settings(),FakeFootball(source="openfootball"))
    assert provider.fetch()==[] and provider.warnings[0]["reason"]=="fallback_source_declined"


def test_confirmed_lineups_use_native_team_ids():
    provider=SportsSkillsFixtureProvider(settings(sports_skills_enrich_limit=1),FakeFootball())
    row=provider.fetch()[0]
    assert len(row.enrichment["lineups"]["home"])==11 and len(row.enrichment["lineups"]["away"])==11


def test_result_availability_is_observed_never_backdated(db):
    finished=event(status="closed");finished["start_time"]=(datetime.now(UTC)-timedelta(days=3)).isoformat()
    sdk=FakeFootball([finished]);provider=SportsSkillsFixtureProvider(settings(),sdk)
    start=datetime.now(UTC).replace(tzinfo=None)
    sync_fixtures(db,provider)
    fixture=db.scalar(select(Fixture))
    assert fixture.result_known_at>=start
    original=fixture.result_known_at
    sync_fixtures(db,provider)
    assert fixture.result_known_at==original
    assert db.scalar(select(Team).where(Team.identity=="espn:team:101"))
    assert fixture.enrichment["provenance"]["result_time_basis"]=="first_observed_final"


def test_source_outage_does_not_destroy_persisted_fixtures(db):
    sdk=FakeFootball();provider=SportsSkillsFixtureProvider(settings(),sdk)
    sync_fixtures(db,provider)
    sdk.get_daily_schedule=lambda **kw:{"status":False,"message":"not available"}
    with pytest.raises(ProviderFailure):sync_fixtures(db,provider)
    assert db.scalar(select(Fixture)) is not None


def test_transient_rate_limit_is_retried(monkeypatch):
    sdk=FakeFootball();calls=[]
    def daily(**kwargs):
        calls.append(1)
        return {"status":False,"status_code":429} if len(calls)==1 else {"status":True,"data":{"events":[event()]}}
    sdk.get_daily_schedule=daily
    monkeypatch.setattr("app.providers.sports_skills.time.sleep",lambda _:None)
    assert len(SportsSkillsFixtureProvider(settings(),sdk).fetch())==1 and len(calls)==2


def test_read_only_allowlist_rejects_arbitrary_commands():
    provider=SportsSkillsFixtureProvider(settings(),FakeFootball())
    with pytest.raises(ProviderFailure,match="read-only"):provider._read("place_order")


def test_simulated_records_are_hidden_in_real_data_mode(client,selection):
    selection.fixture.simulated=selection.model.simulated=True
    assert client.get("/api/fixtures").json()["total"]==0
    assert client.get("/api/predictions").json()["total"]==0
    assert client.get(f"/api/fixtures/{selection.fixture_id}").status_code==404


def test_research_adapter_accepts_all_ten_european_leagues():
    from app.core.leagues import DEFAULT_LEAGUES, EUROPEAN_LEAGUES
    events = []
    for i, (slug, league) in enumerate(EUROPEAN_LEAGUES.items()):
        row = event(event_id=str(700001 + i), season=f"{slug}-current")
        row["competition"] = {"id": slug, "name": league["name"]}
        events.append(row)
    sdk = FakeFootball(events)
    sdk.get_current_season = lambda **kw: {"status": True, "data": {"season": {"id": f"{kw['competition_id']}-current"}}}
    rows = SportsSkillsFixtureProvider(settings(sports_skills_competitions=DEFAULT_LEAGUES), sdk).fetch()
    assert len(rows) == 10 and {row.league_slug for row in rows} == set(EUROPEAN_LEAGUES)
