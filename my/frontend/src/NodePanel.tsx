import { useState } from "react";
import { X, Image as ImageIcon, AlertCircle, DraftingCompass, ArrowRight, Workflow, CornerDownRight, Sparkle, LoaderCircle, DotIcon, TextSearch, PenLine, Search, SearchCheck, Variable as VariableIcon, Code as CodeIcon, User as UserIcon, BotMessageSquare, CheckIcon, CopyIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CodeBlock, CodeBlockCopyButton } from "@/components/ai-elements/code-block";
import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtImage,
  ChainOfThoughtSearchResult,
  ChainOfThoughtSearchResults,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

import type { BundledLanguage } from "shiki";
import Markdown from 'react-markdown';
import remarkGfm from "remark-gfm";
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css'; // KaTeX CSS를 불러옵니다.

function MyComponent({ content }) {
  return (
    <Markdown
      remarkPlugins={[remarkMath, remarkGfm]}
      rehypePlugins={[rehypeKatex]}
      components={{
        // ★ 2. 리스트 및 헤더 스타일 추가 (여기가 핵심입니다)
        ul: ({node, ...props}) => (
          <ul className="list-disc pl-7 " {...props} />
        ),
        ol: ({node, ...props}) => (
          <ol className="list-decimal pl-7" {...props} />
        ),
        li: ({node, ...props}) => (
          <li className="leading-relaxed" {...props} />
        ),
        h1: ({node, ...props}) => <h1 className="text-2xl font-bold mt-6 mb-4" {...props} />,
        h2: ({node, ...props}) => <h2 className="text-xl font-bold mt-5 mb-3" {...props} />,
        h3: ({node, ...props}) => <h3 className="text-lg font-semibold mt-4 mb-2" {...props} />,
        blockquote: ({node, ...props}) => (
          <blockquote className="border-l-4 border-muted pl-4 italic text-muted-foreground my-4" {...props} />
        ),
        a: ({node, ...props}) => (
          <a className="text-primary underline underline-offset-4 font-medium hover:text-primary/80" {...props} />
        ),
        // GFM 테이블 스타일
        table: ({node, ...props}) => (
          <div className="my-4 w-full overflow-y-auto">
            <table className="w-full text-sm border-collapse border" {...props} />
          </div>
        ),
        th: ({node, ...props}) => <th className="border px-4 py-2 bg-muted font-bold text-left" {...props} />,
        td: ({node, ...props}) => <td className="border px-4 py-2" {...props} />,
        code({ node, className, children, ...rest }) {
          const match = /language-(\w+)/.exec(className || '');
          const language = (match ? match[1] : 'text') as BundledLanguage;
          const codeString = String(children).replace(/\n$/, '');
          const isCodeBlock = match || codeString.includes('\n');
          if (isCodeBlock) {
            return (
              <CodeBlock
                className="text-xs"
                code={codeString}
                language={language}
                showLineNumbers={true}
              >
                <CodeBlockCopyButton
                  onCopy={() => console.log("Copied code to clipboard")}
                  onError={() => console.error("Failed to copy code to clipboard")}
                />
              </CodeBlock>
            );
          }
          return <code className="bg-muted rounded px-[0.3rem] py-[0.2rem] text-xs">{children}</code>
        },
      }}
    >
      {content.text}
    </Markdown>
  );
}

