import socketio
import uuid
import time

class RemoteLogger:
    def __init__(self, server_url="http://localhost:8000"):
        # standard sync client for scripts
        self.sio = socketio.Client()
        self.connected = False
        while not self.connected:
            try:
                self.sio.connect(server_url)
                self.connected = True
                print(f"✅ Connected to Visualization Server at {server_url}")
            except Exception as e:
                print(f"⚠️ Warning: Could not connect to server. ({e})")
                print("Running in offline mode.")

    def _send(self, event_name, payload):
        if self.connected:
            try:
                # 서버의 'agent_event' 핸들러로 전송
                self.sio.emit('agent_event', {'event': event_name, 'payload': payload})
                # 너무 빨리 보내면 순서가 꼬일 수 있으므로 아주 짧은 슬립 (선택사항)
                time.sleep(3) 
            except Exception as e:
                print(f"⚠️ Failed to emit: {e}")

    def add_node(self, node_id, label, parent_id=None):
        """
        트리에 노드를 추가합니다.
        :param node_id: 유니크한 노드 ID
        :param label: 노드에 표시될 텍스트
        :param parent_id: 부모 노드 ID (Root인 경우 None)
        """
        payload = {
            "id": str(node_id),
            "label": str(label),
            "parentId": str(parent_id) if parent_id else None,
            "content": (
r"""

$a^2+b^2=c^2$

Math
$$
\int_{a}^{b} f(x) \, dx = F(b) - F(a)
$$

This is inline code `this_is_function()`

```python
def main():
    # Load the CSV file containing the list of people owed money
    owe_list = load_csv('owe_list.csv')
    
    # Iterate over each entry in the owe list
    for entry in owe_list:
        # Extract the necessary details from the entry
        name, amount, description, has_venmo, receipt_filename = extract_details(entry)
        
        # Check if the person has a Venmo account
        if has_venmo:
            # Send the money via Venmo
            send_money_via_venmo(name, amount, description)
        else:
            # Create a Splitwise expense
            create_splitwise_expense(name, amount, description, receipt_filename)
```

```
def main():
    # Load the CSV file containing the list of people owed money
    owe_list = load_csv('owe_list.csv')
    
    # Iterate over each entry in the owe list
    for entry in owe_list:
        # Extract the necessary details from the entry
        name, amount, description, has_venmo, receipt_filename = extract_details(entry)
        
        # Check if the person has a Venmo account
        if has_venmo:
            # Send the money via Venmo
            send_money_via_venmo(name, amount, description)
        else:
            # Create a Splitwise expense
            create_splitwise_expense(name, amount, description, receipt_filename)
```
"""
            ).strip()
        }
        self._send("create_node", payload)
        print(f"🔹 Logged Node: {label} (parent: {parent_id})")

    def visit_node(self, node_id):
        """
        특정 노드를 강조 표시합니다 (현재 실행 중인 노드 표시).
        """
        # 데이터가 너무 빨리 전송되어 씹히는 걸 방지하기 위해 약간의 텀을 줌
        time.sleep(0.05) 
        print(f"👁️ Visiting Node: {node_id}")
        self._send("highlight_node", {"id": str(node_id)})

    def init(self):
        """
        서버와 프론트엔드의 상태를 초기화합니다.
        스크립트 시작 시 호출하세요.
        """
        if self.connected:
            # [수정] _send 대신 emit을 직접 사용해서 'agent_event' 래핑을 피함
            # 이렇게 해야 서버의 'init_session' 핸들러가 직접 반응함
            self.sio.emit("reset", {})
            
            print("🔄 Sent initialization signal to server.")
            time.sleep(0.5) # 프론트엔드가 지울 시간을 잠깐 벌어줌

    def close(self):
        if self.connected:
            self.sio.disconnect()