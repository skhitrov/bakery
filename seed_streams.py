"""Idempotently add Потоки (streams) and demo students split across them.

Safe to re-run: streams are get-or-created by name, existing students are
assigned to Поток 1 only while still unassigned, and new families are skipped
if their email already exists.
"""

from app.database import init_db, get_db
from app.auth import hash_password


def get_or_create_stream(conn, name: str, position: int) -> int:
    row = conn.execute("SELECT id FROM streams WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    conn.execute("INSERT INTO streams (name, position) VALUES (?, ?)", (name, position))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def seed_streams() -> None:
    init_db()  # ensures streams table + students.stream_id exist (runs migration)
    with get_db() as conn:
        s1 = get_or_create_stream(conn, "Поток 1", 1)
        s2 = get_or_create_stream(conn, "Поток 2", 2)

        # Assign the 3 existing seed students to Поток 1 (only if still unassigned)
        for name in ("Петров Ваня", "Сидорова Маша", "Кузнецов Артём"):
            conn.execute(
                "UPDATE students SET stream_id = ? WHERE full_name = ? AND stream_id IS NULL",
                (s1, name),
            )

        # (email, password, parent_name, child_name, stream_id)
        new_families = [
            ("volkov@mail.ru", "pass123", "Волков Сергей Павлович", "Волков Дима", s1),
            ("morozova@mail.ru", "pass123", "Морозова Ольга Игоревна", "Морозова Аня", s1),
            ("novikov@mail.ru", "pass123", "Новиков Андрей Сергеевич", "Новиков Егор", s2),
            ("smirnova@mail.ru", "pass123", "Смирнова Наталья Викторовна", "Смирнова Вика", s2),
            ("popov@mail.ru", "pass123", "Попов Илья Дмитриевич", "Попов Максим", s2),
            ("lebedeva@mail.ru", "pass123", "Лебедева Ирина Александровна", "Лебедева Соня", s2),
        ]

        # First module (if any) for optional starter weekly records
        mod = conn.execute("SELECT id FROM modules ORDER BY position LIMIT 1").fetchone()
        module_id = mod["id"] if mod else None

        added = 0
        for email, password, parent_name, child_name, sid in new_families:
            if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                continue  # idempotent: family already created
            conn.execute(
                "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
                (email, hash_password(password), "parent", parent_name),
            )
            parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO students (full_name, parent_id, stream_id) VALUES (?, ?, ?)",
                (child_name, parent_id, sid),
            )
            student_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if module_id is not None:
                weeks_data = [
                    (student_id, module_id, 1, 1, 0, 1, 1, 0, 0, 1, "", ""),
                    (student_id, module_id, 2, 1, 0, 1, 1, 1, 0, 0, "", ""),
                    (student_id, module_id, 3, 1, 0, 1, 1, 1, 1, 0, "", ""),
                    (student_id, module_id, 4, 0, 1, 1, 0, 1, 1, 0, "", ""),
                ]
                conn.executemany(
                    "INSERT INTO weekly_records "
                    "(student_id, module_id, week_number, theory, practice, hw1, hw2, hw3, hw4, test, trial_exam, comment) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    weeks_data,
                )
            added += 1

    print(f"Streams ready. Added {added} new student(s) this run.")
    print("Поток 1: Петров Ваня, Сидорова Маша, Кузнецов Артём, Волков Дима, Морозова Аня")
    print("Поток 2: Новиков Егор, Смирнова Вика, Попов Максим, Лебедева Соня")
    print("New parents (all pass123): volkov@, morozova@, novikov@, smirnova@, popov@, lebedeva@ mail.ru")


if __name__ == "__main__":
    seed_streams()