function DocumentViewer({ content }) {
  // const { description, arguments, returns } = data;
  const description = content.description;
  const parameters = content.arguments;
  const returns = content.returns;
  return (
    <div className="flex flex-col gap-y-1.5">
      <MyComponent content={{ text: description }} />
      {parameters.length > 0 &&
        <div>
          <div className="font-semibold">
            Parameters
          </div>
          <div className="flex flex-col gap-y-1.5 pl-5">
            {parameters.map((param, index) => (
              <div key={index}>
                <span className="font-mono font-medium">
                  {param.name}
                </span>
                {param.type ? <span> ({param.type})</span> : null}
                :
                <div className="pl-5">
                  <span>{param.description}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      }
      {returns.length > 0 &&
        <div>
          <div className="font-semibold">
            Returns
          </div>
          <div className="flex flex-col gap-y-1.5 pl-5">
            {returns.map((ret, index) => (
              <div key={index}>
                {ret.name && (
                  <div>
                    <span className="font-mono font-medium">{ret.name}</span>
                    {ret.type ? <span> ({ret.type})</span> : null}
                    :
                  </div>
                )}
                <div className={cn("", ret.name ? "pl-5" : "")}>
                  <span>{ret.description}</span>
                </div>
                {/* <span className="font-mono font-medium">{param.name}</span>
                {param.type ? <span> ({param.type})</span> : null}
                :
                <div className="pl-5">
                  <span>{param.description}</span>
                </div> */}
              </div>
            ))}
          </div>
        </div>
      }
    </div>
  );
}

function ReasoningSteps({ steps, className = "", defaultOpen = true }) {
  if (!steps || steps.length === 0) return null;
  return (
    <ChainOfThought defaultOpen={defaultOpen} className={className}>
      {steps.map((step, index) => (
        <div key={index}>
          <ReasoningStep step={step} />
        </div>
      ))}
    </ChainOfThought>
  );
}

function ReasoningStep({ step }) {
  const { type, status, header, content, messages, reasoning_steps: steps } = step;
  const getContentViewer = (type) => {
    switch (type) {
      case "markdown": return MyComponent;
      case "document": return DocumentViewer;
      default: return MyComponent;
    }
  };
  const Viwer = getContentViewer(content?.type);
  const getHeaderIcon = (type) => {
    switch (type) {
      case "draft": return DraftingCompass;
      case "describe": return PenLine;
      case "goto-child": return CornerDownRight;
      case "search": return Search;
      case "verify": return SearchCheck;
      case "fill-api-parameters": return VariableIcon;
      case "implement": return CodeIcon;
      // case 'error': return 'destructive'; // 빨강 (에러)
      // case 'running': return 'secondary'; // 회색 (실행중)
      default: return DotIcon;          // 흰색 (대기)
    }
  };
  const [isCopied, setIsCopied] = useState(false);
  const copyToClipboard = async () => {
    if (typeof window === "undefined" || !navigator?.clipboard?.writeText) return;
    if (!messages || messages.length === 0) return;
    const history = messages.map(msg => 
      `${msg.role === 'user' ? 'USER:' : 'ASSISTANT:'}\n${msg.content}`
    ).join('\n\n');
    try {
      navigator.clipboard.writeText(history);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), timeout);
    } catch (err) {
      console.error(err);
    }
  };
  const CopyButtonIcon = isCopied ? CheckIcon : CopyIcon;
  console.log(messages);
  return (
    <ChainOfThoughtStep
      icon={getHeaderIcon(type)}
      status={status}
      label={
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <span className="truncate">
              {header}
            </span>
            {status === "active" && 
              <LoaderCircle className="animate-spin h-4 w-4" />
            }
          </div>
          {messages.length > 0 &&
            <Dialog>
              <DialogTrigger asChild>
                <Button
                  variant="outline" 
                  size="icon" 
                  className="size-5 rounded-full shrink-0 text-sm font-light" // shrink-0: 텍스트가 길어도 버튼 안 찌그러지게
                  onClick={() => console.log("Button clicked")}
                >
                  {/* Messages */}
                  {/* <div className="flex items-center justify-center size-4 bg-black text-white rounded-full shrink-0"> */}
                    <ArrowRight className="!size-3" /> 
                  {/* </div> */}
                </Button>
              </DialogTrigger>
              <DialogContent className="h-[90vh] min-w-[90vw] flex flex-col">
                <DialogHeader>
                  <div className="flex items-center justify-between pr-8">
                    <DialogTitle>Messages</DialogTitle>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={copyToClipboard}
                      className="flex items-center gap-1.5 h-7 text-xs"
                    >
                      <CopyButtonIcon />
                    </Button>
                  </div>
                  <DialogDescription>
                    Total {messages.length} messages in this step.
                  </DialogDescription>
                </DialogHeader>
                <div className="flex-1 overflow-y-auto min-h-0 p-0">
                  <ChainOfThought defaultOpen className="p-0">
                    {/* {data.reasoning_steps.map((step, index) => (
                      <div key={index}>
                        <ReasoningStep step={step} />
                      </div>
                    ))} */}
                    {messages.map((msg, index) => (
                      <div key={index}>
                        <ChainOfThoughtStep
                          status="active"
                          icon={msg.role === "user" ? UserIcon : BotMessageSquare}
                          label={
                            <span className="font-bold">
                              {msg.role === "user" ? "User" : "Assistant"}
                            </span>
                          }
                        >
                          <MyComponent content={{ text: msg.content }} />
                        </ChainOfThoughtStep>
                      </div>
                    ))}
                  </ChainOfThought>
                  {/* {messages.map((msg, idx) => (
                    <div key={idx} className="flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <Badge variant={msg.role === "user" ? "default" : "secondary"} className="capitalize">
                          {msg.role}
                        </Badge>
                      </div>
                      <div className="bg-blue-500 border rounded-md p-4 shadow-sm text-sm">
                        <MyComponent content={{ text: msg.content }} />
                      </div>
                    </div>
                  ))} */}
                </div>
              </DialogContent>
            </Dialog>
          }
        </div>
      }
      withBoldLabel
    >
      {content && <Viwer content={content} />}
      {steps && steps.length > 0 && (
        <ReasoningSteps steps={steps} className="p-0" />
      )}
    </ChainOfThoughtStep>
  );
}

// export default MyComponent;


export function NodePanel({ selectedNode, onClose }) {
  if (!selectedNode) return null;
  const getStatusVariant = (s) => {
    switch (s) {
      case 'done': return 'default';      // 검정 (완료)
      case 'error': return 'destructive'; // 빨강 (에러)
      case 'running': return 'secondary'; // 회색 (실행중)
      default: return 'outline';          // 흰색 (대기)
    }
  };
  const { data } = selectedNode;
  const status = "running";
  return (
    <div className="h-full flex flex-col bg-background">
      {/* --- [A] Header (고정 영역) --- */}
      <div className="flex items-center justify-between px-4 h-12 shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="font-semibold text-md truncate">
            Details
          </span>
          <Badge className="shrink-0">
            {data.label}
          </Badge>
          <Badge variant={getStatusVariant(status)} className="capitalize shrink-0">
            {status}
          </Badge>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8 shrink-0 ml-2">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <Separator />
      {/* --- [B] Content (스크롤 영역) --- */}
      <div className="flex-1 space-y-0 overflow-y-auto overflow-x-hidden text-sm">
        <div className="flex flex-col p-4 pt-3 gap-y-1">
          <code className="font-semibold text-lg truncate">{data.info.name}</code>
          <DocumentViewer content={data.info} />
        </div>
        <Separator className="" />
        <div className="p-4">
          <ReasoningSteps steps={data.reasoning_steps} />
        </div>
      </div>
    </div>
  );

  return (
    <div style={{
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      width: '300px',
      backgroundColor: 'white',
      borderLeft: '1px solid #ddd',
      padding: '20px',
      boxShadow: '-2px 0 5px rgba(0,0,0,0.05)',
      zIndex: 10, // React Flow 컨트롤보다 위에 오도록
      overflowY: 'auto'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
        <h3 style={{ margin: 0 }}>Node Details</h3>
        <button onClick={onClose} style={{ cursor: 'pointer' }}>✕</button>
      </div>

      <div style={{ marginBottom: '15px' }}>
        <strong>ID:</strong>
        <div style={{ color: '#555' }}>{selectedNode.id}</div>
      </div>

      <div style={{ marginBottom: '15px' }}>
        <strong>Label:</strong>
        <div style={{ fontSize: '1.2em', color: '#333' }}>
          {selectedNode.data.label}
        </div>
      </div>

      {/* 노드에 들어있는 기타 데이터가 있다면 JSON으로 표시 */}
      <div style={{ marginTop: '20px' }}>
        <strong>Raw Data:</strong>
        <pre style={{ 
          background: '#f4f4f4', 
          padding: '10px', 
          borderRadius: '5px',
          fontSize: '11px',
          overflowX: 'auto'
        }}>
          {JSON.stringify(selectedNode.data, null, 2)}
        </pre>
      </div>
    </div>
  );
};
