
[app]

# اسم التطبيق
title = Smart Multi Downloader

# اسم الحزمة
package.name = smartdownload

# نطاق الحزمة
package.domain = com.smart

# رقم الإصدار
version = 2.0.0

# مجلد المشروع
source.dir = .

# الملفات التي تدخل داخل التطبيق
source.include_exts = py,png,jpg,jpeg,kv,atlas,txt,json

# مكتبات Python المطلوبة
requirements = python3,kivy,plyer,yt-dlp,ffmpeg

# Bootstrap الخاص بـ Kivy
p4a.bootstrap = sdl2

# صلاحية الإنترنت فقط
android.permissions = INTERNET

# Android SDK
android.api = 35

# أقل إصدار Android مدعوم
android.minapi = 21

# معماريات Android
android.archs = arm64-v8a,armeabi-v7a

# اتجاه الشاشة
orientation = portrait

# ليس Fullscreen
fullscreen = 0

# اسم التطبيق في APK
android.entrypoint = org.kivy.android.PythonActivity

# إعدادات Buildozer
[buildozer]

# مستوى السجل
log_level = 2

# التحذير عند التشغيل بصلاحيات root
warn_on_root = 1
