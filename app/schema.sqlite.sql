
      CREATE TABLE IF NOT EXISTS account_creation_lock(id INTEGER PRIMARY KEY CHECK(id=1)) STRICT;
      INSERT OR IGNORE INTO account_creation_lock(id) VALUES(1);
      PRAGMA foreign_keys = ON;
      PRAGMA busy_timeout = 5000;
      PRAGMA journal_mode = WAL;
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        fullName TEXT NOT NULL,
        passwordHash TEXT NOT NULL
      ) STRICT;
      CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY,
        studentCode TEXT NOT NULL UNIQUE COLLATE NOCASE
          CHECK (lower(trim(studentCode)) <> 'unknown'),
        fullName TEXT NOT NULL CHECK (lower(trim(fullName)) <> 'unknown')
      ) STRICT;
      CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY,
        roomCode TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL
      ) STRICT;
      CREATE TABLE IF NOT EXISTS room_events (
        id INTEGER PRIMARY KEY,
        studentId INTEGER NOT NULL REFERENCES students(id),
        roomId INTEGER NOT NULL REFERENCES rooms(id),
        direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
        occurredAt TEXT NOT NULL,
        source TEXT NOT NULL CHECK (source IN ('camera', 'manual')),
        eventKey TEXT NOT NULL UNIQUE
      ) STRICT;
      CREATE INDEX IF NOT EXISTS events_time ON room_events(occurredAt DESC, id DESC);
      CREATE INDEX IF NOT EXISTS events_student_time ON room_events(studentId, occurredAt DESC, id DESC);
      CREATE INDEX IF NOT EXISTS events_room_time ON room_events(roomId, occurredAt DESC, id DESC);
CREATE TABLE IF NOT EXISTS student_accounts (userId INTEGER PRIMARY KEY REFERENCES users(id), studentId INTEGER NOT NULL UNIQUE REFERENCES students(id)) STRICT; CREATE TABLE IF NOT EXISTS learning_sessions (id INTEGER PRIMARY KEY, subjectCode TEXT NOT NULL, subjectName TEXT NOT NULL, teacherName TEXT NOT NULL, roomId INTEGER NOT NULL REFERENCES rooms(id), startsAt TEXT NOT NULL, endsAt TEXT NOT NULL, CHECK(endsAt>startsAt)) STRICT; CREATE TABLE IF NOT EXISTS session_students (sessionId INTEGER NOT NULL REFERENCES learning_sessions(id), studentId INTEGER NOT NULL REFERENCES students(id), PRIMARY KEY(sessionId,studentId)) STRICT; CREATE TABLE IF NOT EXISTS lesson_attendance (id INTEGER PRIMARY KEY, sessionId INTEGER NOT NULL, studentId INTEGER NOT NULL, occurredAt TEXT NOT NULL, source TEXT NOT NULL CHECK(source='camera'), UNIQUE(sessionId,studentId), FOREIGN KEY(sessionId,studentId) REFERENCES session_students(sessionId,studentId)) STRICT; CREATE INDEX IF NOT EXISTS sessions_time ON learning_sessions(startsAt);
    
CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, classCode TEXT NOT NULL UNIQUE, name TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS class_students (classId INTEGER NOT NULL REFERENCES classes(id), studentId INTEGER NOT NULL REFERENCES students(id), PRIMARY KEY(classId,studentId)) STRICT;
CREATE TABLE IF NOT EXISTS class_sessions (sessionId INTEGER PRIMARY KEY REFERENCES learning_sessions(id), classId INTEGER NOT NULL REFERENCES classes(id)) STRICT;

CREATE TABLE IF NOT EXISTS attendance_windows (sessionId INTEGER PRIMARY KEY REFERENCES learning_sessions(id), state TEXT NOT NULL CHECK(state IN ('open','closed')), updatedBy INTEGER NOT NULL REFERENCES users(id), updatedAt TEXT NOT NULL) STRICT;
