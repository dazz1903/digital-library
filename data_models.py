"""Database models for the digital library."""

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Author(db.Model):
    """An author whose books can be stored in the library."""

    __tablename__ = "author"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    birth_date = db.Column(db.Date, nullable=True)
    date_of_death = db.Column(db.Date, nullable=True)
    books = db.relationship("Book", back_populates="author", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Author id={self.id!r} name={self.name!r}>"

    def __str__(self):
        return self.name


class Book(db.Model):
    """A book linked to an author through a foreign key."""

    __tablename__ = "book"
    __table_args__ = (db.CheckConstraint("rating BETWEEN 1 AND 10", name="valid_rating"),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    isbn = db.Column(db.String(20), nullable=False, unique=True)
    title = db.Column(db.String(300), nullable=False)
    publication_year = db.Column(db.Integer, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("author.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=True)
    author = db.relationship("Author", back_populates="books")

    def __repr__(self):
        return f"<Book id={self.id!r} title={self.title!r}>"

    def __str__(self):
        return self.title
