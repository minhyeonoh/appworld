
import { useState, useMemo, useCallback } from 'react';
import useSWR from 'swr';
import {
  SidebarProvider,
  SidebarTrigger,
} from "./components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "./components/ui/resizable";
import { ReactFlowProvider } from "@xyflow/react";
import { ReactFlow, Background, Controls } from '@xyflow/react';
import { FunctionNode } from "./FunctionNode";
import { AppSidebar } from './Sidebar';
import { NodePanel } from './NodePanel';
import { ThemeSwitcher } from './components/theme-switcher';
import '@xyflow/react/dist/style.css';
import './flow-theme.css'

const fetcher = (url) => fetch(url).then((res) => res.json());

const nodeTypes = { function: FunctionNode };

import { CodeBlock, CodeBlockCopyButton } from "@/components/ai-elements/code-block";
export default function App() {
  const [selectedExp, setSelectedExp] = useState("domyself");
  const [selectedTask, setSelectedTask] = useState("6b6ca61_1");
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const shouldFetch = selectedExp && selectedTask;
  const { data: graphData, error, isLoading } = useSWR(
    shouldFetch
      ? `http://localhost:8000/graph/${selectedTask}?experiment_name=${encodeURIComponent(selectedExp)}` 
      : null,
    fetcher,
    { 
      refreshInterval: 1000,
      revalidateOnFocus: false,
    }
  );
  // 2. 안전한 데이터 추출 (Default Value Pattern)
  // graphData가 undefined일 때를 대비해 빈 배열을 기본값으로 줍니다.
  // const nodes = graphData?.nodes || [];
  // const edges = graphData?.edges || [];
  // const onNodeClick = (event, node) => { setSelectedNodeId(node.id); };
  // const onPaneClick = () => { setSelectedNodeId(null); };
  const nodes = useMemo(() => graphData?.nodes || [], [graphData]);
  const edges = useMemo(() => graphData?.edges || [], [graphData]);
  const onNodeClick = useCallback((event, node) => { setSelectedNodeId(node.id); }, []);
  const onPaneClick = useCallback(() => { setSelectedNodeId(null); }, []);
  const selectedNode = useMemo(() => {
    console.log(selectedNodeId);
    return nodes.find((n) => n.id === selectedNodeId);
  }, [nodes, selectedNodeId]);

  if (error) return <div>Failed to load graph</div>;
  const codeString = `def insertion_sort(array):
    breakpoint()
    i = 0
    j = 0
    n = len(array)
    for j in range(n):
        key = array[j]
        i = j - 1
        while i >= 0 and array[i] > key:
            array[i + 1] = array[i]
            i = i - 1
        array[i + 1] = key`;
  return (
    <CodeBlock
      className="text-xs"
      code={codeString}
      language="python"
      showLineNumbers={true}
    >
      {/* <CodeBlockCopyButton
        onCopy={() => console.log("Copied code to clipboard")}
        onError={() => console.error("Failed to copy code to clipboard")}
      /> */}
    </CodeBlock>
  );

  return (
    <div className="h-screen w-screen overflow-hidden bg-background flex">
      <SidebarProvider>
        <AppSidebar 
          variant="sidebar"
          className="" 
          selectedExp={selectedExp} 
          selectedTask={selectedTask}
          onSelect={(exp, task) => {
            setSelectedExp(exp);
            setSelectedTask(task);
            setSelectedNodeId(null); // 다른 태스크 가면 선택 해제
          }}
      />
        <main className='flex-1 min-w-0 h-full flex flex-col'>
          <ResizablePanelGroup direction="horizontal">
            <ResizablePanel 
              defaultSize={selectedNodeId ? 70 : 100} 
              minSize={30} 
              className="relative h-full flex flex-col"
            >
              <header className="!h-12 shrink-0 flex w-full items-center px-4 justify-between">
                <div className="h-full shrink-0 flex items-center gap-3.5">
                  <SidebarTrigger className="!p-0 !w-fit !h-fit"/>
                  <Separator className="!h-5" orientation="vertical" />
                  <a className="text-md">
                    Agent View
                  </a>
                  <Separator className="!h-5" orientation="vertical" />
                  <a>
                    {selectedExp}
                  </a>
                  <a>
                    {selectedTask}
                  </a>
                </div>
                <ThemeSwitcher />
              </header>
              <Separator />
              {error ? (
                <div>error</div>
              ) : (!shouldFetch ? (
                <div>select something</div>
              ) : (isLoading && !graphData ? (
                <div>loading...</div>
              ) : (
                <div className="flex-1 w-full min-h-0 relative">
                  <ReactFlowProvider>
                    <ReactFlow
                      nodes={nodes}
                      edges={edges}
                      nodeTypes={nodeTypes}
                      onNodeClick={onNodeClick} 
                      onPaneClick={onPaneClick}
                      fitView
                      fitViewOptions={{
                        maxZoom: 1,
                        minZoom: 0.5,
                        padding: 0.25,
                      }}
                    >
                      <Background />
                      <Controls />
                    </ReactFlow>
                  </ReactFlowProvider>
                </div>
              )))}
            </ResizablePanel>
            {selectedNodeId && (
              <>
                <ResizableHandle withHandle />
                <ResizablePanel 
                  defaultSize={50} 
                  minSize={30} 
                  maxSize={50}
                >
                  <NodePanel 
                    selectedNode={selectedNode} 
                    onClose={() => setSelectedNodeId(null)} 
                  />
                </ResizablePanel>
              </>
            )}
          </ResizablePanelGroup>
        </main>
      </SidebarProvider>
    </div>
  );
}