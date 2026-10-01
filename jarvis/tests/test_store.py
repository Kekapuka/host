import json

import pytest

from jarvis import catalog
from jarvis.store import FOLDER_META, StoreError, sanitize_name


def names(nodes):
    return [n["name"] for n in nodes]


def test_seeding_creates_default_folders(store):
    tree = store.tree()
    top = names(tree)
    assert "Google Chrome" in top and "ВКонтакте" in top and "Система" in top
    vk = next(n for n in tree if n["name"] == "ВКонтакте")
    music = next(n for n in vk["children"] if n["name"] == "Музыка")
    assert "Включить музыку" in names(music["children"])
    # seeding happens once even if the user deletes everything
    for node in tree:
        store.delete(node["path"])
    assert store.ensure_seeded("ru") is False
    assert store.tree() == []


def test_every_catalog_pack_builds_and_is_valid(store):
    for app in catalog.APPS:
        pack = catalog.build_pack(app["id"], "ru")
        assert pack["type"] == "folder" and pack["meta"]["app"] == app["id"]
        assert pack["items"], app["id"]
        catalog.build_pack(app["id"], "en")


def test_crud_and_rename(store):
    folder = store.create_folder("", "Мой софт")
    sub = store.create_folder(folder, "Разное")
    path = store.create_command(sub, "Почта")
    assert path == "Мой софт/Разное/Почта.json"
    saved = store.save_command(path, {"triggers": ["проверь почту", "проверь почту", ""],
                                      "actions": [{"type": "open_url", "url": "https://mail.ru"}, {"type": "evil"}],
                                      "response": "Открываю"})
    assert saved["data"]["triggers"] == ["проверь почту"]
    assert saved["data"]["actions"] == [{"type": "open_url", "url": "https://mail.ru"}]
    renamed = store.rename(path, "Почта 2")
    assert renamed == "Мой софт/Разное/Почта 2.json"
    moved = store.move(renamed, folder)
    assert moved == "Мой софт/Почта 2.json"
    dup = store.duplicate(moved)
    assert dup == "Мой софт/Почта 2 (копия).json"
    with pytest.raises(StoreError):
        store.move(folder, sub)  # into its own child
    store.delete(folder)
    assert "Мой софт" not in names(store.tree())


def test_unique_names(store):
    a = store.create_folder("", "Игры")
    b = store.create_folder("", "Игры")
    assert (a, b) == ("Игры", "Игры (2)")


def test_path_traversal_is_rejected(store):
    with pytest.raises(StoreError):
        store.read("../settings.json")
    with pytest.raises(StoreError):
        store.create_folder("../..", "x")


def test_sanitize_name():
    assert sanitize_name('PUBG: Battlegrounds') == "PUBG Battlegrounds"
    assert sanitize_name(" _folder ") == "folder"
    assert sanitize_name("con") == "con_"
    with pytest.raises(StoreError):
        sanitize_name("  ...  ")


def test_folder_meta_is_inherited(store):
    folder = store.create_folder("", "Игра", {"app": "steam", "path": "C:/Games/game.exe"})
    sub = store.create_folder(folder, "Сохранения")
    cmd = store.create_command(sub, "Запуск")
    item = store.read(cmd)
    assert item["folder"]["app"] == "steam"
    assert item["folder"]["path"] == "C:/Games/game.exe"


def test_entries_cache_and_disabled(store):
    first = store.entries()
    assert store.entries() is first  # cached
    folder = store.create_folder("", "Тест")
    path = store.create_command(folder, "Команда")
    store.save_command(path, {"triggers": ["тестовая фраза"], "actions": []})
    entries = store.entries()
    assert any(e.path == path for e in entries)
    store.save_folder(folder, {"enabled": False})
    assert not any(e.path == path for e in store.entries())


def test_connect_and_disconnect(store):
    path = store.connect_app("telegram", "ru")
    assert path == "Telegram"
    assert store.connect_app("telegram", "ru") == path  # idempotent
    meta = json.loads((store.root / path / FOLDER_META).read_text(encoding="utf-8"))
    assert meta == {"app": "telegram"}
    assert store.connected_apps()["telegram"] == path
    assert store.disconnect_app("telegram") is True
    assert "telegram" not in store.connected_apps()
