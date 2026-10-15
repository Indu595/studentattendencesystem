const authPanel = document.getElementById('authPanel');
const authForm = document.getElementById('authForm');
const authTitle = document.getElementById('authTitle');
const authHelp = document.getElementById('authHelp');
const authMessage = document.getElementById('authMessage');
const authSubmitBtn = document.getElementById('authSubmitBtn');
const homeActions = document.getElementById('homeActions');
const openStaffBtn = document.getElementById('openStaffBtn');
const backFromStaffBtn = document.getElementById('backFromStaffBtn');
const studentPortal = document.getElementById('studentPortal');
const studentCheckinForm = document.getElementById('studentCheckinForm');
const studentCameraVideo = document.getElementById('studentCameraVideo');
const studentCameraStatus = document.getElementById('studentCameraStatus');
const studentCheckinBtn = document.getElementById('studentCheckinBtn');
const studentCheckinMessage = document.getElementById('studentCheckinMessage');
const dashboard = document.getElementById('dashboard');
const userBar = document.getElementById('userBar');
const currentUserLabel = document.getElementById('currentUserLabel');
const logoutBtn = document.getElementById('logoutBtn');
const returnDashboardBtn = document.getElementById('returnDashboardBtn');
const backToHomeBtn = document.getElementById('backToHomeBtn');
const roleNotice = document.getElementById('roleNotice');
const staffOverview = document.getElementById('staffOverview');
const managementPanel = document.getElementById('managementPanel');
const overviewTabBtn = document.getElementById('overviewTabBtn');
const managementTabBtn = document.getElementById('managementTabBtn');
const overviewStudyYear = document.getElementById('overviewStudyYear');
const overviewTableBody = document.getElementById('overviewTableBody');
const overviewMeta = document.getElementById('overviewMeta');
const overviewTotalCount = document.getElementById('overviewTotalCount');
const overviewPresentCount = document.getElementById('overviewPresentCount');
const overviewAbsentCount = document.getElementById('overviewAbsentCount');
const facultyPanel = document.getElementById('facultyPanel');
const facultyForm = document.getElementById('facultyForm');
const facultyTableBody = document.getElementById('facultyTableBody');
const attendanceDateInput = document.getElementById('attendanceDate');
const reportAcademicYear = document.getElementById('reportAcademicYear');
const reportBranch = document.getElementById('reportBranch');
const studentForm = document.getElementById('studentForm');
const attendanceTableBody = document.getElementById('attendanceTableBody');
const saveAttendanceBtn = document.getElementById('saveAttendanceBtn');
const reportMeta = document.getElementById('reportMeta');
const historyStudent = document.getElementById('historyStudent');
const historySummary = document.getElementById('historySummary');
const historyTableBody = document.getElementById('historyTableBody');
const loadHistoryBtn = document.getElementById('loadHistoryBtn');
const cameraVideo = document.getElementById('cameraVideo');
const cameraStatus = document.getElementById('cameraStatus');
const startCameraBtn = document.getElementById('startCameraBtn');
const stopCameraBtn = document.getElementById('stopCameraBtn');
const enrollmentVideo = document.getElementById('enrollmentVideo');
const enrollmentStatus = document.getElementById('enrollmentStatus');
const startEnrollmentCameraBtn = document.getElementById('startEnrollmentCameraBtn');
const stopEnrollmentCameraBtn = document.getElementById('stopEnrollmentCameraBtn');
const enrollStudentSelect = document.getElementById('enrollStudent');
const faceConsentCheckbox = document.getElementById('faceConsent');
const enrollFaceBtn = document.getElementById('enrollFaceBtn');
const removeFaceBtn = document.getElementById('removeFaceBtn');
const autoScanBtn = document.getElementById('autoScanBtn');
const appMessage = document.getElementById('appMessage');

const summaryEls = {
    present: document.getElementById('presentCount'),
    late: document.getElementById('lateCount'),
    excused: document.getElementById('excusedCount'),
    absent: document.getElementById('absentCount'),
    unmarked: document.getElementById('unmarkedCount'),
    percentage: document.getElementById('attendancePercentage'),
};

const FACE_MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.15/model';
const FACE_MATCH_THRESHOLD = 0.43;
const FACE_AMBIGUITY_MARGIN = 0.05;

const state = {
    user: null,
    setupRequired: false,
    students: [],
    attendanceMap: new Map(),
    overviewGroups: [],
    expandedOverviewGroup: null,
    faceProfiles: new Map(),
    cameraStream: null,
    enrollmentCameraStream: null,
    studentCameraStream: null,
    faceModelsLoaded: false,
    autoScanning: false,
    scanBusy: false,
    scanTimer: null,
    markedStudentIds: new Set(),
    toastTimer: null,
    view: 'home',
};

