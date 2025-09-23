from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
import traceback
import asyncio
import shutil

app = FastAPI()

# تأكد من وجود مجلد للتحميلات
DOWNLOADS_DIR = "downloads"
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

class DownloadRequest(BaseModel):
    link: str
    cookies: str = None
    file_type: str = "MP4"

async def download_video(link: str, file_type: str, cookies: str = None, debug: bool = False):
    # إعداد yt-dlp
    output_template = os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s')
    ydl_opts = {
        'outtmpl': output_template,
        'keepvideo': False, # لا تحتفظ بملف الفيديو الأصلي بعد التحويل
    }

    if cookies:
        ydl_opts['http_headers'] = {
            'Cookie': cookies
        }

    if file_type == "MP3":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else: # MP4
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'


    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=True))
            
            base_filename = ydl.prepare_filename(info)
            if file_type == "MP3":
                file_name = os.path.splitext(base_filename)[0] + ".mp3"
            else:
                # yt-dlp قد يحفظ الفيديو بامتداد مختلف (مثل .mkv)، لذا نحتاج إلى التأكد من اسم الملف النهائي
                file_name = base_filename if base_filename.endswith('.mp4') else os.path.splitext(base_filename)[0] + ".mp4"


        if os.path.exists(file_name):
            return file_name
        else:
            await asyncio.sleep(2)
            if os.path.exists(file_name):
                return file_name
            raise HTTPException(status_code=500, detail="لم يتم العثور على الملف الذي تم تنزيله بعد المعالجة.")

    except Exception as e:
        if debug:
            error_details = traceback.format_exc()
            print(error_details)
            raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء التحميل: {error_details}")
        else:
            error_msg = str(e).split("\n")[0]
            raise HTTPException(status_code=400, detail=f"حدث خطأ: {error_msg}")

@app.post("/api/download")
async def api_download(request: DownloadRequest, http_request: Request):
    file_path = None
    try:
        file_path = await download_video(request.link, request.file_type, request.cookies)
        
        file_name = os.path.basename(file_path)
        
        # بناء رابط التحميل الكامل
        base_url = str(http_request.base_url)
        download_url = f"{base_url}downloads/{file_name}"
        
        return JSONResponse(content={"download_url": download_url, "file_name": file_name})

    except Exception as e:
        # حذف الملف إذا كان موجودًا وفشل الطلب
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/downloads/{file_name}")
async def download_file(file_name: str):
    file_path = os.path.join(DOWNLOADS_DIR, file_name)
    if os.path.exists(file_path):
        # حذف الملف بعد إرساله لضمان عدم تراكم الملفات
        response = FileResponse(file_path, media_type='application/octet-stream', filename=file_name)
        
        async def cleanup():
            try:
                await asyncio.sleep(5) # انتظر قليلاً قبل الحذف
                os.remove(file_path)
                print(f"تم حذف الملف: {file_path}")
            except Exception as e:
                print(f"خطأ أثناء حذف الملف {file_path}: {e}")

        asyncio.create_task(cleanup())
        return response
    else:
        raise HTTPException(status_code=404, detail="لم يتم العثور على الملف")

@app.get("/")
def read_root():
    return {"message": "مرحباً بك في API تحميل الفيديو"}
