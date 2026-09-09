# -*- coding: utf-8 -*-
"""
Smart Multi Downloader for Android v2.0.0
إصلاح بدء التشغيل: يتم تهيئة كل شيء متعلق بـ Android بعد بدء التطبيق.
"""

import os
import sys
import queue
import threading
import traceback
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.utils import platform
from kivy.logger import Logger

from plyer import clipboard

from yt_dlp import YoutubeDL

# Jnius للتعامل مع Android APIs – سنقوم باستيراده فقط عند الحاجة
# بدلاً من استيراده في الأعلى، سنقوم باستيراده داخل الدوال التي تحتاجه.
# لكننا نحتاج إلى autoclass في دوال مثل save_to_media_store، لذا سنقوم باستيراده
# داخل تلك الدوال، أو نستورده في الأعلى مع try/except.
# لكن الأفضل استيراده داخل الدوال لتجنب أي مشاكل في التحميل.
# في الكود أدناه سنقوم باستيراد jnius داخل دوال Android المحددة.

# =========================
# اسم التطبيق وإصداره
# =========================
APP_NAME = "Smart Multi Downloader"
APP_VERSION = "2.0.0"

# =========================
# متغيرات عامة سيتم تهيئتها لاحقاً (Lazy)
# =========================
# سيتم تعيين هذه المتغيرات في App.on_start()
_FILES_DIR = None
_CACHE_DIR = None
_COOKIES_FILE = None

# =========================
# دوال مساعدة – يتم استدعاؤها فقط بعد بدء التطبيق
# =========================

def get_android_context():
    """
    إرجاع Context الخاص بالتطبيق (Android).
    يتم استدعاؤها فقط بعد أن يكون PythonActivity متاحاً.
    """
    # استيراد PythonActivity محلياً لتجنب مشاكل التحميل
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    return PythonActivity.mActivity

def initialize_android_paths():
    """
    تهيئة المسارات الخاصة بـ Android.
    يجب استدعاؤها من App.on_start().
    """
    global _FILES_DIR, _CACHE_DIR, _COOKIES_FILE
    if platform == 'android':
        try:
            # استيراد autoclass هنا لضمان توفره
            from jnius import autoclass
            context = get_android_context()
            _FILES_DIR = context.getFilesDir().getAbsolutePath()
            _CACHE_DIR = context.getCacheDir().getAbsolutePath()
            _COOKIES_FILE = os.path.join(_FILES_DIR, 'cookies.txt')
        except Exception as e:
            Logger.error(f"فشل تهيئة مسارات Android: {e}")
            # تعيين قيم افتراضية آمنة لمنع انهيارات لاحقة
            _FILES_DIR = ''
            _CACHE_DIR = ''
            _COOKIES_FILE = ''
    else:
        # سطح المكتب
        _FILES_DIR = os.path.dirname(os.path.abspath(__file__))
        _CACHE_DIR = os.path.join(os.path.expanduser('~'), '.cache', 'smart_downloader')
        _COOKIES_FILE = os.path.join(_FILES_DIR, 'cookies.txt')

def get_files_dir() -> str:
    """إرجاع مسار مجلد Files الخاص بالتطبيق."""
    if _FILES_DIR is None:
        # إذا لم تتم التهيئة بعد (حالة نادرة)، نعيد قيمة افتراضية
        return os.path.dirname(os.path.abspath(__file__))
    return _FILES_DIR

def get_cache_dir() -> str:
    """إرجاع مسار مجلد Cache الخاص بالتطبيق."""
    if _CACHE_DIR is None:
        return os.path.join(os.path.expanduser('~'), '.cache', 'smart_downloader')
    return _CACHE_DIR

def get_cookies_file() -> str:
    """إرجاع مسار ملف cookies.txt."""
    if _COOKIES_FILE is None:
        return os.path.join(get_files_dir(), 'cookies.txt')
    return _COOKIES_FILE