function todayISO() {
    const now = new Date();
    const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 10);
}

function defaultAcademicYear() {
    const now = new Date();
    const startYear = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
    return `${startYear}-${startYear + 1}`;
}

function showMessage(message, isError = false) {
    appMessage.textContent = message;
    appMessage.classList.toggle('error', isError);
    appMessage.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { appMessage.hidden = true; }, 5000);
}

function setCameraStatus(message, isError = false) {
    cameraStatus.textContent = message;
    cameraStatus.classList.toggle('error', isError);
}

async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            ...(options.body ? { 'Content-Type': 'application/json' } : {}),
            ...options.headers,
        },
    });
    const result = response.status === 204 ? {} : await response.json();
    if (!response.ok) {
        if (response.status === 401 && state.user) {
            state.user = null;
            await refreshAuthState();
        }
        throw new Error(result.error || 'The request could not be completed.');
    }
    return result;
}

function resetAuthForm(isSetup) {
    authForm.reset();
    authMessage.textContent = '';
    authTitle.textContent = isSetup ? 'Create the first administrator' : 'Staff login';
    authHelp.textContent = isSetup
        ? 'Create the administrator account to secure this attendance system. Use a unique password of at least 12 characters.'
        : 'Sign in with your administrator or faculty account.';
    authSubmitBtn.textContent = isSetup ? 'Create administrator' : 'Log in';
    document.getElementById('authPassword').autocomplete = isSetup ? 'new-password' : 'current-password';
    document.getElementById('authPassword').minLength = isSetup ? 12 : 1;
}

function setPublicView(view) {
    state.view = view;
    const isSignedIn = Boolean(state.user);
    homeActions.hidden = isSignedIn;
    userBar.hidden = !isSignedIn;
    returnDashboardBtn.hidden = !isSignedIn || view === 'dashboard';
    authPanel.hidden = isSignedIn || view !== 'staff';
    studentPortal.hidden = view === 'staff' || (isSignedIn && view === 'dashboard');
    dashboard.hidden = !isSignedIn || view !== 'dashboard';
}

function setDashboardSection(section) {
    const showOverview = section === 'overview';
    staffOverview.hidden = !showOverview;
    managementPanel.hidden = showOverview;
    overviewTabBtn.classList.toggle('active', showOverview);
    overviewTabBtn.setAttribute('aria-pressed', String(showOverview));
    managementTabBtn.classList.toggle('active', !showOverview);
    managementTabBtn.setAttribute('aria-pressed', String(!showOverview));
}

async function refreshAuthState() {
    try {
        const result = await apiRequest('/api/auth/status');
        state.user = result.user;
        state.setupRequired = result.setup_required;
        userBar.hidden = !state.user;
        if (!state.user) {
            resetAuthForm(state.setupRequired);
            stopCamera();
            setPublicView(state.view);
            return;
        }
        setPublicView('dashboard');
        setDashboardSection('overview');
        currentUserLabel.textContent = `${state.user.username} (${state.user.role})`;
        roleNotice.textContent = state.user.role === 'admin'
            ? 'Administrator access: manage faculty accounts, students, and attendance.'
            : 'Faculty access: register students, enroll consented faces, and manage attendance.';
        facultyPanel.hidden = state.user.role !== 'admin';
        if (state.user.role === 'admin') await loadFaculty();
        await loadStudents();
    } catch (error) {
        authMessage.textContent = error.message;
    }
}

async function loadFaculty() {
    try {
        const users = await apiRequest('/api/users');
        facultyTableBody.replaceChildren();
        users.forEach((user) => {
            const row = document.createElement('tr');
            [user.username, user.role, user.created_at].forEach((value) => {
                const cell = document.createElement('td');
                cell.textContent = value;
                row.appendChild(cell);
            });
            facultyTableBody.appendChild(row);
        });
    } catch (error) {
        showMessage(error.message, true);
    }
}

function populateStudentSelect(select) {
    const selectedId = select.value;
    select.replaceChildren(new Option('Choose a student', ''));
    state.students.forEach((student) => {
        select.add(new Option(`${student.name} (${student.roll_number})`, student.id));
    });
    if (state.students.some((student) => String(student.id) === selectedId)) {
        select.value = selectedId;
    }
}

