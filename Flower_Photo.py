import sys, os
from PyQt6 import QtCore, QtGui, QtWidgets

from mainwin import Ui_MainWindow
from rename import Ui_renameselectfolder
from photo import Ui_Photo

# ---------- Helpers ----------
def sanitize_filename(name: str) -> str:
    forbidden = '<>:"/\\|?*'
    cleaned = ''.join('_' if ch in forbidden else ch for ch in name)
    cleaned = cleaned.strip().rstrip('.')
    return cleaned

def supported_image_extensions():
    fmts = QtGui.QImageReader.supportedImageFormats()
    return {fmt.data().decode('ascii').lower() for fmt in fmts}

def is_image_file(path: str, extset=None) -> bool:
    if not os.path.isfile(path):
        return False
    if extset is None:
        extset = supported_image_extensions()
    ext = os.path.splitext(path)[1][1:].lower()
    return ext in extset

# ---------- Main (home) Window ----------
class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        image_path = os.path.join(os.path.dirname(__file__), "image-imageicon.png")
        self.label_3.setPixmap(QtGui.QPixmap(image_path))
        self.label_3.setScaledContents(True)

        for w in (self.label_3, self.RenameLabel):
            w.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
            w.installEventFilter(self)

        self.RenameButton.clicked.connect(self.open_rename_window)

        self.rename_window = None
        self.photo_window = None

    def eventFilter(self, obj, event):
        if (event.type() == QtCore.QEvent.Type.MouseButtonRelease and
            event.button() == QtCore.Qt.MouseButton.LeftButton and
            obj in (self.label_3, self.RenameLabel)):
            self.RenameButton.click()
            return True
        return super().eventFilter(obj, event)

    def open_rename_window(self):
        if self.rename_window is None:
            self.rename_window = RenameWindow(
                open_photo_window=self.open_photo_window_from_folder
            )
        self.hide()
        self.rename_window.show()

    def open_photo_window_from_folder(self, folder_path: str):
        def back_to_main(cancelled=False):
            if self.rename_window:
                self.rename_window.hide()
            self.show()

        self.photo_window = PhotoWindow(folder_path, on_done=back_to_main)
        self.rename_window.hide()
        self.photo_window.show()
