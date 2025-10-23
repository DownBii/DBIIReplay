from typing import Dict, Optional
import json

try:
	from PyQt6 import QtWidgets, QtCore, QtGui
	from PyQt6.QtSvg import QSvgRenderer
except Exception:
	# Provide fallbacks for static analysis or environments without PyQt6.
	QtWidgets = None
	QtCore = None
	QtGui = None
	QSvgRenderer = None

# Optional OpenCV for previewing capture devices. Not required at import time.
try:
    import cv2
except Exception:
    cv2 = None


if QtCore is not None and QtWidgets is not None:
	class VideoCaptureThread(QtCore.QThread):
		"""Background thread that captures frames from a DirectShow device using OpenCV.

		Emits `frameReady` with a QImage for use in the GUI thread.
		"""
		frameReady = QtCore.pyqtSignal(object)

		def __init__(self, device_name: str, parent=None):
			super().__init__(parent)
			self.device_name = device_name
			self._running = True
			self._cap = None

		def run(self):
			if cv2 is None:
				return

			# Try opening the device via DirectShow name (Windows) using dshow input
			# Build OpenCV capture backend string: "video=Device Name"
			try:
				cap_str = f"video={self.device_name}"
				self._cap = cv2.VideoCapture(f"dshow:{cap_str}")
				if not self._cap.isOpened():
					# Try simple index fallback
					try:
						self._cap = cv2.VideoCapture(0)
					except Exception:
						return

				while self._running and self._cap is not None:
					ret, frame = self._cap.read()
					if not ret or frame is None:
						self.msleep(30)
						continue
					# Convert BGR to RGB
					rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
					h, w, ch = rgb.shape
					# Create QImage without copying where possible
					bytes_per_line = ch * w
					qimg = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
					# Emit a deep-copied QImage because the numpy buffer may be reused
					self.frameReady.emit(qimg.copy())
					self.msleep(30)
			finally:
				try:
					if self._cap is not None:
						self._cap.release()
				except Exception:
					pass

		def stop(self):
			self._running = False
			try:
				if self._cap is not None:
					self._cap.release()
			except Exception:
				pass
			try:
				self.wait(1000)
			except Exception:
				pass


