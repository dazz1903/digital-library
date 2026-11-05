import os
from datetime import date
from urllib.parse import quote

from flask import Flask, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from openai import OpenAIError

from data_models import db, Author, Book
from recommendations import recommend_books


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

@app.route('/book/<int:book_id>/delete', methods=['POST'])
def delete_book(book_id):
    book = db.get_or_404(Book, book_id)
    title = book.title
    author = book.author
    db.session.delete(book)
    db.session.flush()

    remaining_book = db.session.scalar(
        db.select(Book.id).where(Book.author_id == author.id).limit(1)
    )
    if remaining_book is None:
        db.session.delete(author)

    db.session.commit()
    flash(f'Book "{title}" deleted successfully!')
    return redirect(url_for('home'))


@app.route('/book/<int:book_id>')
def book_detail(book_id):
    return render_template('book_detail.html', book=db.get_or_404(Book, book_id))


@app.route('/author/<int:author_id>')
def author_detail(author_id):
    author = db.get_or_404(Author, author_id)
    books = db.session.scalars(
        db.select(Book).where(Book.author_id == author_id).order_by(Book.title)
    ).all()
    return render_template('author_detail.html', author=author, books=books)


@app.route('/author/<int:author_id>/delete', methods=['POST'])
def delete_author(author_id):
    author = db.get_or_404(Author, author_id)
    name = author.name
    db.session.delete(author)
    db.session.commit()
    flash(f'Author "{name}" and all their books deleted successfully!')
    return redirect(url_for('home'))


@app.route('/book/<int:book_id>/rate', methods=['POST'])
def rate_book(book_id):
    book = db.get_or_404(Book, book_id)
    value = request.form.get('rating', '').strip()
    try:
        rating = int(value) if value else None
        if rating is not None and not 1 <= rating <= 10:
            raise ValueError
    except ValueError:
        return render_template('book_detail.html', book=book,
                               error='Choose a whole-number rating from 1 to 10.'), 400
    book.rating = rating
    db.session.commit()
    flash('Rating saved!' if rating else 'Rating removed.')
    return redirect(url_for('book_detail', book_id=book.id))


@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    books = db.session.scalars(
        db.select(Book).options(db.joinedload(Book.author)).order_by(Book.id)
    ).all()
    configured = bool(os.environ.get('OPENAI_API_KEY', '').strip())
    result = None
    error = None
    status = 200
    if request.method == 'POST':
        preferences = request.form.get('preferences', '').strip()
        if not books:
            error = 'Add at least one book before requesting recommendations.'
            status = 400
        elif not configured:
            error = 'AI recommendations are not configured yet. See the project README.'
            status = 503
        elif len(preferences) > 1000:
            error = 'Keep your preferences to 1,000 characters or fewer.'
            status = 400
        else:
            try:
                result = recommend_books(books, preferences)
            except OpenAIError:
                error = 'The AI service is unavailable. Check your API access and try again.'
                status = 502
            except ValueError as exception:
                error = str(exception)
                status = 502
    return render_template('recommend.html', books=books, configured=configured,
                           result=result, error=error), status


# Tables have been created. Uncomment these lines to initialize a new database.
# with app.app_context():
#     db.create_all()


if __name__ == '__main__':
    app.run()
