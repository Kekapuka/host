"""Catalog of known applications and ready-made command packs.

"Connecting" an app in the UI creates a folder in the command editor filled with the commands
built here. Each command is a JSON file with trigger phrases, a list of actions and a reply.
"""
from __future__ import annotations

from typing import Any

from .util import detect_lang

CATEGORIES = [
    {"id": "popular", "ru": "Популярное", "en": "Popular"},
    {"id": "social", "ru": "Соцсети и общение", "en": "Social & messaging"},
    {"id": "creative", "ru": "Дизайн и творчество", "en": "Design & creativity"},
    {"id": "media", "ru": "Видео, музыка и стриминг", "en": "Video, music & streaming"},
    {"id": "work", "ru": "Работа и разработка", "en": "Work & development"},
    {"id": "gaming", "ru": "Игровые сервисы", "en": "Gaming services"},
    {"id": "defaults", "ru": "Команды по умолчанию", "en": "Default commands"},
]

BROWSER_IDS = ("chrome", "yandex", "edge", "firefox", "opera", "operagx", "brave")

PF = "%ProgramFiles%"
PF86 = "%ProgramFiles(x86)%"
LAD = "%LocalAppData%"
AD = "%AppData%"


def _app(id_: str, name: Any, cats: list[str], abbr: str, color: str, aliases: list[str], *,
         kind: str = "app", exe: list[str] | None = None, paths: list[str] | None = None,
         start: list[str] | None = None, uri: str | None = None, scheme: str | None = None,
         web: str | None = None, process: list[str] | None = None, args: list[str] | None = None,
         force_close: bool = False, pack: str | None = None, desc: Any = None,
         private_arg: str | None = None) -> dict[str, Any]:
    return {
        "id": id_, "name": name, "categories": cats, "abbr": abbr, "color": color,
        "aliases": aliases, "kind": kind, "exe": exe or [], "paths": paths or [],
        "start": start or [], "uri": uri, "scheme": scheme, "web": web,
        "process": process if process is not None else list(exe or []),
        "args": args or [], "force_close": force_close, "pack": pack, "desc": desc,
        "private_arg": private_arg,
    }


def _web(id_: str, name: Any, cats: list[str], abbr: str, color: str, aliases: list[str], url: str,
         **kw: Any) -> dict[str, Any]:
    return _app(id_, name, cats, abbr, color, aliases, kind="web", web=url, **kw)


def _steam_game(id_: str, name: str, appid: int, abbr: str, color: str, aliases: list[str],
                process: list[str]) -> dict[str, Any]:
    return _app(id_, name, ["gaming"], abbr, color, aliases, kind="game",
                uri=f"steam://rungameid/{appid}", scheme="steam", process=process,
                desc={"ru": "Запуск через Steam", "en": "Launched via Steam"})


def _pack(id_: str, name: dict[str, str], abbr: str, desc: dict[str, str]) -> dict[str, Any]:
    return _app(id_, name, ["defaults"], abbr, "#111111", [], kind="pack", pack=id_, desc=desc)


