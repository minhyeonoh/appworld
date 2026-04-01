
import networkx as nx
import time

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any


app = FastAPI()
app.add_middleware(
  CORSMiddleware,
  allow_origins=["http://localhost:5173", "localhost:5173"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"]
)


@app.get("/", tags=["root"])
async def read_root() -> dict:
  return {"message": "Welcome to your todo list."}


# 1. 오래 걸리는 함수 (AI 에이전트)
def heavy_ai_task(task_name: str):
  print(f"🤖 [{task_name}] 에이전트 시작...")
  time.sleep(50)  # 5초 동안 복잡한 계산 중이라고 가정
  # 여기서 store.add_node() 등을 호출해서 그래프 데이터 갱신
  print(f"✅ [{task_name}] 에이전트 완료!")


# 2. API 엔드포인트
@app.post("/start")
async def start_agent(background_tasks: BackgroundTasks): # 변수로 주입받음
  # (1) "이 함수(heavy_ai_task)를 나중에 실행해줘"라고 등록
  #     요청이 끝나고(return 후) 실행됩니다.
  background_tasks.add_task(heavy_ai_task, "Task-1")
  # (2) 사용자에겐 즉시 응답 반환
  return {"message": "에이전트가 실행되었습니다. 결과를 기다리세요."}


class GraphManager:

  def __init__(self):
    self.sessions: dict[str, dict[str, nx.DiGraph]] = {}

  def get_experiments(self):
    return list(self.sessions.keys())

  def get_tasks(self, experiment_name: str):
    if experiment_name in self.sessions:
      return list(self.sessions[experiment_name].keys())
    return []

  def get_graph(self, experiment_name: str, task_id: str):
    if experiment_name not in self.sessions:
      self.sessions[experiment_name] = dict()
    graphs = self.sessions[experiment_name]
    if task_id not in graphs:
      graphs[task_id] = nx.DiGraph()
    return self.sessions[experiment_name][task_id]

  def get_experiments_and_tasks(self):
    data = {}
    for experiment_name, tasks in self.sessions.items():
      data[experiment_name] = list(tasks.keys())
    return data

  def add_node(
    self,
    experiment_name: str, 
    task_id: str,
    *,
    id: str,
    data: dict[str, Any],
    parent_id: str | None = None,
  ):
    graph = self.get_graph(experiment_name, task_id)
    graph.add_nodes_from([(id, data)])
    if parent_id is not None:
      graph.add_edges_from([(parent_id, id)])

  def update_node(
    self,
    experiment_name: str, 
    task_id: str,
    *,
    id: str,
    data: dict[str, Any],
  ):
    graph = self.get_graph(experiment_name, task_id)
    if id in graph:
      for key, value in data.items():
        graph.nodes[id][key] = value

  def reset(self, experiment_name: str, task_id: str):
    if experiment_name in self.sessions:
      if task_id in self.sessions[experiment_name]:
        del self.sessions[experiment_name][task_id]
        print(f"🧹 Reset graph for {experiment_name}/{task_id}")

  def get_frontend_graph_view(self, experiment_name: str, task_id: str):
    print(experiment_name, task_id, self.sessions)
    if (
      experiment_name not in self.sessions or 
      task_id not in self.sessions[experiment_name]
    ):
      return {"nodes": [], "edges": []}

    graph = self.sessions[experiment_name][task_id]
    print(graph)
    if graph.number_of_nodes() == 0:
      return {"nodes": [], "edges": []}

    pos = nx.nx_agraph.graphviz_layout(graph, prog="dot")
    nodes = []
    for id, (x, y) in pos.items():
      nodes.append({
        "id": id,
        "data": {"label": id, **graph.nodes[id]},
        "position": {"x": x, "y": -y},
        "type": "function",
      })
    edges = []
    for source, target in graph.edges():
      edges.append({
        "id": f"{source}-{target}",
        "source": source,
        "target": target,
      })
    return {"nodes": nodes, "edges": edges}


graph_manager = GraphManager()
# def _add_node(parent_id, id):
#   experiment_name = "domyself"
#   task_id = "6b6ca61_1"
#   graph_manager.add_node(experiment_name, task_id, id=id, data={}, parent_id=parent_id)
# _add_node("0", "1")
# _add_node("1", "2")
# _add_node("2", "3")
# _add_node("2", "4")
# _add_node("1", "5")
# _add_node("0", "6")


@app.post("/graph/{experiment_name}/{task_id}/reset")
def reset_graph(experiment_name: str, task_id: str):
  print("reset_graph")
  graph_manager.reset(experiment_name, task_id)
  return {"status": "reset complete"}

@app.post("/graph/{experiment_name}/{task_id}/add_node")
def add_node(experiment_name: str, task_id: str, payload: dict):
  print("add_node")
  graph_manager.add_node(experiment_name, task_id, **payload)
  return {"status": "ok"}

@app.post("/graph/{experiment_name}/{task_id}/update_node")
def update_node(experiment_name: str, task_id: str, payload: dict):
  print("update_node")
  graph_manager.update_node(experiment_name, task_id, **payload)
  return {"status": "ok"}

@app.get("/graph/{experiment_name}/{task_id}")
async def get_graph(experiment_name: str, task_id: str):
  print("get_graph", task_id, experiment_name)
  return graph_manager.get_frontend_graph_view(experiment_name, task_id)

@app.get("/graph/{task_id}")
async def _get_graph(task_id: str, experiment_name: str):
  print("get_graph", task_id, experiment_name)
  return graph_manager.get_frontend_graph_view(experiment_name, task_id)

@app.get("/experiments_tasks")
async def get_experiments_and_tasks():
  print("get_experiments_and_tasks")
  return graph_manager.get_experiments_and_tasks()


import os
import json

class FileManager:

  def __init__(self, root_directory: str):
    # 실제 서버의 절대 경로 (예: /home/user/experiments)
    self.root_directory = os.path.abspath(root_directory)

  def get_file_tree(self):
    """
    루트 디렉토리부터 재귀적으로 탐색하여 @headless-tree 호환 Flat JSON 반환
    """
    items = {}
    
    # 1. 루트 아이템 생성
    root_name = os.path.basename(self.root_directory)
    items["/"] = {
      # "id": "root",
      "name": "/",
      "children": [],
      # "type": "folder",
      # "data": { "path": "." } # 루트 기준 상대 경로
    }

    # 2. 재귀 탐색 함수
    def scan_directory(current_real_path, parent_id):
      try:
        # 폴더 내용물 가져오기 (이름순 정렬)
        entries = sorted(os.scandir(current_real_path), key=lambda e: e.name)
      except PermissionError:
        return # 권한 없으면 스킵

      for entry in entries:
        # 숨김 파일(.git 등) 제외하려면 여기서 필터링
        if entry.name.startswith('.'):
          continue

        # 상대 경로 생성 (이게 곧 ID가 됨)
        # 예: root -> experiments -> experiments/task1
        relative_path = os.path.relpath(entry.path, self.root_directory)
        # 윈도우의 경우 역슬래시를 슬래시로 변경
        unique_id = relative_path.replace("\\", "/")
        unique_id = f"/{unique_id}"
        
        # 부모의 자식 목록에 추가
        items[parent_id]["children"].append(unique_id)

        # 아이템 생성
        is_dir = entry.is_dir()
        items[unique_id] = {
          # "id": unique_id,
          "name": entry.name,
          "children": [], # 폴더일 경우 나중에 채워짐
          # "type": "folder" if is_dir else "file",
          # "data": {
          #     "path": unique_id,
          #     "extension": os.path.splitext(entry.name)[1] if not is_dir else ""
          # }
        }

        # 폴더면 재귀 호출
        # print(parent_id)
        # input()
        if is_dir and not parent_id.endswith("tasks"):
          scan_directory(entry.path, unique_id)

    # 탐색 시작
    scan_directory(self.root_directory, "/")
    return items

file_manager = FileManager("./app/db")
@app.get("/tasks")
async def get_tasks():
  print("get_tasks")
  return file_manager.get_file_tree()