function populateReportFilters() {
    const selectedStudyYear = overviewStudyYear.value;
    const studyYears = [...new Set(state.students.map((student) => student.study_year).filter(Boolean))].sort();
    overviewStudyYear.replaceChildren(new Option('All years of study', ''));
    studyYears.forEach((year) => overviewStudyYear.add(new Option(year, year)));
    if (studyYears.includes(selectedStudyYear)) overviewStudyYear.value = selectedStudyYear;

    const years = [...new Set([
        defaultAcademicYear(),
        ...state.students.map((student) => student.academic_year),
    ])].filter(Boolean).sort().reverse();
    const selectedYear = reportAcademicYear.options.length
        ? reportAcademicYear.value
        : defaultAcademicYear();
    reportAcademicYear.replaceChildren(new Option('All academic years', ''));
    years.forEach((year) => reportAcademicYear.add(new Option(year, year)));
    reportAcademicYear.value = years.includes(selectedYear) ? selectedYear : '';

    const branches = [...new Set(state.students.map((student) => student.branch).filter(Boolean))].sort();
    const selectedBranch = reportBranch.value || '';
    reportBranch.replaceChildren(new Option('All branches', ''));
    branches.forEach((branch) => reportBranch.add(new Option(branch, branch)));
    if (branches.includes(selectedBranch)) reportBranch.value = selectedBranch;
}

async function loadStudents() {
    const students = await apiRequest('/api/students');
    state.students = students;
    populateReportFilters();
    populateStudentSelect(enrollStudentSelect);
    populateStudentSelect(historyStudent);
    renderAttendanceTable();
    await loadFaceProfiles();
    await Promise.all([loadDailyReport(), loadStaffOverview()]);
}

async function loadFaceProfiles() {
    const profiles = await apiRequest('/api/face-profiles');
    state.faceProfiles = new Map(profiles.map((profile) => [String(profile.student_id), profile.descriptor]));
    updateEnrollmentControls();
}

async function loadDailyReport() {
    const selectedDate = attendanceDateInput.value || todayISO();
    const year = reportAcademicYear.value;
    const branch = reportBranch.value;
    const query = new URLSearchParams({ date: selectedDate });
    if (year) query.set('academic_year', year);
    if (branch) query.set('branch', branch);
    const report = await apiRequest(`/api/reports/daily?${query}`);
    const summary = report.summary;
    state.attendanceMap = new Map(report.records.map((record) => [record.student_id, record]));
    summaryEls.present.textContent = summary.present;
    summaryEls.late.textContent = summary.late;
    summaryEls.excused.textContent = summary.excused;
    summaryEls.absent.textContent = summary.absent;
    summaryEls.unmarked.textContent = summary.unmarked;
    summaryEls.percentage.textContent = `${summary.percentage}%`;
    reportMeta.textContent = `${summary.marked} of ${summary.total_students} students recorded for ${summary.date} · ${summary.academic_year} · ${summary.branch}; percentage is present + late divided by students in this cohort.`;
    renderAttendanceTable();
}

async function loadStaffOverview() {
    const selectedDate = attendanceDateInput.value || todayISO();
    const query = new URLSearchParams({ date: selectedDate });
    if (overviewStudyYear.value) query.set('study_year', overviewStudyYear.value);
    const result = await apiRequest(`/api/reports/overview?${query}`);
    state.overviewGroups = result.groups;
    if (!state.overviewGroups.some((group) =>
        `${group.academic_year}\u0000${group.branch}\u0000${group.study_year}` === state.expandedOverviewGroup
    )) {
        state.expandedOverviewGroup = null;
    }
    overviewTotalCount.textContent = result.summary.total_students;
    overviewPresentCount.textContent = result.summary.present;
    overviewAbsentCount.textContent = result.summary.absent;
    const studyYearLabel = result.study_year === 'all' ? 'all years of study' : result.study_year;
    overviewMeta.textContent = `${result.date} · ${studyYearLabel} · Present includes late arrivals. Unmarked and excused students are shown separately; unmarked students are not counted as absent. Select a year/branch row to view student details.`;
    renderStaffOverview();
}

function appendCell(row, value) {
    const cell = document.createElement('td');
    cell.textContent = value;
    row.appendChild(cell);
    return cell;
}

function renderStudentDetails(students) {
    const wrapper = document.createElement('div');
    wrapper.className = 'table-wrap student-detail-wrap';
    const table = document.createElement('table');
    const head = document.createElement('thead');
    const headerRow = document.createElement('tr');
    [
        'Name', 'Roll number', 'Year of study', 'Semester', 'Branch',
        'Academic year', 'Phone', 'Status today', 'Days present',
    ].forEach((label) => appendCell(headerRow, label));
    head.appendChild(headerRow);
    table.appendChild(head);

    const body = document.createElement('tbody');
    students.forEach((student) => {
        const row = document.createElement('tr');
        [
            student.name,
            student.roll_number,
            student.study_year,
            student.semester,
            student.branch,
            student.academic_year,
            student.phone || '—',
            student.status === 'unmarked'
                ? 'Not marked'
                : student.status.charAt(0).toUpperCase() + student.status.slice(1),
            student.attended_days,
        ].forEach((value) => appendCell(row, value));
        body.appendChild(row);
    });
    table.appendChild(body);
    wrapper.appendChild(table);
    return wrapper;
}

