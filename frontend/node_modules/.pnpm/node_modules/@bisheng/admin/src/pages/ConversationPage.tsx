import { FormEvent, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Avatar, Button, Empty, Input, List, Space, Typography } from 'antd';
import { PlusOutlined, StopOutlined } from '@ant-design/icons';
import { reportApi } from '@bisheng/api';
import type { AgentEvent } from '@bisheng/types';
import { parseSse } from '@bisheng/sse';

type ChatRole = 'user' | 'assistant';

type ConversationItem = {
  id: number;
  title: string;
  preview: string;
  updatedAt: string;
};

type ChatMessage = {
  id: number;
  role: ChatRole;
  content: string;
  createdAt: string;
};

const { Text, Title } = Typography;
const { TextArea } = Input;

const initialConversations: ConversationItem[] = [
  {
    id: 1,
    title: '新能源汽车行业分析',
    preview: '请分析未来三年的趋势与竞争格局',
    updatedAt: '刚刚',
  },
  {
    id: 2,
    title: '企业知识库问答',
    preview: '如何提升跨部门协同效率？',
    updatedAt: '10:42',
  },
  {
    id: 3,
    title: 'AI Agent 运营建议',
    preview: '请评估运营指标提升空间',
    updatedAt: '昨天',
  },
];

const initialMessages: Record<number, ChatMessage[]> = {
  1: [
    {
      id: 101,
      role: 'user',
      content: '请分析新能源汽车行业未来三年的竞争格局与发展趋势。',
      createdAt: '09:42',
    },
    {
      id: 102,
      role: 'assistant',
      content:
        '新能源汽车行业在未来三年将继续保持高增长，核心驱动因素来自政策支持、成本下降、智能化升级和充电基础设施完善。行业竞争将从“产能扩张”逐步转向“技术与生态竞争”。',
      createdAt: '09:43',
    },
  ],
  2: [
    {
      id: 201,
      role: 'user',
      content: '如何提升企业跨部门协同效率？',
      createdAt: '10:20',
    },
    {
      id: 202,
      role: 'assistant',
      content:
        '建议从统一数据口径、建立标准协同流程和智能化任务跟踪三方面入手。组织间的关键不在于增加沟通频率，而在于减少重复决策与信息断层。',
      createdAt: '10:21',
    },
  ],
  3: [
    {
      id: 301,
      role: 'user',
      content: '请评估 AI Agent 运营指标提升空间。',
      createdAt: '昨天',
    },
    {
      id: 302,
      role: 'assistant',
      content:
        '从调用成功率、响应时延、复用率和任务完成率四个维度看，当前最大提升空间集中在提示词质量和工具链稳定性。',
      createdAt: '昨天',
    },
  ],
};

