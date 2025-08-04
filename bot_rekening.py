import os
import re
import mysql.connector
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# === Konfigurasi Path Folder ===
FOLDER_GAMBAR = "screenshots"
os.makedirs(FOLDER_GAMBAR, exist_ok=True)
os.makedirs("downloads", exist_ok=True)  # ✅ Buat folder downloads jika belum ada

# === Validasi Format Rekening ===
def is_valid_rekening(rek):
    return re.fullmatch(r"\d{5}-\d{2}-\d{5}", rek)

# === Koneksi DB Remote (Rekening) ===
db_rekening = {
    'host': 'qh98k.h.filess.io',
    'port': 61002,
    'user': 'tengz_betweenwho',
    'password': 'e912d03d17534f7cfbc64a365eb0571b60b3af11',
    'database': 'tengz_betweenwho'
}

# === Koneksi DB Lokal (Histori) ===
db_histori = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'db_histori_local'
}

# === Inisialisasi Tabel Histori ===
try:
    conn = mysql.connector.connect(**db_histori)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS histori_cek_saldo (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT,
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            nomor_rekening VARCHAR(20),
            saldo DECIMAL(15,2),
            waktu DATETIME,
            gambar_path VARCHAR(255)
        )
    """)
    conn.commit()
    conn.close()
except mysql.connector.Error as e:
    print(f"[!] Gagal membuat tabel histori: {e}")

# === /start Handler ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sapaan = f"Halo {user.first_name or 'Pengguna'}!\n\n"
    sapaan += "📸 Silakan kirim *screenshot rekening* terlebih dahulu.\n"
    sapaan += "Lalu kirim nomor rekening dalam format: 00000-00-00000\n"
    sapaan += "Ketik /histori untuk melihat histori cek saldo."
    await update.message.reply_text(sapaan)

# === /histori Handler ===
async def histori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        conn = mysql.connector.connect(**db_histori)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nomor_rekening, saldo, waktu, username, first_name, last_name, gambar_path
            FROM histori_cek_saldo
            WHERE user_id = %s
            ORDER BY waktu DESC
            LIMIT 10
        """, (user_id,))
        results = cursor.fetchall()
        conn.close()

        if results:
            pesan = "📄 Histori pengecekan terakhir:\n"
            for rek, saldo, waktu, username, fname, lname, gpath in results:
                uname = f"@{username}" if username else "-"
                nama = f"{fname} {lname[0]}." if lname else fname
                waktu_str = waktu.strftime('%Y-%m-%d %H:%M')
                saldo_str = f"Rp{saldo:,.0f}" if saldo is not None else "❌ Tidak ditemukan"
                gbr_str = f"\n📷 Gambar: {gpath}" if gpath else ""
                pesan += f"• {rek} | {saldo_str} | {waktu_str} | {uname} | {nama}{gbr_str}\n"
        else:
            pesan = "ℹ️ Belum ada histori pengecekan ditemukan."
    except mysql.connector.Error as e:
        pesan = f"⚠️ Gagal mengambil histori: {e}"

    await update.message.reply_text(pesan)

# === Handler Gambar ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    file = await update.message.photo[-1].get_file()
    now = datetime.now()
    filename = f"{user.id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
    filepath = os.path.join(FOLDER_GAMBAR, filename)
    await file.download_to_drive(filepath)

    await update.message.reply_text("✅ Gambar diterima. Silakan kirim nomor rekening Anda.")

    try:
        conn = mysql.connector.connect(**db_histori)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO histori_cek_saldo (
                user_id, username, first_name, last_name,
                nomor_rekening, saldo, waktu, gambar_path
            ) VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s)
        """, (
            user.id, user.username or "", user.first_name or "", user.last_name or "",
            now, filepath
        ))
        conn.commit()
        conn.close()
    except mysql.connector.Error as e:
        print(f"[!] Gagal menyimpan histori gambar: {e}")

# === Handler Pesan Teks ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    now = datetime.now()
    rekening = text
    saldo = None
    pesan_reply = ""
    gambar_path = None

    if text.lower() in ["halo", "hi", "hai"]:
        await start(update, context)
        return

    if not is_valid_rekening(text):
        pesan_reply = "❌ Format rekening tidak valid. Gunakan format: 00000-00-00000"
    else:
        try:
            conn = mysql.connector.connect(**db_rekening)
            cursor = conn.cursor()
            cursor.execute("SELECT saldo FROM Accounts WHERE account_number = %s", (rekening,))
            result = cursor.fetchone()
            conn.close()

            if result:
                saldo = result[0]
                pesan_reply = f"✅ Saldo rekening {rekening} adalah Rp{saldo:,.2f}"
            else:
                pesan_reply = f"❌ Nomor rekening {rekening} tidak ditemukan."
        except mysql.connector.Error as e:
            pesan_reply = f"⚠️ Gagal mengakses database rekening: {e}"

    await update.message.reply_text(pesan_reply)

    try:
        conn = mysql.connector.connect(**db_histori)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT gambar_path FROM histori_cek_saldo
            WHERE user_id = %s AND gambar_path IS NOT NULL
            ORDER BY waktu DESC LIMIT 1
        """, (user.id,))
        result = cursor.fetchone()
        gambar_path = result[0] if result else None
        conn.close()
    except:
        gambar_path = None

    try:
        conn = mysql.connector.connect(**db_histori)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO histori_cek_saldo (
                user_id, username, first_name, last_name,
                nomor_rekening, saldo, waktu, gambar_path
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user.id, user.username or "", user.first_name or "", user.last_name or "",
            rekening, saldo, now, gambar_path
        ))
        conn.commit()
        conn.close()
    except mysql.connector.Error as e:
        print(f"[!] Gagal menyimpan histori teks: {e}")

# === Jalankan Bot ===
if __name__ == '__main__':
    app = ApplicationBuilder().token("7760891685:AAHi4jFDuAjKtQ9uvf_Kr8QsUGcrNGYQUp8").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("histori", histori))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot cek saldo aktif dan siap digunakan...")
    app.run_polling()
