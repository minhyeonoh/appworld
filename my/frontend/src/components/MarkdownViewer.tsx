import React, { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from "@/lib/utils";
// ★ 앞서 만든 CodeBlock 컴포넌트를 가져옵니다. 경로를 확인하세요.
import { CodeBlock, CodeBlockCopyButton } from "@/components/ai-elements/code-block"; 
// 또는 import { CodeBlock } from "@/components/ai-elements/code-block";

export const MarkdownViewer = memo(({ content, className }) => {
  return (
    <ReactMarkdown
      className={cn("text-sm leading-6 text-foreground break-words", className)}
      remarkPlugins={[remarkGfm]} // 테이블, 취소선, URL 자동 링크 등 지원
      components={{
        // 1. 코드 블록 커스텀 (핵심!)
        code({ node, inline, className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || '');
          const language = match ? match[1] : 'text';
          const codeString = String(children).replace(/\n$/, '');

          // A. 멀티라인 코드 블록 (```python ... ```)
          if (!inline && match) {
            return (
              <CodeBlock
                key={Math.random()} // 리렌더링 이슈 방지
                language={language}
                code={codeString}
                className="my-3" // 위아래 간격
                showLineNumbers={true}
              >
                 {/* 복사 버튼 추가 */}
                 <CodeBlockCopyButton />
              </CodeBlock>
            );
          }

          // B. 인라인 코드 (`const a`)
          return (
            <code
              className="bg-muted px-1.5 py-0.5 rounded font-mono text-[0.8em] font-medium text-foreground border border-border"
              {...props}
            >
              {children}
            </code>
          );
        },
        
        // 2. 기타 요소 스타일링 (Tailwind Typography 없이 수동 적용)
        h1: ({children}) => <h1 className="text-xl font-bold mt-6 mb-4 pb-2 border-b">{children}</h1>,
        h2: ({children}) => <h2 className="text-lg font-bold mt-5 mb-3">{children}</h2>,
        h3: ({children}) => <h3 className="text-base font-semibold mt-4 mb-2">{children}</h3>,
        p: ({children}) => <p className="mb-3 last:mb-0">{children}</p>,
        ul: ({children}) => <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>,
        ol: ({children}) => <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>,
        li: ({children}) => <li className="pl-1">{children}</li>,
        blockquote: ({children}) => (
          <blockquote className="border-l-4 border-primary/30 pl-4 italic text-muted-foreground my-4">
            {children}
          </blockquote>
        ),
        a: ({children, href}) => (
          <a 
            href={href} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="text-primary underline underline-offset-4 hover:text-primary/80 font-medium"
          >
            {children}
          </a>
        ),
        // 테이블 스타일링 (border 등)
        table: ({children}) => (
          <div className="my-4 w-full overflow-y-auto rounded-lg border">
            <table className="w-full text-sm">{children}</table>
          </div>
        ),
        thead: ({children}) => <thead className="bg-muted/50 font-medium">{children}</thead>,
        tbody: ({children}) => <tbody className="[&_tr:last-child]:border-0">{children}</tbody>,
        tr: ({children}) => <tr className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">{children}</tr>,
        th: ({children}) => <th className="h-10 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0">{children}</th>,
        td: ({children}) => <td className="p-4 align-middle [&:has([role=checkbox])]:pr-0">{children}</td>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
});

MarkdownViewer.displayName = "MarkdownViewer";