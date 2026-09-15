from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.entities import Category


class CategoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active(self) -> list[Category]:
        statement = select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        return list(self.session.scalars(statement))
