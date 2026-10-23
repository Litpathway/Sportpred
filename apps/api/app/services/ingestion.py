from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Competition, Fixture, PlatformSettings, Team, utcnow
from app.providers.fixtures import FixtureProvider, normalize


def naive_utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC).replace(tzinfo=None) if value else None


def platform_settings(db: Session) -> PlatformSettings:
    item = db.get(PlatformSettings, 1)
    if not item:
        item = PlatformSettings(id=1)
        db.add(item)
        db.flush()
    return item


def sync_fixtures(db: Session, provider: FixtureProvider) -> dict:
    if not platform_settings(db).provider_enabled:
        return {"created": 0, "updated": 0, "disabled": True}
    # Validate entire external batch before mutating persistence.
    incoming = provider.fetch()
    teams = {t.identity: t for t in db.scalars(select(Team))}
    comps = {c.identity: c for c in db.scalars(select(Competition))}
    fixtures = {(f.provider, f.external_id): f for f in db.scalars(select(Fixture))}
    natural = {(f.competition_id, f.home_id, f.away_id, f.kickoff): f for f in fixtures.values()}
    created = updated = stale_ignored = 0
    for row in incoming:
        country = normalize(row.country)
        comp_key = f"{row.id_namespace}:competition:{row.competition_external_id}" if row.id_namespace and row.competition_external_id else f"{country}:{normalize(row.competition)}"
        if comp_key not in comps:
            comps[comp_key] = Competition(name=row.competition.strip(), identity=comp_key, country=row.country, league_slug=row.league_slug)
            db.add(comps[comp_key])
            db.flush()
        if row.league_slug:
            if comps[comp_key].league_slug and comps[comp_key].league_slug != row.league_slug:
                raise ValueError("Provider competition identity changed canonical league")
            comps[comp_key].league_slug = row.league_slug
        participants = []
        for name, external_id in ((row.home, row.home_external_id), (row.away, row.away_external_id)):
            key = f"{row.id_namespace}:team:{external_id}" if row.id_namespace and external_id else f"{country}:{normalize(name)}"
            if key not in teams:
                teams[key] = Team(name=name.strip(), identity=key, country=row.country)
                db.add(teams[key])
                db.flush()
            participants.append(teams[key])
        home, away = participants
        kickoff = naive_utc(row.kickoff)
        natural_key = (comps[comp_key].id, home.id, away.id, kickoff)
        fixture = fixtures.get((provider.name, row.external_id)) or natural.get(natural_key)
        source_time = naive_utc(datetime.fromisoformat(row.enrichment["as_of"])) if provider.name == "api_football" and row.enrichment.get("as_of") else None
        if fixture and source_time and (fixture.enrichment or {}).get("as_of"):
            previous_time = naive_utc(datetime.fromisoformat(fixture.enrichment["as_of"]))
            if source_time < previous_time:
                stale_ignored += 1
                continue
        if not fixture:
            fixture = Fixture(provider=provider.name, external_id=row.external_id, competition_id=comps[comp_key].id,
                              home_id=home.id, away_id=away.id, kickoff=kickoff)
            db.add(fixture)
            fixtures[(provider.name, row.external_id)] = fixture
            created += 1
        else:
            updated += 1
            old_key = (fixture.competition_id, fixture.home_id, fixture.away_id, fixture.kickoff)
            natural.pop(old_key, None)
        previous_result = (fixture.status, fixture.home_goals, fixture.away_goals, fixture.result_known_at)
        fixture.kickoff = kickoff
        fixture.status = row.status
        fixture.home_goals, fixture.away_goals = row.home_goals, row.away_goals
        same_final = previous_result[:3] == ("finished", row.home_goals, row.away_goals) and row.status == "finished"
        fixture.result_known_at = previous_result[3] if same_final and previous_result[3] else naive_utc(row.result_known_at)
        fixture.simulated = row.simulated
        fixture.odds, fixture.odds_at = row.odds, naive_utc(row.odds_at)
        fixture.enrichment, fixture.synced_at = row.enrichment, source_time or utcnow()
        natural[natural_key] = fixture
    db.add(AuditLog(action="fixtures.synced", entity=provider.name, detail={"created": created, "updated": updated,
        "warnings": getattr(provider, "warnings", []), "stale_ignored": stale_ignored}))
    db.commit()
    return {"created": created, "updated": updated}
