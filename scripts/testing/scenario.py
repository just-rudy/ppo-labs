"""Same externally observable contract with HTTPX (E2E) or curl (manual replay)."""

import argparse
import json
import os
import subprocess
from contextlib import nullcontext

import httpx


class CurlClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def request(self, method, path, **kwargs):
        args = [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            "20",
            "--request",
            method,
            "--write-out",
            "\n%{http_code}",
            self.base_url + path,
        ]
        for key, value in kwargs.get("headers", {}).items():
            args.extend(["--header", f"{key}: {value}"])
        if "json" in kwargs:
            args.extend(
                [
                    "--header",
                    "Content-Type: application/json",
                    "--data-binary",
                    json.dumps(kwargs["json"]),
                ]
            )
        completed = subprocess.run(
            args, check=True, capture_output=True, text=True, timeout=25
        )
        body, status = completed.stdout.rsplit("\n", 1)
        return httpx.Response(
            int(status),
            content=body.encode(),
            request=httpx.Request(method, self.base_url + path),
        )


def play_scenario(base_url, *, use_curl=False, record=None, steps=False):
    import allure

    events = []
    context = (
        nullcontext(CurlClient(base_url))
        if use_curl
        else httpx.Client(base_url=base_url, timeout=20)
    )
    with context as client:

        def request(method, path, *, user_id=None, payload=None, status=200):
            label = f"{method} {path} → {status}"
            with allure.step(label) if steps else nullcontext():
                kwargs = {"headers": {"X-User-Id": user_id}} if user_id else {}
                if payload is not None:
                    kwargs["json"] = payload
                response = client.request(method, path, **kwargs)
                event = {
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "response": response.json(),
                }
                events.append(event)
                if record:
                    with open(record, "a") as stream:
                        stream.write(json.dumps(event) + "\n")
                if steps:
                    allure.attach(
                        json.dumps(event, indent=2), label, allure.attachment_type.JSON
                    )
                assert response.status_code == status, response.text
                return response.json()

        users = [
            request(
                "POST",
                "/api/v1/users/register",
                payload={
                    "username": name,
                    "password": "lab-secret12",
                    "password_confirm": "lab-secret12",
                },
            )
            for name in ("labhost", "labguest")
        ]
        assert users[0]["id"] != users[1]["id"]
        assert all(user["role"] == "authenticated" for user in users)
        logged = request(
            "POST",
            "/api/v1/users/login",
            payload={"username": "labhost", "password": "lab-secret12"},
        )
        assert logged["id"] == users[0]["id"]
        host = users[0]["id"]
        game = request(
            "POST",
            "/api/v1/game/new",
            user_id=host,
            payload={"host_user_id": host, "name": "labroom"},
        )
        game_id = game["id"]
        assert game["status"] == "created" and game["name"] == "labroom"
        assert game["players"] == []
        for index, user in enumerate(users, 1):
            game = request(
                "POST",
                "/api/v1/game/join",
                user_id=user["id"],
                payload={"user_id": user["id"], "game_ref": "labroom"},
            )
            assert len(game["players"]) == index
        assert {p["user_id"] for p in game["players"]} == {u["id"] for u in users}
        game = request("POST", f"/api/v1/game/{game_id}/start", user_id=host)
        assert game["status"] == "in_progress"
        assert len(game["market"]) == 5
        assert all(
            len(p["hand"]) == 5 and p["cards_count"] == 10 for p in game["players"]
        )
        current = next(p for p in game["players"] if p["id"] == game["cur_player_id"])
        card = current["hand"][0]
        market = game["market"][0]
        game = request(
            "POST",
            f"/api/v1/game/{game_id}/play",
            user_id=current["user_id"],
            payload={"player_id": current["id"], "card_id": card["id"]},
        )
        updated = next(p for p in game["players"] if p["id"] == current["id"])
        assert card["id"] not in {c["id"] for c in updated["hand"]}
        assert card["id"] in {c["id"] for c in updated["table"]}
        assert updated["cur_echo"] == current["cur_echo"] + card["echo"]
        before_buy = updated["cur_echo"]
        game = request(
            "POST",
            f"/api/v1/game/{game_id}/buy",
            user_id=current["user_id"],
            payload={"player_id": current["id"], "card_id": market["id"]},
        )
        updated = next(p for p in game["players"] if p["id"] == current["id"])
        assert updated["cur_echo"] == before_buy - market["cost"]
        assert market["id"] in {c["id"] for c in updated["discard"]}
        assert market["id"] not in {c["id"] for c in game["market"]}
        game = request(
            "POST",
            f"/api/v1/game/{game_id}/end-turn",
            user_id=current["user_id"],
            payload={"player_id": current["id"]},
        )
        assert game["cur_player_id"] != current["id"]
        assert game["cur_turn"] == 1 and len(game["market"]) == 5
        saved = request("GET", f"/api/v1/game/{game_id}", user_id=host)
        assert saved == game
        finished = request(
            "POST",
            f"/api/v1/game/{game_id}/finish",
            user_id=host,
            payload={"player_id": game["players"][0]["id"]},
        )
        assert finished["status"] == "finished" and finished["cur_player_id"] is None
        assert finished["winner"]["player_id"] in {p["id"] for p in game["players"]}
        assert request("GET", f"/api/v1/game/{game_id}", user_id=host) == finished
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url", default=os.environ.get("API_BASE_URL", "http://api:8000")
    )
    parser.add_argument("--curl", action="store_true")
    parser.add_argument("--record", default="/artifacts/replay.jsonl")
    args = parser.parse_args()
    events = play_scenario(args.url, use_curl=args.curl, record=args.record)
    print(f"Manual replay: {len(events)} checked HTTP requests succeeded")