export default function ConversationPage() {
  const [conversations, setConversations] = useState<ConversationItem[]>(initialConversations);
  const [activeId, setActiveId] = useState<number>(initialConversations[0].id);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages[initialConversations[0].id]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const activeConversation = conversations.find((item) => item.id === activeId) ?? conversations[0];

  const createNewConversation = () => {
    const nextId = Date.now();
    const nextConversation: ConversationItem = {
      id: nextId,
      title: '新对话',
      preview: '开始新的会话',
      updatedAt: '刚刚',
    };

    setConversations((prev) => [nextConversation, ...prev]);
    setActiveId(nextId);
    setMessages([
      {
        id: nextId + 1,
        role: 'assistant',
        content: '您好，我是 AI Gateway 助手。请告诉我你的业务问题，我可以协助分析、总结和规划。',
        createdAt: '刚刚',
      },
    ]);
    setError('');
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim() || loading) return;

    const content = input.trim();
    const userMessage: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content,
      createdAt: '刚刚',
    };

    const assistantId = Date.now() + 1;
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      createdAt: '正在回复…',
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput('');
    setLoading(true);
    setError('');

    const conversationTitle = content.length > 18 ? `${content.slice(0, 18)}…` : content;
    setConversations((prev) =>
      prev.map((item) =>
        item.id === activeId
          ? { ...item, title: item.title === '新对话' ? conversationTitle : item.title, preview: content, updatedAt: '刚刚' }
          : item,
      ),
    );

    abortRef.current = new AbortController();
    let assistantContent = '';

    try {
      const response = await reportApi.create(content, '', abortRef.current.signal);

      for await (const event of parseSse(response)) {
        if (event.event === 'error') throw new Error('流式服务初始化失败');

        try {
          const payload = JSON.parse(event.data) as AgentEvent;
          const body = payload.data;
          const eventType = payload.eventType || event.event || '';

          if (body?.type === 'text' && ['TEXT_START', 'TEXT_DELTA'].includes(eventType)) {
            assistantContent += body.text || '';
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantId ? { ...message, content: assistantContent, createdAt: '正在回复…' } : message,
              ),
            );
          } else if (body?.type === 'message' && eventType === 'MESSAGE_FAILED') {
            throw new Error(body.message || '回复失败');
          }
        } catch (cause) {
          if (cause instanceof Error && cause.message !== 'Unexpected end of JSON input') {
            throw cause;
          }
        }
      }

      setMessages((prev) =>
        prev.map((message) => (message.id === assistantId ? { ...message, createdAt: '刚刚' } : message)),
      );
      setConversations((prev) =>
        prev.map((item) =>
          item.id === activeId ? { ...item, preview: assistantContent || content, updatedAt: '刚刚' } : item,
        ),
      );
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : '请求失败';
      setError(message);
      setMessages((prev) =>
        prev.map((messageItem) =>
          messageItem.id === assistantId
            ? { ...messageItem, content: '抱歉，消息生成失败，请稍后重试。', createdAt: '刚刚' }
            : messageItem,
        ),
      );
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  const stop = () => abortRef.current?.abort();

  const handleSelectConversation = (id: number) => {
    setActiveId(id);
    setMessages(initialMessages[id] ?? []);
    setError('');
  };

  return (
    <section className="chat-shell">
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <div>
            <p className="eyebrow">对话中心</p>
            <Title level={4} className="chat-sidebar-title">
              会话列表
            </Title>
          </div>
          <Button type="primary" icon={<PlusOutlined />} className="chat-new-button" onClick={createNewConversation}>
            新对话
          </Button>
        </div>

        <List
          className="chat-session-list"
          dataSource={conversations}
          renderItem={(item) => (
            <List.Item
              className={`chat-session-item ${item.id === activeId ? 'active' : ''}`}
              onClick={() => handleSelectConversation(item.id)}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space align="center" size={8}>
                  <Avatar size={22} className="chat-session-avatar">
                    ◌
                  </Avatar>
                  <Text strong className="chat-session-title">
                    {item.title}
                  </Text>
                </Space>
                <Text className="chat-session-preview">{item.preview}</Text>
                <Text type="secondary" className="chat-session-time">
                  {item.updatedAt}
                </Text>
              </Space>
            </List.Item>
          )}
        />
      </aside>

      <main className="chat-main">
        <header className="chat-header">
          <div>
            <p className="eyebrow">当前会话</p>
            <Title level={3} className="chat-header-title">
              {activeConversation?.title}
            </Title>
          </div>
          <Button
            type="default"
            icon={<StopOutlined />}
            onClick={stop}
            disabled={!loading}
            className="chat-stop-button"
          >
            停止生成
          </Button>
        </header>

        <div className="chat-message-list">
          {messages.length ? (
            messages.map((message) => (
              <div key={message.id} className={`chat-message-row ${message.role}`}>
                <Avatar className="chat-avatar" style={{ background: message.role === 'assistant' ? '#1677ff' : '#0f172a' }}>
                  {message.role === 'assistant' ? 'AI' : 'U'}
                </Avatar>
                <div className="chat-bubble">
                  {message.role === 'assistant' && message.content ? (
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  ) : (
                    <div>{message.content || '正在思考中…'}</div>
                  )}
                  <span className="chat-time">{message.createdAt}</span>
                </div>
              </div>
            ))
          ) : (
            <div className="chat-empty-state">
              <Empty description="暂无消息" />
            </div>
          )}
          <div ref={endRef} />
        </div>

        {error && <div className="chat-error">{error}</div>}

        <form className="chat-composer" onSubmit={submit}>
          <TextArea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入你的问题…"
            autoSize={{ minRows: 1, maxRows: 5 }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void submit(event as unknown as FormEvent);
              }
            }}
          />
          <Button type="primary" htmlType="submit" className="chat-send-button" disabled={!input.trim() || loading}>
            {loading ? '思考中' : '发送'}
          </Button>
        </form>
      </main>
    </section>
  );
}
