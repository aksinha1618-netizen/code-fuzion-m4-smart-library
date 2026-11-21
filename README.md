# M4 Smart Library Seat Finder

Beginner-friendly hackathon prototype: plain HTML/CSS/JavaScript in the browser, a small Python backend, and SQLite for shared bookings. It uses only Python's built-in libraries.

## What is included

- Three floors with 150 seats each (450 seats total).
- Shared bookings stored in SQLite. A database constraint and transaction prevent two users taking the same active seat.
- Live seat updates over Server-Sent Events; clients refresh immediately when a seat changes.
- Check-in against a fixed seat QR, a 20-minute break timer, early return that keeps the booking, and automatic seat release when the break ends.
- Admin overview showing booking counts, peak booking hours in IST, and most-booked seats.
- One web server serves both the page and its API, so there is no CORS setup or separate frontend build.

## Run it on your computer

1. Install Python 3 if it is not already installed. In VS Code, open this project folder.
2. Open **Terminal → New Terminal**.
3. Run:

   ```powershell
   python server.py
   ```

4. Open `http://localhost:8000` in Chrome. Keep the terminal open while using the app.
5. To show the shared map locally, open the same address in another browser (for example, Chrome and Edge) on the same computer. Book on one screen and watch the other update. The `localhost` address works only on that computer; use the deployed HTTPS address for a phone/camera demo.

The database file `library.db` is created the first time the server starts. Stop the server with **Ctrl+C**. To reset the demo, stop it and delete `library.db`; the server will create a fresh one on next start.

## Demo flow for judges

1. Open the site in two browsers. Book the same seat from both in quick succession: only one should succeed, and the other map should update.
2. After booking, click **Show this seat's QR (demo)**. That button displays the seat label code. To demo check-in on one computer, print that QR (or show it on a separate screen), then use the camera scanner in the same browser that made the booking. Camera access needs HTTPS or `localhost` and permission.
3. Click **Start 20-minute break**. The **End break early (keep seat)** button clears the timer if the student returns early. Otherwise, explain that the server stores the deadline and releases the seat automatically when it expires, even if the student refreshes the page.
4. Scroll to **Admin Overview** to show peak hours and the most-booked seats. These rankings become useful as bookings accumulate.

For the actual library, print a fixed QR label for every seat. The seat map updates across users, but this prototype has no login; the browser that made the booking is the one that can check it in. The page's demo button produces the seat code so a label can be printed for the demo.

## Deploy (Render)

The app is one Python web service; no npm build or Python packages are needed. `render.yaml` is included for a quick free demo deployment.

1. Create a GitHub repository for this folder. The M4 event brief asks for a **public GitHub repository** and a live deployment, so make it public only if your team is comfortable sharing this source code.
2. In VS Code's terminal, from this project folder, create a small commit history and push it (replace the example GitHub URL with the repository you created):

   ```powershell
   git init
   git add index.html style.css
   git commit -m "Add library seat map interface"
   git add server.py .gitignore render.yaml
   git commit -m "Add SQLite booking backend"
   git add app.js
   git commit -m "Connect live booking and QR check-in"
   git add README.md
   git commit -m "Document demo and deployment"
   git branch -M main
   git remote add origin https://github.com/USERNAME/REPOSITORY.git
   git push -u origin main
   ```

3. In Render, choose **New → Blueprint**, connect the repository, and select **Apply**. Render reads `render.yaml` and starts the service.
4. When deployment finishes, open its HTTPS URL. Use this URL on the phone for the camera QR demo and allow camera access.

The free service is enough to show the app live, but Render's free filesystem is temporary and the service may sleep. Bookings can disappear after a restart or redeploy. For persistent SQLite data, use a paid web service with a disk mounted at `/var/data`, and set `DATABASE_PATH=/var/data/library.db`. Keep it to one service instance because the SQLite file is local to that instance. Render documents this limitation in [persistent disks](https://render.com/docs/disks), [free-tier limits](https://render.com/docs/free), and [current pricing](https://render.com/pricing). Check the price in Render before selecting a paid option.

## What to explain in the viva

- **Frontend:** `index.html` is the page, `style.css` controls its appearance, and `app.js` calls the backend with `fetch()`.
- **Backend:** `server.py` provides the API and sends live updates with Server-Sent Events.
- **Database:** `seats` holds the fixed floor map; `bookings` records each user's booking history. Cancelled and released rows remain for analytics.
- **Double-booking protection:** `/api/book` uses a SQLite write transaction. A unique index permits only one active booking per seat (and per browser user). The server returns HTTP 409 when a seat is already taken.
- **Break release:** the break end time is saved in the database. A server loop releases expired breaks, so it does not depend on the student's browser remaining open.
- **Live map:** every successful change broadcasts a small SSE event, and each open browser reloads the current floor from the database.

## AI use and submission notes

The event brief requires teams to declare AI tools and what they were used for. For this version, disclose that OpenAI Codex assisted with backend design, integration, and code corrections; your team should review the code and describe what it understands. Keep Git commits small and meaningful (for example: `add SQLite booking API`, `connect seat map to API`, `add admin analytics`) because the brief asks for a clean, granular history. The brief also requires a public GitHub repository and live demo for submission; follow your team's privacy decision before making the repository public.

## Prototype limits to disclose

- A browser ID identifies a demo user; there is no student login or campus identity verification.
- The demo admin page is open. Add staff authentication before real use.
- A QR seat code proves the selected seat number in this demo; a real deployment should print the fixed QR at each seat and should not treat a QR alone as tamper-proof proof of physical presence.
- SQLite on one server instance is appropriate for a small hackathon demonstration. If the library needs multiple server instances or larger traffic, move the database to managed PostgreSQL and add authentication.
