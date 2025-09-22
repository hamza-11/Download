from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import traceback
import asyncio

app = FastAPI()

class DownloadRequest(BaseModel):
    link: str
    cookies: str = None
    file_type: str = "MP4" # القيمة الافتراضية هي MP4

# ================== تحميل الفيديو ==================
async def download_video(link: str, file_type: str, cookies: str = None, debug: bool = False):
    cookies_file_path = "cookies_temp.txt"
    
    if cookies:
        with open(cookies_file_path, "w") as f:
            f.write(cookies)

    # إعداد yt-dlp
    ydl_opts = {
        'outtmpl': '%(title)s.%(ext)s',
    }

    if file_type == "MP3":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else: # MP4
        ydl_opts['format'] = 'bestvideo+bestaudio/best'

    if cookies:
        ydl_opts['cookiefile'] = cookies_file_path

    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=True))
            
            # تحديد اسم الملف النهائي
            base_filename = ydl.prepare_filename(info)
            if file_type == "MP3":
                file_name = os.path.splitext(base_filename)[0] + ".mp3"
            else:
                file_name = base_filename

        if os.path.exists(file_name):
            return file_name
        else:
            # قد يكون الملف لا يزال قيد المعالجة، ننتظر قليلاً
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
    finally:
        if os.path.exists(cookies_file_path):
            os.remove(cookies_file_path)


@app.post("/api/download")
async def api_download(request: DownloadRequest):
    try:
        file_path = await download_video(request.link, request.file_type, request.cookies)
        
        media_type = "audio/mpeg" if request.file_type == "MP3" else "video/mp4"
        
        return FileResponse(path=file_path, media_type=media_type, filename=os.path.basename(file_path))

    except HTTPException as http_exc:
        # حذف الملف إذا كان موجودًا وفشل الطلب
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise http_exc
    except Exception as e:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "مرحباً بك في API تحميل الفيديو"}
