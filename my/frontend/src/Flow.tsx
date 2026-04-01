import { useEffect, useState, useRef, useMemo } from "react";
import { io } from "socket.io-client";

import { ReactFlow, Background, Controls } from '@xyflow/react';
import { useNodesState, useEdgesState } from '@xyflow/react';
import { useReactFlow } from '@xyflow/react';
import dagre from 'dagre';
// import '@xyflow/react/dist/style.css';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "./components/ui/resizable";

import { NodePanel } from "./NodePanel";
import FunctionNode from "./FunctionNode";

const nodeTypes = { function: FunctionNode };

const nodeHeight = 36;
 
const measureTextWidth = (text) => {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  // ★ 중요: 실제 React Flow 노드의 폰트 스타일과 맞춰야 정확합니다.
  // 기본값 기준: 12px 정도, padding 좌우 합쳐서 여유분 20~30px 추가
  context.font = '12px sans-serif'; 
  const metrics = context.measureText(text || '');
  // 텍스트 폭 + 좌우 패딩(20) + 여유분(10)
  return Math.ceil(metrics.width + 30); 
};

const getLayoutedElements = (nodes, edges, direction = 'TB') => {
  // ★ [핵심 수정] 함수가 호출될 때마다 "새로운 빈 그래프"를 생성합니다.
  // 이렇게 해야 이전 세션의 잔상(유령 노드)이 완전히 사라집니다.
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const isHorizontal = direction === 'LR';
  dagreGraph.setGraph({ rankdir: direction });
 
  nodes.forEach((node) => {
    const label = node.data?.label || '';
    const width = Math.max(50, measureTextWidth(label));
    dagreGraph.setNode(node.id, { width: width, height: nodeHeight });
    node.measuredWidth = width;
  });
 
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });
 
  dagre.layout(dagreGraph);
 
  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const newNode = {
      ...node,
      targetPosition: isHorizontal ? 'left' : 'top',
      sourcePosition: isHorizontal ? 'right' : 'bottom',
      // We are shifting the dagre node position (anchor=center center) to the top left
      // so it matches the React Flow node anchor point (top left).
      position: {
        x: nodeWithPosition.x - node.measuredWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
      style: {
        width: node.measuredWidth,
        height: nodeHeight,
        // borderRadius: '10px',
      },
    };
 
    return newNode;
  });
 
  return { nodes: newNodes, edges };
};

const initialNodes = [];
const initialEdges = [];
const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
  initialNodes,
  initialEdges,
);
// const layoutedNodes = initialNodes;
// const layoutedEdges = initialEdges;

