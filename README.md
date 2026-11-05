# The Reading Room

A personal digital library built with Flask, Flask-SQLAlchemy, SQLite, and Jinja.

## Run locally in Windows PowerShell

Select `.venv\Scripts\python.exe` as the PyCharm project interpreter. From the project terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe migrate_ratings.py
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000. If creating a fresh environment, first run `python -m venv .venv`.
On Linux/Codio, use `python3 -m venv .venv` and `.venv/bin/python` instead.
The migration creates missing tables and adds the rating column to older databases without removing books. It is safe to rerun.

## Features

- Add authors and books, search book titles, and sort by title or author.
- Book and author detail pages, including optional author dates.
- Ratings from 1–10; choose "Not rated" to clear a rating.
- Delete books; deleting an author's final book removes that author.
- Delete an author and all their books using an ORM cascade. The UI asks for confirmation.
- Responsive bookshelf design with Open Library covers and an unavailable-cover fallback.
- AI recommendations based on all saved books and ratings, plus optional preferences.

## AI recommendation setup

The app uses the OpenAI Responses API. An OpenAI API key and API account access are required; API usage may incur charges.

In PyCharm, open **Run → Edit Configurations**, select the `app.py` configuration, and add these environment variables using the environment-variable editor:

- `OPENAI_API_KEY`: your own API key. Keep it private; never commit it or paste it into chat.
- `OPENAI_MODEL`: optional; defaults to `gpt-4.1-mini`. Choose a Responses-compatible model your account can access.
- `SECRET_KEY`: a random private value for signing Flask sessions.

Restart the app, open **Find my next read**, and select **Generate recommendations**. Only this POST sends book titles, author names, publication years, ratings, and any entered preferences to OpenAI. Opening the page does not call the API. Responses are rendered as escaped plain text. No recommendations are fabricated when configuration is missing or the service fails.

The app does not automatically load `.env` files. Set environment variables in the run configuration or launching shell. Local `.env` files are ignored by Git as an additional precaution.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use a temporary in-memory database and mocked API calls, preserving your library and making no paid API requests. Live AI output requires a separately configured API key.

## References

- [OpenAI Python SDK](https://developers.openai.com/api/reference/python)
- [SQLAlchemy cascades](https://docs.sqlalchemy.org/en/20/orm/cascades.html)
- [Open Library Covers API](https://openlibrary.org/dev/docs/api/covers)