def save_to_media_store(file_path: str, display_name: str = None, mime_type: str = None) -> Optional[str]:
    """
    حفظ ملف في MediaStore (مجلد Downloads) باستخدام IS_PENDING.
    تعيد URI للملف المحفوظ أو None في حالة الفشل.
    """
    if platform != 'android':
        # للاختبار على سطح المكتب
        downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
        os.makedirs(downloads, exist_ok=True)
        dest = os.path.join(downloads, os.path.basename(file_path))
        try:
            shutil.copy2(file_path, dest)
            return dest
        except Exception as e:
            Logger.error(f"فشل النسخ إلى Downloads: {e}")
            return None

    try:
        # استيراد Jnius محلياً
        from jnius import autoclass
        context = get_android_context()
        contentResolver = context.getContentResolver()

        if not mime_type:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.mp4':
                mime_type = 'video/mp4'
            elif ext == '.mp3':
                mime_type = 'audio/mpeg'
            elif ext in ('.m4a', '.aac'):
                mime_type = 'audio/mp4'
            else:
                mime_type = 'application/octet-stream'

        MediaStore = autoclass('android.provider.MediaStore')
        ContentValues = autoclass('android.content.ContentValues')
        contentValues = ContentValues()
        if display_name:
            contentValues.put(MediaStore.Files.FileColumns.DISPLAY_NAME, display_name)
        else:
            contentValues.put(MediaStore.Files.FileColumns.DISPLAY_NAME, os.path.basename(file_path))

        contentValues.put(MediaStore.Files.FileColumns.MIME_TYPE, mime_type)
        contentValues.put(MediaStore.Files.FileColumns.RELATIVE_PATH, "Download/")

        # إضافة IS_PENDING = 1 أثناء الكتابة (لـ Android 10+)
        try:
            contentValues.put(MediaStore.Files.FileColumns.IS_PENDING, 1)
        except Exception:
            pass

        uri = contentResolver.insert(MediaStore.Files.getContentUri("external"), contentValues)
        if not uri:
            Logger.error("MediaStore: فشل إنشاء URI")
            return None

        with open(file_path, 'rb') as f_in:
            os_stream = contentResolver.openOutputStream(uri)
            if not os_stream:
                Logger.error("MediaStore: فشل فتح OutputStream")
                contentResolver.delete(uri, None, None)
                return None
            data = f_in.read(8192)
            while data:
                os_stream.write(data)
                data = f_in.read(8192)
            os_stream.close()

        # إنهاء حالة PENDING
        try:
            updateValues = ContentValues()
            updateValues.put(MediaStore.Files.FileColumns.IS_PENDING, 0)
            contentResolver.update(uri, updateValues, None, None)
        except Exception:
            pass

        Logger.info(f"MediaStore: تم حفظ الملف بنجاح: {uri.toString()}")
        return uri.toString()

    except Exception as e:
        Logger.error(f"MediaStore: خطأ أثناء الحفظ: {e}")
        return None

# =========================
# خدمة التحميل (yt-dlp + FFmpeg)
# =========================