function renderStaffOverview() {
    overviewTableBody.replaceChildren();
    state.overviewGroups.forEach((group, index) => {
        const groupKey = `${group.academic_year}\u0000${group.branch}\u0000${group.study_year}`;
        const expanded = groupKey === state.expandedOverviewGroup;
        const row = document.createElement('tr');
        row.className = 'overview-group-row';
        row.tabIndex = 0;
        row.setAttribute('aria-expanded', String(expanded));
        appendCell(row, group.academic_year);
        appendCell(row, group.branch);
        appendCell(row, group.study_year);
        appendCell(row, group.present);
        appendCell(row, group.absent);
        appendCell(row, group.excused);
        appendCell(row, group.unmarked);
        appendCell(row, group.total);

        const toggleGroup = () => {
            state.expandedOverviewGroup = expanded ? null : groupKey;
            renderStaffOverview();
        };
        row.addEventListener('click', toggleGroup);
        row.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggleGroup();
            }
        });
        overviewTableBody.appendChild(row);

        if (expanded) {
            const detailsRow = document.createElement('tr');
            detailsRow.className = 'overview-details-row';
            const detailsCell = document.createElement('td');
            detailsCell.colSpan = 8;
            detailsCell.appendChild(renderStudentDetails(group.students));
            detailsRow.appendChild(detailsCell);
            overviewTableBody.appendChild(detailsRow);
        }
    });

    if (!state.overviewGroups.length) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 8;
        cell.className = 'empty-state';
        cell.textContent = 'No students have been registered yet.';
        row.appendChild(cell);
        overviewTableBody.appendChild(row);
    }
}

function createAttendanceRow(student, existing) {
    const row = document.createElement('tr');
    const values = [
        student.name,
        student.roll_number,
        student.academic_year,
        student.branch,
        student.study_year,
        student.semester,
    ];
    values.forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
    });

    const statusCell = document.createElement('td');
    const statusSelect = document.createElement('select');
    statusSelect.className = 'status-select';
    statusSelect.dataset.studentId = student.id;
    [
        ['unmarked', 'Not marked'],
        ['present', 'Present'],
        ['late', 'Late'],
        ['excused', 'Excused'],
        ['absent', 'Absent'],
    ].forEach(([value, label]) => {
        const option = new Option(label, value);
        option.selected = (existing && existing.status === value)
            || (!existing && value === 'unmarked');
        statusSelect.add(option);
    });
    statusCell.appendChild(statusSelect);
    row.appendChild(statusCell);

    const notesCell = document.createElement('td');
    const notesInput = document.createElement('input');
    notesInput.className = 'notes-input';
    notesInput.type = 'text';
    notesInput.maxLength = 500;
    notesInput.dataset.notesId = student.id;
    notesInput.value = existing ? existing.notes || '' : '';
    notesInput.placeholder = 'Optional note';
    notesCell.appendChild(notesInput);
    row.appendChild(notesCell);

    const recordedByCell = document.createElement('td');
    recordedByCell.textContent = existing
        ? `${existing.marked_by || 'Staff'}${existing.source === 'face' ? ' (webcam)' : ''}`
        : '—';
    row.appendChild(recordedByCell);
    return row;
}

function renderAttendanceTable() {
    attendanceTableBody.replaceChildren();
    const filteredStudents = state.students.filter((student) =>
        (!reportAcademicYear.value || student.academic_year === reportAcademicYear.value)
        && (!reportBranch.value || student.branch === reportBranch.value)
    );
    filteredStudents.forEach((student) => {
        attendanceTableBody.appendChild(
            createAttendanceRow(student, state.attendanceMap.get(student.id))
        );
    });
}

