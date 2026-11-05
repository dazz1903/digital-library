import os

from flask import Flask

from data_models import db, Author, Book


app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"sqlite:///{os.path.join(basedir, 'data/library.sqlite')}"
)

db.init_app(app)

# Tables have been created. Uncomment these lines to initialize a new database.
# with app.app_context():
#     db.create_all()
