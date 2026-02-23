# Google Calendar Setup Guide for OpenZero

To enable Google Calendar integration in your private agent, you need to create a project in the Google Cloud Console and obtain a `credentials.json` file.

## 1. Create Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., "OpenZero-Agent").
3. Search for **"Google Calendar API"** in the Library and click **Enable**.

## 2. Configure OAuth Consent Screen
1. Go to **APIs & Services > OAuth consent screen**.
2. Select **External** (unless you have a Google Workspace organization).
3. Fill in the app name ("OpenZero") and your email.
4. In **Scopes**, click **Add or Remove Scopes**.
5. Add `.../auth/calendar.readonly`.
6. Add your own email address as a **Test User** (Crucial, otherwise it won't work while in "Testing" mode).

## 3. Create Credentials
1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth client ID**.
3. Select **Desktop App** as the application type.
4. Click **Create** and then **Download JSON**.
5. Rename the downloaded file to `credentials.json`.

## 4. Install Credentials in OpenZero
You need to place the `credentials.json` file in the `tokens` directory of the backend.

### On your host machine:
Move the file to:
`src/backend/tokens/credentials.json`

(If you are running in Docker, this directory is mapped to `/app/tokens` inside the container).

## 5. Authorize the App
1. Restart your OpenZero stack: `docker-compose restart backend`.
2. Check the logs: `docker-compose logs -f backend`.
3. You will see a URL in the logs. Copy and paste it into your browser.
4. Log in with your Google account and grant permission.
5. If you see a warning that the app isn't verified, click **Advanced** and then **Go to OpenZero (unsafe)**.
6. The app will receive the token and save it to `tokens/token.json`.

**Note:** If you are running on a remote VPS, you might need to use SSH tunneling to access the local server started by the authentication flow:
`ssh -L 8080:localhost:8080 user@your-vps-ip`
Then open the link in your local browser.
