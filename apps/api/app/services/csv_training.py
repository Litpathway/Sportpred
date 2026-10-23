import csv
import hashlib
import io
import re
import unicodedata
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.leagues import EUROPEAN_LEAGUES
from app.models.entities import AuditLog, Competition, Fixture, Team, utcnow

# football-data.co.uk division codes plus readable names. Restricting imports to
# configured competitions prevents an upload from silently expanding the model.
DIVISIONS = {
    "E0": "premier-league", "ENGLAND": "premier-league", "PREMIER LEAGUE": "premier-league",
    "SP1": "la-liga", "SPAIN": "la-liga", "LA LIGA": "la-liga", "PRIMERA DIVISION": "la-liga",
    "D1": "bundesliga", "GERMANY": "bundesliga", "BUNDESLIGA": "bundesliga",
    "I1": "serie-a", "ITALY": "serie-a", "SERIE A": "serie-a",
    "F1": "ligue-1", "FRANCE": "ligue-1", "LIGUE 1": "ligue-1",
    "N1": "eredivisie", "NETHERLANDS": "eredivisie", "EREDIVISIE": "eredivisie",
    "P1": "primeira-liga", "PORTUGAL": "primeira-liga", "PRIMEIRA LIGA": "primeira-liga",
    "B1": "belgian-pro-league", "BELGIUM": "belgian-pro-league", "FIRST DIVISION A": "belgian-pro-league", "PRO LEAGUE": "belgian-pro-league",
    "T1": "super-lig", "TURKEY": "super-lig", "SUPER LIG": "super-lig",
    "SC0": "scottish-premiership", "SCOTLAND": "scottish-premiership", "SCOTTISH PREMIERSHIP": "scottish-premiership",
}


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _parse_date(value: str) -> datetime:
    raw = value.strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.tzinfo:
                return parsed.astimezone(UTC).replace(tzinfo=None)
            if fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
                return datetime.combine(parsed.date(), time(12), UTC).replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date '{raw}' (use DD/MM/YY or YYYY-MM-DD)")