class DownloaderService:
    def __init__(self, log_callback, progress_callback):
        self.log = log_callback
        self.progress = progress_callback
        self.last_filename = None

        # البحث عن FFmpeg في PATH – آمن لأن shutil.which لا يعتمد على Android
        self.ffmpeg_path = shutil.which('ffmpeg')
        if self.ffmpeg_path:
            self.log(f"✅ FFmpeg موجود: {self.ffmpeg_path}")
        else:
            self.log("⚠️ FFmpeg غير موجود، سيتم استخدام fallback (تحميل فيديو كملف واحد، وصوت بدون تحويل)")

    def base_opts(self, use_cookies: bool) -> Dict[str, Any]:
        opts = {
            "noplaylist": True,
            "windowsfilenames": True,
            "ignoreerrors": False,
            "quiet": True,
            "no_warnings": True,
            "retries": 10,
            "fragment_retries": 10,
            "continuedl": True,
            "restrictfilenames": False,
            "progress_hooks": [self._progress_hook],
        }
        if self.ffmpeg_path:
            opts["ffmpeg_location"] = self.ffmpeg_path
        # استخدام cookies.txt من المسار الصحيح الذي تم تهيئته
        cookies_path = get_cookies_file()
        if use_cookies and os.path.exists(cookies_path):
            opts["cookiefile"] = cookies_path
        return opts

    def info_opts(self, use_cookies: bool) -> Dict[str, Any]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        if self.ffmpeg_path:
            opts["ffmpeg_location"] = self.ffmpeg_path
        cookies_path = get_cookies_file()
        if use_cookies and os.path.exists(cookies_path):
            opts["cookiefile"] = cookies_path
        return opts

    def get_info(self, url: str, use_cookies: bool) -> Dict[str, Any]:
        with YoutubeDL(self.info_opts(use_cookies)) as ydl:
            info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict):
                raise RuntimeError("تعذر قراءة معلومات الميديا.")
            return info

    def build_video_format(self, quality: str) -> str:
        mapping = {
            "Best": "bv*+ba/best",
            "2160p / 4K": "bv*[height<=2160]+ba/best[height<=2160]/best",
            "1440p / 2K": "bv*[height<=1440]+ba/best[height<=1440]/best",
            "1080p": "bv*[height<=1080]+ba/best[height<=1080]/best",
            "720p": "bv*[height<=720]+ba/best[height<=720]/best",
            "480p": "bv*[height<=480]+ba/best[height<=480]/best",
            "360p": "bv*[height<=360]+ba/best[height<=360]/best",
        }
        return mapping.get(quality, "bv*+ba/best")

    def download_video_mp4(self, url: str, save_dir: str, quality: str, use_cookies: bool) -> str:
        os.makedirs(save_dir, exist_ok=True)
        outtmpl = os.path.join(save_dir, "%(title).120s_%(id)s.%(ext)s")

        opts = self.base_opts(use_cookies)
        if not self.ffmpeg_path:
            opts["format"] = "best[ext=mp4]/best"
        else:
            opts["format"] = self.build_video_format(quality)
            opts["merge_output_format"] = "mp4"

        opts["outtmpl"] = outtmpl

        self.log(f"جودة الفيديو المحددة: {quality}")
        self.log("بدء تحميل الفيديو...")

        with YoutubeDL(opts) as ydl:
            ydl.download([url])

        filename = self.last_filename
        if filename and os.path.exists(filename):
            return filename
        else:
            files = [f for f in os.listdir(save_dir) if os.path.isfile(os.path.join(save_dir, f))]
            if files:
                latest = max(files, key=lambda f: os.path.getmtime(os.path.join(save_dir, f)))
                return os.path.join(save_dir, latest)
            raise RuntimeError("تعذر العثور على الملف المحمّل.")

    def download_audio_mp3(self, url: str, save_dir: str, mp3_quality: str, use_cookies: bool) -> str:
        os.makedirs(save_dir, exist_ok=True)
        outtmpl = os.path.join(save_dir, "%(title).120s_%(id)s.%(ext)s")

        opts = self.base_opts(use_cookies)
        opts["format"] = "bestaudio/best"
        opts["outtmpl"] = outtmpl

        if self.ffmpeg_path:
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": mp3_quality,
                }
            ]
            self.log(f"جودة MP3 المحددة: {mp3_quality} kbps")
            self.log("بدء تحميل الصوت وتحويله إلى MP3...")
        else:
            self.log("⚠️ FFmpeg غير موجود، سيتم تحميل الصوت بامتداده الأصلي (قد لا يكون MP3).")
            self.log("بدء تحميل الصوت...")

        with YoutubeDL(opts) as ydl:
            ydl.download([url])

        filename = self.last_filename
        if filename and os.path.exists(filename):
            return filename
        else:
            files = [f for f in os.listdir(save_dir) if os.path.isfile(os.path.join(save_dir, f))]
            if files:
                latest = max(files, key=lambda f: os.path.getmtime(os.path.join(save_dir, f)))
                return os.path.join(save_dir, latest)
            raise RuntimeError("تعذر العثور على الملف المحمّل.")

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            percent = 0.0
            if total:
                percent = max(0.0, min(100.0, downloaded / total * 100))

            speed = d.get("speed")
            eta = d.get("eta")

            speed_str = self._format_bytes(speed) if speed else "-"
            eta_str = f"{eta}s" if eta is not None else "-"

            msg = (f"تحميل {percent:.1f}%  |  "
                   f"{self._format_bytes(downloaded)} / {self._format_bytes(total)}  |  "
                   f"{speed_str}/s  |  ETA: {eta_str}")
            self.progress(percent, msg)

        elif status == "finished":
            self.progress(100.0, "اكتمل التحميل. جارٍ المعالجة...")
            filename = d.get("filename")
            if filename:
                self.last_filename = filename
                self.log(f"الملف الناتج: {filename}")

    @staticmethod
    def _format_bytes(num: Optional[float]) -> str:
        if not num:
            return "-"
        size = float(num)
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