APPS: list[dict[str, Any]] = [
    # --- browsers and Windows essentials (Popular) ------------------------------------------
    _app("chrome", "Google Chrome", ["popular"], "Ch", "#4285F4",
         ["хром", "гугл хром", "google chrome", "chrome", "браузер"],
         kind="browser", exe=["chrome.exe"],
         paths=[rf"{PF}\Google\Chrome\Application\chrome.exe",
                rf"{PF86}\Google\Chrome\Application\chrome.exe",
                rf"{LAD}\Google\Chrome\Application\chrome.exe"],
         start=["Google Chrome"], private_arg="--incognito"),
    _app("yandex", {"ru": "Яндекс Браузер", "en": "Yandex Browser"}, ["popular"], "Яб", "#FC3F1D",
         ["яндекс браузер", "яндекс", "yandex browser", "yandex"],
         kind="browser", exe=["browser.exe"],
         paths=[rf"{LAD}\Yandex\YandexBrowser\Application\browser.exe"],
         start=["Яндекс Браузер", "Yandex Browser", "Yandex", "Яндекс"], private_arg="--incognito"),
    _app("edge", "Microsoft Edge", ["popular"], "Ed", "#0C59A4",
         ["эдж", "edge", "майкрософт эдж", "microsoft edge"],
         kind="browser", exe=["msedge.exe"],
         paths=[rf"{PF86}\Microsoft\Edge\Application\msedge.exe",
                rf"{PF}\Microsoft\Edge\Application\msedge.exe"],
         start=["Microsoft Edge"], uri="microsoft-edge:", private_arg="-inprivate"),
    _app("firefox", "Mozilla Firefox", ["popular"], "Ff", "#FF7139",
         ["файрфокс", "фаерфокс", "firefox", "мозила", "mozilla"],
         kind="browser", exe=["firefox.exe"],
         paths=[rf"{PF}\Mozilla Firefox\firefox.exe", rf"{PF86}\Mozilla Firefox\firefox.exe"],
         start=["Firefox", "Mozilla Firefox"], private_arg="-private-window"),
    _app("opera", "Opera", ["popular"], "Op", "#FF1B2D", ["опера", "opera"],
         kind="browser", exe=["launcher.exe"], process=["opera.exe"],
         paths=[rf"{LAD}\Programs\Opera\launcher.exe"], start=["Opera Browser", "Opera"],
         private_arg="--private"),
    _app("operagx", "Opera GX", ["popular", "gaming"], "GX", "#FA1E4E",
         ["опера gx", "опера джи икс", "opera gx"],
         kind="browser", exe=["launcher.exe"], process=["opera.exe"],
         paths=[rf"{LAD}\Programs\Opera GX\launcher.exe"], start=["Opera GX Browser", "Opera GX"],
         private_arg="--private"),
    _app("brave", "Brave", ["popular"], "Br", "#FB542B", ["брейв", "brave"],
         kind="browser", exe=["brave.exe"],
         paths=[rf"{PF}\BraveSoftware\Brave-Browser\Application\brave.exe",
                rf"{LAD}\BraveSoftware\Brave-Browser\Application\brave.exe"],
         start=["Brave"], private_arg="--incognito"),
    _app("explorer", {"ru": "Проводник", "en": "File Explorer"}, ["popular"], "Пр", "#F5C342",
         ["проводник", "explorer", "файлы", "мой компьютер", "этот компьютер"],
         exe=["explorer.exe"], paths=[r"%WINDIR%\explorer.exe"], process=[], pack="explorer"),
    _app("notepad", {"ru": "Блокнот", "en": "Notepad"}, ["popular"], "Бл", "#5BA4E6",
         ["блокнот", "notepad", "ноутпад"], exe=["notepad.exe"], paths=[r"%WINDIR%\System32\notepad.exe"],
         start=["Блокнот", "Notepad"]),
    _app("calc", {"ru": "Калькулятор", "en": "Calculator"}, ["popular"], "Кл", "#6B6B6B",
         ["калькулятор", "calculator", "калькулятора"], exe=["calc.exe"],
         paths=[r"%WINDIR%\System32\calc.exe"],
         process=["CalculatorApp.exe", "Calculator.exe", "calc.exe"], start=["Калькулятор", "Calculator"]),
    _app("paint", "Paint", ["popular", "creative"], "Pt", "#2C8EF5", ["паинт", "пэйнт", "paint", "пейнт"],
         exe=["mspaint.exe"], start=["Paint"]),
    _app("taskmgr", {"ru": "Диспетчер задач", "en": "Task Manager"}, ["popular"], "Дз", "#3A7D44",
         ["диспетчер задач", "task manager"], exe=["taskmgr.exe"], process=["Taskmgr.exe"],
         pack="taskmgr"),
    _app("settings", {"ru": "Параметры Windows", "en": "Windows Settings"}, ["popular"], "Пм", "#555555",
         ["параметры", "параметры windows", "настройки windows", "настройки виндовс", "windows settings"],
         uri="ms-settings:", process=["SystemSettings.exe"]),
    _app("control", {"ru": "Панель управления", "en": "Control Panel"}, ["popular"], "Пу", "#3B6EA5",
         ["панель управления", "control panel"], exe=["control.exe"], process=[]),
    _app("snipping", {"ru": "Ножницы", "en": "Snipping Tool"}, ["popular"], "Нж", "#C83E83",
         ["ножницы", "snipping tool"], exe=["SnippingTool.exe"], uri="ms-screenclip:",
         start=["Ножницы", "Snipping Tool"]),

    # --- social & messaging -----------------------------------------------------------------
    _web("vk", {"ru": "ВКонтакте", "en": "VK"}, ["social", "media", "popular"], "VK", "#0077FF",
         ["вк", "вконтакте", "в контакте", "vk", "vkontakte"], "https://vk.com/feed", pack="vk"),
    _app("telegram", "Telegram", ["social", "popular"], "Tg", "#26A5E4",
         ["телеграм", "телеграмм", "телега", "telegram", "тг"],
         exe=["Telegram.exe"], paths=[rf"{AD}\Telegram Desktop\Telegram.exe"],
         start=["Telegram", "Telegram Desktop"], uri="tg://", scheme="tg",
         web="https://web.telegram.org/a/", force_close=True),
    _app("whatsapp", "WhatsApp", ["social"], "Wa", "#25D366", ["ватсап", "вотсап", "whatsapp", "ватсапп"],
         exe=["WhatsApp.exe"], process=["WhatsApp.exe", "WhatsApp.Root.exe"], start=["WhatsApp"],
         uri="whatsapp:", scheme="whatsapp", web="https://web.whatsapp.com", force_close=True),
    _app("discord", "Discord", ["social", "gaming", "popular"], "Dc", "#5865F2",
         ["дискорд", "дискорде", "discord", "дс"],
         exe=["Update.exe"], process=["Discord.exe"], paths=[rf"{LAD}\Discord\Update.exe"],
         args=["--processStart", "Discord.exe"], start=["Discord"], uri="discord://", scheme="discord",
         web="https://discord.com/app", force_close=True, pack="discord"),
    _app("max", "MAX", ["social"], "MX", "#7B3FF2", ["макс", "max", "мессенджер макс"],
         exe=["MAX.exe"], start=["MAX"], web="https://web.max.ru", force_close=True),
    _app("zoom", "Zoom", ["social", "work"], "Zm", "#0B5CFF", ["зум", "zoom"],
         exe=["Zoom.exe"], paths=[rf"{AD}\Zoom\bin\Zoom.exe"], start=["Zoom Workplace", "Zoom"],
         uri="zoommtg://", scheme="zoommtg"),
    _app("viber", "Viber", ["social"], "Vb", "#7360F2", ["вайбер", "viber"],
         exe=["Viber.exe"], paths=[rf"{LAD}\Viber\Viber.exe"], start=["Viber"], force_close=True),
    _app("teams", "Microsoft Teams", ["social", "work"], "Ts", "#5059C9", ["тимс", "teams", "майкрософт тимс"],
         exe=["ms-teams.exe"], start=["Microsoft Teams"], uri="msteams:", scheme="msteams"),
    _app("slack", "Slack", ["social", "work"], "Sl", "#4A154B", ["слак", "slack"],
         exe=["slack.exe"], paths=[rf"{LAD}\slack\slack.exe"], start=["Slack"], web="https://app.slack.com"),
    _web("ok", {"ru": "Одноклассники", "en": "Odnoklassniki"}, ["social"], "OK", "#EE8208",
         ["одноклассники", "однокласники", "ок ру", "ok ru"], "https://ok.ru"),
    _web("instagram", "Instagram", ["social"], "Ig", "#E4405F", ["инстаграм", "инста", "instagram"],
         "https://www.instagram.com"),
    _web("x", "X (Twitter)", ["social"], "X", "#000000", ["твиттер", "твитер", "twitter", "икс"], "https://x.com"),
    _web("reddit", "Reddit", ["social"], "Rd", "#FF4500", ["реддит", "редит", "reddit"], "https://www.reddit.com"),
    _web("facebook", "Facebook", ["social"], "Fb", "#1877F2", ["фейсбук", "facebook"], "https://www.facebook.com"),
    _web("gmail", "Gmail", ["social"], "Gm", "#EA4335", ["почту гугл", "джимейл", "gmail", "гмейл"],
         "https://mail.google.com"),
    _web("yandexmail", {"ru": "Яндекс Почта", "en": "Yandex Mail"}, ["social"], "ЯП", "#FC3F1D",
         ["яндекс почту", "яндекс почта", "почту", "почта"], "https://mail.yandex.ru"),
    _web("mailru", {"ru": "Почта Mail.ru", "en": "Mail.ru"}, ["social"], "@", "#005FF9",
         ["мейл ру", "почту мейл", "mail ru"], "https://e.mail.ru"),

    # --- design & creativity ----------------------------------------------------------------
    _app("figma", "Figma", ["creative", "work"], "Fg", "#A259FF", ["фигма", "фигму", "figma"],
         exe=["Figma.exe"], paths=[rf"{LAD}\Figma\Figma.exe"], start=["Figma"], web="https://www.figma.com"),
    _app("photoshop", "Adobe Photoshop", ["creative"], "Ps", "#31A8FF", ["фотошоп", "photoshop"],
         exe=["Photoshop.exe"], start=["Adobe Photoshop"]),
    _app("illustrator", "Adobe Illustrator", ["creative"], "Ai", "#FF9A00", ["иллюстратор", "illustrator"],
         exe=["Illustrator.exe"], start=["Adobe Illustrator"]),
    _app("premiere", "Adobe Premiere Pro", ["creative"], "Pr", "#9999FF", ["премьер", "премьер про", "premiere"],
         exe=["Adobe Premiere Pro.exe"], start=["Adobe Premiere Pro"]),
    _app("aftereffects", "Adobe After Effects", ["creative"], "Ae", "#9999FF",
         ["афтер эффектс", "афтер эффект", "after effects"], exe=["AfterFX.exe"], start=["Adobe After Effects"]),
    _app("lightroom", "Adobe Lightroom", ["creative"], "Lr", "#31A8FF", ["лайтрум", "lightroom"],
         exe=["Lightroom.exe"], start=["Adobe Lightroom Classic", "Adobe Lightroom"]),
    _app("blender", "Blender", ["creative"], "Bl", "#E87D0D", ["блендер", "blender"],
         exe=["blender.exe"], start=["Blender"]),
    _app("gimp", "GIMP", ["creative"], "Gp", "#5C5543", ["гимп", "gimp"],
         exe=["gimp.exe"], process=["gimp-3.0.exe", "gimp-2.10.exe", "gimp.exe"], start=["GIMP"]),
    _app("krita", "Krita", ["creative"], "Kr", "#3BABFF", ["крита", "krita"], exe=["krita.exe"], start=["Krita"]),
    _app("paintnet", "Paint.NET", ["creative"], "P.", "#2D6FD1", ["паинт нет", "пэйнт нет", "paint net"],
         exe=["paintdotnet.exe"], start=["Paint.NET", "paint.net"]),
    _app("inkscape", "Inkscape", ["creative"], "Ik", "#000000", ["инкскейп", "inkscape"],
         exe=["inkscape.exe"], start=["Inkscape"]),
    _app("davinci", "DaVinci Resolve", ["creative"], "Dv", "#233A51", ["давинчи", "давинчи резолв", "davinci"],
         exe=["Resolve.exe"], start=["DaVinci Resolve"]),
    _app("capcut", "CapCut", ["creative"], "Cc", "#000000", ["капкат", "capcut"],
         exe=["CapCut.exe"], start=["CapCut"]),
    _app("canva", "Canva", ["creative"], "Cv", "#00C4CC", ["канва", "canva"],
         exe=["Canva.exe"], start=["Canva"], web="https://www.canva.com"),
    _app("audacity", "Audacity", ["creative"], "Au", "#0000CC", ["аудасити", "audacity"],
         exe=["Audacity.exe"], start=["Audacity"]),
    _app("flstudio", "FL Studio", ["creative"], "FL", "#FF8800", ["фл студио", "fl studio", "фруктовый лупс"],
         exe=["FL64.exe"], process=["FL64.exe", "FL.exe"], start=["FL Studio"]),
    _app("ableton", "Ableton Live", ["creative"], "Ab", "#111111", ["аблетон", "ableton"],
         exe=["Ableton Live.exe"], start=["Ableton Live"]),
    _app("cinema4d", "Cinema 4D", ["creative"], "C4", "#011A6A", ["синема", "синема 4д", "cinema 4d"],
         exe=["Cinema 4D.exe"], start=["Cinema 4D", "Maxon Cinema 4D"]),
    _web("pinterest", "Pinterest", ["creative", "social"], "Pi", "#E60023", ["пинтерест", "pinterest"],
         "https://www.pinterest.com"),

    # --- video, music & streaming -----------------------------------------------------------
    _web("youtube", "YouTube", ["media", "popular"], "YT", "#FF0000",
         ["ютуб", "ютюб", "youtube", "ютубе"], "https://www.youtube.com", pack="youtube"),
    _web("vkvideo", {"ru": "VK Видео", "en": "VK Video"}, ["media"], "VV", "#0077FF",
         ["вк видео", "vk видео", "vk video"], "https://vkvideo.ru"),
    _app("yandexmusic", {"ru": "Яндекс Музыка", "en": "Yandex Music"}, ["media", "popular"], "ЯМ", "#FFCC00",
         ["яндекс музыка", "яндекс музыку", "yandex music"],
         exe=["Яндекс Музыка.exe"], start=["Яндекс Музыка", "Yandex Music"], web="https://music.yandex.ru",
         pack="yandexmusic"),
    _app("spotify", "Spotify", ["media", "popular"], "Sp", "#1DB954", ["спотифай", "спотик", "spotify"],
         exe=["Spotify.exe"], paths=[rf"{AD}\Spotify\Spotify.exe"], start=["Spotify"],
         uri="spotify:", scheme="spotify", web="https://open.spotify.com", pack="spotify"),
    _web("twitch", "Twitch", ["media", "gaming"], "Tw", "#9146FF", ["твич", "twitch"], "https://www.twitch.tv"),
    _web("kinopoisk", {"ru": "Кинопоиск", "en": "Kinopoisk"}, ["media"], "КП", "#FF5500",
         ["кинопоиск", "kinopoisk"], "https://hd.kinopoisk.ru"),
    _web("rutube", "Rutube", ["media"], "Ru", "#100943", ["рутуб", "rutube"], "https://rutube.ru"),
    _web("netflix", "Netflix", ["media"], "N", "#E50914", ["нетфликс", "netflix"], "https://www.netflix.com"),
    _web("soundcloud", "SoundCloud", ["media"], "SC", "#FF5500", ["саундклауд", "soundcloud"], "https://soundcloud.com"),
    _web("ivi", {"ru": "Иви", "en": "ivi"}, ["media"], "ivi", "#EA003D", ["иви", "ivi"], "https://www.ivi.ru"),
    _web("okko", "Okko", ["media"], "Ok", "#5A2AE0", ["окко", "okko"], "https://okko.tv"),
    _web("tiktok", "TikTok", ["media", "social"], "TT", "#000000", ["тикток", "тик ток", "tiktok"],
         "https://www.tiktok.com"),
    _app("applemusic", "Apple Music", ["media"], "AM", "#FA243C", ["эпл мьюзик", "apple music"],
         exe=["AppleMusic.exe"], start=["Apple Music", "iTunes"], web="https://music.apple.com"),
    _app("obs", "OBS Studio", ["media", "creative"], "OBS", "#302E31", ["обс", "obs", "обс студио"],
         exe=["obs64.exe"], paths=[rf"{PF}\obs-studio\bin\64bit\obs64.exe"], start=["OBS Studio"]),
    _app("streamlabs", "Streamlabs Desktop", ["media"], "SL", "#80F5D2", ["стримлабс", "streamlabs"],
         exe=["Streamlabs Desktop.exe"], start=["Streamlabs Desktop", "Streamlabs OBS"]),
    _app("vlc", "VLC", ["media"], "VLC", "#FF8800", ["влц", "vlc", "влс"],
         exe=["vlc.exe"], paths=[rf"{PF}\VideoLAN\VLC\vlc.exe", rf"{PF86}\VideoLAN\VLC\vlc.exe"],
         start=["VLC media player"]),
    _app("aimp", "AIMP", ["media"], "Ai", "#F28C28", ["аимп", "aimp", "аймп"],
         exe=["AIMP.exe"], paths=[rf"{PF}\AIMP\AIMP.exe", rf"{PF86}\AIMP\AIMP.exe"], start=["AIMP"]),
    _app("foobar", "foobar2000", ["media"], "fb", "#444444", ["фубар", "foobar"],
         exe=["foobar2000.exe"], paths=[rf"{PF}\foobar2000\foobar2000.exe", rf"{PF86}\foobar2000\foobar2000.exe"],
         start=["foobar2000"]),

    # --- work & development -----------------------------------------------------------------
    _app("vscode", "Visual Studio Code", ["work", "popular"], "VS", "#007ACC",
         ["вс код", "vs code", "вскод", "визуал студио код", "visual studio code", "код"],
         exe=["Code.exe"], paths=[rf"{LAD}\Programs\Microsoft VS Code\Code.exe", rf"{PF}\Microsoft VS Code\Code.exe"],
         start=["Visual Studio Code"]),
    _app("visualstudio", "Visual Studio", ["work"], "VS", "#5C2D91", ["визуал студио", "visual studio"],
         exe=["devenv.exe"], start=["Visual Studio 2022", "Visual Studio"]),
    _app("pycharm", "PyCharm", ["work"], "PC", "#21D789", ["пайчарм", "pycharm"],
         exe=["pycharm64.exe"], start=["PyCharm"]),
    _app("idea", "IntelliJ IDEA", ["work"], "IJ", "#FE315D", ["идея", "intellij", "интеллиджей"],
         exe=["idea64.exe"], start=["IntelliJ IDEA"]),
    _app("webstorm", "WebStorm", ["work"], "WS", "#07C3F2", ["вебшторм", "webstorm"],
         exe=["webstorm64.exe"], start=["WebStorm"]),
    _app("androidstudio", "Android Studio", ["work"], "AS", "#3DDC84", ["андроид студио", "android studio"],
         exe=["studio64.exe"], start=["Android Studio"]),
    _app("cursor", "Cursor", ["work"], "Cu", "#000000", ["курсор", "cursor"],
         exe=["Cursor.exe"], paths=[rf"{LAD}\Programs\cursor\Cursor.exe"], start=["Cursor"]),
    _app("sublime", "Sublime Text", ["work"], "ST", "#FF9800", ["саблайм", "sublime"],
         exe=["sublime_text.exe"], paths=[rf"{PF}\Sublime Text\sublime_text.exe"], start=["Sublime Text"]),
    _app("notepadpp", "Notepad++", ["work"], "N+", "#90E59A", ["нотпад плюс плюс", "notepad плюс плюс", "notepad++"],
         exe=["notepad++.exe"], paths=[rf"{PF}\Notepad++\notepad++.exe"], start=["Notepad++"]),
    _app("terminal", "Windows Terminal", ["work"], ">_", "#2D2D2D", ["терминал", "terminal"],
         exe=["wt.exe"], process=["WindowsTerminal.exe"], start=["Терминал", "Terminal"]),
    _app("cmd", {"ru": "Командная строка", "en": "Command Prompt"}, ["work"], "C:", "#0C0C0C",
         ["командную строку", "командная строка", "консоль", "cmd"], exe=["cmd.exe"]),
    _app("powershell", "PowerShell", ["work"], "PS", "#012456", ["пауэршелл", "повершелл", "powershell"],
         exe=["powershell.exe"]),
    _app("gitbash", "Git Bash", ["work"], "Gb", "#F05032", ["гит баш", "git bash"],
         exe=["git-bash.exe"], paths=[rf"{PF}\Git\git-bash.exe"], start=["Git Bash"]),
    _app("githubdesktop", "GitHub Desktop", ["work"], "GH", "#24292F", ["гитхаб десктоп", "github desktop"],
         exe=["GitHubDesktop.exe"], paths=[rf"{LAD}\GitHubDesktop\GitHubDesktop.exe"], start=["GitHub Desktop"]),
    _web("github", "GitHub", ["work"], "GH", "#24292F", ["гитхаб", "github"], "https://github.com"),
    _app("docker", "Docker Desktop", ["work"], "Dk", "#2496ED", ["докер", "docker"],
         exe=["Docker Desktop.exe"], paths=[rf"{PF}\Docker\Docker\Docker Desktop.exe"], start=["Docker Desktop"]),
    _app("postman", "Postman", ["work"], "Pm", "#FF6C37", ["постман", "postman"],
         exe=["Postman.exe"], paths=[rf"{LAD}\Postman\Postman.exe"], start=["Postman"]),
    _app("word", "Microsoft Word", ["work", "popular"], "W", "#185ABD", ["ворд", "word", "майкрософт ворд"],
         exe=["winword.exe"], process=["WINWORD.EXE"], start=["Word"]),
    _app("excel", "Microsoft Excel", ["work", "popular"], "X", "#107C41", ["эксель", "excel", "ексель"],
         exe=["excel.exe"], process=["EXCEL.EXE"], start=["Excel"]),
    _app("powerpoint", "Microsoft PowerPoint", ["work"], "P", "#C43E1C", ["пауэрпоинт", "повер поинт", "powerpoint"],
         exe=["powerpnt.exe"], process=["POWERPNT.EXE"], start=["PowerPoint"]),
    _app("outlook", "Microsoft Outlook", ["work"], "O", "#0078D4", ["аутлук", "outlook"],
         exe=["outlook.exe"], process=["OUTLOOK.EXE", "olk.exe"], start=["Outlook", "Outlook (new)"]),
    _app("onenote", "OneNote", ["work"], "N", "#7719AA", ["ван ноут", "onenote"],
         exe=["onenote.exe"], process=["ONENOTE.EXE"], start=["OneNote"]),
    _app("notion", "Notion", ["work"], "No", "#000000", ["ноушен", "ноушн", "notion"],
         exe=["Notion.exe"], paths=[rf"{LAD}\Programs\Notion\Notion.exe"], start=["Notion"],
         web="https://www.notion.so"),
    _app("obsidian", "Obsidian", ["work"], "Ob", "#7C3AED", ["обсидиан", "obsidian"],
         exe=["Obsidian.exe"], paths=[rf"{LAD}\Programs\Obsidian\Obsidian.exe", rf"{LAD}\Obsidian\Obsidian.exe"],
         start=["Obsidian"], uri="obsidian://", scheme="obsidian"),
    _app("chatgpt", "ChatGPT", ["work"], "GP", "#10A37F", ["чат гпт", "чатгпт", "chatgpt", "чат джипити"],
         exe=["ChatGPT.exe"], start=["ChatGPT"], web="https://chatgpt.com"),
    _web("deepseek", "DeepSeek", ["work"], "DS", "#4D6BFE", ["дипсик", "deepseek"], "https://chat.deepseek.com"),
    _app("claude", "Claude", ["work"], "Cl", "#D97757", ["клод", "claude"],
         exe=["claude.exe"], start=["Claude"], web="https://claude.ai"),
    _web("gdocs", "Google Docs", ["work"], "Gd", "#4285F4", ["гугл документы", "google docs", "гугл доки"],
         "https://docs.google.com"),
    _web("gdrive", "Google Drive", ["work"], "Dr", "#0F9D58", ["гугл диск", "google drive"], "https://drive.google.com"),
    _app("yadisk", {"ru": "Яндекс Диск", "en": "Yandex Disk"}, ["work"], "ЯД", "#FC3F1D",
         ["яндекс диск", "yandex disk"], exe=["YandexDisk2.exe"], start=["Яндекс Диск", "Yandex Disk"],
         web="https://disk.yandex.ru"),
    _web("trello", "Trello", ["work"], "Tr", "#0079BF", ["трелло", "trello"], "https://trello.com"),
    _app("anydesk", "AnyDesk", ["work"], "AD", "#EF443B", ["энидеск", "anydesk"],
         exe=["AnyDesk.exe"], paths=[rf"{PF86}\AnyDesk\AnyDesk.exe", rf"{PF}\AnyDesk\AnyDesk.exe"], start=["AnyDesk"]),
    _app("teamviewer", "TeamViewer", ["work"], "TV", "#0E8EE9", ["тимвьювер", "teamviewer"],
         exe=["TeamViewer.exe"], paths=[rf"{PF}\TeamViewer\TeamViewer.exe"], start=["TeamViewer"]),
    _app("winrar", "WinRAR", ["work"], "Rr", "#7D2E8E", ["винрар", "winrar"],
         exe=["WinRAR.exe"], paths=[rf"{PF}\WinRAR\WinRAR.exe"], start=["WinRAR"]),
    _app("7zip", "7-Zip", ["work"], "7z", "#000000", ["севен зип", "7 zip", "7zip"],
         exe=["7zFM.exe"], paths=[rf"{PF}\7-Zip\7zFM.exe"], start=["7-Zip File Manager"]),
    _app("1c", "1С:Предприятие", ["work"], "1С", "#FFD300", ["один с", "1с", "1c", "1 с"],
         exe=["1cv8s.exe"], process=["1cv8.exe", "1cv8s.exe", "1cv8c.exe"], start=["1С:Предприятие", "1C:Enterprise"]),

    # --- gaming services and games ----------------------------------------------------------
    _app("steam", "Steam", ["gaming", "popular"], "St", "#1B2838", ["стим", "steam", "стиме"],
         exe=["steam.exe"], paths=[rf"{PF86}\Steam\steam.exe", rf"{PF}\Steam\steam.exe"],
         start=["Steam"], uri="steam://open/main", scheme="steam", pack="steam"),
    _app("epic", "Epic Games Launcher", ["gaming"], "EG", "#2A2A2A", ["эпик", "эпик геймс", "epic games", "epic"],
         exe=["EpicGamesLauncher.exe"], start=["Epic Games Launcher"],
         uri="com.epicgames.launcher://store", scheme="com.epicgames.launcher"),
    _app("battlenet", "Battle.net", ["gaming"], "BN", "#148EFF", ["батлнет", "батл нет", "battle net"],
         exe=["Battle.net.exe"], paths=[rf"{PF86}\Battle.net\Battle.net Launcher.exe"], start=["Battle.net"],
         uri="battlenet://", scheme="battlenet"),
    _app("eaapp", "EA app", ["gaming"], "EA", "#FF4747", ["еа", "иа апп", "ea app", "ea"],
         exe=["EADesktop.exe"], start=["EA"]),
    _app("ubisoft", "Ubisoft Connect", ["gaming"], "Ub", "#0070FF", ["юбисофт", "ubisoft", "юплей"],
         exe=["UbisoftConnect.exe"], start=["Ubisoft Connect"], uri="uplay://", scheme="uplay"),
    _app("gog", "GOG GALAXY", ["gaming"], "GOG", "#86328A", ["гог", "gog", "гог галакси"],
         exe=["GalaxyClient.exe"], start=["GOG GALAXY"], uri="goggalaxy://", scheme="goggalaxy"),
    _app("xbox", "Xbox", ["gaming"], "Xb", "#107C10", ["иксбокс", "xbox"], start=["Xbox"],
         process=["XboxPcApp.exe"]),
    _app("riot", "Riot Client", ["gaming"], "RC", "#EB0029", ["райот", "riot"],
         exe=["RiotClientServices.exe"], paths=[r"%SystemDrive%\Riot Games\Riot Client\RiotClientServices.exe"],
         start=["Riot Client"], process=["RiotClientServices.exe", "Riot Client.exe"]),
    _app("rockstar", "Rockstar Games Launcher", ["gaming"], "R*", "#FCAF17", ["рокстар", "rockstar"],
         exe=["Launcher.exe"], start=["Rockstar Games Launcher"]),
    _app("vkplay", "VK Play", ["gaming"], "VP", "#0077FF", ["вк плей", "vk play"],
         exe=["GameCenter.exe"], start=["VK Play", "Игровой центр"], web="https://vkplay.ru"),
    _app("lesta", "Lesta Game Center", ["gaming"], "LG", "#FFB400", ["леста", "lesta"],
         exe=["lgc.exe"], start=["Lesta Game Center"]),
    _app("wgc", "Wargaming.net Game Center", ["gaming"], "WG", "#CD1F1F", ["варгейминг", "wargaming"],
         exe=["wgc.exe"], start=["Wargaming.net Game Center"]),
    _app("faceit", "FACEIT", ["gaming"], "Fc", "#FF5500", ["фейсит", "faceit"],
         exe=["FACEIT.exe"], start=["FACEIT"], web="https://www.faceit.com"),
    _app("nvidia", "NVIDIA App", ["gaming"], "Nv", "#76B900", ["нвидиа", "nvidia"],
         exe=["NVIDIA app.exe"], start=["NVIDIA app", "NVIDIA App", "GeForce Experience"]),
    _steam_game("dota2", "Dota 2", 570, "D2", "#A42A13", ["дота", "доту", "дота 2", "dota", "dota 2"], ["dota2.exe"]),
    _steam_game("cs2", "Counter-Strike 2", 730, "CS", "#DE9B35",
                ["кс", "кс 2", "кс2", "контра", "контру", "counter strike", "cs2", "cs 2"], ["cs2.exe"]),
    _steam_game("pubg", "PUBG: Battlegrounds", 578080, "PB", "#F2A900", ["пабг", "пубг", "pubg"], ["TslGame.exe"]),
    _steam_game("rust", "Rust", 252490, "Rs", "#CD412B", ["раст", "rust"], ["RustClient.exe"]),
    _steam_game("apex", "Apex Legends", 1172470, "Ap", "#DA292A", ["апекс", "apex"], ["r5apex.exe", "r5apex_dx12.exe"]),
    _steam_game("deadlock", "Deadlock", 1422450, "Dl", "#8C7B5A", ["дедлок", "deadlock"], ["deadlock.exe"]),
    _steam_game("tf2", "Team Fortress 2", 440, "TF", "#B35A2B", ["тф2", "тим фортресс", "team fortress"], ["tf_win64.exe", "tf.exe"]),
    _steam_game("bg3", "Baldur's Gate 3", 1086940, "BG", "#7B4A2E", ["балдурс гейт", "baldurs gate", "бг3"], ["bg3.exe", "bg3_dx11.exe"]),
    _steam_game("cyberpunk", "Cyberpunk 2077", 1091500, "CP", "#FCEE0A", ["киберпанк", "cyberpunk"], ["Cyberpunk2077.exe"]),
    _steam_game("eldenring", "Elden Ring", 1245620, "ER", "#B89B5E", ["элден ринг", "elden ring"], ["eldenring.exe"]),
    _steam_game("terraria", "Terraria", 105600, "Te", "#4F9A2C", ["террария", "terraria"], ["Terraria.exe"]),
    _steam_game("gta5", "Grand Theft Auto V", 271590, "GTA", "#6CB33E", ["гта", "гта 5", "gta", "gta 5"], ["GTA5.exe"]),
    _app("valorant", "VALORANT", ["gaming"], "Va", "#FF4655", ["валорант", "valorant"],
         exe=["RiotClientServices.exe"], process=["VALORANT.exe", "VALORANT-Win64-Shipping.exe"],
         paths=[r"%SystemDrive%\Riot Games\Riot Client\RiotClientServices.exe"],
         args=["--launch-product=valorant", "--launch-patchline=live"], start=["VALORANT"], kind="game"),
    _app("lol", "League of Legends", ["gaming"], "LoL", "#C89B3C", ["лига легенд", "лол", "league of legends"],
         exe=["RiotClientServices.exe"], process=["LeagueClient.exe", "League of Legends.exe"],
         paths=[r"%SystemDrive%\Riot Games\Riot Client\RiotClientServices.exe"],
         args=["--launch-product=league_of_legends", "--launch-patchline=live"], start=["League of Legends"],
         kind="game"),
    _app("fortnite", "Fortnite", ["gaming"], "Fn", "#7C3AED", ["фортнайт", "fortnite"],
         uri="com.epicgames.launcher://apps/Fortnite?action=launch&silent=true",
         scheme="com.epicgames.launcher", process=["FortniteClient-Win64-Shipping.exe"], kind="game"),
    _app("minecraft", "Minecraft", ["gaming"], "Mc", "#62B47A", ["майнкрафт", "minecraft", "майн"],
         start=["Minecraft Launcher", "Minecraft"], process=["Minecraft.exe", "MinecraftLauncher.exe", "javaw.exe"],
         kind="game"),
    _app("roblox", "Roblox", ["gaming"], "Rb", "#000000", ["роблокс", "roblox"],
         start=["Roblox Player", "Roblox"], process=["RobloxPlayerBeta.exe"], web="https://www.roblox.com/home",
         kind="game"),
    _app("genshin", "Genshin Impact", ["gaming"], "GI", "#4C6A9C", ["геншин", "genshin"],
         start=["Genshin Impact"], process=["GenshinImpact.exe"], kind="game"),
    _app("wot", {"ru": "Мир танков", "en": "World of Tanks"}, ["gaming"], "WoT", "#B23A28",
         ["мир танков", "танки", "world of tanks"], start=["Мир танков", "World of Tanks"],
         process=["WorldOfTanks.exe"], kind="game"),

    # --- default command packs --------------------------------------------------------------
    _pack("pack_basic", {"ru": "Основные", "en": "Basics"}, "Hi",
          {"ru": "Приветствие, время, дата, помощь", "en": "Greetings, time, date, help"}),
    _pack("pack_launcher", {"ru": "Запуск приложений", "en": "App launcher"}, "▶",
          {"ru": "«Открой …», «закрой …» для любой программы", "en": "“Open …”, “close …” for any app"}),
    _pack("pack_media", {"ru": "Медиа и громкость", "en": "Media & volume"}, "♪",
          {"ru": "Пауза, треки, громкость", "en": "Pause, tracks, volume"}),
    _pack("pack_browser", {"ru": "Браузер", "en": "Browser"}, "⌘",
          {"ru": "Вкладки, обновление, масштаб", "en": "Tabs, refresh, zoom"}),
    _pack("pack_search", {"ru": "Поиск в интернете", "en": "Web search"}, "?",
          {"ru": "Google, Яндекс, YouTube, сайты", "en": "Google, Yandex, YouTube, sites"}),
    _pack("pack_windows", {"ru": "Окна", "en": "Windows"}, "▢",
          {"ru": "Свернуть, развернуть, переключить", "en": "Minimize, maximize, switch"}),
    _pack("pack_system", {"ru": "Система", "en": "System"}, "⏻",
          {"ru": "Блокировка, выключение, скриншот", "en": "Lock, shutdown, screenshot"}),
    _pack("pack_typing", {"ru": "Ввод текста", "en": "Typing"}, "Aa",
          {"ru": "Напечатать, копировать, вставить", "en": "Type, copy, paste"}),
    _pack("pack_ai", {"ru": "ИИ-ассистент", "en": "AI assistant"}, "AI",
          {"ru": "Вопросы к DeepSeek", "en": "Questions to DeepSeek"}),
    _pack("pack_jarvis", {"ru": "Управление Джарвисом", "en": "Jarvis control"}, "J",
          {"ru": "Тихий режим, тема, микрофон", "en": "Silent mode, theme, microphone"}),
]

