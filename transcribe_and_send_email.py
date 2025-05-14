from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import os
import whisper
import subprocess
import sys
import yt_dlp
import paramiko
from dotenv import load_dotenv

load_dotenv()

def send_email(receiver_email, video_url, screenshot_paths, subject_name):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = os.getenv("SENDER_EMAIL")
    password = os.getenv("EMAIL_PASSWORD")

    # Sort screenshots by filename to ensure sequential order
    screenshot_paths = sorted(screenshot_paths, key=lambda x: os.path.basename(x))

    # Approximate max size per email (25MB = 25 * 1024 * 1024 bytes)
    MAX_EMAIL_SIZE = 15 * 1024 * 1024
    # Reserve some space for email headers and HTML content (e.g., 1MB)
    MAX_ATTACHMENT_SIZE = MAX_EMAIL_SIZE - 1 * 1024 * 1024

    # Group screenshots by size
    current_group = []
    current_size = 0
    email_groups = []
    
    for path in screenshot_paths:
        file_size = os.path.getsize(path)
        if current_size + file_size > MAX_ATTACHMENT_SIZE:
            if current_group:
                email_groups.append(current_group)
            current_group = [path]
            current_size = file_size
        else:
            current_group.append(path)
            current_size += file_size
    if current_group:
        email_groups.append(current_group)

    # Send an email for each group
    for group_idx, group in enumerate(email_groups, start=1):
        message = MIMEMultipart('related')
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] =  subject_name + f"(Part {group_idx} of {len(email_groups)})"

        # Create HTML body with inline images
        html_body = f"""
        <p>Your video has been processed (Part {group_idx} of {len(email_groups)}).</p>
        <p>Video URL: <a href="{video_url}">{video_url}</a></p>
        <p>Screenshots:</p>
        """
        for i, path in enumerate(group, start=1):
            html_body += f'<p><img src="cid:image{i}" alt="Screenshot {os.path.basename(path)}" style="max-width:800px;"></p>'

        # Attach HTML body
        msg_alternative = MIMEMultipart('alternative')
        message.attach(msg_alternative)
        msg_alternative.attach(MIMEText(html_body, 'html'))

        # Attach images with Content-ID for inline display
        for i, path in enumerate(group, start=1):
            try:
                with open(path, 'rb') as img_file:
                    img = MIMEImage(img_file.read())
                    img.add_header('Content-ID', f'<image{i}>')
                    img.add_header('Content-Disposition', 'inline', filename=os.path.basename(path))
                    message.attach(img)
            except Exception as e:
                print(f"❌ Failed to embed screenshot {path}: {e}")

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(sender_email, password)
                smtp.sendmail(sender_email, receiver_email, message.as_string())
                print(f"📧 Email {group_idx} of {len(email_groups)} sent to {receiver_email} with {len(group)} screenshots")
        except Exception as e:
            print(f"❌ Failed to send email {group_idx}: {e}")


def format_timestamp(seconds):
    millis = int((seconds % 1) * 1000)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02},{millis:03}"


def write_srt(transcription_segments, srt_path):
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(transcription_segments, start=1):
            start = format_timestamp(segment['start'])
            end = format_timestamp(segment['end'])
            text = segment['text'].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