async function loadHistory() {
    const studentId = historyStudent.value;
    if (!studentId) {
        showMessage('Choose a student to view their attendance history.', true);
        return;
    }
    try {
        const result = await apiRequest(`/api/students/${studentId}/history`);
        historySummary.textContent = `${result.student.name} · ${result.student.study_year} · ${result.student.semester}: ${result.attended_days} attended of ${result.eligible_days} eligible recorded days (${result.percentage}%). Excused days are excluded from the percentage.`;
        historyTableBody.replaceChildren();
        result.records.forEach((record) => {
            const row = document.createElement('tr');
            [
                record.date,
                record.academic_year,
                record.branch,
                record.status,
                record.notes || '—',
                record.source === 'face' ? 'Webcam recognition' : 'Manual',
                record.updated_at || '—',
            ].forEach((value) => {
                const cell = document.createElement('td');
                cell.textContent = value;
                row.appendChild(cell);
            });
            historyTableBody.appendChild(row);
        });
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function loadFaceModels() {
    if (state.faceModelsLoaded) return;
    if (!window.faceapi) {
        throw new Error('Face recognition library did not load. Check the internet connection and reload.');
    }
    await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(FACE_MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(FACE_MODEL_URL),
        faceapi.nets.faceRecognitionNet.loadFromUri(FACE_MODEL_URL),
    ]);
    state.faceModelsLoaded = true;
}

async function startCamera() {
    try {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error('Camera access requires localhost or HTTPS in a supported browser.');
        }
        setCameraStatus('Loading face recognition models…');
        await loadFaceModels();
        state.cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user' },
            audio: false,
        });
        cameraVideo.srcObject = state.cameraStream;
        await cameraVideo.play();
        startCameraBtn.disabled = true;
        stopCameraBtn.disabled = false;
        setCameraStatus('Camera ready. Enroll a consented student or start automatic attendance.');
        updateEnrollmentControls();
    } catch (error) {
        stopCamera();
        const message = error.name === 'NotAllowedError'
            ? 'Camera access denied. Allow camera access in browser settings and try again.'
            : error.name === 'NotFoundError'
                ? 'No camera was found on this device.'
                : error.message || 'Could not start the camera.';
        setCameraStatus(message, true);
    }
}

function stopCamera() {
    state.autoScanning = false;
    state.scanBusy = false;
    clearTimeout(state.scanTimer);
    state.scanTimer = null;
    autoScanBtn.textContent = 'Start Automatic Attendance';
    if (state.cameraStream) {
        state.cameraStream.getTracks().forEach((track) => track.stop());
    }
    state.cameraStream = null;
    cameraVideo.srcObject = null;
    startCameraBtn.disabled = false;
    stopCameraBtn.disabled = true;
    if (cameraStatus) setCameraStatus('Camera stopped.');
    stopEnrollmentCamera();
    updateEnrollmentControls();
}

async function startEnrollmentCamera() {
    try {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error('Camera access requires localhost or HTTPS in a supported browser.');
        }
        enrollmentStatus.textContent = 'Loading face recognition models…';
        await loadFaceModels();
        state.enrollmentCameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user' },
            audio: false,
        });
        enrollmentVideo.srcObject = state.enrollmentCameraStream;
        await enrollmentVideo.play();
        startEnrollmentCameraBtn.disabled = true;
        stopEnrollmentCameraBtn.disabled = false;
        enrollmentStatus.textContent = 'Enrollment camera ready. Select a student and confirm consent.';
        updateEnrollmentControls();
    } catch (error) {
        stopEnrollmentCamera();
        enrollmentStatus.textContent = error.message || 'Could not start the enrollment camera.';
        enrollmentStatus.classList.add('error');
    }
}

function stopEnrollmentCamera() {
    if (state.enrollmentCameraStream) {
        state.enrollmentCameraStream.getTracks().forEach((track) => track.stop());
    }
    state.enrollmentCameraStream = null;
    enrollmentVideo.srcObject = null;
    startEnrollmentCameraBtn.disabled = false;
    stopEnrollmentCameraBtn.disabled = true;
    if (enrollmentStatus) enrollmentStatus.textContent = 'Enrollment camera is off.';
    updateEnrollmentControls();
}

function updateEnrollmentControls() {
    const hasStudent = Boolean(enrollStudentSelect.value);
    const hasProfile = hasStudent && state.faceProfiles.has(enrollStudentSelect.value);
    const enrollmentCameraReady = Boolean(state.enrollmentCameraStream) && state.faceModelsLoaded;
    const attendanceCameraReady = Boolean(state.cameraStream) && state.faceModelsLoaded;
    enrollFaceBtn.disabled = !enrollmentCameraReady || !hasStudent || !faceConsentCheckbox.checked;
    removeFaceBtn.disabled = !hasProfile;
    autoScanBtn.disabled = !attendanceCameraReady || state.faceProfiles.size === 0;
}

async function getFaceDetection(video = cameraVideo) {
    if (!video.videoWidth || !video.videoHeight) {
        throw new Error('Wait until the camera preview is ready.');
    }
    const detections = await faceapi
        .detectAllFaces(video, new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 }))
        .withFaceLandmarks()
        .withFaceDescriptors();
    if (detections.length !== 1) {
        throw new Error(detections.length === 0
            ? 'No face detected. Face the camera in good lighting.'
            : 'More than one face detected. Ensure only one student is in view.');
    }
    return detections[0];
}

function stopStudentCamera() {
    if (state.studentCameraStream) {
        state.studentCameraStream.getTracks().forEach((track) => track.stop());
    }
    state.studentCameraStream = null;
    studentCameraVideo.srcObject = null;
    studentCameraStatus.textContent = 'Camera is off.';
}