APPS_BY_ID = {a["id"]: a for a in APPS}

DEFAULT_CONNECTED = [
    "pack_basic", "pack_launcher", "pack_media", "pack_browser", "pack_search", "pack_windows",
    "pack_system", "pack_typing", "pack_ai", "pack_jarvis", "chrome", "vk", "youtube",
]


def app_name(app: dict[str, Any], lang: str = "ru") -> str:
    name = app["name"]
    if isinstance(name, dict):
        return name.get(lang) or name.get("ru") or next(iter(name.values()))
    return name


def all_names(app: dict[str, Any]) -> list[str]:
    name = app["name"]
    names = list(name.values()) if isinstance(name, dict) else [name]
    return names + list(app.get("aliases", []))


# --- pack building ---------------------------------------------------------------------------

def _t(lang: str, ru: str, en: str) -> str:
    return en if lang == "en" else ru


def _cmd(name: str, triggers: list[str], actions: list[dict[str, Any]], response: str = "",
         confirm: bool = False) -> dict[str, Any]:
    return {"type": "command", "name": name,
            "data": {"triggers": triggers, "actions": actions, "response": response,
                     "confirm": confirm, "enabled": True}}


def _folder(name: str, items: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "folder", "name": name, "meta": meta or {}, "items": items}


def _verb_triggers(aliases: list[str], ru_verbs: list[str], en_verbs: list[str], limit: int = 4) -> list[str]:
    out: list[str] = []
    for alias in aliases[:limit]:
        verbs = list(ru_verbs)
        if detect_lang(alias, "ru") == "en":
            verbs += en_verbs
        for verb in verbs:
            phrase = f"{verb} {alias}"
            if phrase not in out:
                out.append(phrase)
    return out


