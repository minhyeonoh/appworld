import uvicorn
import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich import print as rprint
import time

graph_history = []

FRONTEND_ORIGINS = ["http://localhost:5173"]
# -----------------------------
# AsyncServer explained
# -----------------------------
# sio = socketio.AsyncServer(cors_allowed_origins=FRONTEND_ORIGINS, async_mode="asgi")
#
# - AsyncServer: the main Socket.IO server object.
# - cors_allowed_origins=FRONTEND_ORIGINS: allows frontend browser at this origin.
# - async_mode="asgi": tells python-socketio to run in ASGI mode (for FastAPI).
sio = socketio.AsyncServer(cors_allowed_origins=FRONTEND_ORIGINS, async_mode="asgi")
app = FastAPI()
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
async def root():
    return {"message": "Socket.IO server running!"}
@sio.event
async def connect(sid, environ):
    print("🔌 Client connected:", sid)
    # 새로운 친구가 들어오면, 지금까지 쌓인 역사를 브리핑해줍니다.
    if graph_history:
        # await sio.emit("load_history", graph_history, to=sid)
        print(f"🔄 Replaying {len(graph_history)} events to {sid}...")
        await sio.emit("reset", {}, to=sid)
        for event in graph_history:
        #     # event = {"name": "create_node", "data": {...}}
            print(event["name"])
            await sio.emit(event["name"], event["data"], to=sid)

@sio.event
async def disconnect(sid):
    print("❌ Client disconnected:", sid)

@sio.event
async def agent_event(sid, data):
    """
    Logger가 보낸 데이터 구조:
    {
        "event": "update_graph",
        "payload": { "id": "...", "label": "...", "parentId": "..." }
    }
    """
    event_name = data.get("event")
    payload = data.get("payload")
    
    print(f"📡 Relay: {event_name} from {sid}")
    rprint(payload)
    # 1. 역사책에 기록 (Replay를 위해 보기 좋게 저장)
    # 껍데기(agent_event)를 벗기고 알맹이만 저장합니다.
    graph_history.append({
        "name": event_name, 
        "data": payload
    })
    # 모든 연결된 클라이언트(React Frontend)에게 브로드캐스트
    await sio.emit(event_name, payload)

@sio.event
async def add_tree_node(sid, data):
    """
    클라이언트가 요청하거나, 혹은 서버 로직(AI 등)에 의해 호출될 함수
    """
    print(f"Request from {sid}: {data}")
    
    # 예: 서버가 계산 후 새로운 노드 정보를 생성했다고 가정
    new_node_payload = {
        "id": data, 
        "label": "AI Generated Node",
        "parentId": "n1" # 부모 노드 ID (트리 구조 연결용)
    }
    
    # 클라이언트의 'update_graph' 이벤트를 트리거
    await sio.emit("update_graph", new_node_payload)


@sio.event
async def reset(sid, data):
    print(f"🔄 Session Reset requested by {sid}")
    graph_history.clear()
    await sio.emit('reset', {})


@sio.event
async def create_node(sid, data):
    raise
    """
    클라이언트가 요청하거나, 혹은 서버 로직(AI 등)에 의해 호출될 함수
    """
    print(f"Request from {sid}: {data}")
    graph_history.append({"name": "create_node", "data": data})
    await sio.emit("create_node", data)


if __name__ == "__main__":
  uvicorn.run("main:socket_app", host="127.0.0.1", port=8000, reload=True)