async function submitStudentCheckin(event) {
    event.preventDefault();
    const rollNumber = document.getElementById('studentRollInput').value.trim();
    studentCheckinBtn.disabled = true;
    studentCheckinMessage.textContent = '';
    studentCameraStatus.textContent = 'Loading face recognition model…';
    try {
        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error('Camera access requires localhost or HTTPS in a supported browser.');
        }
        await loadFaceModels();
        state.studentCameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user' },
            audio: false,
        });
        studentCameraVideo.srcObject = state.studentCameraStream;
        await studentCameraVideo.play();
        studentCameraStatus.textContent = 'Camera ready. Look directly at the camera.';
        await new Promise((resolve) => setTimeout(resolve, 500));
        const detection = await getFaceDetection(studentCameraVideo);
        const result = await apiRequest('/api/student/check-in', {
            method: 'POST',
            body: JSON.stringify({
                roll_number: rollNumber,
                descriptor: Array.from(detection.descriptor),
            }),
        });
        studentCheckinMessage.textContent = `${result.message} ${result.academic_year} · ${result.branch} · ${result.study_year} · ${result.semester}.`;
        studentCheckinMessage.classList.remove('error');
        studentCameraStatus.textContent = 'Check-in complete.';
    } catch (error) {
        studentCheckinMessage.textContent = error.message || 'Check-in could not be completed.';
        studentCheckinMessage.classList.add('error');
        studentCameraStatus.textContent = 'Check-in failed.';
    } finally {
        stopStudentCamera();
        studentCheckinBtn.disabled = false;
    }
}

function captureJpeg(video = cameraVideo) {
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 960 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Could not capture an image from the camera.');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = canvas.toDataURL('image/jpeg', 0.78);
    if (image.length > 1_450_000) {
        throw new Error('Captured image is too large. Move closer to the camera and try again.');
    }
    return image;
}

async function captureEnrollment() {
    const studentId = enrollStudentSelect.value;
    const student = state.students.find((item) => String(item.id) === studentId);
    if (!student || !faceConsentCheckbox.checked) {
        enrollmentStatus.textContent = 'Choose a student and confirm consent before enrollment.';
        enrollmentStatus.classList.add('error');
        return;
    }
    if (state.faceProfiles.has(studentId)
        && !window.confirm(`Replace stored face photos and profile for ${student.name}?`)) return;

    enrollFaceBtn.disabled = true;
    enrollmentStatus.textContent = `Capturing three face photos for ${student.name}…`;
    try {
        const descriptors = [];
        const images = [];
        for (let index = 0; index < 3; index += 1) {
            const detection = await getFaceDetection(enrollmentVideo);
            descriptors.push(Array.from(detection.descriptor));
            images.push(captureJpeg(enrollmentVideo));
            if (index < 2) await new Promise((resolve) => setTimeout(resolve, 500));
        }
        const descriptor = descriptors[0].map((_, index) =>
            descriptors.reduce((sum, sample) => sum + sample[index], 0) / descriptors.length
        );
        const result = await apiRequest(`/api/face-profiles/${studentId}`, {
            method: 'POST',
            body: JSON.stringify({ descriptor, images, consent: true }),
        });
        await loadFaceProfiles();
        enrollmentStatus.textContent = `${result.message} Stored for ${student.name}.`;
        enrollmentStatus.classList.remove('error');
        faceConsentCheckbox.checked = false;
        updateEnrollmentControls();
    } catch (error) {
        enrollmentStatus.textContent = error.message || 'Face enrollment failed.';
        enrollmentStatus.classList.add('error');
    } finally {
        updateEnrollmentControls();
    }
}

async function removeFaceEnrollment() {
    const studentId = enrollStudentSelect.value;
    const student = state.students.find((item) => String(item.id) === studentId);
    if (!student || !state.faceProfiles.has(studentId)) return;
    if (!window.confirm(`Permanently delete ${student.name}'s stored face photos and recognition profile?`)) return;
    try {
        const result = await apiRequest(`/api/face-profiles/${studentId}`, { method: 'DELETE' });
        await loadFaceProfiles();
        enrollmentStatus.textContent = result.message;
        enrollmentStatus.classList.remove('error');
    } catch (error) {
        enrollmentStatus.textContent = error.message;
        enrollmentStatus.classList.add('error');
    }
}