def _open_close(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    name = app_name(app, lang)
    aliases = app.get("aliases", [])
    items = [_cmd(
        _t(lang, "Открыть", "Open"),
        _verb_triggers(aliases, ["открой", "запусти"], ["open", "launch"]),
        [{"type": "open_app", "app": app["id"]}],
        _t(lang, f"Открываю {name}", f"Opening {name}"),
    )]
    if app.get("process") and app["kind"] != "web":
        items.append(_cmd(
            _t(lang, "Закрыть", "Close"),
            _verb_triggers(aliases, ["закрой"], ["close"]),
            [{"type": "close_app", "app": app["id"], "force": bool(app.get("force_close"))}],
            _t(lang, f"Закрываю {name}", f"Closing {name}"),
        ))
    return items


def build_pack(app_id: str, lang: str = "ru") -> dict[str, Any]:
    """Folder tree (name, meta, items) for an app or a default pack."""
    app = APPS_BY_ID[app_id]
    name = app_name(app, lang)
    meta = {"app": app_id}
    builder = _PACKS.get(app.get("pack") or "")
    if builder:
        items = builder(app, lang)
    elif app["kind"] == "browser":
        items = _browser_items(app, lang)
    else:
        items = _open_close(app, lang)
    return _folder(name, items, meta)


def _browser_items(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    items = _open_close(app, lang)
    name = app_name(app, lang)
    if app.get("private_arg"):
        aliases = app["aliases"][:2]
        items.append(_cmd(
            _t(lang, "Режим инкогнито", "Private window"),
            [f"открой {a} в режиме инкогнито" for a in aliases] + [f"инкогнито в {aliases[0]}",
                                                                 f"open {name} incognito"],
            [{"type": "open_app", "app": app["id"], "args": app["private_arg"]}],
            _t(lang, "Открываю приватное окно", "Opening a private window"),
        ))
    return items


def _pack_vk(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def url(u: str) -> dict[str, Any]:
        return {"type": "open_url", "url": u, "browser": "auto"}

    play_buttons = ["Перемешать все", "Перемешать", "Слушать", "Воспроизвести",
                    "Shuffle all", "Shuffle", "Play"]
    music = _folder(_t(lang, "Музыка", "Music"), [
        _cmd(_t(lang, "Включить музыку", "Play music"),
             ["включи музыку в вк", "включи музыку вконтакте", "включи музыку в контакте",
              "включи вк музыку", "поставь музыку в вк", "запусти музыку в вк",
              "play music on vk", "play vk music"],
             [url("https://vk.com/audio"), {"type": "wait", "seconds": 4},
              {"type": "click_element", "names": play_buttons, "app": "@browser", "timeout": 8, "optional": True}],
             _t(lang, "Включаю музыку ВКонтакте", "Playing music on VK")),
        _cmd(_t(lang, "Моя музыка", "My music"),
             ["открой мою музыку в вк", "открой музыку в вк", "моя музыка вк", "open my vk music"],
             [url("https://vk.com/audio")],
             _t(lang, "Открываю вашу музыку", "Opening your music")),
        _cmd(_t(lang, "Найти музыку", "Find music"),
             ["найди в вк песню {query}", "найди песню {query} в вк", "найди в вк музыку {query}",
              "find {query} on vk music"],
             [url("https://vk.com/audio?q={query}")],
             _t(lang, "Ищу «{query}» ВКонтакте", "Searching VK for {query}")),
    ])
    return [
        _cmd(_t(lang, "Открыть ВКонтакте", "Open VK"),
             ["открой вк", "открой вконтакте", "открой в контакте", "зайди в вк", "open vk", "open vkontakte"],
             [url("https://vk.com/feed")],
             _t(lang, "Открываю ВКонтакте", "Opening VK")),
        _cmd(_t(lang, "Сообщения", "Messages"),
             ["открой сообщения в вк", "открой мессенджер вк", "сообщения вк", "open vk messages"],
             [url("https://vk.com/im")],
             _t(lang, "Открываю сообщения", "Opening messages")),
        _cmd(_t(lang, "Друзья", "Friends"),
             ["открой друзей в вк", "друзья вк", "open vk friends"],
             [url("https://vk.com/friends")],
             _t(lang, "Открываю список друзей", "Opening your friends")),
        _cmd(_t(lang, "Видео", "Video"),
             ["открой видео в вк", "открой вк видео", "open vk video"],
             [url("https://vkvideo.ru")],
             _t(lang, "Открываю VK Видео", "Opening VK Video")),
        music,
    ]


def _pack_youtube(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    return [
        _cmd(_t(lang, "Открыть YouTube", "Open YouTube"),
             ["открой ютуб", "открой youtube", "зайди на ютуб", "open youtube"],
             [{"type": "open_url", "url": "https://www.youtube.com", "browser": "auto"}],
             _t(lang, "Открываю YouTube", "Opening YouTube")),
        _cmd(_t(lang, "Найти на YouTube", "Search YouTube"),
             ["найди на ютубе {query}", "найди {query} на ютубе", "найди в ютубе {query}",
              "включи на ютубе {query}", "search youtube for {query}"],
             [{"type": "search_web", "query": "{query}", "engine": "youtube", "browser": "auto"}],
             _t(lang, "Ищу на YouTube «{query}»", "Searching YouTube for {query}")),
        _cmd(_t(lang, "Полный экран", "Full screen"),
             ["ютуб на весь экран", "видео на весь экран", "youtube full screen"],
             [{"type": "focus_app", "app": "@browser"}, {"type": "hotkey", "keys": "f"}]),
        _cmd(_t(lang, "Следующее видео", "Next video"),
             ["следующее видео", "next video"],
             [{"type": "focus_app", "app": "@browser"}, {"type": "hotkey", "keys": "shift+n"}]),
    ]


def _pack_steam(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def uri(u: str) -> dict[str, Any]:
        return {"type": "open_url", "url": u}

    return [
        _cmd(_t(lang, "Открыть", "Open"),
             ["открой стим", "запусти стим", "открой steam", "open steam", "launch steam"],
             [{"type": "open_app", "app": "steam"}], _t(lang, "Открываю Steam", "Opening Steam")),
        _cmd(_t(lang, "Библиотека", "Library"),
             ["открой библиотеку стим", "библиотека стим", "мои игры", "open steam library"],
             [uri("steam://open/games")], _t(lang, "Открываю библиотеку", "Opening your library")),
        _cmd(_t(lang, "Магазин", "Store"),
             ["открой магазин стим", "магазин стим", "open steam store"],
             [uri("steam://store")], _t(lang, "Открываю магазин Steam", "Opening the Steam store")),
        _cmd(_t(lang, "Друзья", "Friends"),
             ["открой друзей в стиме", "друзья стим", "open steam friends"],
             [uri("steam://open/friends")], _t(lang, "Открываю список друзей", "Opening friends")),
        _cmd(_t(lang, "Загрузки", "Downloads"),
             ["открой загрузки стим", "загрузки стим", "open steam downloads"],
             [uri("steam://open/downloads")], _t(lang, "Открываю загрузки", "Opening downloads")),
        _cmd(_t(lang, "Закрыть", "Close"),
             ["закрой стим", "выйди из стима", "close steam"],
             [uri("steam://exit")], _t(lang, "Закрываю Steam", "Closing Steam")),
    ]


def _pack_spotify(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    items = _open_close(app, lang)
    items.append(_cmd(
        _t(lang, "Включить музыку", "Play music"),
        ["включи спотифай", "включи музыку в спотифай", "включи музыку в spotify", "play spotify"],
        [{"type": "open_app", "app": "spotify"}, {"type": "wait", "seconds": 4},
         {"type": "media", "key": "play_pause"}],
        _t(lang, "Включаю Spotify", "Playing Spotify")))
    return items


def _pack_yandexmusic(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    items = _open_close(app, lang)
    items.append(_cmd(
        _t(lang, "Моя волна", "My Wave"),
        ["включи мою волну", "включи яндекс музыку", "включи музыку в яндекс музыке", "play my wave"],
        [{"type": "open_url", "url": "https://music.yandex.ru/", "browser": "auto"},
         {"type": "wait", "seconds": 4},
         {"type": "click_element", "names": ["Моя волна", "My Wave", "Слушать"], "app": "@browser", "timeout": 8,
          "optional": True}],
        _t(lang, "Включаю Мою волну", "Playing My Wave")))
    return items


def _pack_discord(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    items = _open_close(app, lang)
    items += [
        _cmd(_t(lang, "Выключить микрофон", "Toggle mute"),
             ["выключи микрофон в дискорде", "включи микрофон в дискорде", "мут в дискорде", "mute discord"],
             [{"type": "focus_app", "app": "discord"}, {"type": "hotkey", "keys": "ctrl+shift+m"}]),
        _cmd(_t(lang, "Выключить звук", "Toggle deafen"),
             ["выключи звук в дискорде", "включи звук в дискорде", "deafen discord"],
             [{"type": "focus_app", "app": "discord"}, {"type": "hotkey", "keys": "ctrl+shift+d"}]),
    ]
    return items


def _pack_explorer(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def shell(folder: str) -> dict[str, Any]:
        return {"type": "open_app", "app": "explorer", "args": f"shell:{folder}"}

    return [
        _cmd(_t(lang, "Открыть проводник", "Open Explorer"),
             ["открой проводник", "открой мой компьютер", "открой этот компьютер", "открой файлы",
              "open explorer", "open file explorer"],
             [{"type": "open_app", "app": "explorer"}], _t(lang, "Открываю проводник", "Opening Explorer")),
        _cmd(_t(lang, "Загрузки", "Downloads"),
             ["открой загрузки", "открой папку загрузки", "open downloads"],
             [shell("Downloads")], _t(lang, "Открываю загрузки", "Opening Downloads")),
        _cmd(_t(lang, "Документы", "Documents"),
             ["открой документы", "открой мои документы", "open documents"],
             [shell("Personal")], _t(lang, "Открываю документы", "Opening Documents")),
        _cmd(_t(lang, "Рабочий стол", "Desktop"),
             ["открой папку рабочий стол", "open desktop folder"],
             [shell("Desktop")], _t(lang, "Открываю рабочий стол", "Opening Desktop")),
        _cmd(_t(lang, "Изображения", "Pictures"),
             ["открой изображения", "открой картинки", "открой мои фото", "open pictures"],
             [shell("My Pictures")], _t(lang, "Открываю изображения", "Opening Pictures")),
    ]


def _pack_taskmgr(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    return [_cmd(_t(lang, "Открыть", "Open"),
                 ["открой диспетчер задач", "запусти диспетчер задач", "диспетчер задач", "open task manager"],
                 [{"type": "hotkey", "keys": "ctrl+shift+esc"}],
                 _t(lang, "Открываю диспетчер задач", "Opening Task Manager"))]


def _pack_basic(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    return [
        _cmd(_t(lang, "Привет", "Hello"),
             ["привет", "здравствуй", "здравствуйте", "добрый день", "доброе утро", "добрый вечер",
              "hello", "hi", "good morning", "good evening"],
             [], _t(lang, "Здравствуйте, сэр. Чем могу помочь?", "Hello, sir. How can I help?")),
        _cmd(_t(lang, "Спасибо", "Thanks"),
             ["спасибо", "благодарю", "спасибо большое", "thanks", "thank you"],
             [], _t(lang, "Всегда к вашим услугам, сэр", "Always at your service, sir")),
        _cmd(_t(lang, "Который час", "Time"),
             ["который час", "сколько времени", "сколько время", "скажи время", "what time is it"],
             [], _t(lang, "Сейчас {time}", "It's {time}")),
        _cmd(_t(lang, "Какое сегодня число", "Date"),
             ["какое сегодня число", "какой сегодня день", "какая сегодня дата", "what's the date today",
              "what day is it"],
             [], _t(lang, "Сегодня {weekday}, {date}", "Today is {weekday}, {date}")),
        _cmd(_t(lang, "Что ты умеешь", "Help"),
             ["что ты умеешь", "помощь", "что ты можешь", "what can you do", "help"],
             [], _t(lang,
                    "Я открываю программы и сайты, управляю музыкой, громкостью и окнами, ищу в интернете "
                    "и выполняю команды из редактора. Например: открой хром и включи музыку в вк.",
                    "I open apps and websites, control music, volume and windows, search the web and run "
                    "the commands from the editor. For example: open chrome and play music on VK.")),
        _cmd(_t(lang, "Как дела", "How are you"),
             ["как дела", "как ты", "как поживаешь", "how are you"],
             [], _t(lang, "Все системы работают в штатном режиме, сэр", "All systems are operational, sir")),
        _cmd(_t(lang, "Кто ты", "Who are you"),
             ["кто ты", "как тебя зовут", "представься", "who are you", "what is your name"],
             [], _t(lang, "Я Джарвис, ваш голосовой ассистент", "I am Jarvis, your voice assistant")),
    ]


def _pack_launcher(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    return [
        _cmd(_t(lang, "Открыть приложение", "Open an app"),
             ["открой {app}", "запусти {app}", "open {app}", "launch {app}", "start {app}"],
             [{"type": "open_app", "app": "{app}"}],
             _t(lang, "Открываю {app_name}", "Opening {app_name}")),
        _cmd(_t(lang, "Закрыть приложение", "Close an app"),
             ["закрой {app}", "close {app}", "quit {app}"],
             [{"type": "close_app", "app": "{app}"}],
             _t(lang, "Закрываю {app_name}", "Closing {app_name}")),
    ]


def _pack_media(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def media(key: str, times: int = 1) -> list[dict[str, Any]]:
        action: dict[str, Any] = {"type": "media", "key": key}
        if times > 1:
            action["times"] = times
        return [action]

    return [
        _cmd(_t(lang, "Пауза и воспроизведение", "Play and pause"),
             ["пауза", "поставь на паузу", "продолжи", "продолжи воспроизведение", "сними с паузы",
              "pause", "resume", "play"],
             media("play_pause")),
        _cmd(_t(lang, "Следующий трек", "Next track"),
             ["следующий трек", "следующая песня", "переключи трек", "дальше", "next track", "next song", "skip"],
             media("next")),
        _cmd(_t(lang, "Предыдущий трек", "Previous track"),
             ["предыдущий трек", "предыдущая песня", "верни трек", "previous track", "previous song"],
             media("prev")),
        _cmd(_t(lang, "Громче", "Louder"),
             ["громче", "сделай громче", "прибавь громкость", "погромче", "louder", "volume up"],
             media("volume_up", 5)),
        _cmd(_t(lang, "Тише", "Quieter"),
             ["тише", "сделай тише", "убавь громкость", "потише", "quieter", "volume down"],
             media("volume_down", 5)),
        _cmd(_t(lang, "Выключить звук", "Mute"),
             ["выключи звук", "отключи звук", "без звука", "mute"],
             media("mute")),
        _cmd(_t(lang, "Включить звук", "Unmute"),
             ["включи звук", "верни звук", "unmute"],
             media("mute")),
        _cmd(_t(lang, "Громкость на уровень", "Set volume"),
             ["громкость {level}", "поставь громкость {level}", "установи громкость {level}",
              "сделай громкость {level}", "volume {level}", "set volume to {level}"],
             [{"type": "system_volume", "level": "{level}"}],
             _t(lang, "Громкость {level}", "Volume {level}")),
    ]


def _pack_browser(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def hk(keys: str) -> list[dict[str, Any]]:
        return [{"type": "focus_app", "app": "@browser"}, {"type": "hotkey", "keys": keys}]

    return [
        _folder(_t(lang, "Вкладки", "Tabs"), [
            _cmd(_t(lang, "Новая вкладка", "New tab"),
                 ["новая вкладка", "открой новую вкладку", "new tab", "open a new tab"], hk("ctrl+t")),
            _cmd(_t(lang, "Закрыть вкладку", "Close tab"),
                 ["закрой вкладку", "закрой эту вкладку", "close tab", "close this tab"], hk("ctrl+w")),
            _cmd(_t(lang, "Вернуть вкладку", "Reopen tab"),
                 ["верни вкладку", "открой закрытую вкладку", "reopen tab"], hk("ctrl+shift+t")),
            _cmd(_t(lang, "Следующая вкладка", "Next tab"),
                 ["следующая вкладка", "переключи вкладку", "next tab"], hk("ctrl+tab")),
            _cmd(_t(lang, "Предыдущая вкладка", "Previous tab"),
                 ["предыдущая вкладка", "previous tab"], hk("ctrl+shift+tab")),
        ]),
        _cmd(_t(lang, "Обновить страницу", "Refresh"),
             ["обнови страницу", "перезагрузи страницу", "refresh the page", "reload page"], hk("f5")),
        _cmd(_t(lang, "Назад", "Back"),
             ["назад", "вернись назад", "go back"], hk("alt+left")),
        _cmd(_t(lang, "Вперёд", "Forward"),
             ["вперед", "go forward"], hk("alt+right")),
        _cmd(_t(lang, "Полноэкранный режим", "Full screen"),
             ["полноэкранный режим", "на весь экран", "full screen"], hk("f11")),
        _cmd(_t(lang, "Увеличить масштаб", "Zoom in"),
             ["увеличь масштаб", "приблизь", "zoom in"], hk("ctrl+plus")),
        _cmd(_t(lang, "Уменьшить масштаб", "Zoom out"),
             ["уменьши масштаб", "отдали", "zoom out"], hk("ctrl+minus")),
        _cmd(_t(lang, "Прокрутить вниз", "Scroll down"),
             ["прокрути вниз", "листай вниз", "scroll down"], hk("pagedown")),
        _cmd(_t(lang, "Прокрутить вверх", "Scroll up"),
             ["прокрути вверх", "листай вверх", "scroll up"], hk("pageup")),
    ]


def _pack_search(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def search(engine: str) -> list[dict[str, Any]]:
        return [{"type": "search_web", "query": "{query}", "engine": engine, "browser": "auto"}]

    return [
        _cmd(_t(lang, "Найти в Google", "Google search"),
             ["найди {query}", "загугли {query}", "поищи {query}", "найди в гугле {query}",
              "найди в интернете {query}", "search for {query}", "google {query}"],
             search("google"), _t(lang, "Ищу «{query}»", "Searching for {query}")),
        _cmd(_t(lang, "Найти в Яндексе", "Yandex search"),
             ["найди в яндексе {query}", "поищи в яндексе {query}", "search yandex for {query}"],
             search("yandex"), _t(lang, "Ищу в Яндексе «{query}»", "Searching Yandex for {query}")),
        _cmd(_t(lang, "Найти на YouTube", "YouTube search"),
             ["найди на ютубе {query}", "найди {query} на ютубе", "найди в ютубе {query}",
              "search youtube for {query}"],
             search("youtube"), _t(lang, "Ищу на YouTube «{query}»", "Searching YouTube for {query}")),
        _cmd(_t(lang, "Открыть сайт", "Open a website"),
             ["открой сайт {site}", "зайди на сайт {site}", "перейди на сайт {site}", "open website {site}"],
             [{"type": "open_url", "url": "{site}", "browser": "auto"}],
             _t(lang, "Открываю {site}", "Opening {site}")),
    ]


def _pack_windows(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def hk(keys: str) -> list[dict[str, Any]]:
        return [{"type": "hotkey", "keys": keys}]

    return [
        _cmd(_t(lang, "Свернуть все окна", "Show desktop"),
             ["сверни все окна", "покажи рабочий стол", "show desktop", "minimize all windows"], hk("win+d")),
        _cmd(_t(lang, "Свернуть окно", "Minimize window"),
             ["сверни окно", "minimize window"], hk("win+down win+down")),
        _cmd(_t(lang, "Развернуть окно", "Maximize window"),
             ["разверни окно", "на весь экран окно", "maximize window"], hk("win+up")),
        _cmd(_t(lang, "Закрыть окно", "Close window"),
             ["закрой окно", "закрой это окно", "close window"], hk("alt+f4")),
        _cmd(_t(lang, "Переключить окно", "Switch window"),
             ["переключи окно", "следующее окно", "switch window"], hk("alt+tab")),
    ]


def _pack_system(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def sysop(op: str) -> list[dict[str, Any]]:
        return [{"type": "system", "op": op}]

    return [
        _cmd(_t(lang, "Заблокировать компьютер", "Lock computer"),
             ["заблокируй компьютер", "заблокируй экран", "заблокируй пк", "lock the computer", "lock screen"],
             sysop("lock"), _t(lang, "Блокирую компьютер", "Locking the computer")),
        _cmd(_t(lang, "Выключить компьютер", "Shut down"),
             ["выключи компьютер", "выключи пк", "заверши работу", "shut down the computer", "shutdown"],
             sysop("shutdown"), _t(lang, "Выключаю компьютер. До встречи, сэр", "Shutting down. Goodbye, sir"),
             confirm=True),
        _cmd(_t(lang, "Перезагрузить компьютер", "Restart"),
             ["перезагрузи компьютер", "перезагрузи пк", "перезагрузка", "restart the computer", "reboot"],
             sysop("restart"), _t(lang, "Перезагружаю компьютер", "Restarting the computer"), confirm=True),
        _cmd(_t(lang, "Спящий режим", "Sleep"),
             ["спящий режим", "переведи компьютер в спящий режим", "усыпи компьютер", "sleep mode"],
             sysop("sleep"), _t(lang, "Перевожу в спящий режим", "Going to sleep"), confirm=True),
        _cmd(_t(lang, "Скриншот", "Screenshot"),
             ["сделай скриншот", "скриншот", "снимок экрана", "take a screenshot"],
             sysop("screenshot")),
        _cmd(_t(lang, "Очистить корзину", "Empty recycle bin"),
             ["очисти корзину", "empty the recycle bin"],
             sysop("empty_recycle_bin"), _t(lang, "Корзина очищена", "Recycle bin emptied"), confirm=True),
        _cmd(_t(lang, "Параметры Windows", "Windows Settings"),
             ["открой параметры", "открой параметры windows", "открой настройки windows",
              "открой настройки виндовс", "open windows settings"],
             [{"type": "open_url", "url": "ms-settings:"}], _t(lang, "Открываю параметры", "Opening Settings")),
    ]


def _pack_typing(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def hk(keys: str) -> list[dict[str, Any]]:
        return [{"type": "hotkey", "keys": keys}]

    return [
        _cmd(_t(lang, "Напечатать текст", "Type text"),
             ["напиши {text}", "напечатай {text}", "введи текст {text}", "type {text}"],
             [{"type": "type_text", "text": "{text}"}]),
        _cmd(_t(lang, "Нажать Enter", "Press Enter"),
             ["нажми enter", "нажми энтер", "отправь", "press enter"], hk("enter")),
        _cmd(_t(lang, "Выделить всё", "Select all"),
             ["выдели все", "выдели весь текст", "select all"], hk("ctrl+a")),
        _cmd(_t(lang, "Копировать", "Copy"),
             ["скопируй", "копировать", "copy"], hk("ctrl+c")),
        _cmd(_t(lang, "Вставить", "Paste"),
             ["вставь", "вставить", "paste"], hk("ctrl+v")),
        _cmd(_t(lang, "Отменить действие", "Undo"),
             ["отмени действие", "отмени последнее действие", "undo"], hk("ctrl+z")),
    ]


def _pack_ai(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    return [
        _cmd(_t(lang, "Спросить ИИ", "Ask AI"),
             ["спроси {query}", "вопрос {query}", "расскажи {query}", "объясни {query}",
              "что такое {query}", "кто такой {query}", "кто такая {query}", "почему {query}",
              "ask {query}", "what is {query}", "who is {query}", "tell me {query}"],
             [{"type": "ask_ai", "prompt": "{_text}"}]),
    ]


def _pack_jarvis(app: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    def op(name: str, **extra: Any) -> list[dict[str, Any]]:
        return [{"type": "jarvis", "op": name, **extra}]

    return [
        _cmd(_t(lang, "Тихий режим", "Silent mode"),
             ["тихий режим", "включи тихий режим", "помолчи", "silent mode", "be quiet"], op("silent_on")),
        _cmd(_t(lang, "Голосовые ответы", "Voice replies"),
             ["выключи тихий режим", "можешь говорить", "отвечай голосом", "voice mode"],
             op("silent_off"), _t(lang, "Снова на связи, сэр", "Back online, sir")),
        _cmd(_t(lang, "Тёмная тема", "Dark theme"),
             ["темная тема", "включи темную тему", "dark theme", "dark mode"], op("theme_dark"),
             _t(lang, "Тёмная тема", "Dark theme on")),
        _cmd(_t(lang, "Светлая тема", "Light theme"),
             ["светлая тема", "включи светлую тему", "light theme", "light mode"], op("theme_light"),
             _t(lang, "Светлая тема", "Light theme on")),
        _cmd(_t(lang, "Выключить микрофон", "Stop listening"),
             ["выключи микрофон", "перестань слушать", "stop listening"], op("mic_off"),
             _t(lang, "Микрофон выключен", "Microphone off")),
        _cmd(_t(lang, "Громкость голоса", "Voice volume"),
             ["громкость джарвиса {level}", "громкость голоса {level}", "jarvis volume {level}"],
             op("volume", value="{level}"), _t(lang, "Громкость голоса {level}", "Voice volume {level}")),
        _cmd(_t(lang, "Стоп", "Stop"),
             ["стоп", "хватит", "замолчи", "stop"], op("stop")),
        _cmd(_t(lang, "Открыть настройки", "Open settings"),
             ["открой настройки джарвиса", "настройки джарвиса", "open jarvis settings"],
             op("open_settings")),
        _cmd(_t(lang, "Открыть редактор команд", "Open command editor"),
             ["открой редактор команд", "редактор команд", "open the command editor"], op("open_editor")),
    ]


_PACKS = {
    "vk": _pack_vk,
    "youtube": _pack_youtube,
    "steam": _pack_steam,
    "spotify": _pack_spotify,
    "yandexmusic": _pack_yandexmusic,
    "discord": _pack_discord,
    "explorer": _pack_explorer,
    "taskmgr": _pack_taskmgr,
    "pack_basic": _pack_basic,
    "pack_launcher": _pack_launcher,
    "pack_media": _pack_media,
    "pack_browser": _pack_browser,
    "pack_search": _pack_search,
    "pack_windows": _pack_windows,
    "pack_system": _pack_system,
    "pack_typing": _pack_typing,
    "pack_ai": _pack_ai,
    "pack_jarvis": _pack_jarvis,
}


def catalog_for_ui(lang: str = "ru") -> dict[str, Any]:
    return {
        "categories": [{"id": c["id"], "name": c.get(lang) or c["ru"]} for c in CATEGORIES],
        "apps": [
            {
                "id": a["id"],
                "name": app_name(a, lang),
                "categories": a["categories"],
                "abbr": a["abbr"],
                "color": a["color"],
                "kind": a["kind"],
                "desc": (a["desc"] or {}).get(lang) if isinstance(a.get("desc"), dict) else a.get("desc"),
                "web": a.get("web"),
            }
            for a in APPS
        ],
    }
