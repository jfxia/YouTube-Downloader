import os
import sys
import yt_dlp
import sqlite3
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QProgressBar, QFileDialog,
                             QMessageBox, QFrame, QGroupBox, QSizePolicy, QSpacerItem,
                             QTabWidget, QSplitter, QScrollArea, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QImage, QPainter, QPen
import requests
from io import BytesIO
import platform


class DatabaseManager:
    def __init__(self, db_path="download_history.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database and create tables if they don't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS download_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        uploader TEXT,
                        duration TEXT,
                        view_count TEXT,
                        quality TEXT,
                        output_path TEXT,
                        download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'completed'
                    )
                ''')
                conn.commit()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            print(f"Database initialization error: {e}")
    
    def save_download(self, title, url, uploader, duration, view_count, quality, output_path, status="completed"):
        """Save a download record to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO download_history 
                    (title, url, uploader, duration, view_count, quality, output_path, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (title, url, uploader, duration, view_count, quality, output_path, status))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            print(f"Error saving download: {e}")
            return None
    
    def get_download_history(self, limit=50):
        """Get download history from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, title, url, uploader, duration, view_count, quality, 
                           output_path, download_date, status
                    FROM download_history 
                    ORDER BY download_date DESC 
                    LIMIT ?
                ''', (limit,))
                return cursor.fetchall()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            print(f"Error getting download history: {e}")
            return []
    
    def clear_history(self):
        """Clear all download history"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM download_history')
                conn.commit()
                return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            print(f"Error clearing history: {e}")
            return False
    
    def delete_download(self, download_id):
        """Delete a specific download record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM download_history WHERE id = ?', (download_id,))
                conn.commit()
                return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            print(f"Error deleting download: {e}")
            return False


class DownloadThread(QThread):
    progress_signal = pyqtSignal(float, str, str, dict)
    finished_signal = pyqtSignal(bool, str, str, dict)
    thumbnail_signal = pyqtSignal(str)
    
    def __init__(self, url, output_dir, quality="best"):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.quality = quality
        self.cancelled = False
        self.video_info = {}
        self.output_path = ""  # Add this to track the actual output file path
        
    def run(self):
        print('[DEBUG] DownloadThread started')
        try:
            # 获取视频信息（添加extractor_args）
            ydl_info = yt_dlp.YoutubeDL({
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'skip': ['dash', 'hls']}}
            })
            print(f'[DEBUG] Extracting info for: {self.url}')
            info_dict = ydl_info.extract_info(self.url, download=False)
            print('[DEBUG] Video info extracted')
            
            if not info_dict:
                raise Exception("Failed to get video information. Please check if the URL is valid.")
                
            self.video_info = {
                'title': info_dict.get('title', 'Unknown Video'),
                'description': info_dict.get('description', ''),
                'thumbnail': info_dict.get('thumbnail', ''),
                'duration': self.format_duration(info_dict.get('duration', 0)),
                'uploader': info_dict.get('uploader', 'Unknown Uploader'),
                'view_count': self.format_count(info_dict.get('view_count', 0))
            }
            if self.video_info['thumbnail']:
                # 确保在主线程更新UI
                self.thumbnail_signal.emit(self.video_info['thumbnail'])
            
            # 更新格式映射
            format_mapping = {
                'best': 'bv*+ba/b',
                '1080p': 'bv[height<=1080]+ba/b[height<=1080]',
                '720p': 'bv[height<=720]+ba/b[height<=720]',
                '480p': 'bv[height<=480]+ba/b[height<=480]',
                '360p': 'bv[height<=360]+ba/b[height<=360]',
                'audio_only': 'ba/b'
            }

            if self.quality == "audio_only":
                ydl_opts = {
                    'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                    'progress_hooks': [self.progress_hook],
                    'format': format_mapping[self.quality],
                    'noplaylist': True,
                    'postprocessors': [
                        {
                            'key': 'FFmpegExtractAudio',       
                            'preferredcodec': 'mp3',           
                            'preferredquality': '192',         
                        },
                        {
                            'key': 'EmbedThumbnail',           
                            'already_have_thumbnail': True
                        }
                    ]
                }
            else:
                ydl_opts = {
                    'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                    'progress_hooks': [self.progress_hook],
                    'format': format_mapping.get(self.quality, 'bestvideo+bestaudio/best'),
                    'merge_output_format': 'mp4',  
                    'noplaylist': True,
                    'writethumbnail': True,
                    'postprocessors': [{
                        'key': 'EmbedThumbnail',
                        'already_have_thumbnail': True
                    }]
                }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
                
            if not self.cancelled:
                # Get the actual output file path
                self.output_path = os.path.join(self.output_dir, f"{self.video_info['title']}.{'mp3' if self.quality == 'audio_only' else 'mp4'}")
                self.finished_signal.emit(True, "Download completed!", self.video_info['title'], self.video_info)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            self.finished_signal.emit(False, f"Error: {str(e)}", self.video_info.get('title', 'Unknown Video'), {})
    
    def progress_hook(self, d):
        if self.cancelled:
            raise Exception("Download cancelled")
            
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                percent = d['downloaded_bytes'] / total * 100
                speed = d.get('speed')
                speed_str = f"{speed / 1024:.1f} KB/s" if speed else "Unknown speed"
                self.progress_signal.emit(percent, speed_str, self.video_info.get('title', 'Unknown Video'), d)
    
    def cancel(self):
        self.cancelled = True
        
    def format_duration(self, seconds):
        """Format video duration"""
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
        
    def format_count(self, count):
        """Format view count"""
        if count >= 10**9:
            return f"{count / 10**9:.1f}B"
        if count >= 10**6:
            return f"{count / 10**6:.1f}M"
        if count >= 10**3:
            return f"{count / 10**3:.1f}K"
        return str(count)


