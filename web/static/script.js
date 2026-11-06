
let schedule = [];
let teachers = [];
let groups = [];
let subjects = [];
let activeScheduleTab = "individual";

const $ = id => document.getElementById(id);

function getName(items, id) {
    return items.find(x => Number(x.id) === Number(id))?.name
        || `ID ${id}`;
}

async function loadData() {
    const endpoints = [
        "/api/teachers",
        "/api/groups",
        "/api/subjects"
    ];

    const responses = await Promise.all(
        endpoints.map(url => fetch(url))
    );

    // subjects пока может не иметь API
    const data = await Promise.all(
        responses.map(async response =>
            response.ok ? response.json() : []
        )
    );

    [teachers, groups, subjects] = data;
}

async function generate() {
    const button = $("generateBtn");

    button.disabled = true;
    $("status").textContent = "Генерация выполняется...";
    $("results").hidden = true;

    try {
        const response = await fetch("/api/generate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                group_limit: Number($("groupLimit").value),
                optimize: $("optimize").checked
            })
        });

        const raw = await response.text();
        let data;
        try { data = JSON.parse(raw); } catch { throw new Error(`Сервер вернул ошибку ${response.status}. Подробности в терминале сервера.`); }

        if (!response.ok) {
            throw new Error(
                typeof data.detail === "string"
                    ? data.detail
                    : JSON.stringify(data.detail || data)
            );
        }

        schedule = data.schedule;

        $("lessonsCount").textContent = data.lessons_count;
        $("windowsBefore").textContent = data.windows_before;
        $("windowsAfter").textContent = data.windows_after;
        $("scoreAfter").textContent = data.score_after;
        $("groupWindowsAfter").textContent = data.group_windows_after;
        $("optimizationSeconds").textContent = data.optimization_seconds;

        $("results").hidden = false;
        $("status").textContent = "Расписание создано";

        updateEntities();
        renderSchedule();

    } catch (error) {
        $("status").textContent = `Ошибка: ${error.message}`;
    } finally {
        button.disabled = false;
    }
}

function updateEntities() {
    const type = $("viewType").value;
    const idField = type === "group" ? "group_id" : "teacher_id";
    const items = type === "group" ? groups : teachers;

    const ids = [...new Set(schedule.map(x => x[idField]))]
        .sort((a, b) => a - b);

    const select = $("entitySelect");
    select.replaceChildren();

    for (const id of ids) {
        const option = document.createElement("option");
        option.value = String(id);
        option.textContent = getName(items, id);
        select.appendChild(option);
    }

    renderSchedule();
}

function renderSchedule() {
    if (activeScheduleTab === "overview") {
        renderOverview();
        return;
    }
    const table = $("scheduleTable");
    table.replaceChildren();

    const week = $("weekSelect").value;
    const type = $("viewType").value;
    const selectedId = Number($("entitySelect").value);
    const idField = type === "group" ? "group_id" : "teacher_id";

    const header = table.insertRow();
    ["Пара", "Понедельник", "Вторник", "Среда",
     "Четверг", "Пятница"].forEach(label => {
        const th = document.createElement("th");
        th.textContent = label;
        header.appendChild(th);
    });

    for (let slot = 1; slot <= 4; slot++) {
        const row = table.insertRow();
        row.insertCell().textContent = String(slot);

        for (let day = 0; day < 5; day++) {
            const cell = row.insertCell();

            const lessons = schedule.filter(lesson =>
                lesson.week === week &&
                lesson.day === day &&
                lesson.slot === slot &&
                lesson[idField] === selectedId
            );

            if (type === "teacher") {
                const teacher = teachers.find(t => Number(t.id) === selectedId);
                if (teacher?.methodical_days?.includes(day) && slot === 1) {
                    cell.textContent = "Методический день";
                    cell.classList.add("methodical-day");
                }
            }

            for (const lesson of lessons) {
                const block = document.createElement("div");
                block.className = "lesson";

                const title = document.createElement("strong");
                title.textContent = getName(
                    subjects, lesson.subject_id
                );

                const details = document.createElement("small");
                details.textContent = type === "group"
                    ? getName(teachers, lesson.teacher_id)
                    : getName(groups, lesson.group_id);

                block.append(title, details);
                cell.appendChild(block);
            }
        }
    }
}

function selectScheduleTab(tab) {
    activeScheduleTab = tab;
    const overview = tab === "overview";
    $("individualPanel").hidden = overview;
    $("overviewPanel").hidden = !overview;
    $("viewTypeControl").hidden = overview;
    $("entityControl").hidden = overview;
    for (const [id, selected] of [["individualTab", !overview], ["overviewTab", overview]]) {
        $(id).setAttribute("aria-selected", String(selected));
        $(id).tabIndex = selected ? 0 : -1;
    }
    renderSchedule();
}