class MainWindow:
	"""A small wrapper around a PyQt6 QMainWindow.

	It accepts a config dict with keys: title, width, height.
	Replaces the central label with an SVG icon at `assets/icon.svg` and adds
	a top menu bar with simple animations.
	"""

	def __init__(self, config: Dict = None):
		config = config or {}
		title = config.get("title", "Capsule v0.1")
		width = int(config.get("width", 800))
		height = int(config.get("height", 600))

		if QtWidgets is None:
			raise RuntimeError("PyQt6 is required to create the window")

		self._window = QtWidgets.QMainWindow()
		self._window.setWindowTitle(title)
		self._window.resize(width, height)

		# Create menu bar
		menubar = self._window.menuBar()
		# We'll add a couple of example menus
		file_menu = menubar.addMenu("File")
		view_menu = menubar.addMenu("View")
		help_menu = menubar.addMenu("Help")

		# Example actions
		exit_action = QtGui.QAction("Exit", self._window)
		exit_action.triggered.connect(QtWidgets.QApplication.quit)
		file_menu.addAction(exit_action)

		about_action = QtGui.QAction("About", self._window)
		view_menu.addAction(about_action)

		# Central widget with SVG icon rendered into a QPixmap (for good scaling)
		central = QtWidgets.QWidget()
		layout = QtWidgets.QVBoxLayout(central)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		svg_path = QtCore.QDir.cleanPath(QtCore.QDir.currentPath() + "/assets/icon.svg")
		svg_label = None
		if QSvgRenderer is not None:
			try:
				renderer = QSvgRenderer(svg_path)
				# Target pixmap size: scale to 40% of window width, max 400
				target_w = min(int(width * 0.4), 400)
				target_h = min(int(height * 0.4), 400)
				# Keep aspect ratio: use renderer's default size
				default_size = renderer.defaultSize()
				if default_size.width() > 0 and default_size.height() > 0:
					aspect = default_size.width() / default_size.height()
					if target_w / aspect <= target_h:
						pix_w = target_w
						pix_h = int(target_w / aspect)
					else:
						pix_h = target_h
						pix_w = int(target_h * aspect)
				else:
					pix_w, pix_h = target_w, target_h

				pix = QtGui.QPixmap(pix_w, pix_h)
				pix.fill(QtCore.Qt.GlobalColor.transparent)
				painter = QtGui.QPainter(pix)
				renderer.render(painter)

				# Apply a subtle tint overlay: multiply with a semi-transparent color
				tint_color = QtGui.QColor(100, 180, 255, 70)  # light bluish tint, low alpha
				painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceAtop)
				painter.fillRect(pix.rect(), tint_color)
				painter.end()

				svg_label = QtWidgets.QLabel()
				svg_label.setPixmap(pix)
				svg_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
				svg_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
				container = QtWidgets.QWidget()
				container_layout = QtWidgets.QHBoxLayout(container)
				container_layout.addStretch()
				container_layout.addWidget(svg_label)
				container_layout.addStretch()
				layout.addStretch()
				layout.addWidget(container)
				layout.addStretch()
				# keep references so we can replace the icon with a preview later
				self._icon_label = svg_label
				self._icon_container = container
			except Exception:
				svg_label = None

		if svg_label is None:
			fallback = QtWidgets.QLabel("[icon]")
			fallback.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
			layout.addWidget(fallback)
			self._icon_label = fallback
			self._icon_container = None

		self._window.setCentralWidget(central)

		# Center the window on the screen
		screen = QtWidgets.QApplication.primaryScreen()
		if screen:
			screen_geo = screen.availableGeometry()
			x = (screen_geo.width() - width) // 2
			y = (screen_geo.height() - height) // 2
			self._window.move(x, y)

		# Simple animations: slide-down for menubar and fade-in for icon (if available)
		# Slide menubar: animate its geometry from y=-menubar.height() to y=0
		try:
			menubar_height = menubar.sizeHint().height()
			menubar_anim = QtCore.QPropertyAnimation(menubar, b"geometry", self._window)
			start_rect = QtCore.QRect(0, -menubar_height, width, menubar_height)
			end_rect = QtCore.QRect(0, 0, width, menubar_height)
			menubar_anim.setStartValue(start_rect)
			menubar_anim.setEndValue(end_rect)
			menubar_anim.setDuration(400)
			menubar_anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
			self._menubar_anim = menubar_anim
		except Exception:
			self._menubar_anim = None

		# Fade-in for rendered SVG label
		if svg_label is not None:
			try:
				svg_opacity = QtWidgets.QGraphicsOpacityEffect(svg_label)
				svg_label.setGraphicsEffect(svg_opacity)
				svg_fade = QtCore.QPropertyAnimation(svg_opacity, b"opacity", self._window)
				svg_fade.setStartValue(0.0)
				svg_fade.setEndValue(1.0)
				svg_fade.setDuration(600)
				svg_fade.setEasingCurve(QtCore.QEasingCurve.Type.InOutQuad)
				self._svg_fade = svg_fade
			except Exception:
				self._svg_fade = None
		else:
			self._svg_fade = None

		# Video capture worker placeholder
		self._video_thread = None
		self._preview_label = None

		# If config.json has a capture device, try to start a preview
		try:
			cfg_path = QtCore.QDir.cleanPath(QtCore.QDir.currentPath() + "/config.json")
			with open(cfg_path, 'r', encoding='utf-8') as f:
				cfg = json.load(f)
				if isinstance(cfg, dict) and cfg.get('source') == 'capture' and cfg.get('device'):
					self._start_preview(cfg.get('device'), pix_w if 'pix_w' in locals() else None, pix_h if 'pix_h' in locals() else None)
		except Exception:
			# ignore config/preview failures and keep the icon
			pass

	def show(self):
		self._window.show()
		# start animations if available
		if getattr(self, "_menubar_anim", None) is not None:
			self._menubar_anim.start()
		if getattr(self, "_svg_fade", None) is not None:
			self._svg_fade.start()


	def closeEvent(self, ev):
		# stop preview thread if running
		if getattr(self, '_video_thread', None) is not None:
			try:
				self._video_thread.stop()
			except Exception:
				pass
		return self._window.closeEvent(ev) if hasattr(self._window, 'closeEvent') else None

	def _start_preview(self, device_name: str, target_w: Optional[int] = None, target_h: Optional[int] = None):
		"""Replace the icon with a live preview from the capture device.
		If OpenCV is not available or the device can't be opened, this is a no-op.
		"""
		if cv2 is None:
			# OpenCV not installed; cannot preview
			return

		# Create preview label
		preview = QtWidgets.QLabel()
		preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
		self._preview_label = preview

		# replace icon widget if we have a container
		if getattr(self, '_icon_container', None) is not None:
			# remove current icon widget and insert preview
			container_layout = self._icon_container.layout()
			# assume icon is at index 1 (stretch, icon, stretch)
			for i in range(container_layout.count()):
				w = container_layout.itemAt(i).widget()
				if w is getattr(self, '_icon_label', None):
					container_layout.removeWidget(w)
					w.setParent(None)
					break
			container_layout.addWidget(preview)
		else:
			# last resort: add to main layout
			self._window.centralWidget().layout().addWidget(preview)

		# Start worker thread
		worker = VideoCaptureThread(device_name, parent=self._window)
		worker.frameReady.connect(lambda qimg: self._on_frame(qimg, target_w, target_h))
		self._video_thread = worker
		worker.start()

	def _on_frame(self, qimg, target_w: Optional[int], target_h: Optional[int]):
		# Scale and set pixmap
		pix = QtGui.QPixmap.fromImage(qimg)
		if target_w and target_h:
			pix = pix.scaled(target_w, target_h, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
		if getattr(self, '_preview_label', None) is not None:
			self._preview_label.setPixmap(pix)

	# Expose a few convenience methods to mimic a Qt window object
	def resize(self, w: int, h: int):
		self._window.resize(w, h)

	def setWindowTitle(self, title: str):
		self._window.setWindowTitle(title)
