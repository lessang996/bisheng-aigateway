import { FormEvent, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { reportApi } from '@bisheng/api'
import type { AgentEvent } from '@bisheng/types'
import { parseSse } from '@bisheng/sse'

type RequestStatus = 'idle' | 'loading' | 'done'
type Workspace = 'dashboard' | 'reports'

const navigation = [
  ['dashboard', '工作台', '▦'],
  ['agents', 'Agent 管理', '◇'],
  ['conversations', '对话中心', '◌'],
  ['reports', '报告中心', '▤'],
  ['knowledge', '知识库', '▱'],
  ['users', '用户与权限', '♙'],
  ['system', '系统监控', '◉'],
] as const

const metrics = [
  { label: '今日请求量', value: '12,846', change: '+12.6%', tone: 'blue' },
  { label: '运行中 Agent', value: '18', change: '2 个待发布', tone: 'violet' },
  { label: 'Token 使用量', value: '2.84M', change: '+8.2%', tone: 'orange' },
  { label: '请求成功率', value: '99.82%', change: '+0.14%', tone: 'green' },
]

const recentReports = [
  ['银行业发展趋势研究报告', '行业研究 Agent', '已完成', '10:32'],
  ['新能源汽车行业研究报告', '报告生成 Agent', '生成中', '09:48'],
  ['人工智能产业链分析报告', '行业研究 Agent', '已完成', '昨天'],
]

export default function IndustryReportPage() {
  const [workspace, setWorkspace] = useState<Workspace>('dashboard')
  const [input, setInput] = useState('分析新能源汽车行业的竞争格局与未来三年发展趋势')
  const [token, setToken] = useState('')
  const [report, setReport] = useState('')
  const [reasoning, setReasoning] = useState('')
  const [status, setStatus] = useState<RequestStatus>('idle')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const reportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    reportRef.current?.scrollTo({ top: reportRef.current.scrollHeight, behavior: 'smooth' })
  }, [report])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!input.trim() || status === 'loading') return

    abortRef.current = new AbortController()
    setReport('')
    setReasoning('')
    setError('')
    setNotice('正在建立与行业研究 Agent 的连接')
    setStatus('loading')

    try {
      const response = await reportApi.create(input.trim(), token, abortRef.current.signal)

      for await (const event of parseSse(response)) {
        if (event.event === 'error') throw new Error('流式服务初始化失败')

        try {
          const payload = JSON.parse(event.data) as AgentEvent
          const body = payload.data
          const eventType = payload.eventType || event.event || ''

          if (body?.type === 'text' && ['TEXT_START', 'TEXT_DELTA'].includes(eventType)) {
            setReport((current) => current + (body.text || ''))
          } else if (body?.type === 'reasoning' && ['REASONING_START', 'REASONING_DELTA'].includes(eventType)) {
            setReasoning((current) => current + (body.text || ''))
          } else if (body?.type === 'agent_status' && body.message) {
            setNotice(body.message)
          } else if (body?.type === 'message' && eventType === 'MESSAGE_FAILED') {
            throw new Error(body.message || '分析任务失败')
          }
        } catch (cause) {
          if (cause instanceof Error && cause.message !== 'Unexpected end of JSON input') throw cause
        }
      }

      setNotice('报告已生成完成')
      setStatus('done')
    } catch (cause) {
      if ((cause as Error).name !== 'AbortError') {
        setError(cause instanceof Error ? cause.message : '请求失败')
        setNotice('')
        setStatus('idle')
      }
    } finally {
      abortRef.current = null
    }
  }

  const stop = () => abortRef.current?.abort()

  const clear = () => {
    stop()
    setReport('')
    setReasoning('')
    setError('')
    setNotice('')
    setStatus('idle')
  }

  const openReport = () => {
    setWorkspace('reports')
    clear()
  }

  return (
    <>
      {workspace === 'dashboard' ? (
        <Dashboard onCreateReport={openReport} />
      ) : (
        <ReportWorkspace
          input={input}
          setInput={setInput}
          token={token}
          setToken={setToken}
          report={report}
          reasoning={reasoning}
          status={status}
          error={error}
          notice={notice}
          reportRef={reportRef}
          onSubmit={submit}
          onStop={stop}
          onClear={clear}
        />
      )}
    </>
  )
}

