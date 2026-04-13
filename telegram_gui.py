"""
Telegram-like Messenger - ИСПРАВЛЕННАЯ ВЕРСИЯ
Сообщения теперь точно видны
"""

import sys
import json
import asyncio
import requests
import websockets
from datetime import datetime
from threading import Thread, Lock
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

API_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

# Стиль как в Telegram
STYLE = """
QMainWindow {
    background-color: #0F0F0F;
}
QListWidget {
    background-color: #1E1E1E;
    border: none;
    color: #FFFFFF;
    font-size: 14px;
    outline: none;
}
QListWidget::item {
    padding: 12px;
    border-bottom: 1px solid #2B2B2B;
}
QListWidget::item:selected {
    background-color: #2B5278;
}
QTextEdit {
    background-color: #1E1E1E;
    border: 1px solid #2B2B2B;
    border-radius: 8px;
    color: #FFFFFF;
    font-size: 14px;
    padding: 10px;
}
QLineEdit {
    background-color: #1E1E1E;
    border: 1px solid #2B2B2B;
    border-radius: 20px;
    color: #FFFFFF;
    font-size: 14px;
    padding: 10px 15px;
}
QPushButton {
    background-color: #2B5278;
    border: none;
    border-radius: 20px;
    color: white;
    font-size: 14px;
    font-weight: bold;
    padding: 10px 20px;
}
QPushButton:hover {
    background-color: #3B6E9E;
}
"""

