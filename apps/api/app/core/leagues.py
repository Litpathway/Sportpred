"""Stable application IDs, independent of a feed's native competition IDs."""

EUROPEAN_LEAGUES = {
    "premier-league": {"name": "Premier League", "country": "England"},
    "la-liga": {"name": "La Liga", "country": "Spain"},
    "bundesliga": {"name": "Bundesliga", "country": "Germany"},
    "serie-a": {"name": "Serie A", "country": "Italy"},
    "ligue-1": {"name": "Ligue 1", "country": "France"},
    "eredivisie": {"name": "Eredivisie", "country": "Netherlands"},
    "primeira-liga": {"name": "Primeira Liga", "country": "Portugal"},
    "belgian-pro-league": {"name": "Belgian Pro League", "country": "Belgium"},
    "super-lig": {"name": "Süper Lig", "country": "Turkey"},
    "scottish-premiership": {"name": "Scottish Premiership", "country": "Scotland"},
}
DEFAULT_LEAGUES = ",".join(EUROPEAN_LEAGUES)
