from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)
PAGE = Path(__file__).resolve().parents[1] / "admin" / "puzzles.html"
CONTENT_PAGE = Path(__file__).resolve().parents[1] / "admin" / "content.html"


@router.get("/admin/puzzles")
def puzzle_authoring_page() -> FileResponse:
    return FileResponse(PAGE, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/admin/content")
def content_management_page() -> FileResponse:
    return FileResponse(CONTENT_PAGE, media_type="text/html", headers={"Cache-Control": "no-store"})
