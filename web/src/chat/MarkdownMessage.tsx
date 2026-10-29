import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'
import { useCallback } from 'react'

export function MarkdownMessage({ content }: { content: string }) {
  const copy = useCallback(async (text: string) => {
    try { await navigator.clipboard.writeText(text) } catch {}
  }, [])
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" className="link" />
          ),
          code: ({ node, className, children, ...props }) => {
            const isBlock = (className || '').includes('hljs')
            if (!isBlock) return <code className="inline-code" {...props}>{children}</code>
            const text = String(children).replace(/\n$/, '')
            return (
              <div className="code-block">
                <button className="copy-btn" onClick={() => copy(text)}>Copy</button>
                <code className={className} {...props}>{children}</code>
              </div>
            )
          },
          pre: ({ children }) => <pre className="code-pre">{children}</pre>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
