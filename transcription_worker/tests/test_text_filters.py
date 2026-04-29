from app.text_filters import normalize_transcript


def test_normalize_transcript_removes_noise_only_tags() -> None:
    assert normalize_transcript("[tos]") == ""


def test_normalize_transcript_preserves_inaudible() -> None:
    assert normalize_transcript("Paciente [inaudible] refiere dolor.") == (
        "Paciente [inaudible] refiere dolor."
    )