def take_screenshots(video_path, segments, screenshot_folder):
    os.makedirs(screenshot_folder, exist_ok=True)
    screenshot_paths = []
    for i, segment in enumerate(segments, start=1):
        timestamp = segment['start']
        timestamp_str = f"{int(timestamp // 3600):02}:{int((timestamp % 3600) // 60):02}:{int(timestamp % 60):02}.{int((timestamp % 1) * 100):02}"
        screenshot_path = os.path.join(screenshot_folder, f"screenshot_{i:07}.jpg")
        subprocess.run([
            "ffmpeg", "-ss", timestamp_str, "-i", video_path,
            "-frames:v", "1", "-q:v", "2", "-y", screenshot_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        screenshot_paths.append(screenshot_path)
    return screenshot_paths


def download_video(url, download_folder):
    os.makedirs(download_folder, exist_ok=True)
    ydl_opts = {
        'outtmpl': f'{download_folder}/%(upload_date)s - %(title)s.%(ext)s',
        'cookiefile': './youtube.com_cookies.txt',
        'format': 'mp4/bestvideo+bestaudio',
        'merge_output_format': 'mp4'
        # 'ratelimit': 1_000_000,  # ~1MB/s max download speed
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        info = ydl.extract_info(url, download=False)
        filename = ydl.prepare_filename(info).replace('.webm', '.mp4').replace('.mkv', '.mp4')
    return filename



def upload_video_sftp(local_path, remote_path, hostname, username, password):
    # print(f"📂 Checking local file: {os.path.exists(local_path)} - {local_path}")

    try:

        transport = paramiko.Transport((hostname, os.getenv("SFTP_PORT")))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        sftp.put(local_path, remote_path)
        print(f"✅ Successfully uploaded {local_path} to {username}@{hostname}:{remote_path}")
        
        sftp.close()
        transport.close()

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, port=2222, username=username, password=password)

        commands = f"""
        source ~/.bashrc
        cd /home/bosh/Desktop/project/video/
        ./generate_png.sh
        """
        stdin, stdout, stderr = ssh.exec_command(commands)
        output = stdout.read().decode()
        error = stderr.read().decode()

        print(f"🛰️ Remote output:\n{output}")
        if error.strip():
            print(f"⚠️ Remote errors:\n{error}")

        ssh.close()


    except Exception as e:
        print(f"❌ Failed to upload via SFTP: {e}")


def process_video(video_path, output_root, video_url, receiver_email):
    model = whisper.load_model("base")
    base_name = os.path.splitext(os.path.basename(video_path))[0]

    video_output_folder = os.path.join(output_root, base_name)
    os.makedirs(video_output_folder, exist_ok=True)

    srt_path = os.path.join(video_output_folder, f"{base_name}.srt")
    output_video_path = os.path.join(video_output_folder, f"{base_name}_subtitled.mp4")
    screenshots_folder = os.path.join(video_output_folder, "screenshots")

    print(f"\n🎧 Transcribing {base_name}...")
    try:
        result = model.transcribe(video_path, verbose=True)
        write_srt(result['segments'], srt_path)
        print(f"✅ SRT saved: {srt_path}")
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        return

    print(f"🎞️ Burning subtitles into video...")
    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", f"subtitles={srt_path}:force_style='FontSize=24'",
            "-c:v", "libx264",
            "-c:a", "aac", "-b:a", "192k",
            "-y", output_video_path
        ], check=True)
        print(f"✅ Subtitled video saved: {output_video_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to burn subtitles: {e}")
        return

    print(f"📸 Taking screenshots...")
    screenshot_paths = take_screenshots(output_video_path, result['segments'], screenshots_folder)
    print(f"✅ Screenshots saved to: {screenshots_folder}")

    print(f"📧 Sending email to {receiver_email}...")
    send_email(receiver_email, video_url, screenshot_paths, f'\n🎧 Transcribed {base_name}')

    print(f"🛰️ Uploading to remote server...")
    remote_path = f"/home/bosh/Desktop/project/video/videos/{os.path.basename(output_video_path)}"
    upload_video_sftp(
        local_path=output_video_path,
        remote_path=remote_path,
        hostname=os.getenv("SFTP_HOSTNAME"),
        username=os.getenv("SFTP_USERNAME"),
        password=os.getenv("SFTP_PASSWORD")
    )



if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python fetch_url.py <video_url> <receiver_email>")
        sys.exit(1)

    video_url = sys.argv[1]
    receiver_email = sys.argv[2]

    today = datetime.today().strftime("%Y-%m-%d")
    base_output_folder = os.path.abspath(today)

    print(f"📥 Downloading video from {video_url} to {base_output_folder}...")
    try:
        video_path = download_video(video_url, base_output_folder)
    except Exception as e:
        print(f"❌ Failed to download video: {e}")
        sys.exit(1)

    process_video(video_path, output_root=base_output_folder, video_url=video_url, receiver_email=receiver_email)


