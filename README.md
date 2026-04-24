# St. Jude's School Website

This website includes a small Python backend for admission enquiries, with Supabase used for inquiry storage.

## Project structure

```text
project/
|-- frontend/
|   |-- index.html
|   |-- styles.css
|   |-- script.js
|   `-- assets/
|-- backend/
|   |-- server.py
|   |-- requirements.txt
|   |-- supabase_schema.sql
|   |-- data/
|   |   `-- .gitkeep
|   |-- .env
|   `-- .env.example
`-- README.md
```

## What it does

- Serves the frontend from `frontend/`
- Saves every enquiry in Supabase
- Emails the school when SMTP is configured

## Supabase setup

1. Create a Supabase project.
2. Open the SQL Editor in Supabase.
3. Run the SQL from `backend/supabase_schema.sql`.
4. Copy your project URL into `SUPABASE_URL`.
5. Copy a backend-only key into `SUPABASE_SERVICE_KEY`.
6. Update `backend/.env` with those values.

Use a backend-only key such as a legacy `service_role` key or a secure backend secret key. Never expose it in the browser.

## Run locally

1. Open `backend/.env`
2. Fill in the Supabase and SMTP settings in `backend/.env`
3. Run `python backend/server.py`
4. Open `http://127.0.0.1:8000`

## Notes

- The website sends enquiry details to `POST /api/inquiries`
- If SMTP is not configured yet, enquiries are still saved in Supabase
- For Gmail, use an App Password instead of your regular password
- The `backend/data/` folder is kept for future exports or backup files
