import { create } from 'zustand';
import { io } from 'socket.io-client';
import { Node, Edge } from '@xyflow/react';
import dagre from '@dagrejs/dagre';

// --- Types ---
interface AgentNode {
  id: string;
  name: string;
  parentId: string | null;
  status: string;
  draft: string;
  description: string;
  logs: { role: string; content: string }[];
}

interface AgentStore {
  agentNodes: Record<string, AgentNode>;
  rfNodes: Node[];
  rfEdges: Edge[];
  selectedNodeId: string | null;
  
  initializeSocket: () => void;
  selectNode: (id: string | null) => void;
}

// --- Layout Helper (Dagre) ---
const getLayoutedElements = (nodes: Node[], edges: Edge[]) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: 'TB' }); // Top to Bottom

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 150, height: 50 });
  });
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: { x: nodeWithPosition.x - 75, y: nodeWithPosition.y - 25 },
    };
  });

  return { nodes: layoutedNodes, edges };
};

// --- Store ---
export const useAgentStore = create<AgentStore>((set, get) => ({
  agentNodes: {},
  rfNodes: [],
  rfEdges: [],
  selectedNodeId: null,

  selectNode: (id) => set({ selectedNodeId: id }),

  initializeSocket: () => {
    const socket = io('http://localhost:8000');

    socket.on('node_created', (data) => {
      set((state) => {
        const newNode: AgentNode = { ...data, logs: [], draft: '' };
        const newAgentNodes = { ...state.agentNodes, [data.id]: newNode };
        
        // React Flow Node 생성
        const rfNode: Node = {
          id: data.id,
          data: { label: data.name, status: data.status },
          position: { x: 0, y: 0 }, // Layout이 나중에 처리함
          type: 'default', // 커스텀 노드로 교체 가능
          style: { 
            background: '#fff', border: '1px solid #777', borderRadius: '5px', 
            width: 150, padding: 10, textAlign: 'center' 
          }
        };

        // Edge 생성 (부모가 있다면)
        const newEdges = [...state.rfEdges];
        if (data.parentId) {
          newEdges.push({
            id: `e-${data.parentId}-${data.id}`,
            source: data.parentId,
            target: data.id,
            type: 'smoothstep',
            animated: true,
          });
        }
        
        // 레이아웃 다시 계산
        const { nodes: layoutedNodes } = getLayoutedElements([...state.rfNodes, rfNode], newEdges);
        return { agentNodes: newAgentNodes, rfNodes: layoutedNodes, rfEdges: newEdges };
      });
    });

    socket.on('node_updated', (data) => {
      set((state) => {
        const node = state.agentNodes[data.id];
        if (!node) return state;

        // 데이터 업데이트
        const updatedNode = { ...node, ...data };
        const newAgentNodes = { ...state.agentNodes, [data.id]: updatedNode };

        // 시각적 상태 업데이트 (색상 등)
        const newRfNodes = state.rfNodes.map((n) => {
            if (n.id === data.id && data.status) {
                let bg = '#fff';
                if (data.status === 'WIP') bg = '#eef';
                if (data.status === 'COMPLETED') bg = '#dfd';
                return { ...n, style: { ...n.style, background: bg }};
            }
            return n;
        });

        return { agentNodes: newAgentNodes, rfNodes: newRfNodes };
      });
    });

    socket.on('log_added', (data) => {
      set((state) => {
        const node = state.agentNodes[data.nodeId];
        if (!node) return state;
        
        const updatedNode = { 
            ...node, 
            logs: [...node.logs, { role: data.role, content: data.content }] 
        };
        return { agentNodes: { ...state.agentNodes, [data.nodeId]: updatedNode } };
      });
    });
  },
}));