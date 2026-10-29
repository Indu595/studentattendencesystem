from __future__ import annotations

import math
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.components.v1 import declare_component
from streamlit.errors import StreamlitSecretNotFoundError


def load_deployment_secrets() -> None:
    try:
        secrets = dict(st.secrets)
    except StreamlitSecretNotFoundError:
        return
    for key in ("APP_SECRET_KEY", "ATTENDANCE_DATABASE"):
        if key in secrets and secrets[key]:
            os.environ[key] = str(secrets[key])


load_deployment_secrets()

import app as backend  # noqa: E402


st.set_page_config(
    page_title="Student Attendance System",
    page_icon="📚",
    layout="wide",
)

face_camera = declare_component(
    "student_attendance_face_camera",
    path=str(Path(__file__).parent / "face_camera"),
)

ATTENDANCE_STATUSES = ["unmarked", "present", "late", "excused", "absent"]
STATUS_LABELS = {
    "unmarked": "Not marked",
    "present": "Present",
    "late": "Late",
    "excused": "Excused",
    "absent": "Absent",
}
FACE_MATCH_THRESHOLD = 0.43
FACE_AMBIGUITY_MARGIN = 0.05


def initialize_state() -> None:
    if "api_client" not in st.session_state:
        st.session_state.api_client = backend.app.test_client()
        st.session_state.api_client_id = uuid.uuid4().hex
    st.session_state.setdefault("processed_face_events", set())
    st.session_state.setdefault("scanned_students", set())


