# Adri Poltronas - Preview Run Doc

## How to reproduce artifacts

1. Ensure Python dependencies are installed:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Initialize the database:
   ```bash
   cd backend
   python -c "import database; database.criar_tabela()"
   ```

## How to run the server

1. Start the Flask server:
   ```bash
   cd backend
   pythonw app.py
   ```

2. The server will be available at `http://localhost:5000`

3. To stop the server, kill the `pythonw.exe` process on port 5000.

## Notes

- The app runs on port 5000 by default
- Frontend files are served from the `frontend/` directory
- Backend API endpoints are prefixed with `/api/`
- The app uses SQLite database stored in `%APPDATA%/AdriPoltronas/adri_poltronas.db`
