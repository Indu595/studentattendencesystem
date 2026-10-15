# Student Attendance System

A Flask/Streamlit and SQLite attendance app with administrator/faculty accounts, consent-based webcam face enrollment, daily reports, and editable attendance.

## Features

- First-run setup for a unique administrator login; no default credentials.
- Admin-created faculty accounts with role-based access.
- Student registration with unique roll numbers, year of study, and semester.
- Branch/department and academic-year cohort assignment for each student.
- Year- and branch-filtered daily reports and attendance registers.
- Student check-in using roll number plus a live webcam face match against that student's enrolled face.
- Student self check-in is available only from 9:00 AM to 11:00 AM, using the server's local time.
- Face detection and recognition through the browser webcam.
- Three consented JPEG face photos and a recognition template stored in SQLite for each enrolled student.
- Automatic attendance scans with database-enforced duplicate prevention for each student and date.
- Daily register and attendance report with present, late, excused, absent, unmarked, and percentage totals.
- Staff overview with year/branch attendance totals and expandable student details, including each student's attended-day count.
- Student attendance history and percentage calculation.
- Manual status and note corrections from the daily register.
- Delete face photos and recognition profile from a student's enrollment controls.

## Getting started

### Run with Streamlit

1. Install the dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Start the Streamlit interface:
   ```powershell
   streamlit run streamlit_app.py
   ```
3. Create the first administrator account when prompted. The Streamlit interface reuses the same SQLite database and attendance API as the Flask interface.

The Streamlit interface includes the year-of-study overview filter, attendance grouped by academic year/branch/year of study, student history, manual attendance corrections, faculty and student management, face enrollment, automatic face attendance, and student self check-in. Camera use requires HTTPS (provided by Streamlit Community Cloud) and an internet connection to load the face-recognition models.

### Deploy on Streamlit Community Cloud

1. Push this project to a GitHub repository and open [share.streamlit.io](https://share.streamlit.io/).
2. Choose **Create app**, select the repository and branch, and set the main file path to `streamlit_app.py`.
3. In the app's **Settings → Secrets**, set `APP_SECRET_KEY` to a long, private random value.
4. Deploy and complete the first administrator setup in the app.

**Important data-storage limitation:** Streamlit Community Cloud's local filesystem is not persistent across app restarts or redeployments. This app currently uses SQLite, including for face descriptors and face photos. Do not use Community Cloud for real attendance or biometric data until the database has been migrated to a persistent, access-controlled database. Do not commit any live database, student data, face images, passwords, or secrets to GitHub. Existing tracked database files must be removed from the repository history before using it for real data.

To configure a local or self-hosted SQLite location, set `ATTENDANCE_DATABASE` to the database file path in the process environment or Streamlit secrets.

### Run with Flask

1. Open a terminal in the project root.
2. Create a virtual environment if needed:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Start the app:
   ```powershell
   python app.py
   ```
5. Open http://127.0.0.1:5000. On first use, create the administrator account with a unique password of at least 12 characters.
6. Sign in as administrator and create faculty accounts. Staff can register students with a year of study, semester, academic year (such as `2026-2027`), and branch/department, then enroll faces.

Students can use **Student Attendance Check-in** on the opening page without a staff login, daily from 9:00 AM to 11:00 AM according to the server's local time. They enter their roll number and verify with a live webcam scan. The server compares the submitted live face descriptor only to the enrolled profile for that roll number, then records today's attendance under the student's academic year and branch. Each roll number can be checked in only once per day. Failed checks return a generic message and are rate-limited per roll number and network address.

Staff can filter the daily register and report by academic year and branch. The selected cohort determines the report percentage denominator; attendance entries keep the year and branch snapshot from the time they were marked.

Webcam access is generally restricted to localhost or HTTPS. The app loads the face recognition library and models from jsDelivr, so an internet connection is required for face enrollment and recognition.

## Face-data privacy

Face enrollment requires staff to confirm student or guardian consent. Enrollment captures three JPEG photos and a recognition template; both are stored in the SQLite database and accessible to authenticated staff. **The database is not encrypted by this app.** Restrict access to the host and database file, use disk/database encryption appropriate to your environment, and do not deploy this development server directly to the public internet. Use HTTPS in any network deployment. Use **Delete Face Data** to remove a student's photos and template. Obtain any required consent and follow applicable biometric-data retention and deletion rules.

Recognition may make mistakes and does not detect spoofing. Review the daily report and correct mistakes manually. A student's percentage is attended days (present or late) divided by recorded non-excused days. The daily percentage is present plus late divided by students in the selected year/branch cohort; unmarked students remain separate from explicit absences.

## Deployment configuration

- Set `APP_SECRET_KEY` to a long random secret and keep it private; this preserves signed sessions across restarts.
- Set `ATTENDANCE_DATABASE` to an absolute path for the SQLite database if the working directory may change.
- Set `COOKIE_SECURE=1` when serving behind HTTPS.
- Keep `FLASK_DEBUG` unset in production. The built-in Flask server is for local development only; use a production WSGI server and HTTPS for a real deployment.

## Project structure

- `app.py` — Flask routes, authentication, SQLite persistence, reports
- `streamlit_app.py` — Streamlit interface, reusing the Flask API and SQLite database
- `face_camera/index.html` — Streamlit webcam/face-recognition component
- `templates/index.html` — login and attendance dashboard
- `static/app.js` — dashboard, webcam recognition, enrollment
- `static/style.css` — responsive UI styling
- `attendance.db` — SQLite database generated automatically
