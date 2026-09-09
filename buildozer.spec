[app]

title = Smart Multi Downloader
package.name = smartdownload
package.domain = com.smart
version = 2.0.0

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,txt,json

requirements = python3,kivy,plyer,yt-dlp,ffmpeg

p4a.bootstrap = sdl2

android.permissions = INTERNET

android.api = 35
android.minapi = 21

android.archs = arm64-v8a,armeabi-v7a

orientation = portrait
fullscreen = 0


[buildozer]

log_level = 2
warn_on_root = 1