function findMatchingStudent(descriptor) {
    const matches = [];
    state.faceProfiles.forEach((profile, studentId) => {
        if (!Array.isArray(profile) || profile.length !== descriptor.length) return;
        const student = state.students.find((item) => String(item.id) === studentId);
        if (student) {
            matches.push({
                student,
                distance: faceapi.euclideanDistance(descriptor, profile),
            });
        }
    });
    matches.sort((first, second) => first.distance - second.distance);
    if (!matches.length || matches[0].distance > FACE_MATCH_THRESHOLD) return null;
    if (matches.length > 1 && matches[1].distance - matches[0].distance < FACE_AMBIGUITY_MARGIN) {
        throw new Error('The face match is ambiguous. Try again or correct attendance manually.');
    }
    return matches[0].student;
}

async function scanAndMarkAttendance() {
    if (!state.cameraStream || state.scanBusy) return;
    state.scanBusy = true;
    try {
        if (!cameraVideo.videoWidth || !cameraVideo.videoHeight) {
            throw new Error('Wait until the camera preview is ready.');
        }
        const detections = await faceapi
            .detectAllFaces(
                cameraVideo,
                new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 }),
            )
            .withFaceLandmarks()
            .withFaceDescriptors();
        if (!detections.length) {
            if (!state.autoScanning) setCameraStatus('No faces detected. Ensure students are visible.', true);
            return;
        }

        const selectedDate = attendanceDateInput.value || todayISO();
        const matchedStudents = new Map();
        let ambiguousFaces = 0;
        let unmatchedFaces = 0;
        detections.forEach((detection) => {
            try {
                const student = findMatchingStudent(Array.from(detection.descriptor));
                if (student) matchedStudents.set(student.id, student);
                else unmatchedFaces += 1;
            } catch (error) {
                if (!error.message.includes('ambiguous')) throw error;
                ambiguousFaces += 1;
            }
        });

        if (!matchedStudents.size) {
            setCameraStatus(
                `No enrolled students matched${ambiguousFaces ? `; ${ambiguousFaces} face match(es) were ambiguous` : ''}.`,
                true,
            );
            return;
        }

        const markedNames = [];
        const recordedNames = [];
        const failedNames = [];
        let attendanceChanged = false;
        for (const student of matchedStudents.values()) {
            if (state.markedStudentIds.has(student.id)) continue;
            try {
                const result = await apiRequest('/api/attendance/automatic', {
                    method: 'POST',
                    body: JSON.stringify({ student_id: student.id, date: selectedDate }),
                });
                state.markedStudentIds.add(student.id);
                if (result.duplicate) {
                    recordedNames.push(`${student.name} (${result.status})`);
                } else {
                    markedNames.push(student.name);
                    attendanceChanged = true;
                }
            } catch (error) {
                failedNames.push(`${student.name}: ${error.message}`);
            }
        }

        if (attendanceChanged) {
            await Promise.all([loadDailyReport(), loadStaffOverview()]);
        }

        const messages = [];
        if (markedNames.length) messages.push(`Marked: ${markedNames.join(', ')}`);
        if (recordedNames.length) messages.push(`Already recorded: ${recordedNames.join(', ')}`);
        if (unmatchedFaces) messages.push(`${unmatchedFaces} unmatched face(s)`);
        if (ambiguousFaces) messages.push(`${ambiguousFaces} ambiguous face match(es)`);
        if (failedNames.length) messages.push(`Could not mark ${failedNames.join('; ')}`);
        if (messages.length) {
            setCameraStatus(messages.join('. '), failedNames.length > 0);
        }
    } catch (error) {
        setCameraStatus(error.message || 'Face recognition failed.', true);
    } finally {
        state.scanBusy = false;
        if (state.autoScanning && state.cameraStream) {
            state.scanTimer = setTimeout(scanAndMarkAttendance, 1200);
        }
    }
}

function toggleAutomaticAttendance() {
    if (state.autoScanning) {
        state.autoScanning = false;
        autoScanBtn.textContent = 'Start Automatic Attendance';
        setCameraStatus('Automatic attendance stopped.');
        return;
    }
    if (!state.faceProfiles.size) {
        setCameraStatus('Enroll at least one consented student before automatic attendance.', true);
        return;
    }
    state.autoScanning = true;
    autoScanBtn.textContent = 'Stop Automatic Attendance';
    setCameraStatus('Automatic attendance is scanning all visible faces. Each uniquely matched student is marked once per date.');
    scanAndMarkAttendance();
}

authForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    authSubmitBtn.disabled = true;
    authMessage.textContent = '';
    const formData = new FormData(authForm);
    const url = state.setupRequired ? '/api/auth/setup' : '/api/auth/login';
    try {
        await apiRequest(url, {
            method: 'POST',
            body: JSON.stringify(Object.fromEntries(formData.entries())),
        });
        await refreshAuthState();
    } catch (error) {
        authMessage.textContent = error.message;
    } finally {
        authSubmitBtn.disabled = false;
    }
});