# =========================
# واجهة المستخدم (Kivy)
# =========================

class SmartDownloaderLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=12, padding=16, **kwargs)
        self.app = App.get_running_app()
        self.service = None
        self.worker_thread = None
        self.msg_queue = queue.Queue()

        # لا يتم استدعاء أي دالة تعتمد على Android هنا
        # سنقوم بتهيئة مجلد التخزين المؤقت لاحقاً في on_start

        # ---- عناصر الواجهة ----
        self.add_widget(Label(text=f"{APP_NAME} v{APP_VERSION}",
                              font_size='24sp', size_hint_y=None, height=50,
                              color=(0.2, 0.6, 1, 1)))

        url_box = BoxLayout(size_hint_y=None, height=50, spacing=8)
        self.url_input = TextInput(text='', multiline=False,
                                   hint_text='أدخل رابط الميديا',
                                   font_size='16sp')
        url_box.add_widget(self.url_input)
        paste_btn = Button(text='لصق', size_hint_x=None, width=70)
        paste_btn.bind(on_press=self.paste_from_clipboard)
        url_box.add_widget(paste_btn)
        self.add_widget(url_box)

        info_label = Label(text="سيتم حفظ الملفات في مجلد Downloads (باستخدام MediaStore)",
                           size_hint_y=None, height=30, color=(0.7, 0.7, 0.7, 1),
                           halign='center')
        info_label.bind(size=info_label.setter('text_size'))
        self.add_widget(info_label)

        mode_box = BoxLayout(size_hint_y=None, height=50, spacing=8)
        mode_box.add_widget(Label(text='النوع:', size_hint_x=0.25))
        self.mode_spinner = Spinner(text='Video MP4',
                                    values=('Video MP4', 'Audio MP3'),
                                    size_hint_x=0.75)
        self.mode_spinner.bind(text=self.on_mode_change)
        mode_box.add_widget(self.mode_spinner)
        self.add_widget(mode_box)

        video_box = BoxLayout(size_hint_y=None, height=50, spacing=8)
        video_box.add_widget(Label(text='جودة الفيديو:', size_hint_x=0.25))
        self.video_quality_spinner = Spinner(
            text='Best',
            values=('Best', '2160p / 4K', '1440p / 2K', '1080p', '720p', '480p', '360p'),
            size_hint_x=0.75
        )
        video_box.add_widget(self.video_quality_spinner)
        self.add_widget(video_box)

        mp3_box = BoxLayout(size_hint_y=None, height=50, spacing=8)
        mp3_box.add_widget(Label(text='جودة MP3:', size_hint_x=0.25))
        self.mp3_quality_spinner = Spinner(
            text='192',
            values=('320', '256', '192', '128'),
            size_hint_x=0.75
        )
        mp3_box.add_widget(self.mp3_quality_spinner)
        self.add_widget(mp3_box)

        cookies_box = BoxLayout(size_hint_y=None, height=40, spacing=8)
        self.cookies_check = CheckBox(active=False, size_hint_x=None, width=40)
        cookies_box.add_widget(self.cookies_check)
        cookies_box.add_widget(Label(text='استخدام cookies.txt (في مجلد التطبيق)'))
        self.add_widget(cookies_box)

        self.download_btn = Button(text='بدء التحميل', size_hint_y=None, height=60,
                                   background_color=(0.2, 0.5, 0.9, 1),
                                   font_size='18sp')
        self.download_btn.bind(on_press=self.start_download)
        self.add_widget(self.download_btn)

        self.progress_bar = ProgressBar(value=0, size_hint_y=None, height=30)
        self.add_widget(self.progress_bar)

        self.status_label = Label(text='جاهز', size_hint_y=None, height=30,
                                  color=(0.8, 0.8, 0.8, 1))
        self.add_widget(self.status_label)

        log_box = BoxLayout(orientation='vertical', size_hint_y=1)
        log_box.add_widget(Label(text='سجل التطبيق', size_hint_y=None, height=30,
                                 color=(0.5, 0.8, 1, 1)))
        scroll = ScrollView(size_hint_y=1)
        self.log_label = Label(text='', halign='left', valign='top',
                               size_hint_y=None, color=(0.9, 0.9, 0.9, 1))
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        scroll.add_widget(self.log_label)
        log_box.add_widget(scroll)
        self.add_widget(log_box)

        btn_row = BoxLayout(size_hint_y=None, height=50, spacing=10)
        clear_btn = Button(text='مسح السجل')
        clear_btn.bind(on_press=self.clear_log)
        btn_row.add_widget(clear_btn)
        reset_btn = Button(text='إعادة ضبط')
        reset_btn.bind(on_press=self.reset_form)
        btn_row.add_widget(reset_btn)
        self.add_widget(btn_row)

        # سيتم تهيئة الخدمة لاحقاً في on_start
        # لكننا سنقوم بتهيئتها هنا بعد أن يصبح كل شيء جاهزاً
        # لكن يجب أن ننتظر حتى يتم تهيئة المسارات. سنقوم بتهيئة الخدمة في on_start
        # بعد تهيئة المسارات.

        # معالجة الرسائل من الخيط
        Clock.schedule_interval(self.process_queue, 0.1)

        self.on_mode_change(self.mode_spinner, self.mode_spinner.text)

    # ---- دوال الأحداث ----

    def on_mode_change(self, spinner, text):
        if text == 'Video MP4':
            self.video_quality_spinner.disabled = False
            self.mp3_quality_spinner.disabled = True
        else:
            self.video_quality_spinner.disabled = True
            self.mp3_quality_spinner.disabled = False

    def paste_from_clipboard(self, instance):
        try:
            text = clipboard.get()
            if text:
                self.url_input.text = text.strip()
        except Exception as e:
            self.show_popup('خطأ', f'تعذر الوصول إلى الحافظة:\n{str(e)}')

    def start_download(self, instance):
        if self.worker_thread and self.worker_thread.is_alive():
            self.show_popup('تنبيه', 'يوجد تحميل قيد التشغيل حالياً.')
            return

        url = self.url_input.text.strip()
        if not url:
            self.show_popup('خطأ', 'الرجاء إدخال رابط الميديا.')
            return

        # التأكد من أن مجلد التخزين المؤقت جاهز
        cache_dir = get_cache_dir()
        if not cache_dir:
            self.show_popup('خطأ', 'تعذر الحصول على مجلد التخزين المؤقت.')
            return

        self.download_btn.disabled = True
        self.progress_bar.value = 0
        self.status_label.text = 'جارٍ التحميل...'

        self.threadsafe_log('=' * 60)
        self.threadsafe_log(f'الرابط: {url}')
        self.threadsafe_log(f'المجلد المؤقت: {cache_dir}')
        self.threadsafe_log(f'النوع: {self.mode_spinner.text}')
        self.threadsafe_log(f'جودة الفيديو: {self.video_quality_spinner.text}')
        self.threadsafe_log(f'جودة MP3: {self.mp3_quality_spinner.text}')
        self.threadsafe_log(f'استخدام cookies: {self.cookies_check.active}')

        self.worker_thread = threading.Thread(
            target=self._download_worker,
            args=(url,),
            daemon=True
        )
        self.worker_thread.start()

    def _download_worker(self, url: str):
        try:
            use_cookies = self.cookies_check.active
            mode = self.mode_spinner.text
            cache_dir = get_cache_dir()

            self.threadsafe_log('جاري قراءة معلومات الميديا...')
            info = self.service.get_info(url, use_cookies)
            title = info.get('title', 'عنوان غير معروف')
            extractor = info.get('extractor', 'موقع غير معروف')
            duration = self._seconds_to_text(info.get('duration'))
            uploader = info.get('uploader') or info.get('channel') or '-'

            self.threadsafe_log(f'الموقع: {extractor}')
            self.threadsafe_log(f'العنوان: {title}')
            self.threadsafe_log(f'القناة: {uploader}')
            self.threadsafe_log(f'المدة: {duration}')

            if mode == 'Video MP4':
                file_path = self.service.download_video_mp4(
                    url=url,
                    save_dir=cache_dir,
                    quality=self.video_quality_spinner.text,
                    use_cookies=use_cookies,
                )
            else:
                file_path = self.service.download_audio_mp3(
                    url=url,
                    save_dir=cache_dir,
                    mp3_quality=self.mp3_quality_spinner.text,
                    use_cookies=use_cookies,
                )

            self.threadsafe_log(f'تم التحميل إلى: {file_path}')

            if os.path.exists(file_path):
                base, ext = os.path.splitext(os.path.basename(file_path))
                display_name = f"{title[:100]}{ext}"
                mime_type = None
                if ext.lower() in ('.mp4', '.m4v'):
                    mime_type = 'video/mp4'
                elif ext.lower() in ('.mp3',):
                    mime_type = 'audio/mpeg'
                elif ext.lower() in ('.m4a', '.aac'):
                    mime_type = 'audio/mp4'
                else:
                    mime_type = 'application/octet-stream'

                uri = save_to_media_store(file_path, display_name, mime_type)
                if uri:
                    self.threadsafe_log(f'✅ تم حفظ الملف في Downloads: {display_name}')
                    self.threadsafe_log(f'URI: {uri}')
                else:
                    self.threadsafe_log('⚠️ فشل حفظ الملف في MediaStore، تم الاحتفاظ به مؤقتاً.')
                    self.threadsafe_log(f'الملف المؤقت: {file_path}')

                try:
                    os.remove(file_path)
                except Exception:
                    pass
            else:
                self.threadsafe_log('⚠️ لم يتم العثور على الملف المحمّل.')

            self.threadsafe_progress(100, '✅ تم الانتهاء بنجاح')
            self.threadsafe_log('✅ اكتمل التحميل وحفظ الملف.')

        except Exception as e:
            error_msg = str(e)
            self.threadsafe_log(f'❌ خطأ: {error_msg}')
            self.threadsafe_log(traceback.format_exc())
            self.threadsafe_progress(0, f'فشل التحميل: {error_msg[:50]}...')
        finally:
            Clock.schedule_once(lambda dt: self.enable_download_button(), 0)

    def enable_download_button(self):
        self.download_btn.disabled = False

    @staticmethod
    def _seconds_to_text(seconds: Optional[int]) -> str:
        if not seconds:
            return '-'
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h:
            return f'{h}:{m:02d}:{s:02d}'
        return f'{m}:{s:02d}'

    # ---- تحديث الواجهة من الخيوط ----

    def threadsafe_log(self, text: str):
        self.msg_queue.put(('log', text))

    def threadsafe_progress(self, percent: float, text: str):
        self.msg_queue.put(('progress', (percent, text)))

    def process_queue(self, dt):
        try:
            while True:
                msg_type, payload = self.msg_queue.get_nowait()
                if msg_type == 'log':
                    self.log_label.text += payload + '\n'
                    self.log_label.parent.parent.scroll_y = 0
                elif msg_type == 'progress':
                    percent, text = payload
                    self.progress_bar.value = percent
                    self.status_label.text = text
        except queue.Empty:
            pass

    # ---- دوال الأزرار ----

    def clear_log(self, instance):
        self.log_label.text = ''

    def reset_form(self, instance):
        self.url_input.text = ''
        self.mode_spinner.text = 'Video MP4'
        self.video_quality_spinner.text = 'Best'
        self.mp3_quality_spinner.text = '192'
        self.cookies_check.active = False
        self.progress_bar.value = 0
        self.status_label.text = 'جاهز'
        self.on_mode_change(self.mode_spinner, self.mode_spinner.text)

    def show_popup(self, title, message):
        popup = Popup(title=title,
                      content=Label(text=message, text_size=(300, None)),
                      size_hint=(0.8, 0.4))
        popup.open()