def api_request(
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    response = st.session_state.api_client.open(
        path,
        method=method,
        json=payload,
        environ_overrides={"REMOTE_ADDR": st.session_state.api_client_id},
    )
    result = response.get_json(silent=True)
    if not response.is_json:
        raise RuntimeError(f"The attendance service returned HTTP {response.status_code}.")
    if response.status_code >= 400:
        message = result.get("error", "The request could not be completed.")
        raise RuntimeError(message)
    return result


def process_face_event(event: Any, event_type: str) -> dict[str, Any] | None:
    if not isinstance(event, dict) or event.get("event_type") != event_type:
        return None
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or event_id in st.session_state.processed_face_events:
        return None
    st.session_state.processed_face_events.add(event_id)
    return event


def render_camera(mode: str, key: str) -> Any:
    return face_camera(mode=mode, key=key, default=None)


def render_student_checkin() -> None:
    st.subheader("Student Attendance Check-in")
    st.caption(
        "Enter your roll number and verify your face using the camera. "
        "Check-in is available from 9:00 AM to 11:00 AM server local time."
    )
    roll_number = st.text_input(
        "Student roll number",
        key="public_checkin_roll",
        max_chars=40,
    )
    event = render_camera("checkin", "student-checkin-camera")
    event = process_face_event(event, "checkin")
    if event is not None:
        try:
            result = api_request(
                "/api/student/check-in",
                "POST",
                {
                    "roll_number": roll_number,
                    "descriptor": event.get("descriptor"),
                },
            )
            st.success(
                f"{result['message']} {result.get('academic_year', '')} · "
                f"{result.get('branch', '')} · {result.get('study_year', '')}."
            )
        except (KeyError, RuntimeError) as error:
            st.error(str(error))


def render_auth() -> bool:
    try:
        status = api_request("/api/auth/status")
    except RuntimeError as error:
        st.error(f"Could not load sign-in status: {error}")
        return False

    if st.session_state.get("current_user"):
        return True

    if status["setup_required"]:
        st.title("Set up staff access")
        st.info("Create the first administrator account. Use a unique password of at least 12 characters.")
        with st.form("admin_setup"):
            username = st.text_input("Administrator username", max_chars=80)
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Create administrator", type="primary")
        if submitted:
            try:
                user = api_request(
                    "/api/auth/setup",
                    "POST",
                    {"username": username, "password": password},
                )
                st.session_state.current_user = user
                st.rerun()
            except RuntimeError as error:
                st.error(str(error))
        return False

    st.title("Staff login")
    with st.form("staff_login"):
        username = st.text_input("Username", max_chars=80)
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        try:
            user = api_request(
                "/api/auth/login",
                "POST",
                {"username": username, "password": password},
            )
            st.session_state.current_user = user
            st.rerun()
        except RuntimeError as error:
            st.error(str(error))
    return False


def load_students() -> list[dict[str, Any]]:
    students = api_request("/api/students")
    return students if isinstance(students, list) else []


def render_overview(students: list[dict[str, Any]], selected_date: date) -> None:
    st.header("Staff overview")
    study_years = sorted({student["study_year"] for student in students if student["study_year"]})
    study_year = st.selectbox("Filter by year of study", ["All years", *study_years])
    query = f"/api/reports/overview?date={selected_date.isoformat()}"
    if study_year != "All years":
        query += f"&study_year={study_year}"
    report = api_request(query)
    groups = report["groups"]
    total = sum(group["total"] for group in groups)
    present = sum(group["present"] for group in groups)
    absent = sum(group["absent"] for group in groups)

    metric_columns = st.columns(3)
    metric_columns[0].metric("Total students", total)
    metric_columns[1].metric("Present today", present)
    metric_columns[2].metric("Absent today", absent)
    st.caption(
        f"Attendance for {report['date']} · {study_year}. "
        "Present includes late arrivals. Unmarked students are not counted as absent."
    )

    st.subheader("Attendance by academic year, branch, and year of study")
    if not groups:
        st.info("No students match this filter.")
        return

    for group in groups:
        title = (
            f"{group['academic_year']} · {group['branch']} · {group['study_year']}  "
            f"— Present {group['present']} · Absent {group['absent']} · "
            f"Total {group['total']}"
        )
        with st.expander(title):
            st.write(
                f"Excused: **{group['excused']}** · "
                f"Unmarked: **{group['unmarked']}**"
            )
            st.dataframe(
                [
                    {
                        "Name": student["name"],
                        "Roll number": student["roll_number"],
                        "Year of study": student["study_year"],
                        "Semester": student["semester"],
                        "Academic year": student["academic_year"],
                        "Branch": student["branch"],
                        "Phone": student["phone"] or "—",
                        "Status today": STATUS_LABELS.get(student["status"], student["status"]),
                        "Days present": student["attended_days"],
                    }
                    for student in group["students"]
                ],
                hide_index=True,
                use_container_width=True,
            )


def render_faculty_management() -> None:
    st.subheader("Faculty accounts")
    with st.form("create_faculty"):
        username = st.text_input("Faculty username", max_chars=80)
        password = st.text_input("Temporary password (12+ characters)", type="password", min_chars=12)
        submitted = st.form_submit_button("Create faculty account", type="primary")
    if submitted:
        try:
            api_request(
                "/api/users",
                "POST",
                {"username": username, "password": password, "role": "faculty"},
            )
            st.success(f"Faculty account created for {username}.")
        except RuntimeError as error:
            st.error(str(error))
    users = api_request("/api/users")
    st.dataframe(users, hide_index=True, use_container_width=True)


def render_student_registration() -> None:
    st.subheader("Register a student")
    with st.form("register_student", clear_on_submit=True):
        columns = st.columns(2)
        name = columns[0].text_input("Full name")
        roll_number = columns[1].text_input("Roll number")
        study_year = columns[0].text_input("Year of study", placeholder="Year 1")
        semester = columns[1].text_input("Semester", placeholder="Semester 1")
        branch = columns[0].text_input("Branch / department")
        academic_year = columns[1].text_input(
            "Academic year",
            value=backend.current_academic_year(),
            placeholder="2026-2027",
        )
        phone = st.text_input("Phone number")
        submitted = st.form_submit_button("Register student", type="primary")
    if submitted:
        try:
            result = api_request(
                "/api/students",
                "POST",
                {
                    "name": name,
                    "roll_number": roll_number,
                    "study_year": study_year,
                    "semester": semester,
                    "branch": branch,
                    "academic_year": academic_year,
                    "phone": phone,
                },
            )
            st.success(f"Registered {result['name']}.")
            st.rerun()
        except (KeyError, RuntimeError) as error:
            st.error(str(error))


def render_face_enrollment(students: list[dict[str, Any]]) -> None:
    st.subheader("Consent-based face enrollment")
    if not students:
        st.info("Register a student before enrolling a face.")
        return

    options = {
        f"{student['name']} ({student['roll_number']})": student
        for student in students
    }
    selected_label = st.selectbox("Student", list(options))
    student = options[selected_label]
    profiles = api_request("/api/face-profiles")
    enrolled_ids = {profile["student_id"] for profile in profiles}
    if student["id"] in enrolled_ids:
        st.warning("This student already has an enrolled face profile. New enrollment replaces it.")
        if st.button("Delete face photos and profile", key=f"delete_face_{student['id']}"):
            try:
                result = api_request(
                    f"/api/face-profiles/{student['id']}",
                    "DELETE",
                )
                st.success(result["message"])
                st.rerun()
            except RuntimeError as error:
                st.error(str(error))

    consent = st.checkbox(
        "I confirm the student or guardian has consented to capture and store three face photos.",
        key=f"face_consent_{student['id']}",
    )
    if consent:
        event = render_camera("enroll", f"enroll-camera-{student['id']}")
        event = process_face_event(event, "enroll")
        if event is not None:
            try:
                result = api_request(
                    f"/api/face-profiles/{student['id']}",
                    "POST",
                    {
                        "descriptor": event.get("descriptor"),
                        "images": event.get("images"),
                        "consent": True,
                    },
                )
                st.success(result["message"])
                st.rerun()
            except RuntimeError as error:
                st.error(str(error))
    else:
        st.info("Face capture is disabled until consent is confirmed.")


def render_attendance_management(students: list[dict[str, Any]], selected_date: date) -> None:
    st.subheader("Daily attendance and manual corrections")
    year_options = sorted({student["academic_year"] for student in students}, reverse=True)
    branch_options = sorted({student["branch"] for student in students})
    filters = st.columns(2)
    academic_year = filters[0].selectbox("Academic year", ["All academic years", *year_options])
    branch = filters[1].selectbox("Branch / department", ["All branches", *branch_options])
    cohort = [
        student for student in students
        if (academic_year == "All academic years" or student["academic_year"] == academic_year)
        and (branch == "All branches" or student["branch"] == branch)
    ]

    query = f"/api/summary?date={selected_date.isoformat()}"
    if academic_year != "All academic years":
        query += f"&academic_year={academic_year}"
    if branch != "All branches":
        query += f"&branch={branch}"
    summary = api_request(query)
    metrics = st.columns(5)
    metrics[0].metric("Present", summary["present"])
    metrics[1].metric("Late", summary["late"])
    metrics[2].metric("Absent", summary["absent"])
    metrics[3].metric("Excused", summary["excused"])
    metrics[4].metric("Unmarked", summary["unmarked"])

    attendance_query = f"/api/attendance?date={selected_date.isoformat()}"
    if academic_year != "All academic years":
        attendance_query += f"&academic_year={academic_year}"
    if branch != "All branches":
        attendance_query += f"&branch={branch}"
    records = api_request(attendance_query)
    existing = {record["student_id"]: record for record in records}

    if not cohort:
        st.info("No students match the selected academic year and branch.")
        return

    updates: list[dict[str, Any]] = []
    for student in cohort:
        record = existing.get(student["id"])
        columns = st.columns([2, 1, 1])
        columns[0].write(
            f"**{student['name']}**  \n{student['roll_number']} · "
            f"{student['study_year']} · {student['branch']}"
        )
        current_status = record["status"] if record else "unmarked"
        status = columns[1].selectbox(
            "Status",
            ATTENDANCE_STATUSES,
            index=ATTENDANCE_STATUSES.index(current_status),
            format_func=lambda value: STATUS_LABELS[value],
            key=f"attendance_status_{selected_date}_{student['id']}",
            label_visibility="collapsed",
        )
        notes = columns[2].text_input(
            "Notes",
            value=record.get("notes", "") if record else "",
            max_chars=500,
            key=f"attendance_notes_{selected_date}_{student['id']}",
            placeholder="Optional note",
            label_visibility="collapsed",
        )
        if status != "unmarked":
            updates.append(
                {"student_id": student["id"], "status": status, "notes": notes}
            )
        st.divider()

    if st.button("Save attendance corrections", type="primary"):
        if not updates:
            st.error("Choose at least one attendance status before saving.")
            return
        payload = {
            "date": selected_date.isoformat(),
            "academic_year": "" if academic_year == "All academic years" else academic_year,
            "branch": "" if branch == "All branches" else branch,
            "records": updates,
        }
        try:
            result = api_request("/api/attendance", "POST", payload)
            st.success(result["message"])
            st.rerun()
        except RuntimeError as error:
            st.error(str(error))


def match_face(descriptor: Any, profiles: list[dict[str, Any]], students: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(descriptor, list):
        return None
    student_by_id = {student["id"]: student for student in students}
    matches = []
    for profile in profiles:
        saved = profile["descriptor"]
        if len(saved) != len(descriptor):
            continue
        distance = math.sqrt(
            sum((float(observed) - float(expected)) ** 2 for observed, expected in zip(descriptor, saved))
        )
        student = student_by_id.get(profile["student_id"])
        if student:
            matches.append((distance, student))
    matches.sort(key=lambda match: match[0])
    if not matches or matches[0][0] > FACE_MATCH_THRESHOLD:
        return None
    if len(matches) > 1 and matches[1][0] - matches[0][0] < FACE_AMBIGUITY_MARGIN:
        return None
    return matches[0][1]


def render_automatic_attendance(students: list[dict[str, Any]], selected_date: date) -> None:
    st.subheader("Automatic face attendance")
    st.caption(
        "Start the camera scan to mark enrolled students present. "
        "Ambiguous or unmatched faces are not marked."
    )
    enabled = st.toggle("Enable automatic camera scan", key="automatic_scan_enabled")
    if not enabled:
        return
    profiles = api_request("/api/face-profiles")
    event = render_camera("scan", "automatic-attendance-camera")
    event = process_face_event(event, "scan")
    if event is None:
        return
    descriptors = event.get("descriptors")
    if not isinstance(descriptors, list):
        return
    if st.session_state.get("scan_date") != selected_date.isoformat():
        st.session_state.scanned_students = set()
        st.session_state.scan_date = selected_date.isoformat()
    marked = []
    errors = []
    for descriptor in descriptors:
        student = match_face(descriptor, profiles, students)
        if not student or student["id"] in st.session_state.scanned_students:
            continue
        try:
            result = api_request(
                "/api/attendance/automatic",
                "POST",
                {"student_id": student["id"], "date": selected_date.isoformat()},
            )
            st.session_state.scanned_students.add(student["id"])
            if not result["duplicate"]:
                marked.append(student["name"])
        except (KeyError, RuntimeError) as error:
            errors.append(f"{student['name']}: {error}")
    if marked:
        st.success(f"Marked present: {', '.join(marked)}")
    if errors:
        st.error("Could not mark attendance: " + "; ".join(errors))


def render_history(students: list[dict[str, Any]]) -> None:
    st.subheader("Student attendance history")
    if not students:
        st.info("No students are registered.")
        return
    choices = {
        f"{student['name']} ({student['roll_number']})": student
        for student in students
    }
    selected = st.selectbox("Student history", list(choices), key="history_student")
    student = choices[selected]
    result = api_request(f"/api/students/{student['id']}/history")
    st.write(
        f"**{result['attended_days']} days present** out of "
        f"{result['eligible_days']} eligible recorded days · "
        f"{result['percentage']}% attendance"
    )
    st.dataframe(
        [
            {
                "Date": record["date"],
                "Academic year": record["academic_year"],
                "Branch": record["branch"],
                "Status": STATUS_LABELS.get(record["status"], record["status"]),
                "Notes": record["notes"] or "—",
                "Source": record["source"],
                "Last updated": record["updated_at"],
            }
            for record in result["records"]
        ],
        hide_index=True,
        use_container_width=True,
    )


def main() -> None:
    initialize_state()
    st.title("Student Attendance System")
    st.caption("Academic management · Attendance overview and staff tools")

    user = st.session_state.get("current_user")
    if user:
        with st.sidebar:
            st.write(f"Signed in as **{user['username']}** ({user['role']})")
            selected_date = st.date_input("Attendance / report date", value=date.today())
            if st.button("Log out"):
                st.session_state.api_client = backend.app.test_client()
                st.session_state.pop("current_user", None)
                st.session_state.scanned_students = set()
                st.rerun()
        try:
            students = load_students()
            overview_tab, management_tab = st.tabs(["Overview", "Manage students & attendance"])
            with overview_tab:
                render_overview(students, selected_date)
            with management_tab:
                if user["role"] == "admin":
                    render_faculty_management()
                register_tab, faces_tab, daily_tab, face_scan_tab, history_tab = st.tabs(
                    [
                        "Register student",
                        "Face enrollment",
                        "Daily attendance",
                        "Automatic face attendance",
                        "Student history",
                    ]
                )
                with register_tab:
                    render_student_registration()
                    st.dataframe(students, hide_index=True, use_container_width=True)
                with faces_tab:
                    render_face_enrollment(students)
                with daily_tab:
                    render_attendance_management(students, selected_date)
                with face_scan_tab:
                    render_automatic_attendance(students, selected_date)
                with history_tab:
                    render_history(students)
        except RuntimeError as error:
            st.error(f"Could not load the attendance dashboard: {error}")
        return

    sign_in_tab, student_checkin_tab = st.tabs(["Staff sign in", "Student check-in"])
    with sign_in_tab:
        if not render_auth():
            st.info("Staff sign-in is required to view student and attendance records.")
    with student_checkin_tab:
        render_student_checkin()


if __name__ == "__main__":
    main()
