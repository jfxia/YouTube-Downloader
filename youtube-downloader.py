import os
import sys
import yt_dlp
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QProgressBar, QFileDialog,
                             QMessageBox, QFrame, QGroupBox, QSizePolicy, QSpacerItem,
                             QTabWidget, QSplitter, QScrollArea, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QImage, QPainter, QPen
import requests
from io import BytesIO
import platform


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
        
    def run(self):
        try:
            # Get video information
            ydl_info = yt_dlp.YoutubeDL({
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True
            })
            info_dict = ydl_info.extract_info(self.url, download=False)
            
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
            
            # Emit thumbnail signal
            if self.video_info['thumbnail']:
                self.thumbnail_signal.emit(self.video_info['thumbnail'])
            
            # Set download format
            format_mapping = {
                'best': 'bestvideo+bestaudio/best',
                '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                '480p': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
                '360p': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
                'audio_only': 'bestaudio/best'  # 保持原始音频流选择
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
                self.finished_signal.emit(True, "Download completed!", self.video_info['title'], self.video_info)
                
        except Exception as e:
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
        
        # Initialize variables
        self.download_thread = None
        self.download_timer = QTimer(self)
        self.download_timer.timeout.connect(self.update_eta)
        self.eta_remaining = 0
        self.last_progress_time = 0
        
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
                padding: 8px 12px;
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
        
        history_frame = QFrame()
        history_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 4px;")
        history_frame_layout = QVBoxLayout()
        history_frame_layout.setContentsMargins(15, 15, 15, 15)
        
        # Empty history message
        self.history_empty_label = QLabel("No download history")
        self.history_empty_label.setFont(QFont("Segoe UI", 10))  
        self.history_empty_label.setStyleSheet("color: #6c757d;")
        self.history_empty_label.setAlignment(Qt.AlignCenter)
        self.history_empty_label.setMinimumHeight(200)
        
        history_frame_layout.addWidget(self.history_empty_label)
        
        # History list will be dynamically added here
        
        history_frame.setLayout(history_frame_layout)
        
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
        """Load and display video thumbnail"""
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.content
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                scaled_pixmap = pixmap.scaled(
                    self.thumbnail_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.thumbnail_label.setPixmap(scaled_pixmap)
                self.thumbnail_label.setText("")
        except Exception as e:
            self.thumbnail_label.setText("Failed to load thumbnail")
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
            
            # TODO: Save to history
        else:
            self.status_label.setText(f"Download failed: {message}")
            self.speed_label.setText("Download failed")
            self.eta_label.setText("")
            
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
