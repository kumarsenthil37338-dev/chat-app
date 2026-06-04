# Campus Chat - Real-Time Multi-User Chat Application

Campus Chat is a complete Flask and Flask-SocketIO chat application for college projects and portfolio demos. It supports user accounts, real-time messaging, online users, typing indicators, read receipts, file sharing, profile pictures, dark mode, and permanent SQLite chat history.

## Features

- User registration, login, logout, password hashing, and Flask session management
- Real-time chat using Flask-SocketIO
- Sender names, timestamps, join notifications, and leave notifications
- SQLite database with SQLAlchemy models for users, messages, and files
- File upload and download support for images, PDFs, text files, and Word documents
- Image previews inside chat bubbles
- Typing indicator, message search, read receipts, emoji picker, and profile pictures
- Responsive layout with mobile sidebar and dark mode toggle
- Input validation, file type validation, SQLAlchemy query protection, and client-side HTML escaping

## Project Structure

```text
chat_app/
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── chat.js
│   ├── images/
│   │   └── default-avatar.svg
│   └── uploads/
├── templates/
│   ├── login.html
│   ├── register.html
│   └── chat.html
├── app.py
├── models.py
├── database.db
├── requirements.txt
└── README.md
```

## Installation

1. Open a terminal in the project folder:

```bash
cd chat_app
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

On macOS or Linux, activate it with:

```bash
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the application:

```bash
python app.py
```

5. Open the app in your browser:

```text
http://127.0.0.1:5000
```

The SQLite database is created automatically as `database.db` when the app starts.

## Share With a Friend

`http://127.0.0.1:5000` works only on your own computer. To give your friend a working link, deploy the project to a hosting service such as Render, Railway, PythonAnywhere, or any VPS that supports Python.

### Render-style deployment

1. Upload this `chat_app` folder to a GitHub repository.
2. Create a new web service from that repository.
3. Use this build command:

```bash
pip install -r requirements.txt
```

4. Use this start command:

```bash
gunicorn --worker-class eventlet -w 1 app:app
```

5. Add an environment variable:

```text
SECRET_KEY=replace-with-a-long-random-secret
```

After deployment, the hosting service gives you a public URL like:

```text
https://your-chat-app.onrender.com
```

Share that URL with your friend. Both of you can register, log in, and chat from different devices.

## How It Works

- `models.py` defines the database tables and helper methods for password hashing.
- `app.py` contains the Flask routes, authentication logic, upload handling, and Socket.IO events.
- `templates/` contains the login, registration, and chat pages.
- `static/js/chat.js` connects to Socket.IO and updates the chat interface in real time.
- `static/css/style.css` provides the responsive layout, chat bubbles, dark mode, and mobile styling.

## Security Notes

- Passwords are hashed with Werkzeug before being stored.
- SQLAlchemy is used instead of raw SQL to reduce SQL injection risk.
- Messages are escaped in the browser before display to reduce XSS risk.
- Uploaded files are restricted by extension and MIME type.
- File names are sanitized with Werkzeug's `secure_filename`.
- A production deployment should replace the development `SECRET_KEY` with an environment variable.

## Suggested Demo Flow

1. Register two users in different browsers or one regular window and one private window.
2. Send messages from both accounts and watch them appear instantly.
3. Upload an image and confirm the preview appears in the chat.
4. Upload a PDF or text document and download it from the chat bubble.
5. Try search, dark mode, emoji picker, typing indicator, and read receipts.

## Notes for Portfolio Use

This project is intentionally beginner-friendly and modular. For a more advanced version, you can add private rooms, friend lists, admin moderation, deployment configuration, and cloud file storage.
