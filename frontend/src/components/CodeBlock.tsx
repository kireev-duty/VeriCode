import { Highlight, themes } from 'prism-react-renderer'

const LANG: Record<string, string> = {
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  jsx: 'jsx',
  sql: 'sql',
  bash: 'bash',
  html: 'markup',
  css: 'css',
  dockerfile: 'docker',
  text: 'text',
}

export function CodeBlock({ code, lang }: { code: string; lang: string }) {
  return (
    <Highlight theme={themes.oneLight} code={code} language={LANG[lang] ?? 'text'}>
      {({ tokens, getLineProps, getTokenProps }) => (
        <pre className="overflow-x-auto rounded-xl border border-line bg-[#fafafa] p-4 font-mono text-[13px] leading-relaxed">
          {tokens.map((line, i) => (
            <div key={i} {...getLineProps({ line })}>
              <span className="mr-4 inline-block w-5 text-right text-muted/50 select-none">{i + 1}</span>
              {line.map((token, key) => (
                <span key={key} {...getTokenProps({ token })} />
              ))}
            </div>
          ))}
        </pre>
      )}
    </Highlight>
  )
}
