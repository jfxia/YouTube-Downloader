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
            # 获取视频信息
            ydl_info = yt_dlp.YoutubeDL({
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True
            })
            info_dict = ydl_info.extract_info(self.url, download=False)
            
            if not info_dict:
                raise Exception("无法获取视频信息，请检查URL是否有效")
                
            self.video_info = {
                'title': info_dict.get('title', '未知视频'),
                'description': info_dict.get('description', ''),
                'thumbnail': info_dict.get('thumbnail', ''),
                'duration': self.format_duration(info_dict.get('duration', 0)),
                'uploader': info_dict.get('uploader', '未知上传者'),
                'view_count': self.format_count(info_dict.get('view_count', 0))
            }
            
            # 发送缩略图信号
            if self.video_info['thumbnail']:
                self.thumbnail_signal.emit(self.video_info['thumbnail'])
            
            # 设置下载格式
            format_mapping = {
                'best': 'bestvideo+bestaudio/best',
                '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                '480p': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
                '360p': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
                'audio_only': 'bestaudio/best'
            }
            
            ydl_opts = {
                'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
                'format': format_mapping.get(self.quality, 'bestvideo+bestaudio/best'),
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'writethumbnail': True,  # 下载缩略图
                'postprocessors': [{
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': True
                }]
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
                
            if not self.cancelled:
                self.finished_signal.emit(True, "下载完成!", self.video_info['title'], self.video_info)
                
        except Exception as e:
            self.finished_signal.emit(False, f"错误: {str(e)}", self.video_info.get('title', '未知视频'), {})
    
    def progress_hook(self, d):
        if self.cancelled:
            raise Exception("下载已取消")
            
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                percent = d['downloaded_bytes'] / total * 100
                speed = d.get('speed')
                speed_str = f"{speed / 1024:.1f} KB/s" if speed else "未知速度"
                self.progress_signal.emit(percent, speed_str, self.video_info.get('title', '未知视频'), d)
    
    def cancel(self):
        self.cancelled = True
        
    def format_duration(self, seconds):
        """格式化视频时长"""
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
        
    def format_count(self, count):
        """格式化观看次数"""
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
        self.setWindowTitle("YouTube视频下载器")
        self.setGeometry(100, 100, 1000, 700)  # 增大窗口尺寸
        self.setMinimumSize(900, 600)  # 增大最小尺寸
        
        # 初始化变量
        self.download_thread = None
        self.download_timer = QTimer(self)
        self.download_timer.timeout.connect(self.update_eta)
        self.eta_remaining = 0
        self.last_progress_time = 0
        
        # 创建主部件和布局
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # 设置应用样式
        self.setStyle()
        
        # 标题区域
        title_layout = QHBoxLayout()
        title_label = QLabel("YouTube视频下载器")
        title_label.setFont(QFont("微软雅黑 Light", 18, QFont.Bold))  # 修改为目标字体
        title_label.setStyleSheet("color: #2c3e50;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # 添加图标
        icon_label = QLabel()
        try:
            icon_pixmap = QPixmap("youtube_icon.png").scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(icon_pixmap)
        except:
            icon_label.setText("YT")
            icon_label.setFont(QFont("微软雅黑 Light", 16, QFont.Bold))  # 修改为目标字体
            icon_label.setStyleSheet("color: #ff0000; background-color: #ffffff; padding: 5px; border-radius: 4px;")
        title_layout.addWidget(icon_label)
        
        # 创建标签页
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("QTabWidget::pane { border: none; }")
        
        # 主下载标签页
        main_tab = QWidget()
        main_tab_layout = QVBoxLayout()
        main_tab_layout.setContentsMargins(0, 0, 0, 0)
        main_tab_layout.setSpacing(10)
        
        # URL输入部分
        url_group = QGroupBox("视频URL")
        url_group.setFont(QFont("微软雅黑 Light", 10, QFont.Bold))  # 修改为目标字体
        url_layout = QHBoxLayout()
        url_layout.setContentsMargins(15, 10, 15, 10)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入YouTube视频链接...")
        self.url_input.setMinimumHeight(36)
        self.url_input.setFont(QFont("微软雅黑 Light", 10))  # 修改为目标字体
        self.url_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 8px 12px;
            }
            QLineEdit:focus {
                border-color: #3498db;
                box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.25);
            }
        """)
        url_layout.addWidget(self.url_input, 1)
        
        self.paste_btn = QPushButton("粘贴")
        self.paste_btn.setMinimumHeight(36)
        self.paste_btn.setFont(QFont("微软雅黑 Light", 9, QFont.Bold))  # 修改为目标字体
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
        
        # 视频信息部分
        info_group = QGroupBox("视频信息")
        info_group.setFont(QFont("微软雅黑 Light", 10, QFont.Bold))  # 修改为目标字体
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(15, 10, 15, 10)
        info_layout.setSpacing(15)
        
        # 缩略图区域
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
        self.thumbnail_label.setText("暂无缩略图")
        thumbnail_layout.addWidget(self.thumbnail_label)
        
        info_layout.addWidget(thumbnail_frame)
        
        # 视频信息文本区域
        info_text_layout = QVBoxLayout()
        info_text_layout.setSpacing(8)
        
        # 视频标题
        title_layout = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setFont(QFont("微软雅黑 Light", 11, QFont.Bold))  # 修改为目标字体
        self.title_label.setStyleSheet("color: #212529;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        info_text_layout.addLayout(title_layout)
        
        # 视频元信息
        meta_info_layout = QVBoxLayout()
        meta_info_layout.setSpacing(4)
        
        self.uploader_label = QLabel("")
        self.uploader_label.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.uploader_label.setStyleSheet("color: #6c757d;")
        meta_info_layout.addWidget(self.uploader_label)
        
        self.views_label = QLabel("")
        self.views_label.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.views_label.setStyleSheet("color: #6c757d;")
        meta_info_layout.addWidget(self.views_label)
        
        self.duration_label = QLabel("")
        self.duration_label.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.duration_label.setStyleSheet("color: #6c757d;")
        meta_info_layout.addWidget(self.duration_label)
        
        info_text_layout.addLayout(meta_info_layout)
        
        # 视频描述
        self.description_label = QLabel("")
        self.description_label.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.description_label.setStyleSheet("color: #495057;")
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        info_text_layout.addWidget(self.description_label)
        
        info_layout.addLayout(info_text_layout)
        info_layout.addStretch()
        
        info_group.setLayout(info_layout)
        main_tab_layout.addWidget(info_group)
        
        # 下载选项
        options_group = QGroupBox("下载选项")
        options_group.setFont(QFont("微软雅黑 Light", 10, QFont.Bold))  # 修改为目标字体
        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(15, 10, 15, 10)
        options_layout.setSpacing(15)
        
        # 质量选择
        quality_layout = QVBoxLayout()
        quality_layout.addWidget(QLabel("视频质量:"))
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["最佳质量", "1080p","720p", "480p", "360p", "仅音频"])
        self.quality_combo.setCurrentIndex(0)
        self.quality_combo.setMinimumHeight(32)
        self.quality_combo.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        quality_layout.addWidget(self.quality_combo)
        
        options_layout.addLayout(quality_layout)
        
        # 保存路径
        path_layout = QVBoxLayout()
        path_layout.addWidget(QLabel("保存路径:"))
        
        path_hbox = QHBoxLayout()
        
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setMinimumHeight(32)
        self.path_display.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.path_display.setText(os.path.expanduser("~/Downloads"))
        path_hbox.addWidget(self.path_display, 1)
        
        browse_btn = QPushButton("浏览...")
        browse_btn.setMinimumHeight(32)
        browse_btn.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
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
        
        # 进度显示组
        progress_group = QGroupBox("下载进度")
        progress_group.setFont(QFont("微软雅黑 Light", 10, QFont.Bold))  # 修改为目标字体
        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(15, 10, 15, 10)
        progress_layout.setSpacing(8)
        
        # 进度条区域
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
        
        # 进度信息
        progress_info_layout = QHBoxLayout()
        progress_info_layout.setSpacing(15)
        
        self.percentage_label = QLabel("0%")
        self.percentage_label.setFont(QFont("微软雅黑 Light", 10, QFont.Bold))  # 修改为目标字体
        self.percentage_label.setStyleSheet("color: #3498db; min-width: 40px;")
        
        self.speed_label = QLabel("准备下载...")
        self.speed_label.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.speed_label.setStyleSheet("color: #6c757d;")
        
        self.eta_label = QLabel("剩余时间: --:--")
        self.eta_label.setFont(QFont("微软雅黑 Light", 9))  # 修改为目标字体
        self.eta_label.setStyleSheet("color: #6c757d;")
        
        progress_info_layout.addWidget(self.percentage_label)
        progress_info_layout.addWidget(self.speed_label)
        progress_info_layout.addWidget(self.eta_label)
        progress_info_layout.addStretch()
        
        progress_layout.addLayout(progress_info_layout)
        progress_layout.addWidget(self.progress_bar)
        
        progress_group.setLayout(progress_layout)
        main_tab_layout.addWidget(progress_group)
        
        # 按钮部分
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 5, 0, 5)
        button_layout.setSpacing(15)
        
        self.download_btn = QPushButton("开始下载")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.setFont(QFont("微软雅黑 Light", 10, QFont.Bold))  # 修改为目标字体
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
        
        self.cancel_btn = QPushButton("取消下载")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setFont(QFont("微软雅黑 Light", 10))  # 修改为目标字体
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
        
        # 历史记录标签页
        history_tab = QWidget()
        history_layout = QVBoxLayout()
        history_layout.setContentsMargins(0, 0, 0, 0)
        
        history_frame = QFrame()
        history_frame.setStyleSheet("background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 4px;")
        history_frame_layout = QVBoxLayout()
        history_frame_layout.setContentsMargins(15, 15, 15, 15)
        
        # 历史记录为空时的提示
        self.history_empty_label = QLabel("暂无下载历史")
        self.history_empty_label.setFont(QFont("微软雅黑 Light", 10))  # 修改为目标字体
        self.history_empty_label.setStyleSheet("color: #6c757d;")
        self.history_empty_label.setAlignment(Qt.AlignCenter)
        self.history_empty_label.setMinimumHeight(200)
        
        history_frame_layout.addWidget(self.history_empty_label)
        
        # 历史记录列表将在这里动态添加
        
        history_frame.setLayout(history_frame_layout)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(history_frame)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        history_layout.addWidget(scroll_area)
        history_tab.setLayout(history_layout)
        
        # 添加标签页
        tab_widget.addTab(main_tab, "下载")
        tab_widget.addTab(history_tab, "历史记录")
        
        # 状态栏
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.StyledPanel)
        status_frame.setStyleSheet("background-color: #f8f9fa; border-top: 1px solid #e9ecef;")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(10, 5, 10, 5)
        self.status_label = QLabel("就绪")
        self.status_label.setFont(QFont("微软雅黑 Light", 8))  # 修改为目标字体
        self.status_label.setStyleSheet("color: #6c757d;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        # 添加版本信息
        version_label = QLabel("版本: 1.2.0")
        version_label.setFont(QFont("微软雅黑 Light", 8))  # 修改为目标字体
        version_label.setStyleSheet("color: #6c757d;")
        status_layout.addWidget(version_label)
        
        status_frame.setLayout(status_layout)
        
        # 组装主布局
        main_layout.addLayout(title_layout)
        main_layout.addWidget(tab_widget)
        main_layout.addWidget(status_frame)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # 设置窗口图标
        try:
            self.setWindowIcon(QIcon("youtube_icon.png"))
        except:
            pass
    
    def setStyle(self):
        # 设置全局样式
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
                font-family: "微软雅黑 Light";  # 修改为目标字体
                font-weight: 500;
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
        path = QFileDialog.getExistingDirectory(self, "选择保存目录", self.path_display.text())
        if path:
            self.path_display.setText(path)
    
    def start_download(self):
        url = self.url_input.text().strip()
        output_dir = self.path_display.text()
        
        if not url:
            QMessageBox.warning(self, "输入错误", "请输入YouTube视频URL")
            return
            
        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "路径错误", "指定的保存路径无效")
            return
            
        # 禁用UI元素
        self.url_input.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.percentage_label.setText("0%")
        self.speed_label.setText("准备下载...")
        self.eta_label.setText("剩余时间: --:--")
        self.status_label.setText("开始下载...")
        
        # 重置视频信息
        self.title_label.setText("")
        self.uploader_label.setText("")
        self.views_label.setText("")
        self.duration_label.setText("")
        self.description_label.setText("")
        self.thumbnail_label.setText("加载中...")
        
        # 获取质量选项
        quality_mapping = {
            "最佳质量": "best",
            "1080p": "1080p",
            "720p": "720p",
            "480p": "480p",
            "360p": "360p",
            "仅音频": "audio_only"
        }
        quality = quality_mapping[self.quality_combo.currentText()]
        
        # 创建并启动下载线程
        self.download_thread = DownloadThread(url, output_dir, quality)
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.thumbnail_signal.connect(self.load_thumbnail)
        self.download_thread.start()
        
        # 启动计时器更新ETA
        self.last_progress_time = 0
        self.download_timer.start(1000)
    
    def cancel_download(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.status_label.setText("正在取消下载...")
    
    def load_thumbnail(self, url):
        """加载并显示视频缩略图"""
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
            self.thumbnail_label.setText("无法加载缩略图")
            print(f"Error loading thumbnail: {e}")
    
    def update_progress(self, percent, speed, title, data):
        """更新下载进度"""
        # 更新进度条
        self.progress_bar.setValue(int(percent))
        self.percentage_label.setText(f"{int(percent)}%")
        self.speed_label.setText(f"下载速度: {speed}")
        
        # 更新视频信息（如果尚未设置）
        if not self.title_label.text() and title:
            self.title_label.setText(title)
        
        # 计算剩余时间
        if percent > 0 and percent < 100:
            current_time = data.get('elapsed', 0)
            if current_time > self.last_progress_time and current_time > 0:
                # 计算平均速度和估计剩余时间
                downloaded_bytes = data.get('downloaded_bytes', 0)
                total_bytes = data.get('total_bytes') or data.get('total_bytes_estimate', 0)
                
                if total_bytes > 0:
                    avg_speed = downloaded_bytes / current_time if current_time > 0 else 0
                    remaining_bytes = total_bytes - downloaded_bytes
                    
                    if avg_speed > 0:
                        remaining_seconds = remaining_bytes / avg_speed
                        self.eta_remaining = remaining_seconds
        
        # 更新状态
        self.status_label.setText(f"下载中: {int(percent)}% 完成")
    
    def update_eta(self):
        """更新剩余时间显示"""
        if self.eta_remaining > 0:
            mins = int(self.eta_remaining / 60)
            secs = int(self.eta_remaining % 60)
            self.eta_label.setText(f"剩余时间: {mins:02d}:{secs:02d}")
            self.eta_remaining -= 1
    
    def download_finished(self, success, message, title, video_info):
        """下载完成后的处理"""
        # 停止计时器
        self.download_timer.stop()
        
        # 启用UI元素
        self.url_input.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        # 更新视频信息（如果有）
        if video_info:
            self.title_label.setText(video_info.get('title', '未知视频'))
            self.uploader_label.setText(f"上传者: {video_info.get('uploader', '未知上传者')}")
            self.views_label.setText(f"观看次数: {video_info.get('view_count', '0')}")
            self.duration_label.setText(f"时长: {video_info.get('duration', '0:00')}")
            self.description_label.setText(video_info.get('description', '无描述'))
        
        # 显示结果消息
        if success:
            self.status_label.setText(f"下载完成: {title}")
            self.speed_label.setText("下载完成")
            self.eta_label.setText("")
            self.progress_bar.setValue(100)
            self.percentage_label.setText("100%")
            
            # 显示成功消息
            QMessageBox.information(self, "下载完成", f"视频 '{title}' 下载成功！")
            
            # TODO: 保存到历史记录
        else:
            self.status_label.setText(f"下载失败: {message}")
            self.speed_label.setText("下载失败")
            self.eta_label.setText("")
            
            # 显示错误消息
            if "下载已取消" not in message:
                QMessageBox.critical(self, "下载失败", message)
        
        self.download_thread = None


if __name__ == "__main__":
    # 创建应用
    app = QApplication(sys.argv)
    
    # 设置字体
    font = QFont("微软雅黑 Light")
    if not font.exactMatch():  # 如果找不到"微软雅黑 Light"
        font = QFont("微软雅黑")  # 尝试使用"微软雅黑"
    app.setFont(font)
    
    # 检查必要依赖
    try:
        import yt_dlp
    except ImportError:
        QMessageBox.critical(None, "依赖错误", "请先安装yt-dlp: pip install yt-dlp")
        sys.exit(1)
    
    # 创建窗口
    window = YouTubeDownloader()
    window.show()
    
    # 执行应用
    sys.exit(app.exec_())