class MessageBubble(QWidget):
    def __init__(self, text, sender, is_own=False, timestamp=""):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)
        
        bubble = QFrame()
        bubble.setObjectName("bubble")
        
        if is_own:
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: #2B5278;
                    border-radius: 12px;
                    padding: 8px 12px;
                    margin: 2px;
                }
            """)
            layout.addStretch()
        else:
            bubble.setStyleSheet("""
                QFrame#bubble {
                    background-color: #1E1E1E;
                    border-radius: 12px;
                    padding: 8px 12px;
                    margin: 2px;
                }
            """)
        
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(3)
        
        if not is_own:
            name_label = QLabel(sender)
            name_label.setStyleSheet("color: #2B5278; font-size: 11px; font-weight: bold;")
            bubble_layout.addWidget(name_label)
        
        msg_label = QLabel(text)
        msg_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        msg_label.setWordWrap(True)
        bubble_layout.addWidget(msg_label)
        
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("color: #8E8E8E; font-size: 10px;")
        time_label.setAlignment(Qt.AlignRight)
        bubble_layout.addWidget(time_label)
        
        bubble.setLayout(bubble_layout)
        
        if is_own:
            layout.addWidget(bubble)
        else:
            layout.addWidget(bubble)
            layout.addStretch()
        
        self.setLayout(layout)

class ChatWindow(QMainWindow):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.current_chat = None
        self.websocket = None
        self.websocket_thread = None
        self.running = True
        self.messages = {}  # {chat_username: [{"text": str, "from": str, "timestamp": str, "is_own": bool}]}
        self.lock = Lock()
        self.init_ui()
        self.start_websocket()
        self.load_users()
        
    def init_ui(self):
        self.setWindowTitle(f"Telegram Messenger - {self.username}")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Левая панель
        left_panel = QWidget()
        left_panel.setMaximumWidth(280)
        left_panel.setMinimumWidth(250)
        left_panel.setStyleSheet("background-color: #1E1E1E;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # Шапка
        profile_header = QWidget()
        profile_header.setStyleSheet("padding: 15px; border-bottom: 1px solid #2B2B2B;")
        profile_layout = QHBoxLayout(profile_header)
        
        avatar = QLabel("📱")
        avatar.setStyleSheet("font-size: 32px;")
        profile_layout.addWidget(avatar)
        
        name_label = QLabel(self.username)
        name_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        profile_layout.addWidget(name_label)
        profile_layout.addStretch()
        
        left_layout.addWidget(profile_header)
        
        # Список чатов
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        left_layout.addWidget(self.chat_list)
        
        # Правая панель
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        self.chat_header = QLabel("Выберите чат")
        self.chat_header.setObjectName("chatHeader")
        self.chat_header.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF; font-size: 18px; font-weight: bold; padding: 15px; border-bottom: 1px solid #2B2B2B;")
        self.chat_header.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.chat_header)
        
        # Область сообщений
        self.messages_area = QScrollArea()
        self.messages_area.setWidgetResizable(True)
        self.messages_area.setStyleSheet("background-color: #0F0F0F; border: none;")
        
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch()
        
        self.messages_area.setWidget(self.messages_container)
        right_layout.addWidget(self.messages_area)
        
        # Панель ввода
        input_widget = QWidget()
        input_widget.setStyleSheet("background-color: #1E1E1E; padding: 10px;")
        input_layout = QHBoxLayout(input_widget)
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Сообщение...")
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input)
        
        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #2B5278;
                border-radius: 20px;
                font-size: 18px;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)
        
        right_layout.addWidget(input_widget)
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
    
    def add_message_to_ui(self, sender, text, timestamp, is_own):
        """Добавляет сообщение в интерфейс (должен вызываться в главном потоке)"""
        bubble = MessageBubble(text, sender, is_own, timestamp)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        # Прокрутка вниз
        QTimer.singleShot(100, lambda: self.messages_area.verticalScrollBar().setValue(
            self.messages_area.verticalScrollBar().maximum()
        ))
    
    def add_message(self, sender, text, timestamp, is_own=False):
        """Сохраняет сообщение и отображает его"""
        # Сохраняем в историю
        if sender not in self.messages:
            self.messages[sender] = []
        self.messages[sender].append({
            "text": text,
            "from": sender,
            "is_own": is_own,
            "timestamp": timestamp
        })
        
        # Если это текущий чат - отображаем
        if self.current_chat == sender or (is_own and self.current_chat):
            # Обновляем UI в главном потоке
            QMetaObject.invokeMethod(self, "add_message_to_ui",
                Qt.QueuedConnection,
                Q_ARG(str, sender),
                Q_ARG(str, text),
                Q_ARG(str, timestamp),
                Q_ARG(bool, is_own))
    
    @pyqtSlot(str, str, str, bool)
    def add_message_to_ui(self, sender, text, timestamp, is_own):
        """Слот для добавления сообщения в UI из другого потока"""
        bubble = MessageBubble(text, sender, is_own, timestamp)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        self.messages_area.verticalScrollBar().setValue(
            self.messages_area.verticalScrollBar().maximum()
        )
    
    def start_websocket(self):
        """Запускает WebSocket в отдельном потоке"""
        def run_websocket():
            asyncio.new_event_loop().run_until_complete(self.websocket_loop())
        
        self.websocket_thread = Thread(target=run_websocket, daemon=True)
        self.websocket_thread.start()
    
    async def websocket_loop(self):
        """Основной цикл WebSocket"""
        while self.running:
            try:
                async with websockets.connect(f"{WS_URL}/ws/{self.username}") as ws:
                    self.websocket = ws
                    print(f"✅ WebSocket connected for {self.username}")
                    
                    # Получаем оффлайн сообщения
                    try:
                        resp = requests.get(f"{API_URL}/offline_messages/{self.username}")
                        offline = resp.json().get("messages", [])
                        for msg in offline:
                            self.add_message(
                                msg["from"], 
                                msg["text"], 
                                msg["timestamp"], 
                                is_own=False
                            )
                    except:
                        pass
                    
                    # Слушаем входящие сообщения
                    async for message in ws:
                        data = json.loads(message)
                        if data["type"] == "message":
                            msg = data["data"]
                            self.add_message(
                                msg["from"], 
                                msg["text"], 
                                msg["timestamp"], 
                                is_own=False
                            )
                        elif data["type"] == "user_list":
                            # Обновляем список пользователей в UI
                            QMetaObject.invokeMethod(self, "update_user_list",
                                Qt.QueuedConnection,
                                Q_ARG(list, data["data"]))
                        elif data["type"] == "user_joined":
                            QMetaObject.invokeMethod(self, "user_joined",
                                Qt.QueuedConnection,
                                Q_ARG(str, data["data"]["user"]))
                        elif data["type"] == "user_left":
                            QMetaObject.invokeMethod(self, "user_left",
                                Qt.QueuedConnection,
                                Q_ARG(str, data["data"]["user"]))
                            
            except Exception as e:
                print(f"❌ WebSocket error: {e}")
                await asyncio.sleep(3)  # Переподключение через 3 секунды
    
    @pyqtSlot(list)
    def update_user_list(self, users):
        """Обновляет список пользователей в UI"""
        self.chat_list.clear()
        for user in users:
            if user != self.username:
                item = QListWidgetItem(f"👤 {user}")
                item.setData(Qt.UserRole, user)
                self.chat_list.addItem(item)
    
    @pyqtSlot(str)
    def user_joined(self, username):
        """Пользователь зашел"""
        # Проверяем, есть ли уже в списке
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            if item.data(Qt.UserRole) == username:
                return
        item = QListWidgetItem(f"👤 {username}")
        item.setData(Qt.UserRole, username)
        self.chat_list.addItem(item)
    
    @pyqtSlot(str)
    def user_left(self, username):
        """Пользователь вышел"""
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            if item.data(Qt.UserRole) == username:
                self.chat_list.takeItem(i)
                break
    
    def load_users(self):
        """Загружает список пользователей"""
        try:
            response = requests.get(f"{API_URL}/users")
            users = response.json()["users"]
            
            self.chat_list.clear()
            for user in users:
                if user != self.username:
                    item = QListWidgetItem(f"👤 {user}")
                    item.setData(Qt.UserRole, user)
                    self.chat_list.addItem(item)
        except Exception as e:
            print(f"Error loading users: {e}")
    
    def on_chat_selected(self, item):
        """Выбран чат"""
        self.current_chat = item.data(Qt.UserRole)
        self.chat_header.setText(f"Чат с {self.current_chat}")
        
        # Очищаем область сообщений
        while self.messages_layout.count() > 1:
            widget = self.messages_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        
        # Показываем сохраненные сообщения
        if self.current_chat in self.messages:
            for msg in self.messages[self.current_chat]:
                bubble = MessageBubble(
                    msg["text"], 
                    msg["from"], 
                    msg["is_own"], 
                    msg["timestamp"]
                )
                self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
    
    def send_message(self):
        """Отправляет сообщение"""
        if not self.current_chat:
            QMessageBox.warning(self, "Ошибка", "Выберите получателя")
            return
        
        text = self.message_input.text().strip()
        if not text:
            return
        
        timestamp = datetime.now().strftime("%H:%M")
        
        # Отображаем сообщение сразу
        self.add_message(self.username, text, timestamp, is_own=True)
        self.message_input.clear()
        
        # Отправляем через WebSocket
        if self.websocket:
            async def send():
                try:
                    await self.websocket.send(json.dumps({
                        "type": "private_message",
                        "to": self.current_chat,
                        "text": text
                    }))
                except Exception as e:
                    print(f"Send error: {e}")
            
            asyncio.run_coroutine_threadsafe(send(), asyncio.new_event_loop())
    
    def closeEvent(self, event):
        """Закрытие окна"""
        self.running = False
        if self.websocket:
            async def close():
                await self.websocket.close()
            asyncio.run_coroutine_threadsafe(close(), asyncio.new_event_loop())
        event.accept()

class LoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram Messenger")
        self.setFixedSize(400, 500)
        self.setStyleSheet(STYLE)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        logo = QLabel("📱")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("font-size: 64px; margin: 30px;")
        layout.addWidget(logo)
        
        title = QLabel("Telegram Messenger")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2B5278;")
        layout.addWidget(title)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Имя пользователя")
        self.username_input.setStyleSheet("padding: 12px;")
        layout.addWidget(self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet("padding: 12px;")
        layout.addWidget(self.password_input)
        
        login_btn = QPushButton("Войти")
        login_btn.clicked.connect(self.login)
        layout.addWidget(login_btn)
        
        register_btn = QPushButton("Создать аккаунт")
        register_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #2B5278;
            }
        """)
        register_btn.clicked.connect(self.register)
        layout.addWidget(register_btn)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        
        try:
            response = requests.post(
                f"{API_URL}/login",
                json={"username": username, "password": password}
            )
            if response.status_code == 200:
                self.accept()
                self.chat_window = ChatWindow(username)
                self.chat_window.show()
            else:
                QMessageBox.warning(self, "Ошибка", "Неверное имя пользователя или пароль")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось подключиться: {e}")
    
    def register(self):
        username = self.username_input.text()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Ошибка", "Заполните все поля")
            return
        
        try:
            response = requests.post(
                f"{API_URL}/register",
                json={"username": username, "password": password}
            )
            if response.status_code == 200:
                QMessageBox.information(self, "Успех", "Аккаунт создан! Теперь войдите.")
            else:
                QMessageBox.warning(self, "Ошибка", response.json()["detail"])
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось подключиться: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    login = LoginWindow()
    login.show()
    sys.exit(app.exec_())