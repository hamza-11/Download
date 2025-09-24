from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
import traceback
import asyncio
import uuid

app = FastAPI()

# ================== إدارة المهام والملفات ==================

# قاموس لتخزين حالة المهام في الذاكرة
tasks = {}

# تأكد من وجود مجلد للتحميلات
DOWNLOADS_DIR = "downloads"
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

class DownloadRequest(BaseModel):
    link: str
    cookies: str = None
    file_type: str = "MP4"

# ================== منطق تحميل الفيديو (يعمل في الخلفية) ==================

async def run_download_task(task_id: str, link: str, file_type: str, cookies: str, base_url: str):
    """
    هذه هي المهمة الفعلية التي تعمل في الخلفية.
    تقوم بتحميل الفيديو وتحديث حالة المهمة عند الانتهاء.
    """
    try:
        # إعداد yt-dlp
        output_template = os.path.join(DOWNLOADS_DIR, f"{task_id}_%(title)s.%(ext)s")
        ydl_opts = {
            'outtmpl': output_template,
            'keepvideo': False,
        }

        if cookies:
            ydl_opts['http_headers'] = {'Cookie': cookies}

        if file_type == "MP3":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }]
        else: # MP4
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        # بدء التحميل
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            
            base_filename = ydl.prepare_filename(info)
            if file_type == "MP3":
                final_filename = os.path.splitext(base_filename)[0] + ".mp3"
            else:
                final_filename = base_filename if base_filename.endswith('.mp4') else os.path.splitext(base_filename)[0] + ".mp4"

        if os.path.exists(final_filename):
            # بناء رابط التحميل وتحديث حالة المهمة
            download_url = f"{base_url}downloads/{os.path.basename(final_filename)}"
            tasks[task_id] = {
                "status": "completed",
                "download_url": download_url,
                "file_name": os.path.basename(final_filename)
            }
        else:
            raise FileNotFoundError("لم يتم العثور على الملف بعد المعالجة.")

    except Exception as e:
        error_msg = str(e).split("\n")[0]
        tasks[task_id] = {"status": "failed", "error": error_msg}
        print(f"Task {task_id} failed: {traceback.format_exc()}")


# ================== نقاط النهاية (API Endpoints) ==================

@app.post("/api/start-download")
async def start_download(request: DownloadRequest, http_request: Request, background_tasks: BackgroundTasks):
    """
    يبدأ مهمة تحميل جديدة ويعيد معرف المهمة على الفور.
    """
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing"}
    
    base_url = str(http_request.base_url)
    
    # إضافة مهمة التحميل لتعمل في الخلفية
    background_tasks.add_task(run_download_task, task_id, request.link, request.file_type, request.cookies, base_url)
    
    return {"task_id": task_id}

@app.get("/api/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    يستعلم عن حالة مهمة تحميل معينة.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="لم يتم العثور على المهمة")
    return task

def remove_file(path: str):
    """دالة لحذف الملف بأمان بعد فترة."""
    try:
        # تأخير بسيط قبل الحذف للتأكد من اكتمال الإرسال
        asyncio.run(asyncio.sleep(10))
        os.remove(path)
        print(f"تم حذف الملف بنجاح: {path}")
    except Exception as e:
        print(f"خطأ أثناء محاولة حذف الملف {path}: {e}")

@app.get("/downloads/{file_name}")
async def download_file(file_name: str, background_tasks: BackgroundTasks):
    """
    يقوم بتقديم الملف النهائي للتحميل ويجدول حذفه.
    """
    file_path = os.path.join(DOWNLOADS_DIR, file_name)
    if os.path.exists(file_path):
        # إضافة مهمة الحذف لتعمل في الخلفية بعد إرسال الاستجابة
        background_tasks.add_task(remove_file, file_path)
        return FileResponse(file_path, media_type='application/octet-stream', filename=file_name)
    else:
        raise HTTPException(status_code=404, detail="لم يتم العثور على الملف")

@app.get("/")
def read_root():
    return {"message": "مرحباً بك في API تحميل الفيديو (نظام المهام)"}
