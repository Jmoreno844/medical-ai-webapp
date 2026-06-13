from __future__ import annotations

from context_pipeline.decompose.lib import parse_decompose_result


def test_parse_decompose_result() -> None:
    raw = """
    {
      "claims": [
        {
          "claim_id": "dn_01",
          "text": "Paciente pálido.",
          "claim_type": "observation"
        }
      ]
    }
    """
    result = parse_decompose_result(raw)
    assert len(result.claims) == 1
    assert result.claims[0].claim_id == "dn_01"


def test_parse_decompose_result_via_extract_json() -> None:
    raw = 'prefix {"claims": []} suffix'
    result = parse_decompose_result(raw)
    assert result.claims == []
