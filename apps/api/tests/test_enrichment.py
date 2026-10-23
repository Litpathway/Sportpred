def test_context_statistics_require_observation_timestamp():
    from pydantic import ValidationError
    from app.schemas.contracts import EnrichmentDTO
    import pytest
    with pytest.raises(ValidationError):
        EnrichmentDTO.model_validate({"xg":{"home":1.2,"away":.8}})


def test_enrichment_records_unknowns_instead_of_assuming_no_injuries():
    from app.schemas.contracts import EnrichmentDTO
    value=EnrichmentDTO.model_validate({}).model_dump(exclude_none=True)
    assert "injuries" not in value and "lineups" not in value
