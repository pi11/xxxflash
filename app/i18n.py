"""Site language support.

UI text lives in the templates themselves: `templates/<SITE>/` is Russian and
`templates/<SITE>-<lang>/` is a full copy in another language (e.g. `xxxflash-en`). What is
left for Python is here: messages produced by views (form errors, the vote reply, the login
email) and number / plural formatting. Genre names are data: `theme_translations`, entered
in the admin.
"""

LANGUAGES = ("ru", "en")

MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "already_voted": "Вы уже голосовали",
        "bad_email": "Введите правильный адрес электронной почты.",
        "too_many_logins": "Слишком много попыток входа. Попробуйте позже.",
        "name_required": "Введите название (до {n} символов).",
        "description_required": "Введите описание (до {n} символов).",
        "theme_required": "Выберите хотя бы одну тему.",
        "swf_required": "Выберите файл игры.",
        "swf_too_big": "Файл больше {n} МБ.",
        "not_swf": "Неверный тип файла",
        "swf_damaged": "Файл повреждён",
        "swf_duplicate": "Эта игра уже загружена",
        "thumb_required": "Выберите скриншот.",
        "bad_image": "Неверный формат изображения",
        "login_subject": "Вход на сайт {host}",
        "login_body": (
            "Для входа на сайт {host} пройдите по ссылке:\n{link}\n\n"
            "Ссылка одноразовая и действует 24 часа.\n\n"
            "Если вы не запрашивали вход, просто проигнорируйте это письмо."
        ),
    },
    "en": {
        "already_voted": "You've already voted",
        "bad_email": "Enter a valid email address.",
        "too_many_logins": "Too many login attempts. Try again later.",
        "name_required": "Enter a title (up to {n} characters).",
        "description_required": "Enter a description (up to {n} characters).",
        "theme_required": "Choose at least one genre.",
        "swf_required": "Choose a game file.",
        "swf_too_big": "The file is larger than {n} MB.",
        "not_swf": "This isn't a SWF file",
        "swf_damaged": "The file is damaged",
        "swf_duplicate": "This game is already on the site",
        "thumb_required": "Choose a screenshot.",
        "bad_image": "This image format isn't supported",
        "login_subject": "Log in to {host}",
        "login_body": (
            "To log in to {host}, open this link:\n{link}\n\n"
            "The link works once and expires in 24 hours.\n\n"
            "If you didn't request this, ignore this email."
        ),
    },
}


def _ru_plural_index(n: int) -> int:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 1
    return 2


class Locale:
    def __init__(self, language: str = "ru"):
        if language not in LANGUAGES:
            raise ValueError(f"unsupported SITE_LANGUAGE {language!r}; use one of {LANGUAGES}")
        self.language = language

    def msg(self, key: str, **params) -> str:
        return MESSAGES[self.language][key].format(**params)

    def plural(self, n: int, forms: str) -> str:
        """Forms in the template's own language: "игра|игры|игр" (ru), "game|games" (en)."""
        variants = forms.split("|")
        index = _ru_plural_index(n) if self.language == "ru" else int(abs(n) != 1)
        return variants[min(index, len(variants) - 1)]

    def number(self, n: int | None) -> str:
        grouped = f"{n or 0:,}"
        return grouped if self.language == "en" else grouped.replace(",", " ")