# ---------- Rename (select folder) Window ----------
class RenameWindow(QtWidgets.QWidget):
    def __init__(self, parent=None, open_photo_window=None):
        super().__init__(parent)
        self.ui = Ui_renameselectfolder()
        self.ui.setupUi(self)

        self.setAcceptDrops(True)  # allow dropping anywhere
        self.selected_folder = None
        self.open_photo_window = open_photo_window  # callback to open photo window

        # Click-to-choose (label_3 or pushButton)
        self.ui.label_3.installEventFilter(self)
        self.ui.label_3.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.ui.pushButton.clicked.connect(self.choose_folder)

    # ----- Drag detection -----
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and os.path.isdir(urls[0].toLocalFile()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            folder_path = urls[0].toLocalFile()
            if os.path.isdir(folder_path):
                self.set_selected_folder(folder_path)

    # ----- Click detection -----
    def eventFilter(self, obj, event):
        if obj == self.ui.label_3 and event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            self.choose_folder()
            return True
        return super().eventFilter(obj, event)

    # ----- Folder choosing -----
    def choose_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.set_selected_folder(folder)

    def set_selected_folder(self, folder_path):
        self.selected_folder = folder_path
        if self.open_photo_window:
            self.open_photo_window(folder_path)
# ---------- Photo Window ----------
class EnterShortcutFilter(QtCore.QObject):
    """Maps Enter to Next and Shift+Enter to Previous wherever focus is."""
    def __init__(self, on_next, on_prev, parent=None):
        super().__init__(parent)
        self.on_next = on_next
        self.on_prev = on_prev

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.on_prev()
                else:
                    self.on_next()
                return True
        return super().eventFilter(obj, event)


class PhotoWindow(QtWidgets.QWidget):
    MAX_DISPLAY_W = 1920
    MAX_DISPLAY_H = 1080

    def __init__(self, folder_path: str, on_done=None, parent=None):
        super().__init__(parent)
        self.ui = Ui_Photo()
        self.ui.setupUi(self)

        self.folder = folder_path
        self.on_done = on_done

        # Collect images
        extset = supported_image_extensions()
        entries = sorted(os.listdir(self.folder))
        self.images = [
            os.path.join(self.folder, f)
            for f in entries
            if is_image_file(os.path.join(self.folder, f), extset)
        ]
        if not self.images:
            QtWidgets.QMessageBox.information(self, "No images found",
                                              "The selected folder has no image files.")
            if self.on_done:
                self.on_done(cancelled=True)
            self.close()
            return

        self.names = ["" for _ in self.images]
        self.index = 0
        self.current_pixmap = None

        # Wire buttons based on your .ui names
        self.ui.pushButton_2.setText("Previous")
        self.ui.pushButton_2.clicked.connect(self.on_prev)
        self.ui.pushButton.setText("Next")
        self.ui.pushButton.clicked.connect(self.on_next)

        # Install Enter/Shift+Enter handler
        self._enter_filter = EnterShortcutFilter(self.on_next, self.on_prev, self)
        self.installEventFilter(self._enter_filter)
        self.ui.lineEdit.installEventFilter(self._enter_filter)

        self.show_image()

    def show_image(self):
        path = self.images[self.index]
        pix = QtGui.QPixmap(path)
        if pix.isNull():
            pix = QtGui.QPixmap(200, 200)
            pix.fill(QtGui.QColor("lightgray"))
        self.current_pixmap = pix

        self._resize_window_to_image()

        self.ui.label.setPixmap(self._scaled_for_label())
        total = len(self.images)
        self.ui.label_2.setText(f"Photo {self.index+1}/{ '♾️' if total>999 else total }")
        self.ui.lineEdit.setText(self.names[self.index])
        self.ui.lineEdit.setFocus()
        self.ui.lineEdit.selectAll()
        self.ui.pushButton_2.setEnabled(self.index > 0)
        self.ui.pushButton.setText("Finish" if self.index == total - 1 else "Next")

    def _resize_window_to_image(self):
        if not self.current_pixmap:
            return
        w, h = self.current_pixmap.width(), self.current_pixmap.height()
        scale = min(1.0, self.MAX_DISPLAY_W / w, self.MAX_DISPLAY_H / h)
        disp_w, disp_h = int(w * scale), int(h * scale)

        layout = self.layout()
        if layout:
            margins = layout.contentsMargins()
            spacing = layout.spacing()
        else:
            margins = QtCore.QMargins(0, 0, 0, 0)
            spacing = 0

        extra_h = (self.ui.lineEdit.sizeHint().height() +
                   self.ui.pushButton.sizeHint().height() +
                   (spacing * 2) + margins.top() + margins.bottom())
        extra_w = margins.left() + margins.right()
        self.resize(max(disp_w+extra_w, 600), max(disp_h+extra_h, 500))

    def _scaled_for_label(self):
        return self.current_pixmap.scaled(
            self.ui.label.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_pixmap:
            self.ui.label.setPixmap(self._scaled_for_label())

    def save_current_name(self):
        self.names[self.index] = self.ui.lineEdit.text().strip()

    def on_next(self):
        self.save_current_name()
        if self.index == len(self.images) - 1:
            self.finalize_and_rename()
            return
        self.index += 1
        self.show_image()

    def on_prev(self):
        self.save_current_name()
        if self.index > 0:
            self.index -= 1
            self.show_image()

    def finalize_and_rename(self):
        reply = QtWidgets.QMessageBox.question(
            self, "Rename photos",
            "Finish and rename the photos now?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        renamed, skipped = 0, 0
        for i, src in enumerate(self.images):
            base, ext = os.path.splitext(os.path.basename(src))
            new_stem = sanitize_filename(self.names[i].strip())
            if not new_stem:
                skipped += 1
                continue
            dst = os.path.join(self.folder, new_stem + ext)
            if os.path.abspath(dst) == os.path.abspath(src):
                skipped += 1
                continue
            if os.path.exists(dst):
                k = 1
                while True:
                    candidate = os.path.join(self.folder, f"{new_stem}-{k}{ext}")
                    if not os.path.exists(candidate):
                        dst = candidate
                        break
                    k += 1
            try:
                os.rename(src, dst)
                renamed += 1
                self.images[i] = dst
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, "Rename error",
                    f"Could not rename:\n{os.path.basename(src)}\n→ {os.path.basename(dst)}\n\n{e}"
                )

        QtWidgets.QMessageBox.information(
            self, "Done",
            f"Renaming complete.\nRenamed: {renamed}\nUnchanged: {skipped}"
        )

        if self.on_done:
            self.on_done(cancelled=False)
        self.close()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
