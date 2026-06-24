CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    client TEXT,
    location TEXT,
    status TEXT NOT NULL DEFAULT 'Belum Mulai',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT,
    serial_number TEXT,
    status TEXT NOT NULL DEFAULT 'Tersedia',
    total_flight_hours REAL DEFAULT 0,
    last_calibration_date TEXT,
    next_calibration_due TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS crew (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    license_number TEXT,
    license_expiry TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'Aktif',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS assignments (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    crew_id INTEGER REFERENCES crew(id) ON DELETE SET NULL,
    asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    assignment_date TEXT,
    role_in_project TEXT,
    status TEXT NOT NULL DEFAULT 'Dijadwalkan',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS project_logs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    log_date TIMESTAMP DEFAULT NOW(),
    note TEXT NOT NULL,
    progress_at_time INTEGER,
    created_by TEXT
);
