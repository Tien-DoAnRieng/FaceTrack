CREATE TABLE IF NOT EXISTS account_creation_lock(id INT PRIMARY KEY) ENGINE=InnoDB;
INSERT IGNORE INTO account_creation_lock(id) VALUES(1);
CREATE TABLE IF NOT EXISTS users (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    fullName VARCHAR(200) NOT NULL,
    passwordHash VARCHAR(200) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;
CREATE TABLE IF NOT EXISTS students (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    studentCode VARCHAR(50) NOT NULL UNIQUE,
    fullName VARCHAR(200) NOT NULL,
    CHECK (LOWER(TRIM(studentCode)) <> 'unknown'),
    CHECK (LOWER(TRIM(fullName)) <> 'unknown')
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;
CREATE TABLE IF NOT EXISTS rooms (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    roomCode VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;
CREATE TABLE IF NOT EXISTS room_events (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    studentId INT NOT NULL,
    roomId INT NOT NULL,
    direction VARCHAR(3) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    occurredAt VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source VARCHAR(6) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    eventKey VARCHAR(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL UNIQUE,
    FOREIGN KEY (studentId) REFERENCES students(id),
    FOREIGN KEY (roomId) REFERENCES rooms(id),
    CHECK (direction IN ('in', 'out')),
    CHECK (source IN ('camera', 'manual')),
    INDEX events_time (occurredAt DESC, id DESC),
    INDEX events_student_time (studentId, occurredAt DESC, id DESC),
    INDEX events_room_time (roomId, occurredAt DESC, id DESC)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_ci;
CREATE TABLE IF NOT EXISTS student_accounts (userId INT PRIMARY KEY, studentId INT NOT NULL UNIQUE, FOREIGN KEY(userId) REFERENCES users(id), FOREIGN KEY(studentId) REFERENCES students(id)) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS learning_sessions (id INT AUTO_INCREMENT PRIMARY KEY, subjectCode VARCHAR(50) NOT NULL, subjectName VARCHAR(200) NOT NULL, teacherName VARCHAR(200) NOT NULL, roomId INT NOT NULL, startsAt VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, endsAt VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, FOREIGN KEY(roomId) REFERENCES rooms(id), CHECK(endsAt>startsAt), INDEX sessions_time(startsAt)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS session_students (sessionId INT NOT NULL, studentId INT NOT NULL, PRIMARY KEY(sessionId,studentId), FOREIGN KEY(sessionId) REFERENCES learning_sessions(id), FOREIGN KEY(studentId) REFERENCES students(id)) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS lesson_attendance (id INT AUTO_INCREMENT PRIMARY KEY, sessionId INT NOT NULL, studentId INT NOT NULL, occurredAt VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, source VARCHAR(6) NOT NULL CHECK(source='camera'), UNIQUE(sessionId,studentId), FOREIGN KEY(sessionId,studentId) REFERENCES session_students(sessionId,studentId)) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS classes (id INT AUTO_INCREMENT PRIMARY KEY, classCode VARCHAR(50) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS class_students (classId INT NOT NULL, studentId INT NOT NULL, PRIMARY KEY(classId,studentId), FOREIGN KEY(classId) REFERENCES classes(id), FOREIGN KEY(studentId) REFERENCES students(id)) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS class_sessions (sessionId INT PRIMARY KEY, classId INT NOT NULL, FOREIGN KEY(sessionId) REFERENCES learning_sessions(id), FOREIGN KEY(classId) REFERENCES classes(id)) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS attendance_windows (sessionId INT PRIMARY KEY, state VARCHAR(6) NOT NULL, updatedBy INT NOT NULL, updatedAt VARCHAR(24) NOT NULL, FOREIGN KEY(sessionId) REFERENCES learning_sessions(id), FOREIGN KEY(updatedBy) REFERENCES users(id), CHECK(state IN ('open','closed'))) ENGINE=InnoDB;
