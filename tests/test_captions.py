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


def test_zero_length_cues_get_a_readable_duration():
    caps = [
        Caption("a", 1, 10.0, 15.67, "en", "That's a good point.", track="en", original=True),
        Caption("a", 2, 15.67, 15.67, "en", "We didn't.", track="en", original=True),  # nació y murió a la vez
        Caption("a", 3, 15.67, 19.0, "en", "Can I share the audio?", track="en", original=True),
        Caption("a", 4, 30.0, 30.2, "en", "Last one.", track="en", original=True),
    ]
    srt = to_srt(caps, "en")
    assert "00:00:15,670 --> 00:00:15,670" not in srt
    assert "00:00:15,670 --> 00:00:16,470\nWe didn't." in srt  # 0,8 s como mínimo
    assert "00:00:30,000 --> 00:00:30,800\nLast one." in srt
    assert "00:00:10,000 --> 00:00:15,670\nThat's a good point." in srt  # las normales no cambian


def test_missing_translation_falls_back_to_original():
    c = Caption("a", 1, 0, 1, "en", "kubectl apply", {})
    assert c.in_lang("pt") == "kubectl apply"
