import sys
import os
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QTextEdit, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal

class ExporterThread(QThread):
    output_signal = Signal(str)
    finished_signal = Signal(int)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd

    def run(self):
        process = subprocess.Popen(
            self.cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in iter(process.stdout.readline, ''):
            self.output_signal.emit(line)
        process.stdout.close()
        process.wait()
        self.finished_signal.emit(process.returncode)

class AutoRiggerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live2D Auto Rigger - Desktop Launcher")
        self.resize(650, 450)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Input File
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Input File (PSD/PNG) or Folder:"))
        self.input_edit = QLineEdit()
        row1.addWidget(self.input_edit)
        btn_browse_in = QPushButton("Browse...")
        btn_browse_in.clicked.connect(self.browse_input)
        row1.addWidget(btn_browse_in)
        layout.addLayout(row1)

        # Output Folder
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Output Directory:"))
        self.output_edit = QLineEdit(os.path.join(os.getcwd(), "output"))
        row2.addWidget(self.output_edit)
        btn_browse_out = QPushButton("Browse...")
        btn_browse_out.clicked.connect(self.browse_output)
        row2.addWidget(btn_browse_out)
        layout.addLayout(row2)

        # Model Name
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Model Name:"))
        self.name_edit = QLineEdit("MyAvatar")
        row3.addWidget(self.name_edit)
        layout.addLayout(row3)
        
        # Options
        self.validate_check = QCheckBox("Run Structural Validation (Recommended)")
        self.validate_check.setChecked(True)
        layout.addWidget(self.validate_check)

        # Generate Button
        self.btn_generate = QPushButton("🚀 Generate Live2D Model")
        self.btn_generate.setStyleSheet("font-size: 14pt; padding: 10px; font-weight: bold; background-color: #4CAF50; color: white;")
        self.btn_generate.clicked.connect(self.run_export)
        layout.addWidget(self.btn_generate)

        # Console Output
        layout.addWidget(QLabel("Console Output:"))
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.console)

    def browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Input PSD or PNG", "", "Images (*.psd *.png);;All Files (*)")
        if not path:
            path = QFileDialog.getExistingDirectory(self, "Select Folder of Layer PNGs")
        if path:
            self.input_edit.setText(path)

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.output_edit.setText(path)

    def run_export(self):
        input_path = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()
        model_name = self.name_edit.text().strip()

        if not input_path:
            QMessageBox.warning(self, "Error", "Please select an input file or folder.")
            return

        cmd = [sys.executable, "export_live2d.py", input_path, "-o", output_path, "-n", model_name]
        if self.validate_check.isChecked():
            cmd.append("--validate")

        self.btn_generate.setEnabled(False)
        self.console.clear()
        self.console.append(f"Running command: {' '.join(cmd)}\n")

        self.thread = ExporterThread(cmd)
        self.thread.output_signal.connect(self.append_log)
        self.thread.finished_signal.connect(self.export_finished)
        self.thread.start()

    def append_log(self, text):
        self.console.insertPlainText(text)
        self.console.ensureCursorVisible()

    def export_finished(self, returncode):
        self.btn_generate.setEnabled(True)
        if returncode == 0:
            QMessageBox.information(self, "Success", f"Model generated successfully!\nSaved to: {self.output_edit.text()}")
        else:
            QMessageBox.critical(self, "Failed", f"Process exited with error code {returncode}. Check console output.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AutoRiggerApp()
    window.show()
    sys.exit(app.exec())
