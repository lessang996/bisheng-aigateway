import { FormEvent, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { createIndustryReport } from '../../api/industry'
import type { AgentEvent } from '../../types/api'
import { parseSse } from '../../utils/sse'

export default function App() {
  const [input, setInput] = useState(''); const [token, setToken] = useState('')
  const [report, setReport] = useState(''); const [reasoning, setReasoning] = useState(''); const [status, setStatus] = useState<'idle'|'loading'|'done'>('idle'); const [error, setError] = useState(''); const [notice, setNotice] = useState('')
  const abortRef = useRef<AbortController | null>(null); const reportRef = useRef<HTMLDivElement>(null)
  useEffect(() => { reportRef.current?.scrollTo({ top: reportRef.current.scrollHeight, behavior: 'smooth' }) }, [report])
  const submit = async (e: FormEvent) => {
    e.preventDefault(); if (!input.trim() || status === 'loading') return
    abortRef.current = new AbortController(); setReport(''); setReasoning(''); setError(''); setNotice(''); setStatus('loading')
    try {
      const response = await createIndustryReport(input.trim(), token, abortRef.current.signal)
      for await (const event of parseSse(response)) {
        if (event.event === 'error') throw new Error('流式服务初始化失败')
        try { const payload = JSON.parse(event.data) as AgentEvent; const body = payload.data; if (body?.type === 'text' && ['TEXT_START','TEXT_DELTA'].includes(payload.eventType || event.event || '')) setReport(current => current + (body.text || '')); else if (body?.type === 'reasoning' && ['REASONING_START','REASONING_DELTA'].includes(payload.eventType || event.event || '')) setReasoning(current => current + (body.text || '')); else if (body?.type === 'agent_status' && body.message) setNotice(body.message); else if (body?.type === 'message' && payload.eventType === 'MESSAGE_FAILED') throw new Error(body.message || '分析任务失败') } catch (error) { if (error instanceof Error && error.message === '分析任务失败') throw error }
      }
      setStatus('done')
    } catch (cause) { if ((cause as Error).name !== 'AbortError') { setError(cause instanceof Error ? cause.message : '请求失败'); setStatus('idle') } }
    finally { abortRef.current = null }
  }
  const stop = () => abortRef.current?.abort(); const clear = () => { stop(); setReport(''); setReasoning(''); setError(''); setNotice(''); setStatus('idle') }
  return <main className="page"><section className="card"><div className="eyebrow">BISHENG GATEWAY</div><h1>行业分析报告</h1><p className="intro">输入企业或行业需求，实时生成专业分析报告。</p><form onSubmit={submit}><label>分析需求<textarea value={input} onChange={e => setInput(e.target.value)} placeholder="例如：分析新能源汽车行业的竞争格局与未来趋势" rows={5} /></label><label className="token">Bearer Token <span>（可选）</span><input type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="需要鉴权时填写" /></label><div className="actions"><button className="primary" disabled={!input.trim() || status === 'loading'}>{status === 'loading' ? '分析中…' : '开始分析'}</button>{status === 'loading' && <button type="button" onClick={stop}>停止</button>} {(report || error) && <button type="button" className="quiet" onClick={clear}>清空</button>}</div></form>{notice && <div className="notice">{notice}</div>}{reasoning && <details className="reasoning"><summary>思考过程</summary><pre>{reasoning}</pre></details>}<div className="report" ref={reportRef} aria-live="polite">{report ? <ReactMarkdown>{report}</ReactMarkdown> : <div className="empty">{status === 'loading' ? '正在等待报告正文…' : 'Markdown 格式的报告将在这里实时显示'}</div>}</div>{error && <div className="error">{error}</div>}{status === 'done' && !error && <div className="success">分析已完成</div>}</section></main>
}
