import os
from datetime import date
from urllib.parse import quote

from flask import Flask, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from data_models import db, Author, Book


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'local-library-development')

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"sqlite:///{os.path.join(basedir, 'data/library.sqlite')}"
)

db.init_app(app)


@app.route('/')
def home():
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'title')
    if sort not in ('title', 'author'):
        sort = 'title'
    order_column = Author.name if sort == 'author' else Book.title
    query = db.select(Book).join(Author).options(db.joinedload(Book.author))
    if search:
        query = query.where(Book.title.icontains(search, autoescape=True))
    books = db.session.execute(
        query.order_by(db.func.lower(order_column), Book.title, Book.id)
    ).scalars().all()
    return render_template('home.html', books=books, sort=sort, search=search)


@app.template_filter('cover_url')
def cover_url(isbn):
    return f"https://covers.openlibrary.org/b/isbn/{quote(isbn, safe='')}-M.jpg?default=false"


@app.route('/add_author', methods=['GET', 'POST'])
def add_author():
    error = None
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name or len(name) > 200:
                raise ValueError('Enter an author name of 1–200 characters.')
            birth = request.form.get('birth_date', '').strip()
            death = request.form.get('date_of_death', '').strip()
            try:
                birth = date.fromisoformat(birth) if birth else None
                death = date.fromisoformat(death) if death else None
            except ValueError:
                raise ValueError('Enter valid dates in YYYY-MM-DD format.') from None
            if birth and death and death < birth:
                raise ValueError('Date of death cannot be before birth date.')
            db.session.add(Author(name=name, birth_date=birth, date_of_death=death))
            db.session.commit()
        except ValueError as exception:
            error = str(exception)
        else:
            flash('Author added successfully!')
            return redirect(url_for('add_author'))
    return render_template('add_author.html', error=error), 400 if error else 200


@app.route('/add_book', methods=['GET', 'POST'])
def add_book():
    error = None
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            isbn = request.form.get('isbn', '').replace('-', '').replace(' ', '').upper()
            if not title or len(title) > 300:
                raise ValueError('Enter a book title of 1–300 characters.')
            if not (len(isbn) == 13 and isbn.isascii() and isbn.isdigit()
                    or len(isbn) == 10 and isbn[:9].isascii() and isbn[:9].isdigit()
                    and (isbn[-1] in '0123456789X')):
                raise ValueError('Enter a 10- or 13-character ISBN.')
            try:
                year = int(request.form.get('publication_year', ''))
                author_id = int(request.form.get('author_id', ''))
            except ValueError:
                raise ValueError('Select an author and enter a whole publication year.') from None
            if not 1 <= year <= 9999:
                raise ValueError('Publication year must be between 1 and 9999.')
            if db.session.get(Author, author_id) is None:
                raise ValueError('Select an existing author.')
            db.session.add(Book(title=title, isbn=isbn, publication_year=year,
                                author_id=author_id))
            db.session.commit()
        except ValueError as exception:
            error = str(exception)
        except IntegrityError:
            db.session.rollback()
            error = 'A book with this ISBN already exists.'
        else:
            flash('Book added successfully!')
            return redirect(url_for('add_book'))
    authors = db.session.execute(db.select(Author).order_by(Author.name)).scalars().all()
    return render_template('add_book.html', authors=authors, error=error), 400 if error else 200

# Tables have been created. Uncomment these lines to initialize a new database.
# with app.app_context():
#     db.create_all()


if __name__ == '__main__':
    app.run()
