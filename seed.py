"""Seed the database with demo data for testing."""

from app.database import init_db, get_db
from app.auth import hash_password


def seed() -> None:
    init_db()
    with get_db() as conn:
        # Check if already seeded
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            print("Database already seeded, skipping.")
            return

        # Create admin (curator)
        conn.execute(
            "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
            ("curator@test.ru", hash_password("pass123"), "admin", "Куратор"),
        )

        # Create a teacher
        conn.execute(
            "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
            ("admin@bulochka.ru", hash_password("teacher123"), "teacher", "Иванова Мария Петровна"),
        )

        # Create default module
        conn.execute(
            "INSERT INTO modules (name, position) VALUES (?, ?)",
            ("Сентябрь", 1),
        )
        module_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create parents with their children
        families = [
            ("petrov@mail.ru", "pass123", "Петров Алексей Иванович", "Петров Ваня"),
            ("sidorova@mail.ru", "pass123", "Сидорова Елена Викторовна", "Сидорова Маша"),
            ("kuznetsov@mail.ru", "pass123", "Кузнецов Дмитрий Олегович", "Кузнецов Артём"),
        ]

        for email, password, parent_name, child_name in families:
            conn.execute(
                "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
                (email, hash_password(password), "parent", parent_name),
            )
            parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            conn.execute(
                "INSERT INTO students (full_name, parent_id) VALUES (?, ?)",
                (child_name, parent_id),
            )
            student_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Seed weekly records (4 weeks of data), hw1-hw4 are boolean (0/1)
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

    print("Database seeded successfully!")
    print("Demo accounts:")
    print("  Admin:   curator@test.ru / pass123")
    print("  Parent:  petrov@mail.ru / pass123")
    print("  Parent:  sidorova@mail.ru / pass123")
    print("  Parent:  kuznetsov@mail.ru / pass123")
    print("  Teacher: admin@bulochka.ru / teacher123")


if __name__ == "__main__":
    seed()
