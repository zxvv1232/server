"""
Мессенджер с уведомлениями о подключении пользователей
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Messenger")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище данных
users: Dict[str, dict] = {}  # {username: {"password": str, "online": bool}}
offline_messages: Dict[str, list] = {}
active_connections: Dict[str, Set[WebSocket]] = {}

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

# Функция для оповещения всех пользователей об изменении списка онлайн
async def broadcast_user_list():
    """Отправляет всем подключенным пользователям актуальный список онлайн"""
    online_users = [u for u, data in users.items() if data.get("online", False)]
    
    for username, connections in active_connections.items():
        for conn in connections:
            try:
                await conn.send_json({
                    "type": "user_list",
                    "data": online_users
                })
            except:
                pass

async def broadcast_user_joined(username: str):
    """Оповещает всех о подключении нового пользователя"""
    online_users = [u for u, data in users.items() if data.get("online", False)]
    
    for user, connections in active_connections.items():
        for conn in connections:
            try:
                await conn.send_json({
                    "type": "user_joined",
                    "data": {
                        "user": username,
                        "online_users": online_users
                    }
                })
            except:
                pass

async def broadcast_user_left(username: str):
    """Оповещает всех об отключении пользователя"""
    online_users = [u for u, data in users.items() if data.get("online", False)]
    
    for user, connections in active_connections.items():
        for conn in connections:
            try:
                await conn.send_json({
                    "type": "user_left",
                    "data": {
                        "user": username,
                        "online_users": online_users
                    }
                })
            except:
                pass

@app.post("/register")
async def register(request: RegisterRequest):
    if request.username in users:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    users[request.username] = {
        "password": request.password,
        "online": False
    }
    offline_messages[request.username] = []
    active_connections[request.username] = set()
    
    return {"status": "success", "message": f"User {request.username} created"}

@app.post("/login")
async def login(request: LoginRequest):
    user = users.get(request.username)
    if not user or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {"status": "success", "message": "Login successful"}

@app.post("/logout/{username}")
async def logout(username: str):
    if username in users:
        users[username]["online"] = False
        # Удаляем из активных соединений
        if username in active_connections:
            active_connections[username] = set()
        # Оповещаем всех
        await broadcast_user_left(username)
    return {"status": "success"}

@app.get("/users")
async def get_users():
    return {"users": list(users.keys())}

@app.get("/users/online")
async def get_online_users():
    online = [u for u, data in users.items() if data.get("online", False)]
    return {"online": online}

@app.get("/offline_messages/{username}")
async def get_offline_messages(username: str):
    messages = offline_messages.get(username, [])
    offline_messages[username] = []
    return {"messages": messages}

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()
    
    if username not in users:
        await websocket.close(code=1008, reason="User not found")
        return
    
    # Отмечаем пользователя онлайн
    users[username]["online"] = True
    active_connections[username].add(websocket)
    
    # Оповещаем всех о новом пользователе
    await broadcast_user_joined(username)
    
    # Отправляем новому пользователю список всех пользователей
    all_users = list(users.keys())
    await websocket.send_json({
        "type": "user_list",
        "data": all_users
    })
    
    # Отправляем оффлайн сообщения
    pending = offline_messages.get(username, [])
    if pending:
        for msg in pending:
            await websocket.send_json({
                "type": "message",
                "data": msg
            })
        offline_messages[username] = []
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "private_message":
                to_user = message_data["to"]
                text = message_data["text"]
                
                msg_packet = {
                    "from": username,
                    "text": text,
                    "timestamp": datetime.now().strftime("%H:%M")
                }
                
                # Отправляем получателю, если онлайн
                if to_user in active_connections and active_connections[to_user]:
                    for conn in active_connections[to_user]:
                        try:
                            await conn.send_json({
                                "type": "message",
                                "data": msg_packet
                            })
                        except:
                            pass
                else:
                    # Сохраняем оффлайн
                    offline_messages.setdefault(to_user, []).append(msg_packet)
                
                # Отправляем подтверждение отправителю
                await websocket.send_json({
                    "type": "sent",
                    "data": {"to": to_user, "text": text}
                })
                
    except WebSocketDisconnect:
        # Пользователь отключился
        users[username]["online"] = False
        active_connections[username].discard(websocket)
        await broadcast_user_left(username)

if __name__ == "__main__":
    print("🚀 Server starting...")
    print("📍 http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)