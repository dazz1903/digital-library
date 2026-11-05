"""Behavior checks using a disposable database and mocked AI responses."""

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openai import OpenAIError
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError

from app import app, db
from data_models import Author, Book
from recommendations import recommend_books


class LibraryTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.context = app.app_context()
        self.context.push()
        self.original = db.engines[None]
        self.engine = create_engine('sqlite:///:memory:')

        @event.listens_for(self.engine, 'connect')
        def enable_foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')

        db.engines[None] = self.engine
        db.create_all()
        author = Author(name='Zebra Writer')
        other = Author(name='Alpha Writer')
        db.session.add_all([author, other])
        db.session.flush()
        self.author_id, self.other_id = author.id, other.id
        self.books = [
            Book(title='Alpha Story', isbn='1111111111', publication_year=2000, author=author),
            Book(title='Beta Story', isbn='2222222222', publication_year=2001, author=author),
            Book(title='Gamma Story', isbn='3333333333', publication_year=2002, author=other),
        ]
        db.session.add_all(self.books)
        db.session.commit()
        self.ids = [book.id for book in self.books]
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engines[None] = self.original
        self.engine.dispose()
        self.context.pop()

    def test_detail_pages_and_missing_records(self):
        self.assertIn(b'Alpha Story', self.client.get(f'/book/{self.ids[0]}').data)
        author_page = self.client.get(f'/author/{self.author_id}').text
        self.assertIn('Alpha Story', author_page)
        self.assertIn('Beta Story', author_page)
        self.assertNotIn('Gamma Story', author_page)
        for path in ['/book/999', '/author/999']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_author_delete_cascades_only_their_books(self):
        path = f'/author/{self.author_id}/delete'
        self.assertEqual(self.client.get(path).status_code, 405)
        response = self.client.post(path, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'deleted successfully', response.data)
        self.assertIsNone(db.session.get(Author, self.author_id))
        self.assertIsNone(db.session.get(Book, self.ids[0]))
        self.assertIsNone(db.session.get(Book, self.ids[1]))
        self.assertIsNotNone(db.session.get(Book, self.ids[2]))
        self.assertEqual(self.client.post(path).status_code, 404)

    def test_book_delete_preserves_author_until_last_book(self):
        self.client.post(f'/book/{self.ids[0]}/delete')
        self.assertIsNotNone(db.session.get(Author, self.author_id))
        self.client.post(f'/book/{self.ids[1]}/delete')
        self.assertIsNone(db.session.get(Author, self.author_id))
        self.assertIsNotNone(db.session.get(Author, self.other_id))

    def test_rating_boundaries_update_and_clear(self):
        path = f'/book/{self.ids[0]}/rate'
        for value in ['1', '10', '7']:
            response = self.client.post(path, data={'rating': value}, follow_redirects=True)
            self.assertIn(b'Rating saved', response.data)
            self.assertEqual(db.session.get(Book, self.ids[0]).rating, int(value))
        for value in ['0', '11', '-1', '7.5', 'bad']:
            self.assertEqual(self.client.post(path, data={'rating': value}).status_code, 400)
            self.assertEqual(db.session.get(Book, self.ids[0]).rating, 7)
        self.client.post(path, data={'rating': ''})
        self.assertIsNone(db.session.get(Book, self.ids[0]).rating)
        self.assertEqual(self.client.get(path).status_code, 405)
        self.assertEqual(self.client.post('/book/999/rate').status_code, 404)

    def test_database_rejects_invalid_rating(self):
        self.books[0].rating = 11
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_search_sort_and_links(self):
        page = self.client.get('/?search=STORY&sort=author').text
        self.assertLess(page.index('Gamma Story'), page.index('Alpha Story'))
        self.assertIn(f'/book/{self.ids[0]}', page)
        self.assertIn(f'/author/{self.author_id}/delete', page)
        self.assertIn('No books match', self.client.get('/?search=%25').text)
        self.assertNotIn('<script>alert(1)</script>', self.client.get('/?search=<script>alert(1)</script>').text)

    @patch.dict(os.environ, {'OPENAI_API_KEY': ''})
    @patch('app.recommend_books')
    def test_missing_key_never_calls_ai(self, mock_recommend):
        self.assertIn(b'need setup', self.client.get('/recommend').data)
        self.assertEqual(self.client.post('/recommend').status_code, 503)
        mock_recommend.assert_not_called()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-placeholder'})
    @patch('app.recommend_books')
    def test_recommendation_success_and_errors(self, mock_recommend):
        self.client.get('/recommend')
        mock_recommend.assert_not_called()
        mock_recommend.return_value = 'Try another book. <script>bad</script>'
        response = self.client.post('/recommend', data={'preferences': 'A mystery'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'&lt;script&gt;', response.data)
        books, preferences = mock_recommend.call_args.args
        self.assertEqual(len(books), 3)
        self.assertEqual(preferences, 'A mystery')
        mock_recommend.side_effect = OpenAIError('Service unavailable')
        self.assertEqual(self.client.post('/recommend').status_code, 502)
        mock_recommend.reset_mock()
        self.assertEqual(self.client.post('/recommend', data={'preferences': 'x' * 1001}).status_code, 400)
        mock_recommend.assert_not_called()

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-placeholder'})
    @patch('app.recommend_books')
    def test_empty_library_no_ai_request(self, mock_recommend):
        for author in db.session.scalars(db.select(Author)).all():
            db.session.delete(author)
        db.session.commit()
        self.assertEqual(self.client.post('/recommend').status_code, 400)
        mock_recommend.assert_not_called()

    @patch('recommendations.OpenAI')
    def test_ai_payload_includes_all_books_and_ratings(self, mock_client):
        self.books[0].rating = 9
        client = mock_client.return_value.__enter__.return_value
        client.responses.create.return_value = SimpleNamespace(output_text='A new book')
        self.assertEqual(recommend_books(self.books, 'Cozy fiction'), 'A new book')
        kwargs = client.responses.create.call_args.kwargs
        payload = json.loads(kwargs['input'])
        self.assertEqual(len(payload['library']), 3)
        self.assertEqual(payload['library'][0]['rating_out_of_10'], 9)
        self.assertEqual(payload['preferences'], 'Cozy fiction')
        self.assertFalse(kwargs['store'])
        client.responses.create.return_value = SimpleNamespace(output_text=' ')
        with self.assertRaises(ValueError):
            recommend_books(self.books, '')


if __name__ == '__main__':
    unittest.main()
