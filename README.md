# YouTube-Downloader

Input a YouTube video URL, then download the video to the local disk.If you choose **audio_only** option, a MP3 file will be downloaded.

The program is on the basis of **yt_dlp**(https://github.com/yt-dlp)) and **PyQt5**, so make sure yt-dlp and PyQt5 have been installed before running this program.
For better experience,install **FFMpeg** and **FFprobe**(https://github.com/yt-dlp/FFmpeg-Builds) first, and add the directory containing the executable files to **PATH** environment variable.


```
pip install PyQt5 requests yt_dlp
```

**Usage**:

```
python youtube-downloader.py
```

Screenshot:

![screenshot](/assets/screenshot1.png)

![screenshot](/assets/screenshot2.png)

![screenshot](/assets/screenshot3.png)

![screenshot](/assets/history.png)


**If some error occurs while downloading youtube videos, just close the program and try it once more.**
