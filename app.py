import os
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ganti-secret-key-ini-saat-deploy")

init_db()
_conn = get_db()
_admin_exists = _conn.execute("SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()
if _admin_exists["c"] == 0:
    _conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        ("admin", generate_password_hash(os.environ.get("ADMIN_PASSWORD", "ubah_password_ini")), "admin"),
    )
    _conn.commit()
_conn.close()


# ---------- AUTH HELPERS ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Hanya admin yang bisa mengakses halaman ini.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return dict(current_user=session.get("username"), current_role=session.get("role"))


# ---------- AUTH ROUTES ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Username atau password salah.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- DASHBOARD ----------
@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    total_projects = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    active_projects = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='Berjalan'").fetchone()["c"]
    completed_projects = conn.execute("SELECT COUNT(*) c FROM projects WHERE status='Selesai'").fetchone()["c"]
    total_assets = conn.execute("SELECT COUNT(*) c FROM assets").fetchone()["c"]
    assets_in_use = conn.execute("SELECT COUNT(*) c FROM assets WHERE status='Digunakan'").fetchone()["c"]
    assets_maintenance = conn.execute("SELECT COUNT(*) c FROM assets WHERE status='Maintenance'").fetchone()["c"]
    total_crew = conn.execute("SELECT COUNT(*) c FROM crew WHERE status='Aktif'").fetchone()["c"]

    status_breakdown = conn.execute(
        "SELECT status, COUNT(*) c FROM projects GROUP BY status"
    ).fetchall()

    upcoming_calibration = conn.execute(
        "SELECT * FROM assets WHERE next_calibration_due IS NOT NULL AND next_calibration_due != '' "
        "ORDER BY next_calibration_due ASC LIMIT 5"
    ).fetchall()

    expiring_licenses = conn.execute(
        "SELECT * FROM crew WHERE license_expiry IS NOT NULL AND license_expiry != '' "
        "ORDER BY license_expiry ASC LIMIT 5"
    ).fetchall()

    recent_projects = conn.execute(
        "SELECT * FROM projects ORDER BY updated_at DESC LIMIT 6"
    ).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        total_projects=total_projects,
        active_projects=active_projects,
        completed_projects=completed_projects,
        total_assets=total_assets,
        assets_in_use=assets_in_use,
        assets_maintenance=assets_maintenance,
        total_crew=total_crew,
        status_breakdown=status_breakdown,
        upcoming_calibration=upcoming_calibration,
        expiring_licenses=expiring_licenses,
        recent_projects=recent_projects,
        today=datetime.now().strftime("%Y-%m-%d"),
    )


# ---------- PROJECTS ----------
@app.route("/projects")
@login_required
def projects_list():
    conn = get_db()
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    sql = "SELECT * FROM projects WHERE 1=1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR client LIKE ? OR location LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)
    sql += " ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("projects_list.html", projects=rows, q=q, status_filter=status_filter)


@app.route("/projects/new", methods=["GET", "POST"])
@login_required
def project_new():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO projects (name, client, location, status, progress_percent, start_date, end_date, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["name"], request.form.get("client"), request.form.get("location"),
                request.form.get("status", "Belum Mulai"), int(request.form.get("progress_percent") or 0),
                request.form.get("start_date"), request.form.get("end_date"), request.form.get("description"),
            ),
        )
        conn.commit()
        conn.close()
        flash("Project berhasil ditambahkan.", "success")
        return redirect(url_for("projects_list"))
    return render_template("project_form.html", project=None)