def import_training_csv(db: Session, content: bytes, filename: str, actor: str) -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("CSV must use UTF-8 encoding") from None
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames:
            raise ValueError("CSV is empty or has no header row")
        columns = {_key(name): name for name in reader.fieldnames if name}
        required = {"date": ("date", "kickoff"), "home": ("hometeam", "home", "hometeamname"),
                    "away": ("awayteam", "away", "awayteamname"), "home_goals": ("fthg", "homegoals", "home_goals"),
                    "away_goals": ("ftag", "awaygoals", "away_goals")}
        selected = {}
        for field, aliases in required.items():
            selected[field] = next((columns[a] for a in aliases if a in columns), None)
            if not selected[field]:
                raise ValueError(f"Missing required column for {field}: {', '.join(aliases)}")
        league_col = next((columns[a] for a in ("div", "league", "competition", "country") if a in columns), None)
        if not league_col:
            raise ValueError("Include a Div, League, Competition, or Country column")
        parsed = []
        errors = []
        seen_rows = set()
        for line, row in enumerate(reader, start=2):
            if None in row:
                errors.append(f"row {line}: too many values for the CSV columns")
                continue
            if not any(isinstance(value, str) and value.strip() for value in row.values()):
                continue
            label = (row.get(league_col) or "").strip()
            slug = DIVISIONS.get(_key(label).upper()) or DIVISIONS.get(_key(label))
            if not slug:
                errors.append(f"row {line}: unsupported league '{label}'")
                continue
            if slug not in EUROPEAN_LEAGUES:
                errors.append(f"row {line}: {label} is not enabled in this site")
                continue
            home, away = ((row.get(selected[k]) or "").strip() for k in ("home", "away"))
            try:
                kickoff = _parse_date(row.get(selected["date"]) or "")
                hg_raw, ag_raw = row.get(selected["home_goals"]), row.get(selected["away_goals"])
                if not hg_raw or not ag_raw or not hg_raw.strip().isdigit() or not ag_raw.strip().isdigit():
                    raise ValueError("final scores must be non-negative whole numbers")
                hg, ag = int(hg_raw), int(ag_raw)
                if hg > 30 or ag > 30:
                    raise ValueError("score is outside the accepted range")
                if not home or not away or _key(home) == _key(away):
                    raise ValueError("home and away teams must be different non-empty names")
                if kickoff >= utcnow():
                    raise ValueError("training data must contain completed matches in the past")
                row_key = (slug, kickoff.date(), _key(home), _key(away))
                if row_key in seen_rows:
                    raise ValueError("duplicate match row")
                seen_rows.add(row_key)
                parsed.append((slug, label, kickoff, home, away, hg, ag, line))
                if len(parsed) > 50_000:
                    raise ValueError("CSV cannot contain more than 50,000 match rows")
            except ValueError as exc:
                errors.append(f"row {line}: {exc}")
        if errors:
            raise ValueError("CSV validation failed: " + "; ".join(errors[:8]) + (f"; and {len(errors)-8} more" if len(errors) > 8 else ""))
        if not parsed:
            raise ValueError("CSV contains no completed match rows")
        natural = {}
        for fixture in db.scalars(select(Fixture)):
            key = (fixture.competition.league_slug, _key(fixture.home.name), _key(fixture.away.name), fixture.kickoff.date())
            natural[key] = fixture
        competitions = {c.league_slug: c for c in db.scalars(select(Competition)) if c.league_slug}
        teams = {(_key(t.name), _key(t.country)): t for t in db.scalars(select(Team))}
        created = updated = 0
        digest = hashlib.sha256(content).hexdigest()[:24]
        for slug, label, kickoff, home_name, away_name, hg, ag, line in parsed:
            league = EUROPEAN_LEAGUES[slug]
            competition = competitions.get(slug)
            if not competition:
                competition = Competition(name=league["name"], identity=f"csv-training:competition:{slug}", country=league["country"], league_slug=slug)
                db.add(competition); db.flush(); competitions[slug] = competition
            country_key = _key(league["country"])
            pair = []
            for name in (home_name, away_name):
                team = teams.get((_key(name), country_key))
                if not team:
                    team = Team(name=name, identity=f"csv-training:team:{country_key}:{_key(name)}", country=league["country"])
                    db.add(team); db.flush(); teams[(_key(name), country_key)] = team
                pair.append(team)
            home, away = pair
            match_key = (slug, _key(home_name), _key(away_name), kickoff.date())
            fixture = natural.get(match_key)
            known_at = kickoff + timedelta(hours=24)
            external_id = hashlib.sha256(f"{slug}:{kickoff.date()}:{_key(home_name)}:{_key(away_name)}".encode()).hexdigest()
            if fixture:
                updated += 1
            else:
                fixture = Fixture(provider="csv_training", external_id=external_id, competition_id=competition.id,
                                  home_id=home.id, away_id=away.id, kickoff=kickoff)
                db.add(fixture); natural[match_key] = fixture; created += 1
            fixture.competition_id, fixture.home_id, fixture.away_id = competition.id, home.id, away.id
            fixture.kickoff, fixture.status = kickoff, "finished"
            fixture.home_goals, fixture.away_goals = hg, ag
            fixture.result_known_at = known_at
            fixture.simulated = False
            fixture.enrichment = {**(fixture.enrichment or {}), "historical_import": {
                "source": "admin_csv_upload", "dataset_sha256_prefix": digest,
                "availability_rule": "kickoff_plus_24_hours_estimate", "filename": filename[:120]}}
            fixture.synced_at = utcnow()
        db.add(AuditLog(action="training_data.csv_imported", actor=actor, entity=filename[:120],
                        detail={"created": created, "updated": updated, "rows": len(parsed), "dataset_sha256_prefix": digest,
                                "availability_rule": "kickoff_plus_24_hours_estimate"}))
        db.commit()
        return {"created": created, "updated": updated, "rows": len(parsed),
                "availability_rule": "kickoff_plus_24_hours_estimate"}
    except Exception:
        db.rollback()
        raise
