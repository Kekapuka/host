from jarvis.textproc import normalize, parse_number, phonetic, phrase_score, tokenize, word_sim


def test_normalize_and_tokens_keep_offsets():
    text = "Джарвис, открой Хром!"
    assert normalize(text) == "джарвис открой хром"
    toks = tokenize(text)
    assert [t.norm for t in toks] == ["джарвис", "открой", "хром"]
    assert text[toks[2].start:toks[2].end] == "Хром"
    assert normalize("Ёлка ёж") == "елка еж"


def test_word_similarity_handles_inflections_but_not_antonyms():
    assert word_sim("музыку", "музыка") >= 0.75
    assert word_sim("открой", "открыть") >= 0.75
    assert word_sim("включи", "выключи") == 0.0
    assert word_sim("mute", "unmute") == 0.0
    assert word_sim("вк", "в") == 0.0
    assert word_sim("50", "30") == 0.0


def test_phrase_score_requires_key_words():
    score, coverage = phrase_score(["включи", "музыку"], ["включи", "музыку", "в", "вк"])
    assert coverage < 0.8
    score, coverage = phrase_score(["включи", "музыку", "вк"], ["включи", "музыку", "в", "вк"])
    assert coverage >= 0.8 and score >= 0.85
    _, coverage = phrase_score(["не", "открывай", "хром"], ["открой", "хром"])
    assert coverage < 0.8


def test_phonetic_maps_scripts_together():
    assert phonetic("джарвис") == phonetic("jarvis") == "jarvis"
    assert phonetic("жарвис") == "jarvis"
    assert phonetic("фотошоп") == phonetic("photoshop")


def test_parse_number():
    assert parse_number("50") == 50
    assert parse_number("громкость 30%") == 30
    assert parse_number("пятьдесят пять") == 55
    assert parse_number("forty two") == 42
    assert parse_number("громче") is None