@app.route("/projects/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def project_edit(pid):
    conn = get_db()
    project = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not project:
        conn.close()
        flash("Project tidak ditemukan.", "error")
        return redirect(url_for("projects_list"))
    if request.method == "POST":
        conn.execute(
            "UPDATE projects SET name=?, client=?, location=?, status=?, progress_percent=?, "
            "start_date=?, end_date=?, description=?, updated_at=datetime('now') WHERE id=?",
            (
                request.form["name"], request.form.get("client"), request.form.get("location"),
                request.form.get("status"), int(request.form.get("progress_percent") or 0),
                request.form.get("start_date"), request.form.get("end_date"),
                request.form.get("description"), pid,
            ),
        )
        log_note = request.form.get("log_note", "").strip()
        if log_note:
            conn.execute(
                "INSERT INTO project_logs (project_id, note, progress_at_time, created_by) VALUES (?, ?, ?, ?)",
                (pid, log_note, int(request.form.get("progress_percent") or 0), session.get("username")),
            )
        conn.commit()
        conn.close()
        flash("Project berhasil diperbarui.", "success")
        return redirect(url_for("project_detail", pid=pid))
    conn.close()
    return render_template("project_form.html", project=project)


@app.route("/projects/<int:pid>")
@login_required
def project_detail(pid):
    conn = get_db()
    project = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    logs = conn.execute("SELECT * FROM project_logs WHERE project_id=? ORDER BY log_date DESC", (pid,)).fetchall()
    assignments = conn.execute(
        "SELECT a.*, c.name as crew_name, s.name as asset_name FROM assignments a "
        "LEFT JOIN crew c ON a.crew_id = c.id LEFT JOIN assets s ON a.asset_id = s.id "
        "WHERE a.project_id=? ORDER BY a.assignment_date DESC", (pid,)
    ).fetchall()
    conn.close()
    if not project:
        flash("Project tidak ditemukan.", "error")
        return redirect(url_for("projects_list"))
    return render_template("project_detail.html", project=project, logs=logs, assignments=assignments)


@app.route("/projects/<int:pid>/delete", methods=["POST"])
@login_required
@admin_required
def project_delete(pid):
    conn = get_db()
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    flash("Project dihapus.", "success")
    return redirect(url_for("projects_list"))


# ---------- ASSETS ----------
@app.route("/assets")
@login_required
def assets_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM assets ORDER BY updated_at DESC").fetchall()
    conn.close()
    return render_template("assets_list.html", assets=rows)


@app.route("/assets/new", methods=["GET", "POST"])
@login_required
def asset_new():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO assets (name, asset_type, serial_number, status, total_flight_hours, "
            "last_calibration_date, next_calibration_due, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["name"], request.form.get("asset_type"), request.form.get("serial_number"),
                request.form.get("status", "Tersedia"), float(request.form.get("total_flight_hours") or 0),
                request.form.get("last_calibration_date"), request.form.get("next_calibration_due"),
                request.form.get("notes"),
            ),
        )
        conn.commit()
        conn.close()
        flash("Aset berhasil ditambahkan.", "success")
        return redirect(url_for("assets_list"))
    return render_template("asset_form.html", asset=None)


@app.route("/assets/<int:aid>/edit", methods=["GET", "POST"])
@login_required
def asset_edit(aid):
    conn = get_db()
    asset = conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
    if request.method == "POST":
        conn.execute(
            "UPDATE assets SET name=?, asset_type=?, serial_number=?, status=?, total_flight_hours=?, "
            "last_calibration_date=?, next_calibration_due=?, notes=?, updated_at=datetime('now') WHERE id=?",
            (
                request.form["name"], request.form.get("asset_type"), request.form.get("serial_number"),
                request.form.get("status"), float(request.form.get("total_flight_hours") or 0),
                request.form.get("last_calibration_date"), request.form.get("next_calibration_due"),
                request.form.get("notes"), aid,
            ),
        )
        conn.commit()
        conn.close()
        flash("Aset berhasil diperbarui.", "success")
        return redirect(url_for("assets_list"))
    conn.close()
    return render_template("asset_form.html", asset=asset)


@app.route("/assets/<int:aid>/delete", methods=["POST"])
@login_required
@admin_required
def asset_delete(aid):
    conn = get_db()
    conn.execute("DELETE FROM assets WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    flash("Aset dihapus.", "success")
    return redirect(url_for("assets_list"))


# ---------- CREW ----------
@app.route("/crew")
@login_required
def crew_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM crew ORDER BY updated_at DESC").fetchall()
    conn.close()
    return render_template("crew_list.html", crew=rows)


@app.route("/crew/new", methods=["GET", "POST"])
@login_required
def crew_new():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO crew (name, role, license_number, license_expiry, phone, status, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["name"], request.form.get("role"), request.form.get("license_number"),
                request.form.get("license_expiry"), request.form.get("phone"),
                request.form.get("status", "Aktif"), request.form.get("notes"),
            ),
        )
        conn.commit()
        conn.close()
        flash("Kru berhasil ditambahkan.", "success")
        return redirect(url_for("crew_list"))
    return render_template("crew_form.html", member=None)