function Dashboard({ onCreateReport }: { onCreateReport: () => void }) {
  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">工作台</p>
          <h1>欢迎回来，张明远</h1>
          <p>查看 AI Gateway 的运行概况与近期任务。</p>
        </div>
        <button className="primary-button" onClick={onCreateReport}>
          ＋ 创建报告
        </button>
      </section>

      <section className="metrics-grid">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <div className={`metric-icon ${metric.tone}`}>◔</div>
            <p>{metric.label}</p>
            <strong>{metric.value}</strong>
            <small className={metric.tone === 'orange' ? 'muted' : 'positive'}>{metric.change}</small>
          </article>
        ))}
      </section>

      <section className="dashboard-grid">
        <article className="panel trend-panel">
          <div className="panel-heading">
            <div>
              <h2>请求趋势</h2>
              <p>近 7 天 API 调用情况</p>
            </div>
            <button className="select-button">近 7 天⌄</button>
          </div>
          <div className="chart">
            <div className="chart-scale">
              <span>2.4k</span>
              <span>1.8k</span>
              <span>1.2k</span>
              <span>600</span>
              <span>0</span>
            </div>
            <svg viewBox="0 0 640 210" role="img" aria-label="近七天请求趋势图">
              <path d="M0 169 H640 M0 122 H640 M0 75 H640 M0 28 H640" className="grid-line" />
              <path d="M0 160 C36 145 55 164 91 137 S146 124 183 132 S241 73 274 91 S326 122 364 96 S422 61 457 76 S511 36 546 55 S599 64 640 28" className="trend-area" />
              <path d="M0 160 C36 145 55 164 91 137 S146 124 183 132 S241 73 274 91 S326 122 364 96 S422 61 457 76 S511 36 546 55 S599 64 640 28" className="trend-line" />
            </svg>
            <div className="chart-days">
              <span>09/22</span>
              <span>09/23</span>
              <span>09/24</span>
              <span>09/25</span>
              <span>09/26</span>
              <span>09/27</span>
              <span>今天</span>
            </div>
          </div>
        </article>

        <article className="panel health-panel">
          <div className="panel-heading">
            <div>
              <h2>系统状态</h2>
              <p>核心服务健康检查</p>
            </div>
            <button className="link-button">查看监控</button>
          </div>
          {[
            ['Gateway API', '运行正常', '12ms'],
            ['Redis', '运行正常', '3ms'],
            ['BiSheng 服务', '运行正常', '86ms'],
            ['LLM Provider', '轻微波动', '1.2s'],
          ].map(([name, detail, latency], index) => (
            <div className="health-row" key={name}>
              <span className={`status-dot ${index === 3 ? 'warning' : 'online'}`} />
              <div>
                <b>{name}</b>
                <small>{detail}</small>
              </div>
              <span>{latency}</span>
            </div>
          ))}
        </article>
      </section>

      <section className="panel tasks-panel">
        <div className="panel-heading">
          <div>
            <h2>最近任务</h2>
            <p>最近创建或更新的报告任务</p>
          </div>
          <button className="link-button" onClick={onCreateReport}>
            查看全部
          </button>
        </div>
        <div className="task-table">
          <div className="table-head">
            <span>报告名称</span>
            <span>所属 Agent</span>
            <span>状态</span>
            <span>更新时间</span>
          </div>
          {recentReports.map(([title, agent, taskStatus, time]) => (
            <div className="table-row" key={title}>
              <span className="report-name">
                <i>▤</i>
                {title}
              </span>
              <span>{agent}</span>
              <span>
                <b className={`tag ${taskStatus === '生成中' ? 'processing' : ''}`}>{taskStatus}</b>
              </span>
              <span>{time}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

type ReportWorkspaceProps = {
  input: string
  setInput: (value: string) => void
  token: string
  setToken: (value: string) => void
  report: string
  reasoning: string
  status: RequestStatus
  error: string
  notice: string
  reportRef: React.RefObject<HTMLDivElement | null>
  onSubmit: (event: FormEvent) => void
  onStop: () => void
  onClear: () => void
}

function ReportWorkspace(props: ReportWorkspaceProps) {
  const { input, setInput, token, setToken, report, reasoning, status, error, notice, reportRef, onSubmit, onStop, onClear } = props

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">报告中心</p>
          <h1>行业研究报告</h1>
          <p>使用行业研究 Agent，实时生成可编辑的专业分析报告。</p>
        </div>
        <div className="page-actions">
          <button className="secondary-button" onClick={onClear}>
            清空内容
          </button>
          <button className="primary-button" form="report-form" type="submit" disabled={!input.trim() || status === 'loading'}>
            {status === 'loading' ? '正在生成' : '生成报告'}
          </button>
        </div>
      </section>

      <section className="report-grid">
        <article className="panel report-config">
          <div className="panel-heading">
            <div>
              <h2>报告配置</h2>
              <p>设置研究范围与生成参数</p>
            </div>
          </div>
          <form id="report-form" onSubmit={onSubmit}>
            <label>
              分析需求
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="例如：分析新能源汽车行业的竞争格局与未来趋势"
                rows={7}
              />
            </label>
            <div className="field-help">清晰描述行业、研究视角和时间范围，可获得更准确的结果。</div>
            <label>
              执行 Agent
              <div className="field-select">
                行业研究 Agent <span>⌄</span>
              </div>
            </label>
            <label>
              访问令牌 <span className="optional">可选</span>
              <input
                type="password"
                value={token}
                onChange={(event) => setToken(event.target.value)}
                placeholder="需要鉴权时填写"
                autoComplete="off"
              />
            </label>
            <div className="form-actions">
              <button className="primary-button" disabled={!input.trim() || status === 'loading'}>
                {status === 'loading' ? '◌ 生成中' : '开始生成'}
              </button>
              {status === 'loading' && (
                <button className="secondary-button" type="button" onClick={onStop}>
                  停止生成
                </button>
              )}
            </div>
          </form>
          <div className="agent-summary">
            <span className="agent-icon">◇</span>
            <div>
              <b>行业研究 Agent</b>
              <small>Qwen-Max · 支持流式输出</small>
            </div>
            <span className="status-dot online" />
          </div>
        </article>

        <article className="panel report-output">
          <div className="panel-heading">
            <div>
              <h2>报告预览</h2>
              <p>{status === 'loading' ? '正在接收流式内容' : 'Markdown 格式，可导出为文档'}</p>
            </div>
            <div className="output-status">
              <span className={`status-dot ${status === 'loading' ? 'processing-dot' : 'online'}`} />
              {status === 'loading' ? '生成中' : status === 'done' ? '已完成' : '等待生成'}
            </div>
          </div>
          {notice && (
            <div className="stream-notice">
              <span className="status-dot processing-dot" />
              {notice}
            </div>
          )}
          {reasoning && (
            <details className="reasoning">
              <summary>查看 Agent 思考过程</summary>
              <pre>{reasoning}</pre>
            </details>
          )}
          <div className="report" ref={reportRef} aria-live="polite">
            {report ? (
              <ReactMarkdown>{report}</ReactMarkdown>
            ) : (
              <div className="empty">
                <span className="empty-icon">▤</span>
                <b>{status === 'loading' ? '正在等待报告正文' : '报告将在这里生成'}</b>
                <p>{status === 'loading' ? 'Agent 正在准备行业研究上下文' : '提交研究需求后，实时查看 Markdown 格式的报告内容。'}</p>
              </div>
            )}
          </div>
          {error && (
            <div className="error">
              <b>生成失败</b>
              <span>{error}</span>
              <button onClick={onClear}>重新开始</button>
            </div>
          )}
        </article>
      </section>
    </>
  )
}