from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
import sqlite3
import pandas as pd
from datetime import datetime
import os
from twilio.rest import Client
app = Flask(__name__)
app.secret_key = "your_secret_key"

@app.context_processor
def inject_datetime():
    return {'datetime': datetime}

AVAILABLE_SLOTS = [
    "09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM",
    "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM"
]

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # Change this to a secure password

DB_NAME = 'appointments.db'

# ---------- Utility Functions ---------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            reason TEXT
        )
    ''')
    conn.commit()
    conn.close()

def is_slot_available(date, time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM appointments WHERE date=? AND time=?", (date, time))
    count = c.fetchone()[0]
    conn.close()
    return count == 0  # 0 means the slot is available

def send_whatsapp_confirmation(to_number, message_text):
    account_sid = 'your key'
    auth_token = 'your token'
    client = Client(account_sid, auth_token)

    message = client.messages.create(
        from_='whatsapp:+14155238886',  # Twilio sandbox number
        body=message_text,
        to=f'whatsapp:{to_number}'
    )

    return message.sid

# ---------- Routes ----------

@app.route('/')
def home():
    return render_template('home.html')

# ✅ Route for booking appointments
@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        date = request.form['date']
        time = request.form['time']
        reason = request.form['reason']

        if is_slot_available(date, time):
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("INSERT INTO appointments (name, email, phone, date, time, reason) VALUES (?, ?, ?, ?, ?, ?)",
                      (name, email, phone, date, time, reason))
            conn.commit()
            conn.close()

            # ✅ Send WhatsApp confirmation
            message_text = f"Hi {name}, your appointment on {date} at {time} is confirmed. See you soon!"
            send_whatsapp_confirmation(phone, message_text)

            flash("✅ Appointment booked successfully!", "success")
            return redirect(url_for("home"))
        else:
            flash("❌ Selected time slot is already booked. Please choose a different time.", "error")
            return redirect(url_for("book"))

    return render_template('book.html')

@app.route('/available_slots', methods=['POST'])
def available_slots():
    selected_date = request.json.get('date')

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT time FROM appointments WHERE date = ?", (selected_date,))
    booked = [row[0] for row in c.fetchall()]
    conn.close()

    available = [slot for slot in AVAILABLE_SLOTS if slot not in booked]
    return jsonify({'available': available})

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("❌ Invalid username or password", "error")
    return render_template("admin_login.html")

@app.route('/cancel')
def cancel():
    return render_template('cancel.html')

@app.route('/cancel_appointment/<int:id>')
def cancel_appointment(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Appointment cancelled successfully.", "warning")
    return redirect(url_for('cancel'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    search = request.args.get('search', '').strip().lower()

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if search:
        c.execute("""
            SELECT * FROM appointments 
            WHERE LOWER(name) LIKE ? OR LOWER(email) LIKE ?
            ORDER BY date, time
        """, (f'%{search}%', f'%{search}%'))
    else:
        c.execute("SELECT * FROM appointments ORDER BY date, time")

    appointments = c.fetchall()
    conn.close()

    return render_template('admin.html', appointments=appointments)

@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM appointments WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Appointment deleted.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/reschedule/<int:id>', methods=['GET', 'POST'])
def reschedule(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == 'POST':
        new_date = request.form['new_date']
        new_time = request.form['new_time']
        if is_slot_available(new_date, new_time):
            c.execute("UPDATE appointments SET date=?, time=? WHERE id=?", (new_date, new_time, id))
            conn.commit()
            flash('Appointment rescheduled!', 'success')
        else:
            flash('Selected slot not available!', 'danger')
        conn.close()
        return redirect(url_for('admin_dashboard'))

    c.execute("SELECT * FROM appointments WHERE id=?", (id,))
    appointment = c.fetchone()
    conn.close()
    return render_template('reschedule.html', appointment=appointment)

@app.route('/export')
def export():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM appointments", conn)
    export_file = 'appointments_export.xlsx'
    df.to_excel(export_file, index=False)
    conn.close()
    return send_file(export_file, as_attachment=True)

@app.route('/confirm', methods=['POST'])
def confirm_appointment():
    data = request.form
    user_whatsapp = data['phone']  # e.g., "+919876543210"
    msg = f"Hi {data['name']}, your appointment for {data['date']} at {data['time']} is confirmed."
    send_whatsapp_confirmation(user_whatsapp, msg)
    return redirect('/success')


# ---------- Initialize & Run ----------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)