from backend.app.repositories.categories import CategoryRepository
from backend.app.repositories.content import ContentRepository
from backend.app.repositories.movies import MovieRepository
from backend.app.repositories.puzzles import PuzzleRepository
from backend.app.repositories.schedule import ScheduleRepository
from backend.app.repositories.game import GameRepository
from backend.app.repositories.albumnesia_game import AlbumnesiaGameRepository
from backend.app.repositories.badly_game import BadlyGameRepository

__all__ = ["AlbumnesiaGameRepository", "BadlyGameRepository", "CategoryRepository", "ContentRepository", "GameRepository", "MovieRepository", "PuzzleRepository", "ScheduleRepository"]