function renderOverview() {
    const table = $("overviewTable");
    table.replaceChildren();
    const week = $("weekSelect").value;
    const dayNames = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"];
    const caption = document.createElement("caption");
    caption.textContent = `Общее расписание — ${week === "A" ? "числитель (A)" : "знаменатель (B)"}`;
    table.appendChild(caption);
    const head = table.createTHead();
    const daysRow = head.insertRow();
    const teacherHeader = document.createElement("th");
    teacherHeader.textContent = "Преподаватель";
    teacherHeader.rowSpan = 2;
    teacherHeader.scope = "col";
    teacherHeader.className = "overview-teacher";
    daysRow.appendChild(teacherHeader);
    const slotsRow = head.insertRow();
    for (const name of dayNames) {
        const dayHeader = document.createElement("th");
        dayHeader.textContent = name;
        dayHeader.colSpan = 4;
        dayHeader.scope = "colgroup";
        dayHeader.className = "overview-day";
        daysRow.appendChild(dayHeader);
        for (let slot = 1; slot <= 4; slot++) {
            const th = document.createElement("th");
            th.textContent = `${slot} пара`;
            th.scope = "col";
            if (slot === 1) th.className = "overview-day-start";
            slotsRow.appendChild(th);
        }
    }
    const byPosition = new Map();
    const groupNames = new Map(groups.map(g => [Number(g.id), g.name]));
    const subjectNames = new Map(subjects.map(s => [Number(s.id), s.name]));
    for (const lesson of schedule) {
        if (lesson.week !== week) continue;
        const key = `${lesson.teacher_id}:${lesson.day}:${lesson.slot}`;
        if (!byPosition.has(key)) byPosition.set(key, []);
        byPosition.get(key).push(lesson);
    }
    // Keep teachers with no lessons visible; include unknown IDs defensively.
    const people = new Map(teachers.map(t => [Number(t.id), t]));
    for (const lesson of schedule) {
        if (!people.has(Number(lesson.teacher_id))) {
            people.set(Number(lesson.teacher_id), {id: lesson.teacher_id, name: `ID ${lesson.teacher_id}`, methodical_days: []});
        }
    }
    const body = table.createTBody();
    for (const teacher of [...people.values()].sort((a, b) => a.name.localeCompare(b.name, "ru") || Number(a.id) - Number(b.id))) {
        const row = body.insertRow();
        const name = document.createElement("th");
        name.textContent = teacher.name;
        name.scope = "row";
        name.className = "overview-teacher";
        row.appendChild(name);
        for (let day = 0; day < 5; day++) {
            const methodical = (teacher.methodical_days || []).map(Number).includes(day);
            for (let slot = 1; slot <= 4; slot++) {
                const cell = row.insertCell();
                if (slot === 1) cell.classList.add("overview-day-start");
                const lessons = byPosition.get(`${teacher.id}:${day}:${slot}`) || [];
                if (methodical) cell.classList.add("methodical-day");
                for (const lesson of lessons) {
                    const group = document.createElement("span");
                    group.className = "overview-group";
                    group.textContent = groupNames.get(Number(lesson.group_id)) || `ID ${lesson.group_id}`;
                    group.title = subjectNames.get(Number(lesson.subject_id)) || `Предмет ID ${lesson.subject_id}`;
                    cell.appendChild(group);
                }
                if (!lessons.length) {
                    cell.textContent = methodical ? "МД" : "—";
                    cell.title = methodical ? "Методический день" : "Нет занятий";
                }
            }
        }
    }
}

$("individualTab").addEventListener("click", () => selectScheduleTab("individual"));
$("overviewTab").addEventListener("click", () => selectScheduleTab("overview"));
for (const id of ["individualTab", "overviewTab"]) {
    $(id).addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const tab = event.key === "Home" ? "individual" : event.key === "End" ? "overview" : activeScheduleTab === "overview" ? "individual" : "overview";
        selectScheduleTab(tab);
        $(tab === "overview" ? "overviewTab" : "individualTab").focus();
    });
}

$("generateBtn").addEventListener("click", generate);
$("viewType").addEventListener("change", updateEntities);
$("entitySelect").addEventListener("change", renderSchedule);
$("weekSelect").addEventListener("change", renderSchedule);

loadData().catch(error => {
    $("status").textContent =
        `Не удалось загрузить справочники: ${error.message}`;
});
