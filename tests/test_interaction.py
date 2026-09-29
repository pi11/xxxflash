from app.models import Ban, BannedWord, Comment, Game, User, Vote
from tests.factories import CLIENT_IP, CSRF, headers, make_game, make_user


def _vote(client, game_id, kind, user=None, ip=CLIENT_IP):
    return client.post(
        "/mark/", data={"pk": str(game_id), "vote": kind}, headers=headers(user, ip=ip)
    )


async def test_vote_requires_csrf(client):
    game = await make_game()
    _, resp = await client.post("/mark/", data={"pk": str(game.id), "vote": "up"})
    assert resp.status == 403
    bad = headers()
    bad["X-CSRFToken"] = "wrong"
    _, resp = await client.post("/mark/", data={"pk": str(game.id), "vote": "up"}, headers=bad)
    assert resp.status == 403


async def test_vote_flow(client):
    uploader = await make_user("uploader", score=0)
    voter = await make_user("voter", score=0)
    game = await make_game(user=uploader, rate=0)

    _, resp = await _vote(client, game.id, "up", user=voter)
    assert resp.status == 200
    assert resp.json == {"success": 1}

    # same IP again -> refused
    _, resp = await _vote(client, game.id, "up", user=voter)
    assert resp.json == {"success": "Вы уже голосовали"}

    await game.refresh_from_db()
    await uploader.refresh_from_db()
    await voter.refresh_from_db()
    assert game.rate == 1
    assert uploader.score == 1  # uploader gets +mark
    assert voter.score == 1  # voter +1 (only for counted votes)
    assert await Vote.filter(game_id=game.id).count() == 1


async def test_staff_can_vote_repeatedly(client):
    staff = await make_user("staff", is_staff=True)
    game = await make_game(rate=0)
    await _vote(client, game.id, "up", user=staff)
    _, resp = await _vote(client, game.id, "up", user=staff)
    assert resp.json == {"success": 2}


async def test_downvote_auto_hides(client):
    staff = await make_user("staff", is_staff=True)
    game = await make_game(rate=-4)
    _, resp = await _vote(client, game.id, "down", user=staff)
    assert resp.json == {"success": -5}
    await game.refresh_from_db()
    assert game.active is False


async def test_vote_unknown_game(client):
    _, resp = await _vote(client, 999999, "up")
    assert resp.status == 404


def _comment(client, game_id, text, user, **extra):
    data = {"csrf_token": CSRF, "flash_id": str(game_id), "text": text, "email": ""}
    data.update(extra)
    return client.post("/add-comment", data=data, headers=headers(user))


async def test_comment_requires_login(client):
    game = await make_game()
    _, resp = await client.post(
        "/add-comment",
        data={"csrf_token": CSRF, "flash_id": str(game.id), "text": "hi"},
        headers=headers(),
    )
    assert resp.status == 302
    assert resp.headers["location"] == "/login/"


async def test_comment_flow(client):
    user = await make_user(score=0)
    game = await make_game()
    _, resp = await _comment(client, game.id, "Классная игра!", user)
    assert resp.status == 302
    assert resp.headers["location"] == f"/game/{game.id}/?new"
    comment = await Comment.get(game_id=game.id)
    assert comment.text == "Классная игра!"
    await user.refresh_from_db()
    assert user.score == 3
    _, page = await client.get(f"/game/{game.id}/")
    assert "Классная игра!" in page.text


async def test_comment_honeypot_and_banned_words(client):
    user = await make_user()
    game = await make_game()
    await BannedWord.create(word="казино")
    await _comment(client, game.id, "spam", user, email="bot@example.com")
    await _comment(client, game.id, "Лучшее КАЗИНО тут", user)
    assert await Comment.filter(game_id=game.id).count() == 0


async def test_banned_ip_cannot_comment(client):
    user = await make_user()
    game = await make_game()
    await Ban.create(ip=CLIENT_IP)
    _, resp = await _comment(client, game.id, "hello", user)
    assert resp.status == 403


async def test_delete_comment_staff_only_and_penalizes_author(client):
    author = await make_user("author", score=20)
    staff = await make_user("mod", is_staff=True, score=5)
    game = await make_game()
    comment = await Comment.create(game=game, user=author, text="x", ip="10.0.0.1")

    _, resp = await client.post(
        f"/del-comment/{comment.id}", data={"csrf_token": CSRF}, headers=headers(author)
    )
    assert resp.status == 403
    assert await Comment.exists(id=comment.id)

    await client.post(
        f"/del-comment/{comment.id}", data={"csrf_token": CSRF}, headers=headers(staff)
    )
    assert not await Comment.exists(id=comment.id)
    await author.refresh_from_db()
    await staff.refresh_from_db()
    assert author.score == 10
    assert staff.score == 5


async def test_ban_is_staff_only(client):
    user = await make_user()
    staff = await make_user("mod", is_staff=True)
    game = await make_game()
    comment = await Comment.create(game=game, user=user, text="x", ip="10.0.0.9")

    _, resp = await client.post(
        f"/ban/{comment.id}/", data={"csrf_token": CSRF}, headers=headers(user)
    )
    assert resp.status == 403
    assert not await Ban.exists(ip="10.0.0.9")

    await client.post(f"/ban/{comment.id}/", data={"csrf_token": CSRF}, headers=headers(staff))
    assert await Ban.exists(ip="10.0.0.9")


async def test_x_forwarded_for_only_from_trusted_proxy(client):
    staff = await make_user("mod", is_staff=True)
    game = await make_game()
    # the test client peer is a trusted proxy -> X-Forwarded-For is honoured
    await _vote(client, game.id, "up", user=staff, ip="203.0.113.7")
    vote = await Vote.get(game_id=game.id)
    assert vote.ip == "203.0.113.7"
    assert (await Game.get(id=game.id)).rate == 1
    assert await User.filter(id=staff.id, score=1).exists()