# =========================
# تطبيق Kivy الرئيسي
# =========================

class SmartDownloaderApp(App):
    def build(self):
        # لا نحدد Window.size ليتكيف مع أي شاشة
        return SmartDownloaderLayout()

    def on_start(self):
        """
        يتم استدعاؤها بعد بدء التطبيق، هنا نقوم بتهيئة كل ما يعتمد على Android.
        """
        layout = self.root

        # تهيئة المسارات الخاصة بـ Android
        try:
            initialize_android_paths()
        except Exception as e:
            layout.threadsafe_log(f"❌ فشل تهيئة مسارات Android: {e}")
            # نستمر مع قيم افتراضية إن أمكن

        # الآن أصبحت المسارات جاهزة، يمكننا تهيئة الخدمة
        layout.service = DownloaderService(layout.threadsafe_log, layout.threadsafe_progress)

        layout.threadsafe_log(f'{APP_NAME} v{APP_VERSION}')
        layout.threadsafe_log(f'📁 المجلد المؤقت: {get_cache_dir()}')
        layout.threadsafe_log(f'📁 مجلد التطبيق الخاص: {get_files_dir()}')

        # التحقق من FFmpeg (تم بالفعل داخل الخدمة)
        # نعيد عرض حالة FFmpeg
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            layout.threadsafe_log(f'✅ FFmpeg موجود: {ffmpeg}')
        else:
            layout.threadsafe_log('⚠️ FFmpeg غير موجود، سيتم استخدام fallback.')

        # طلب الأذونات فقط إذا كان الإصدار أقل من Android 10 (API 29)
        if platform == 'android':
            try:
                from android import api_version
                if api_version < 29:
                    layout.request_android_permissions()
                else:
                    layout.threadsafe_log("✅ Android 10+ لا يحتاج أذونات تخزين (باستخدام MediaStore).")
            except Exception as e:
                layout.threadsafe_log(f"⚠️ تعذر التحقق من إصدار Android: {e}")

        layout.threadsafe_log('جاهز للتحميل.')

    def request_android_permissions(self):
        """طلب أذونات التخزين للإصدارات الأقدم."""
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                perms = [Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE]
                request_permissions(perms, callback=self.on_permissions_result)
            except Exception as e:
                Logger.error(f"Permissions error: {e}")

    def on_permissions_result(self, permissions, grant_results):
        layout = self.root
        if all(grant_results):
            layout.threadsafe_log('✅ تم منح أذونات التخزين (للإصدارات الأقدم).')
        else:
            layout.threadsafe_log('⚠️ لم تُمنح الأذونات، قد لا يعمل الحفظ على Android 9 وما دونه.')

if __name__ == '__main__':
    SmartDownloaderApp().run()
