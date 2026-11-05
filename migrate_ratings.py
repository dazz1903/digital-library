"""Add optional ratings to an existing library without losing its records."""

from sqlalchemy import inspect, text

from app import app, db


def migrate():
    with app.app_context():
        db.create_all()
        columns = {column['name'] for column in inspect(db.engine).get_columns('book')}
        if 'rating' not in columns:
            with db.engine.begin() as connection:
                connection.execute(text(
                    'ALTER TABLE book ADD COLUMN rating INTEGER '
                    'CHECK (rating BETWEEN 1 AND 10)'
                ))
            print('Added rating column. Existing books preserved.')
        else:
            print('Rating column already exists.')


if __name__ == '__main__':
    migrate()