class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Video Downloader")
        self.setGeometry(100, 100, 1000, 800)  # Increase window size
        self.setMinimumSize(900, 600)  # Increase minimum size
        
        # Initialize database manager
        self.db_manager = DatabaseManager()
        
        # Initialize variables
        self.download_thread = None
        self.download_timer = QTimer(self)
        self.download_timer.timeout.connect(self.update_eta)
        self.eta_remaining = 0
        self.last_progress_time = 0
        self.history_widgets = []  # Store history widget references
        
        # Create main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Set application style
        self.setStyle()
        
        # Title area
        title_layout = QHBoxLayout()
        title_label = QLabel("YouTube Video Downloader")
        title_label.setFont(QFont("Segoe UI", 18, QFont.Bold))  
        title_label.setStyleSheet("color: #2c3e50;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # Add icon
        icon_label = QLabel()
        try:
            icon_pixmap = QPixmap("youtube_icon.png").scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_pixmap)
        except:
            icon_label.setText("YT")
            icon_label.setFont(QFont("Segoe UI", 16, QFont.Bold))  
            icon_label.setStyleSheet("color: #ff0000; background-color: #ffffff; padding: 5px; border-radius: 4px;")
        title_layout.addWidget(icon_label)
        
        # Create tab widget
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("QTabWidget::pane { border: none; }")
        
        # Main download tab
        main_tab = QWidget()
        main_tab_layout = QVBoxLayout()
        main_tab_layout.setContentsMargins(0, 0, 0, 0)
        main_tab_layout.setSpacing(10)
        
        # URL input section
        url_group = QGroupBox("Video URL")
        url_group.setFont(QFont("Segoe UI", 10, QFont.Bold))  
        url_layout = QHBoxLayout()
        url_layout.setContentsMargins(15, 10, 15, 10)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube video link...")
        self.url_input.setMinimumHeight(36)
        self.url_input.setFont(QFont("Segoe UI", 10))  
        self.url_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 0px 12px;
				font-weight: bold;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
        """)
        url_layout.addWidget(self.url_input, 1)
        
        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setMinimumHeight(36)
        self.paste_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))  
        self.paste_btn.setStyleSheet("""
            QPushButton {
                background-color: #e9ecef;
                color: #212529;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 0 12px;
                margin-left: 8px;
            }
            QPushButton:hover {
                background-color: #dee2e6;
            }
            QPushButton:pressed {
                background-color: #d1d5db;
            }
        """)
        self.paste_btn.clicked.connect(lambda: self.url_input.setText(app.clipboard().text()))
        url_layout.addWidget(self.paste_btn)
        
        url_group.setLayout(url_layout)
        main_tab_layout.addWidget(url_group)
        
        # Video information section
        info_group = QGroupBox("Video Information")
        info_group.setFont(QFont("Segoe UI", 10, QFont.Bold))  
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(15, 10, 15, 10)
        info_layout.setSpacing(15)
        
        # Thumbnail area
        thumbnail_frame = QFrame()
        thumbnail_frame.setFixedSize(180, 100)
        thumbnail_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
            }
        """)
        thumbnail_layout = QVBoxLayout(thumbnail_frame)
        thumbnail_layout.setContentsMargins(5, 5, 5, 5)
        thumbnail_layout.setAlignment(Qt.AlignCenter)
        
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setMinimumSize(170, 90)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setWordWrap(True)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                background-color: #f8f9fa;
                border: 1px dashed #dee2e6;
                border-radius: 2px;
           }
        """)
        self.thumbnail_label.setText("No thumbnail available")
        thumbnail_layout.addWidget(self.thumbnail_label)
        
        info_layout.addWidget(thumbnail_frame)
        
        # Video information text area
        info_text_layout = QVBoxLayout()
        info_text_layout.setSpacing(8)
        
        # Video title
        title_layout = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Bold))  
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title_label.setStyleSheet("color: #212529;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        info_text_layout.addLayout(title_layout)
        
        # Video meta information
        meta_info_layout = QVBoxLayout()
        meta_info_layout.setSpacing(4)
        
        self.uploader_label = QLabel("")
        self.uploader_label.setFont(QFont("Segoe UI", 9))  
        self.uploader_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.uploader_label.setStyleSheet("color: #6c757d;")
        meta_info_layout.addWidget(self.uploader_label)
        
        self.views_label = QLabel("")
        self.views_label.setFont(QFont("Segoe UI", 9))  
        self.views_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.views_label.setStyleSheet("color: #6c757d;")
        meta_info_layout.addWidget(self.views_label)
        
        self.duration_label = QLabel("")
        self.duration_label.setFont(QFont("Segoe UI", 9))  
        self.duration_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.duration_label.setStyleSheet("color: #6c757d;")
        meta_info_layout.addWidget(self.duration_label)
        
        info_text_layout.addLayout(meta_info_layout)
        
        # Video description
        self.description_label = QLabel("")
        self.description_label.setFont(QFont("Segoe UI", 9))  
        self.description_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.description_label.setStyleSheet("color: #495057;")
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        info_text_layout.addWidget(self.description_label)
        
        info_layout.addLayout(info_text_layout)
        info_layout.addStretch()
        
        info_group.setLayout(info_layout)
        main_tab_layout.addWidget(info_group)
        
        # Download options
        options_group = QGroupBox("Download Options")
        options_group.setFont(QFont("Segoe UI", 10, QFont.Bold))  
        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(15, 10, 15, 10)
        options_layout.setSpacing(15)
        
        # Quality selection
        quality_layout = QVBoxLayout()
        quality_layout.addWidget(QLabel("Video Quality:"))
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Best Quality", "1080p", "720p", "480p", "360p", "Audio Only"])
        self.quality_combo.setCurrentIndex(0)
        self.quality_combo.setMinimumHeight(32)
        self.quality_combo.setFont(QFont("Segoe UI", 9))  
        quality_layout.addWidget(self.quality_combo)
        
        options_layout.addLayout(quality_layout)
        
        # Save path
        path_layout = QVBoxLayout()
        path_layout.addWidget(QLabel("Save Path:"))
        
        path_hbox = QHBoxLayout()
        
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setMinimumHeight(32)
        self.path_display.setFont(QFont("Segoe UI", 9))  
        self.path_display.setText(os.path.expanduser("~/Downloads"))
        path_hbox.addWidget(self.path_display, 1)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setMinimumHeight(32)
        browse_btn.setFont(QFont("Segoe UI", 9))  
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #1d6fa5;
            }
        """)
        browse_btn.clicked.connect(self.select_directory)
        path_hbox.addWidget(browse_btn)
        
        path_layout.addLayout(path_hbox)
        options_layout.addLayout(path_layout)
        
        options_group.setLayout(options_layout)
        main_tab_layout.addWidget(options_group)
        
        # Progress display group
        progress_group = QGroupBox("Download Progress")
        progress_group.setFont(QFont("Segoe UI", 10, QFont.Bold))  
        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(15, 10, 15, 10)
        progress_layout.setSpacing(8)
        
        # Progress bar area
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(24)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: #f8f9fa;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
                width: 10px;
                margin: 0.5px;
            }
        """)
        
        # Progress information
        progress_info_layout = QHBoxLayout()
        progress_info_layout.setSpacing(15)
        
        self.percentage_label = QLabel("0%")
        self.percentage_label.setFont(QFont("Segoe UI", 10, QFont.Bold))  
        self.percentage_label.setStyleSheet("color: #3498db; min-width: 40px;")
        
        self.speed_label = QLabel("")
        self.speed_label.setFont(QFont("Segoe UI", 9))  
        self.speed_label.setStyleSheet("color: #6c757d;")
        
        self.eta_label = QLabel("")
        self.eta_label.setFont(QFont("Segoe UI", 9))  
        self.eta_label.setStyleSheet("color: #6c757d;")
        
        progress_info_layout.addWidget(self.percentage_label)
        progress_info_layout.addWidget(self.speed_label)
        progress_info_layout.addWidget(self.eta_label)
        progress_info_layout.addStretch()
        
        progress_layout.addLayout(progress_info_layout)
        progress_layout.addWidget(self.progress_bar)
        
        progress_group.setLayout(progress_layout)
        main_tab_layout.addWidget(progress_group)
        
        # Button section
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 5, 0, 5)
        button_layout.setSpacing(15)
        
        self.download_btn = QPushButton("Start Download")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))  
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                width:150;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:pressed {
                background-color: #219d55;
            }
            QPushButton:disabled {
                background-color: #a3e4d7;
            }
        """)
        self.download_btn.clicked.connect(self.start_download)
        
        self.cancel_btn = QPushButton("Cancel Download")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setFont(QFont("Segoe UI", 10))  
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a5281b;
            }
            QPushButton:disabled {
                background-color: #f5b7b1;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.cancel_btn.setEnabled(False)
        
        button_layout.addStretch()
        button_layout.addWidget(self.download_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addStretch()
        
        main_tab_layout.addLayout(button_layout)
        main_tab.setLayout(main_tab_layout)
        
        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout()
        history_layout.setContentsMargins(0, 0, 0, 0)
        
        # History controls
        history_controls = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumHeight(32)
        refresh_btn.setFont(QFont("Segoe UI", 9))
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        refresh_btn.clicked.connect(self.load_history)
        history_controls.addWidget(refresh_btn)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.setMinimumHeight(32)
        clear_btn.setFont(QFont("Segoe UI", 9))
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        clear_btn.clicked.connect(self.clear_history)
        history_controls.addWidget(clear_btn)
        
        history_controls.addStretch()
        history_layout.addLayout(history_controls)
        
        # History content
        history_frame = QFrame()
        history_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 4px;")
        self.history_frame_layout = QVBoxLayout()
        self.history_frame_layout.setContentsMargins(15, 15, 15, 15)
        
        # Empty history message
        self.history_empty_label = QLabel("No download history")
        self.history_empty_label.setFont(QFont("Segoe UI", 10))
        self.history_empty_label.setStyleSheet("color: #6c757d;")
        self.history_empty_label.setAlignment(Qt.AlignCenter)
        self.history_empty_label.setMinimumHeight(200)
        
        self.history_frame_layout.addWidget(self.history_empty_label)
        
        history_frame.setLayout(self.history_frame_layout)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(history_frame)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        history_layout.addWidget(scroll_area)
        history_tab.setLayout(history_layout)
        
        # Add tabs
        tab_widget.addTab(main_tab, "Download")
        tab_widget.addTab(history_tab, "History")
        
        # Status bar
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.StyledPanel)
        status_frame.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #e9ecef;")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(10, 5, 10, 5)
        self.status_label = QLabel("Ready")
        self.status_label.setFont(QFont("Segoe UI", 8))  
        self.status_label.setStyleSheet("color: #6c757d;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        # Add version information
        version_label = QLabel("Version: 1.2.0")
        version_label.setFont(QFont("Segoe UI", 8))  
        version_label.setStyleSheet("color: #6c757d;")
        status_layout.addWidget(version_label)
        
        status_frame.setLayout(status_layout)
        
        # Assemble main layout
        main_layout.addLayout(title_layout)
        main_layout.addWidget(tab_widget)
        main_layout.addWidget(status_frame)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Set window icon
        try:
            self.setWindowIcon(QIcon("youtube_icon.png"))
        except:
            pass
        
        # Load history on startup
        self.load_history()
    
    def setStyle(self):
        # Set global style with increased tab width
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #e9ecef;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
            }
            QTabBar::tab {
                background-color: #f8f9fa;
                color: #212529;
                border: 1px solid #e9ecef;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 16px;
                margin-right: 2px;
                font-family: "Segoe UI";  
                font-weight: 500;
                min-width: 100px;  /* Increase minimum tab width */
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #3498db;
                border: 1px solid #e9ecef;
                border-bottom: 1px solid #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #e9ecef;
            }
        """)
    
    def select_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.path_display.text())
        if path:
            self.path_display.setText(path)
    
    def start_download(self):
        print('[DEBUG] Start download clicked')
        url = self.url_input.text().strip()
        output_dir = self.path_display.text()
        
        if not url:
            QMessageBox.warning(self, "Input Error", "Please enter a YouTube video URL")
            return
            
        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "Path Error", "The specified save path is invalid")
            return
            
        # Disable UI elements
        self.url_input.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.percentage_label.setText("0%")
        self.speed_label.setText("Preparing to download...")
        self.eta_label.setText("ETA: --:--")
        self.status_label.setText("Starting download...")
        
        # Reset video information
        self.title_label.setText("")
        self.uploader_label.setText("")
        self.views_label.setText("")
        self.duration_label.setText("")
        self.description_label.setText("")
        self.thumbnail_label.setText("Loading...")
        
        # Get quality option
        quality_mapping = {
            "Best Quality": "best",
            "1080p": "1080p",
            "720p": "720p",
            "480p": "480p",
            "360p": "360p",
            "Audio Only": "audio_only"
        }
        quality = quality_mapping[self.quality_combo.currentText()]
        
        # Create and start download thread
        self.download_thread = DownloadThread(url, output_dir, quality)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.thumbnail_signal.connect(self.load_thumbnail)
        self.download_thread.start()
        
        # Start timer to update ETA
        self.last_progress_time = 0
        self.download_timer.start(1000)
    
    def cancel_download(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.status_label.setText("Canceling download...")
    
    def load_thumbnail(self, url):
        """加载并显示视频缩略图"""
        try:
            if not url:
                self.thumbnail_label.setText("No thumbnail URL")
                return
                
            # 添加超时处理
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.content
                
                # 使用QImage加载图片数据
                image = QImage()
                image.loadFromData(data)
                
                if not image.isNull():
                    # 转换为QPixmap并缩放
                    pixmap = QPixmap.fromImage(image)
                    scaled_pixmap = pixmap.scaled(
                        self.thumbnail_label.width(),
                        self.thumbnail_label.height(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.thumbnail_label.setPixmap(scaled_pixmap)
                    self.thumbnail_label.setText("")
                else:
                    self.thumbnail_label.setText("Invalid image data")
            else:
                self.thumbnail_label.setText(f"HTTP error: {response.status_code}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'[DEBUG] Exception in thread: {str(e)}')
            self.thumbnail_label.setText(f"Error: {str(e)}")
            print(f"Error loading thumbnail: {e}")
    
    def update_progress(self, percent, speed, title, data):
        """Update download progress"""
        # Update progress bar
        self.progress_bar.setValue(int(percent))
        self.percentage_label.setText(f"{int(percent)}%")
        self.speed_label.setText(f"Download speed: {speed}")
        
        # Update video information (if not set yet)
        if not self.title_label.text() and title:
            self.title_label.setText(title)
        
        # Calculate estimated time remaining
        if percent > 0 and percent < 100:
            current_time = data.get('elapsed', 0)
            if current_time > self.last_progress_time and current_time > 0:
                # Calculate average speed and estimated remaining time
                downloaded_bytes = data.get('downloaded_bytes', 0)
                total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate', 0)
                
                if total_bytes > 0:
                    avg_speed = downloaded_bytes / current_time if current_time > 0 else 0
                    remaining_bytes = total_bytes - downloaded_bytes
                    
                    if avg_speed > 0:
                        remaining_seconds = remaining_bytes / avg_speed
                        self.eta_remaining = remaining_seconds
        
        # Update status
        #self.status_label.setText(f" {int(percent)}% complete")
    
    def update_eta(self):
        """Update estimated time remaining display"""
        if self.eta_remaining > 0:
            mins = int(self.eta_remaining / 60)
            secs = int(self.eta_remaining % 60)
            self.eta_label.setText(f"ETA: {mins:02d}:{secs:02d}")
            self.eta_remaining -= 1
    
    def create_history_item(self, download_data):
        """Create a history item widget"""
        item_frame = QFrame()
        item_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
                margin: 2px 0px;
            }
            QFrame:hover {
                background-color: #e9ecef;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Title and delete button row
        title_row = QHBoxLayout()
        
        title_label = QLabel(download_data[1])  # title
        title_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        title_label.setStyleSheet("color: #212529;")
        title_label.setWordWrap(True)
        title_row.addWidget(title_label, 1)
        
        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(20, 20)
        delete_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_history_item(download_data[0], item_frame))
        title_row.addWidget(delete_btn)
        
        layout.addLayout(title_row)
        
        # URL row with copy and reuse buttons
        url_row = QHBoxLayout()
        
        url_label = QLabel(download_data[2])  # url
        url_label.setFont(QFont("Segoe UI", 8))
        url_label.setStyleSheet("color: #007bff; text-decoration: underline;")
        url_label.setWordWrap(True)
        url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        url_row.addWidget(url_label, 1)
        
        # Copy URL button
        copy_btn = QPushButton("Copy URL")
        copy_btn.setFixedSize(70, 24)
        copy_btn.setFont(QFont("Segoe UI", 7))
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        copy_btn.clicked.connect(lambda: self.copy_url_to_clipboard(download_data[2]))
        url_row.addWidget(copy_btn)
        
        # Reuse URL button
        reuse_btn = QPushButton("Reuse")
        reuse_btn.setFixedSize(50, 24)
        reuse_btn.setFont(QFont("Segoe UI", 7))
        reuse_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        reuse_btn.clicked.connect(lambda: self.reuse_url(download_data[2]))
        url_row.addWidget(reuse_btn)
        
        layout.addLayout(url_row)
        
        # Details row
        details_layout = QHBoxLayout()
        
        # Left column
        left_details = QVBoxLayout()
        left_details.setSpacing(2)
        
        uploader_label = QLabel(f"Uploader: {download_data[3] or 'Unknown'}")
        uploader_label.setFont(QFont("Segoe UI", 8))
        uploader_label.setStyleSheet("color: #6c757d;")
        left_details.addWidget(uploader_label)
        
        duration_label = QLabel(f"Duration: {download_data[4] or 'Unknown'}")
        duration_label.setFont(QFont("Segoe UI", 8))
        duration_label.setStyleSheet("color: #6c757d;")
        left_details.addWidget(duration_label)
        
        views_label = QLabel(f"Views: {download_data[5] or 'Unknown'}")
        views_label.setFont(QFont("Segoe UI", 8))
        views_label.setStyleSheet("color: #6c757d;")
        left_details.addWidget(views_label)
        
        details_layout.addLayout(left_details)
        
        # Right column
        right_details = QVBoxLayout()
        right_details.setSpacing(2)
        
        quality_label = QLabel(f"Quality: {download_data[6] or 'Unknown'}")
        quality_label.setFont(QFont("Segoe UI", 8))
        quality_label.setStyleSheet("color: #6c757d;")
        right_details.addWidget(quality_label)
        
        date_label = QLabel(f"Date: {download_data[8]}")
        date_label.setFont(QFont("Segoe UI", 8))
        date_label.setStyleSheet("color: #6c757d;")
        right_details.addWidget(date_label)
        
        status_label = QLabel(f"Status: {download_data[9]}")
        status_label.setFont(QFont("Segoe UI", 8))
        status_label.setStyleSheet("color: #28a745;" if download_data[9] == "completed" else "color: #dc3545;")
        right_details.addWidget(status_label)
        
        details_layout.addLayout(right_details)
        details_layout.addStretch()
        
        layout.addLayout(details_layout)
        
        item_frame.setLayout(layout)
        return item_frame
    
    def copy_url_to_clipboard(self, url):
        """Copy URL to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(url)
        QMessageBox.information(self, "URL Copied", "URL has been copied to clipboard!")
    
    def reuse_url(self, url):
        """Reuse URL in the download input field"""
        self.url_input.setText(url)
        # Switch to download tab
        self.parent().findChild(QTabWidget).setCurrentIndex(0)
        QMessageBox.information(self, "URL Reused", "URL has been added to the download field!")
    
    def load_history(self):
        """Load and display download history"""
        # Clear existing history widgets
        for widget in self.history_widgets:
            widget.setParent(None)
        self.history_widgets.clear()
        
        # Get history from database
        history_data = self.db_manager.get_download_history()
        
        if not history_data:
            self.history_empty_label.show()
            return
        
        # Hide empty label
        self.history_empty_label.hide()
        
        # Create history items
        for download_data in history_data:
            history_item = self.create_history_item(download_data)
            self.history_frame_layout.addWidget(history_item)
            self.history_widgets.append(history_item)
    
    def clear_history(self):
        """Clear all download history"""
        reply = QMessageBox.question(
            self, 
            "Clear History", 
            "Are you sure you want to clear all download history?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.db_manager.clear_history():
                self.load_history()
                QMessageBox.information(self, "Success", "Download history cleared successfully!")
            else:
                QMessageBox.critical(self, "Error", "Failed to clear download history!")
    
    def delete_history_item(self, download_id, item_widget):
        """Delete a specific history item"""
        reply = QMessageBox.question(
            self,
            "Delete Item",
            "Are you sure you want to delete this download record?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.db_manager.delete_download(download_id):
                item_widget.setParent(None)
                self.history_widgets.remove(item_widget)
                # Reload history if no items left
                if not self.history_widgets:
                    self.load_history()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete download record!")
    
    def download_finished(self, success, message, title, video_info):
        """Handle download completion"""
        # Stop timer
        self.download_timer.stop()
        
        # Enable UI elements
        self.url_input.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        # Update video information (if available)
        if video_info:
            self.title_label.setText(video_info.get('title', 'Unknown Video'))
            self.uploader_label.setText(f"Uploader: {video_info.get('uploader', 'Unknown Uploader')}")
            self.views_label.setText(f"Views: {video_info.get('view_count', '0')}")
            self.duration_label.setText(f"Duration: {video_info.get('duration', '0:00')}")
            self.description_label.setText(video_info.get('description', 'No description'))
        
        # Display result message
        if success:
            self.status_label.setText(f"Download completed: {title}")
            self.speed_label.setText("Download completed")
            self.eta_label.setText("")
            self.progress_bar.setValue(100)
            self.percentage_label.setText("100%")
            
            # Show success message
            QMessageBox.information(self, "Download Complete", f"Video '{title}' downloaded successfully!")
            
            # Save to database
            quality_mapping = {
                "Best Quality": "best",
                "1080p": "1080p", 
                "720p": "720p",
                "480p": "480p",
                "360p": "360p",
                "Audio Only": "audio_only"
            }
            quality = quality_mapping[self.quality_combo.currentText()]
            
            self.db_manager.save_download(
                title=title,
                url=self.download_thread.url,
                uploader=video_info.get('uploader', 'Unknown Uploader'),
                duration=video_info.get('duration', '0:00'),
                view_count=video_info.get('view_count', '0'),
                quality=quality,
                output_path=self.download_thread.output_path,
                status="completed"
            )
            
            # Refresh history tab
            self.load_history()
        else:
            self.status_label.setText(f"Download failed: {message}")
            self.speed_label.setText("Download failed")
            self.eta_label.setText("")
            
            # Save failed download to database
            if video_info:
                quality_mapping = {
                    "Best Quality": "best",
                    "1080p": "1080p",
                    "720p": "720p", 
                    "480p": "480p",
                    "360p": "360p",
                    "Audio Only": "audio_only"
                }
                quality = quality_mapping[self.quality_combo.currentText()]
                
                self.db_manager.save_download(
                    title=title,
                    url=self.download_thread.url,
                    uploader=video_info.get('uploader', 'Unknown Uploader'),
                    duration=video_info.get('duration', '0:00'),
                    view_count=video_info.get('view_count', '0'),
                    quality=quality,
                    output_path="",
                    status="failed"
                )
            
            # Show error message
            if "Download cancelled" not in message:
                QMessageBox.critical(self, "Download Failed", message)
        
        self.download_thread = None


if __name__ == "__main__":
    # Create application
    app = QApplication(sys.argv)
    
    # Set font
    font = QFont("Segoe UI")
    app.setFont(font)
    
    # Check required dependencies
    try:
        import yt_dlp
    except ImportError:
        QMessageBox.critical(None, "Dependency Error", "Please install yt-dlp first: pip install yt-dlp")
        sys.exit(1)
    
    # Create window
    window = YouTubeDownloader()
    window.show()
    
    # Execute application
    sys.exit(app.exec_())