export function Flow() {
  const reactFlow = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges);
  const [messages, setMessages] = useState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const selectedNode = useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId);
  }, [nodes, selectedNodeId]);

  // ★ 2. 노드 클릭 핸들러
  const onNodeClick = (event, node) => {
    // 클릭된 노드 정보를 state에 저장 -> 패널이 열림
    console.log("Clicked Node:", node);
    setSelectedNodeId(node.id);
  };

  // ★ 3. 빈 공간(Pane) 클릭 핸들러
  const onPaneClick = () => {
    // 배경을 누르면 패널 닫기
    setSelectedNodeId(null);
  };

  const socketRef = useRef(null);
  useEffect(() => {
    const socket = io("http://127.0.0.1:8000", {
      path: "/socket.io/",
      transports: ["websocket"], // force WebSocket (optional)
    });
    socketRef.current = socket;
    socket.on("connect", () => {
      console.log("✅ Connected", socket.id);
      // 1. 노드와 엣지 상태를 빈 배열로 초기화
      // setNodes([]);
      // setEdges([]);
      // setTimeout(reactFlow.fitView);
      // console.log("🧹 Canvas Cleared!");
    });
    socket.on("reset", () => {
      // 1. 노드와 엣지 상태를 빈 배열로 초기화
      setNodes([]);
      setEdges([]);
      setTimeout(reactFlow.fitView);
      console.log("🧹 Canvas Cleared!");
    });
    // socket.on("create_node", (data) => {
    //   console.log("New!", data.id);
    //   const { id: id, parentId: parentId } = data;
    //   // 1. 현재 상태 가져오기 (가장 최신 상태 보장)
    //   const currentNodes = reactFlow.getNodes();
    //   const currentEdges = reactFlow.getEdges();
    //   // 2. 새 노드/엣지 생성
    //   const newNode = { type: "function", id, data: { label: id, ...data }, position: { x: 50, y: 50 } };
    //   console.log(newNode);
    //   const newEdge = { id: `${parentId}-${id}`, source: parentId, target: id };
    //   // 3. 리스트 합치기
    //   const nextNodes = [...currentNodes, newNode];
    //   const nextEdges = [...currentEdges, newEdge];
    //   // 4. ★ 레이아웃 계산 실행 ★
    //   const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
    //       nextNodes, 
    //       nextEdges, 
    //       'TB'
    //   );
    //   // 5. 계산된 결과로 상태 한방에 업데이트
    //   setNodes(layoutedNodes);
    //   setEdges(layoutedEdges);
    // });
    socket.on("create_node", (data) => {
      console.log("New!", data.id);
      const { id: id, parentId: parentId } = data;
      // 2. 새 노드/엣지 생성
      const newNode = { type: "function", id, data: { label: id, ...data }, position: { x: 50, y: 50 } };
      const newEdge = { id: `${parentId}-${id}`, source: parentId, target: id };
      setNodes((prevNodes) => {
        // ★ 이 함수는 React가 실제로 상태를 바꿀 때 실행됩니다.
        // 이때 'prevNodes'는 큐에 쌓인 앞선 작업(update_node)이 모두 끝난 '진짜 최신 상태'입니다.
        const nextNodes = [...prevNodes, newNode];
        // 2. 엣지는 그냥 getEdges()로 가져옴 (이걸로도 충분함)
        const currentEdges = reactFlow.getEdges(); 
        const nextEdges = [...currentEdges, newEdge];
        // 4. ★ 레이아웃 계산 실행 ★
        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
          nextNodes, 
          nextEdges, 
          'TB'
        );
        // 4. 엣지 업데이트 (setTimeout으로 렌더링 충돌 방지)
        // "이 작업은 노드 업데이트가 끝난 직후에 처리해줘"라는 의미
        setTimeout(() => setEdges(layoutedEdges), 0);
        
        // 5. 계산된 노드 반환 -> 화면 갱신
        return layoutedNodes;
        // (선택) 여기서 레이아웃 계산도 최신 상태 기반으로 수행
        // const layouted = getLayoutedElements(nextNodes, ...);
        
        // return layouted.nodes; // 새로운 상태 반환
      });
      // setEdges((prevEdges) => {
      //   const nextEdges = [...prevEdges, newEdge];
      //   return nextEdges;
      // });
    });
    socket.on("update_node", (data) => {
      const { id, new_data } = data;
      console.log("Update", id);
      setNodes((nds) => 
        nds.map((node) => {
          if (node.id === id) {
            return {
              ...node,
              // 스타일 업데이트 (기본 클래스 + 상태 클래스)
              // className: `bg-card border-2 ${statusClass}`,
              // 데이터 병합 (기존 데이터 유지하면서 새 데이터로 덮어쓰기)
              data: {
                ...node.data,
                ...new_data,
              },
            };
          }
          return node;
        })
      )
    });
    // ★ 새로운 이벤트 리스너 추가: 노드 강조
    socket.on("highlight_node", (data) => {
      const targetId = data.id;

      setNodes((nds) => 
        nds.map((node) => {
          // 1. 목표 노드 찾기
          if (node.id === targetId) {
            return {
              ...node,
              className: 'highlighted'
            };
          }
          
          // 2. 목표가 아닌 노드는 다시 원래 스타일로 복구 (선택 사항)
          // 만약 '지나온 경로'를 다 표시하고 싶다면 이 부분을 제거하세요.
          return {
            ...node,
            className: '',
          };
        })
      );
    });
    return () => socket.disconnect();
  }, []);
  return (
    <div className="h-screen w-screen overflow-hidden bg-background">
      <ResizablePanelGroup direction="horizontal">
        {/* 3. [Left] 메인 캔버스 영역 */}
        {/* 우측 패널이 열리면 70%, 닫히면 100% */}
        <ResizablePanel 
          defaultSize={selectedNodeId ? 70 : 100} 
          minSize={30} 
          className="relative h-full"
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={onNodeClick} 
            onPaneClick={onPaneClick}
          >
            <Background />
            <Controls />
          </ReactFlow>
        </ResizablePanel>
        {/* 4. [Handle & Right] 패널이 활성화되었을 때만 렌더링 */}
        {selectedNodeId && (
          <>
            {/* 드래그 핸들 (중앙 점 포함) */}
            <ResizableHandle withHandle />
            {/* 우측 패널 영역 */}
            <ResizablePanel 
              defaultSize={50} 
              minSize={30} 
              maxSize={50}
              className="bg-background"
            >
              <NodePanel 
                selectedNode={selectedNode} 
                onClose={() => setSelectedNodeId(null)} 
              />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
      {/* <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={onNodeClick} 
        onPaneClick={onPaneClick}
      >
        <Background />
        <Controls />
      </ReactFlow> */}
      {/* <div style={{ width: "50%" }}>
        <NodePanel 
          selectedNode={selectedNode} 
          onClose={() => setSelectedNode(null)} 
        />
      </div> */}
    </div>
  );
}