@app.route("/crew/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def crew_edit(cid):
    conn = get_db()
    member = conn.execute("SELECT * FROM crew WHERE id=?", (cid,)).fetchone()
    if request.method == "POST":
        conn.execute(
            "UPDATE crew SET name=?, role=?, license_number=?, license_expiry=?, phone=?, status=?, notes=?, "
            "updated_at=datetime('now') WHERE id=?",
            (
                request.form["name"], request.form.get("role"), request.form.get("license_number"),
                request.form.get("license_expiry"), request.form.get("phone"),
                request.form.get("status"), request.form.get("notes"), cid,
            ),
        )
        conn.commit()
        conn.close()
        flash("Data kru berhasil diperbarui.", "success")
        return redirect(url_for("crew_list"))
    conn.close()
    return render_template("crew_form.html", member=member)


@app.route("/crew/<int:cid>/delete", methods=["POST"])
@login_required
@admin_required
def crew_delete(cid):
    conn = get_db()
    conn.execute("DELETE FROM crew WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    flash("Data kru dihapus.", "success")
    return redirect(url_for("crew_list"))


# ---------- ASSIGNMENTS ----------
@app.route("/assignments")
@login_required
def assignments_list():
    conn = get_db()
    rows = conn.execute(
        "SELECT a.*, p.name as project_name, c.name as crew_name, s.name as asset_name "
        "FROM assignments a "
        "LEFT JOIN projects p ON a.project_id = p.id "
        "LEFT JOIN crew c ON a.crew_id = c.id "
        "LEFT JOIN assets s ON a.asset_id = s.id "
        "ORDER BY a.assignment_date DESC"
    ).fetchall()
    conn.close()
    return render_template("assignments_list.html", assignments=rows)


@app.route("/assignments/new", methods=["GET", "POST"])
@login_required
def assignment_new():
    conn = get_db()
    if request.method == "POST":
        conn.execute(
            "INSERT INTO assignments (project_id, crew_id, asset_id, assignment_date, role_in_project, status, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["project_id"], request.form.get("crew_id") or None,
                request.form.get("asset_id") or None, request.form.get("assignment_date"),
                request.form.get("role_in_project"), request.form.get("status", "Dijadwalkan"),
                request.form.get("notes"),
            ),
        )
        conn.commit()
        conn.close()
        flash("Assignment berhasil ditambahkan.", "success")
        return redirect(url_for("assignments_list"))
    projects = conn.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    crew = conn.execute("SELECT id, name FROM crew WHERE status='Aktif' ORDER BY name").fetchall()
    assets = conn.execute("SELECT id, name FROM assets WHERE status != 'Rusak' ORDER BY name").fetchall()
    conn.close()
    return render_template("assignment_form.html", projects=projects, crew=crew, assets=assets, assignment=None)


@app.route("/assignments/<int:aid>/delete", methods=["POST"])
@login_required
@admin_required
def assignment_delete(aid):
    conn = get_db()
    conn.execute("DELETE FROM assignments WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    flash("Assignment dihapus.", "success")
    return redirect(url_for("assignments_list"))


# ---------- USER MANAGEMENT (admin only) ----------
@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users_manage():
    conn = get_db()
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form.get("role", "staff")
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
            conn.commit()
            flash(f"User {username} berhasil dibuat.", "success")
        except Exception:
            flash("Username sudah ada, pilih username lain.", "error")
    rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at").fetchall()
    conn.close()
    return render_template("users.html", users=rows)


@app.route("/users/<int:uid>/delete", methods=["POST"])
@login_required
@admin_required
def user_delete(uid):
    if uid == session.get("user_id"):
        flash("Tidak bisa menghapus akun sendiri.", "error")
        return redirect(url_for("users_manage"))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    flash("User dihapus.", "success")
    return redirect(url_for("users_manage"))


# ---------- API untuk chart dashboard ----------
@app.route("/api/chart/status")
@login_required
def api_chart_status():
    conn = get_db()
    rows = conn.execute("SELECT status, COUNT(*) c FROM projects GROUP BY status").fetchall()
    conn.close()
    return jsonify({"labels": [r["status"] for r in rows], "data": [r["c"] for r in rows]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
