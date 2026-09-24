from subtitula.captions import Caption, to_srt, to_txt, to_vtt


def caps():
    return [
        Caption("a", 1, 0.0, 2.5, "en", "Hello everyone.", {"es": "Hola a todos."}),
        Caption("a", 2, 2.5, 5.0, "en", "Welcome to Nerdearla.", {"es": "Bienvenidos a Nerdearla."}),
        Caption("a", 3, 9.0, 11.0, "es", "¿Preguntas?", {"en": "Questions?"}),
    ]


def test_srt():
    out = to_srt(caps(), "es")
    assert out.startswith("1\n00:00:00,000 --> 00:00:02,500\nHola a todos.\n")
    assert "3\n00:00:09,000 --> 00:00:11,000\n¿Preguntas?" in out  # el tramo ya en español queda igual


def test_vtt_and_original():
    out = to_vtt(caps(), "original")
    assert out.startswith("WEBVTT")
    assert "00:00:02.500 --> 00:00:05.000\nWelcome to Nerdearla." in out


def test_txt_paragraphs_on_long_pause():
    out = to_txt(caps(), "en")
    assert out == "Hello everyone. Welcome to Nerdearla.\n\nQuestions?\n"


def test_missing_translation_falls_back_to_original():
    c = Caption("a", 1, 0, 1, "en", "kubectl apply", {})
    assert c.in_lang("pt") == "kubectl apply"
