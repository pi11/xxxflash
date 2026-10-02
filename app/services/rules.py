"""Business rules ported from the legacy views (pure functions, unit-tested)."""

# Score changes (legacy flash/views.py)
COMMENT_SCORE = 3  # add_comment: commenter +3
VOTE_SCORE = 1  # mark: logged-in voter +1
UPLOAD_SCORE = 10  # upload: uploader +10
DELETE_COMMENT_PENALTY = 10  # del_comment: author -10 (legacy wrongly hit the staff user)

AUTO_HIDE_BELOW = -4  # mark: rate < -4 -> game deactivated
INDEX_MIN_RATE = -2  # index: rate > -2

# Literal spam phrase rejected by the legacy CommentForm.
SPAM_PHRASES = ("апиши этот коммент",)


def vote_value(kind: str) -> int | None:
    return {"up": 1, "down": -1}.get(kind)


def compute_xrate(rate: int, views: int) -> float:
    """Legacy "top" score, recomputed on every counted view (uses views before increment)."""
    views = max(views, 1)
    if rate > 0:
        return rate * 10000 / views
    return float(rate)


def should_auto_hide(rate: int) -> bool:
    return rate < AUTO_HIDE_BELOW


def comment_rejected(text: str, banned_words: list[str]) -> bool:
    """True when the comment must be silently dropped (banned word or spam phrase)."""
    lowered = text.lower()
    if any(p in lowered for p in SPAM_PHRASES):
        return True
    return any(w and w.lower() in lowered for w in banned_words)


def truncate_words(text: str, count: int) -> str:
    """Django's |truncatewords."""
    words = (text or "").split()
    if len(words) <= count:
        return " ".join(words)
    return " ".join(words[:count]) + " …"
