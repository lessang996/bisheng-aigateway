import type { ReactNode } from 'react'
export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) { return <section className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>{action}</section> }
export function StatusTag({ children, processing = false }: { children: ReactNode; processing?: boolean }) { return <b className={`tag ${processing ? 'processing' : ''}`}>{children}</b> }
export function EmptyState({ title, description }: { title: string; description: string }) { return <div className="empty"><span className="empty-icon">▤</span><b>{title}</b><p>{description}</p></div> }