logoutBtn.addEventListener('click', async () => {
    stopCamera();
    try {
        await apiRequest('/api/auth/logout', { method: 'POST' });
        state.user = null;
        state.students = [];
        state.faceProfiles.clear();
        state.view = 'home';
        await refreshAuthState();
    } catch (error) {
        showMessage(error.message, true);
    }
});

backToHomeBtn.addEventListener('click', () => setPublicView('home'));
returnDashboardBtn.addEventListener('click', () => setPublicView('dashboard'));
openStaffBtn.addEventListener('click', () => setPublicView('staff'));
backFromStaffBtn.addEventListener('click', () => setPublicView('home'));

facultyForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        const formData = new FormData(facultyForm);
        const result = await apiRequest('/api/users', {
            method: 'POST',
            body: JSON.stringify({ ...Object.fromEntries(formData.entries()), role: 'faculty' }),
        });
        facultyForm.reset();
        await loadFaculty();
        showMessage(`Faculty account created for ${result.username}.`);
    } catch (error) {
        showMessage(error.message, true);
    }
});

studentForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        const formData = new FormData(studentForm);
        const result = await apiRequest('/api/students', {
            method: 'POST',
            body: JSON.stringify(Object.fromEntries(formData.entries())),
        });
        studentForm.reset();
        await loadStudents();
        showMessage(`Registered student ${result.name}. Enroll their face with consent to enable recognition.`);
    } catch (error) {
        showMessage(error.message, true);
    }
});

studentCheckinForm.addEventListener('submit', submitStudentCheckin);

saveAttendanceBtn.addEventListener('click', async () => {
    const filteredStudents = state.students.filter((student) =>
        (!reportAcademicYear.value || student.academic_year === reportAcademicYear.value)
        && (!reportBranch.value || student.branch === reportBranch.value)
    );
    const records = filteredStudents.flatMap((student) => {
        const select = document.querySelector(`select[data-student-id="${student.id}"]`);
        const notes = document.querySelector(`input[data-notes-id="${student.id}"]`);
        return select && select.value !== 'unmarked'
            ? [{ student_id: student.id, status: select.value, notes: notes ? notes.value : '' }]
            : [];
    });
    if (!records.length) {
        showMessage('No attendance statuses to save.', true);
        return;
    }
    try {
        const result = await apiRequest('/api/attendance', {
            method: 'POST',
            body: JSON.stringify({
                date: attendanceDateInput.value || todayISO(),
                academic_year: reportAcademicYear.value,
                branch: reportBranch.value,
                records,
            }),
        });
        await Promise.all([loadDailyReport(), loadStaffOverview()]);
        showMessage(result.message);
    } catch (error) {
        showMessage(error.message, true);
    }
});

attendanceDateInput.addEventListener('change', async () => {
    state.markedStudentIds.clear();
    try {
        await Promise.all([loadDailyReport(), loadStaffOverview()]);
    } catch (error) {
        showMessage(error.message, true);
    }
});

reportAcademicYear.addEventListener('change', async () => {
    state.markedStudentIds.clear();
    renderAttendanceTable();
    try {
        await loadDailyReport();
    } catch (error) {
        showMessage(error.message, true);
    }
});

reportBranch.addEventListener('change', async () => {
    state.markedStudentIds.clear();
    renderAttendanceTable();
    try {
        await loadDailyReport();
    } catch (error) {
        showMessage(error.message, true);
    }
});

loadHistoryBtn.addEventListener('click', loadHistory);
overviewTabBtn.addEventListener('click', () => setDashboardSection('overview'));
managementTabBtn.addEventListener('click', () => setDashboardSection('management'));
overviewStudyYear.addEventListener('change', async () => {
    state.expandedOverviewGroup = null;
    try {
        await loadStaffOverview();
    } catch (error) {
        showMessage(error.message, true);
    }
});
startCameraBtn.addEventListener('click', startCamera);
stopCameraBtn.addEventListener('click', stopCamera);
startEnrollmentCameraBtn.addEventListener('click', startEnrollmentCamera);
stopEnrollmentCameraBtn.addEventListener('click', stopEnrollmentCamera);
enrollStudentSelect.addEventListener('change', () => {
    faceConsentCheckbox.checked = false;
    updateEnrollmentControls();
});
faceConsentCheckbox.addEventListener('change', updateEnrollmentControls);
enrollFaceBtn.addEventListener('click', captureEnrollment);
removeFaceBtn.addEventListener('click', removeFaceEnrollment);
autoScanBtn.addEventListener('click', toggleAutomaticAttendance);
window.addEventListener('beforeunload', () => {
    stopCamera();
    stopStudentCamera();
});

attendanceDateInput.value = todayISO();
document.getElementById('studentAcademicYear').value = defaultAcademicYear();
setPublicView('home');
refreshAuthState();
