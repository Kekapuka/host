import pytest

from jarvis.matcher import (
    CommandEntry,
    Matcher,
    find_wake_word,
    match_word_list,
    parse_trigger,
    split_chain,
)

CHAIN = ["и", "затем", "потом"]


def cmd(path, *triggers):
    return CommandEntry(path, path, [parse_trigger(t) for t in triggers])


@pytest.fixture
def matcher():
    return Matcher([
        cmd("chrome/open", "открой хром", "запусти хром", "open chrome"),
        cmd("vk/music", "включи музыку в вк", "включи музыку вконтакте"),
        cmd("launcher/open", "открой {app}", "запусти {app}"),
        cmd("search/google", "найди {query}"),
        cmd("search/youtube", "найди {query} на ютубе"),
        cmd("typing/type", "напиши {text}"),
        cmd("media/mute", "выключи звук"),
        cmd("media/unmute", "включи звук"),
        cmd("volume/set", "громкость {level}"),
    ])


@pytest.mark.parametrize("text,expected", [
    ("Джарвис, открой хром", (True, "открой хром")),
    ("джарвиз открой хром", (True, "открой хром")),
    ("Jarvis open chrome", (True, "open chrome")),
    ("эй джарвис", (True, "")),
    ("открой хром, джарвис", (True, "открой хром")),
    ("Давид открой хром", (False, "Давид открой хром")),
])
def test_wake_word(text, expected):
    assert find_wake_word(text, "джарвис") == expected


def test_custom_wake_word():
    assert find_wake_word("Компьютер, который час", "компьютер") == (True, "который час")


def test_chain_of_commands(matcher):
    plan = matcher.plan("открой хром и включи музыку в вк", CHAIN)
    assert [s.match.command.path for s in plan] == ["chrome/open", "vk/music"]


def test_chain_reuses_verb(matcher):
    plan = matcher.plan("открой хром и телеграм", CHAIN)
    assert [s.match.command.path for s in plan] == ["chrome/open", "launcher/open"]
    assert plan[1].match.captures == {"app": "телеграм"}


def test_free_text_is_not_split(matcher):
    plan = matcher.plan("напиши привет и пока", CHAIN)
    assert len(plan) == 1
    assert plan[0].match.captures["text"] == "привет и пока"


def test_placeholder_prefers_more_specific_trigger(matcher):
    m = matcher.match("найди котиков на ютубе")
    assert m.command.path == "search/youtube"
    assert m.captures == {"query": "котиков"}
    assert matcher.match("найди рецепт борща").captures == {"query": "рецепт борща"}


def test_captures_keep_original_case(matcher):
    assert matcher.match("напиши Привет, Мир").captures == {"text": "Привет, Мир"}


def test_antonyms_and_negation(matcher):
    assert matcher.match("выключи звук").command.path == "media/mute"
    assert matcher.match("включи звук").command.path == "media/unmute"
    assert matcher.match("выключи музыку в вк") is None
    assert matcher.match("не открывай хром") is None


def test_missing_key_word_does_not_match(matcher):
    assert matcher.match("включи музыку") is None


def test_unknown_parts_are_reported(matcher):
    plan = matcher.plan("открой хром и свари кофе", CHAIN)
    assert plan[0].match.command.path == "chrome/open"


def test_split_chain_custom_words():
    assert split_chain("открой хром а потом найди котиков", ["а потом"]) == ["открой хром", "найди котиков"]
    assert split_chain("и открой хром", ["и"]) == ["открой хром"]


def test_word_lists():
    yes = ["да", "правильно", "подтверждаю"]
    assert match_word_list("да", yes)
    assert match_word_list("Да, подтверждаю", yes)
    assert match_word_list("правильно", yes)
    assert not match_word_list("нет", yes)
    assert not match_word_list("отмени действие", ["отмена", "отменить"], strict=True)
    assert match_word_list("отмена", ["отмена", "отменить"], strict=True)
    assert match_word_list("давай", ["давай"])
