import uuid

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_list_categories() -> None:
    response = TestClient(create_app()).get("/api/v1/categories")

    assert response.status_code == 200
    assert len(response.json()) == 9
    assert {item["slug"] for item in response.json()} >= {"anime", "superheroes", "marvel", "dc"}


def test_list_and_get_movies() -> None:
    client = TestClient(create_app())
    listing = client.get("/api/v1/movies")

    assert listing.status_code == 200
    assert len(listing.json()) == 16
    iron_man = next(movie for movie in listing.json() if movie["title"] == "Iron Man")
    assert {category["slug"] for category in iron_man["categories"]} == {"superheroes", "marvel"}

    detail = client.get(f"/api/v1/movies/{iron_man['id']}")
    assert detail.status_code == 200
    assert detail.json() == iron_man


def test_get_unknown_movie_returns_404() -> None:
    response = TestClient(create_app()).get(f"/api/v1/movies/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Movie not found"}
