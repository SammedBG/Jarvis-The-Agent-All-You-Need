import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'

describe('Markdown sanitizer', () => {
  it('does not render script tags or onerror attributes', () => {
    const malicious = 'hi <script>alert(1)</script> <img src=x onerror="alert(2)" />'
    const { container } = render(
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{malicious}</ReactMarkdown>
    )
    expect(container.querySelector('script')).toBeNull()
    const html = container.innerHTML
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
  })
})
