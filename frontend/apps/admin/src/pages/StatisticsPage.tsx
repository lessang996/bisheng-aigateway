import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Col, Descriptions, Drawer, Form, Input, Row, Select, Space, Statistic, Table, Tabs, Typography } from 'antd';
import { apiClient } from '@bisheng/api';
import { tokenStore } from '@bisheng/auth';

type Metrics = {total:number; success:number; failed:number; interrupted:number; processing:number; unknown:number; cache_hits:number; cache_queries:number; cache_rate:number|null; avg_duration_ms:number|null};
type Group = Metrics & {name:string|null};
type Detail = {id:number;session_id:number;user_id:string;user_department:string|null;content:string|null;request_id:string|null;cache_status:string;execution_status:string;is_stream:boolean|null;created_at:string;completed_at:string|null;duration_ms:number|null;error_code:string|null;error_summary:string|null};
const cacheLabels:Record<string,string>={hit:'命中',miss:'未命中',unavailable:'不可用',error:'读取失败',unknown:'未知'};
const statusLabels:Record<string,string>={processing:'处理中',success:'成功',failed:'失败',interrupted:'中断',unknown:'未知'};
const formatTime=(value:string|null)=>value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'—';
const beijingDate=(offset=0)=>new Date(Date.now()+8*3600000+offset*86400000).toISOString().slice(0,10);

export default function StatisticsPage(){
  const token=tokenStore.get();
  const [filters,setFilters]=useState<Record<string,string>>({start:beijingDate(-29),end:beijingDate()});
  const [tab,setTab]=useState('user'),[page,setPage]=useState(1),[selected,setSelected]=useState<number|null>(null);
  const qs=new URLSearchParams(Object.entries(filters).filter(([,v])=>v!=='' && v!==undefined)).toString();
  const overview=useQuery({queryKey:['stats',token,qs],queryFn:()=>apiClient.json<Metrics>(`/stats/industry-report/overview?${qs}`)});
  const rows=useQuery({queryKey:['stats-rows',token,qs,tab,page],queryFn:()=>apiClient.json<{items:(Group&Detail)[];total:number}>(`/stats/industry-report/${tab==='details'?'details':'groups'}?${qs}&dimension=${tab}&page=${page}`)});
  const detail=useQuery({queryKey:['stats-detail',token,selected],queryFn:()=>apiClient.json<{request:Detail;answers:{id:number;content:string|null;role:string;created_at:string}[]}>(`/stats/industry-report/${selected}`),enabled:selected!==null});
  const metricsColumns=[{title:'请求数',dataIndex:'total'},{title:'成功',dataIndex:'success'},{title:'失败',dataIndex:'failed'},{title:'中断',dataIndex:'interrupted'},{title:'处理中',dataIndex:'processing'},{title:'未知',dataIndex:'unknown'},{title:'命中次数',dataIndex:'cache_hits'},{title:'命中率',dataIndex:'cache_rate',render:(v:number|null)=>v===null?'—':`${v}%`},{title:'平均耗时(ms)',dataIndex:'avg_duration_ms',render:(v:number|null)=>v??'—'}];
  const columns=tab==='details'?[
    {title:'用户',dataIndex:'user_id'},{title:'部门',dataIndex:'user_department',render:(v:string|null)=>v||'未知部门'},
    {title:'提问',dataIndex:'content',ellipsis:true},{title:'时间（北京时间）',dataIndex:'created_at',render:formatTime},
    {title:'缓存',dataIndex:'cache_status',render:(v:string)=>cacheLabels[v]||'未知'},
    {title:'结果',dataIndex:'execution_status',render:(v:string)=>statusLabels[v]||'未知'},
    {title:'耗时(ms)',dataIndex:'duration_ms',render:(v:number|null)=>v??'—'},
    {title:'操作',render:(_:unknown,r:Detail)=><Button onClick={()=>setSelected(r.id)}>详情</Button>},
  ]:[{title:'分组',dataIndex:'name',render:(v:string|null)=>tab==='cache'?cacheLabels[v||'unknown']:v||(tab==='department'?'未知部门':'未知用户')},...metricsColumns];
  return <section className="panel"><Typography.Title level={3}>使用统计</Typography.Title>
    <Typography.Paragraph type="secondary">按提问计次；日期为北京时间（含结束日）。命中率仅包含命中与未命中的有效缓存查询，历史缺失信息显示未知。</Typography.Paragraph>
    <Form layout="inline" initialValues={filters} onFinish={values=>{setFilters(values);setPage(1);}} style={{gap:12,marginBottom:20}}>
      <Form.Item name="start" label="开始日期"><Input type="date"/></Form.Item><Form.Item name="end" label="结束日期"><Input type="date"/></Form.Item>
      <Form.Item name="user_id" label="用户"><Input placeholder="精确用户名" allowClear/></Form.Item><Form.Item name="department" label="部门"><Input placeholder="精确部门名" allowClear/></Form.Item>
      <Form.Item name="cache_status" label="缓存"><Select allowClear style={{width:125}} options={Object.entries(cacheLabels).map(([value,label])=>({value,label}))}/></Form.Item>
      <Form.Item name="execution_status" label="结果"><Select allowClear style={{width:125}} options={Object.entries(statusLabels).map(([value,label])=>({value,label}))}/></Form.Item>
      <Form.Item name="is_stream" label="模式"><Select allowClear style={{width:115}} options={[{value:'true',label:'流式'},{value:'false',label:'非流式'}]}/></Form.Item>
      <Button type="primary" htmlType="submit">查询</Button><Button onClick={()=>{void overview.refetch();void rows.refetch();}}>刷新</Button>
    </Form>
    {(overview.error||rows.error) && <Alert type="error" message={(overview.error||rows.error)?.message}/>}
    <Row gutter={[16,16]} style={{marginBottom:24}}>{[
      ['请求总数',overview.data?.total],['成功',overview.data?.success],['失败',overview.data?.failed],['中断',overview.data?.interrupted],['缓存命中率',overview.data?.cache_rate==null?'—':`${overview.data.cache_rate}%`],['平均耗时(ms)',overview.data?.avg_duration_ms??'—'],
    ].map(([label,value])=><Col key={label} xs={12} lg={4}><Statistic title={label} value={value??'—'}/></Col>)}</Row>
    <Tabs activeKey={tab} onChange={value=>{setTab(value);setPage(1);}} items={[['user','按用户'],['department','按部门'],['day','按日'],['month','按月'],['cache','按缓存'],['details','使用明细']].map(([key,label])=>({key,label}))}/>
    <Table rowKey={row=>tab==='details'?row.id:row.name??'unknown'} loading={rows.isFetching} dataSource={rows.error ? [] : rows.data?.items} columns={columns} scroll={{x:1200}} pagination={{current:page,total:rows.data?.total,pageSize:20,onChange:setPage,showSizeChanger:false}}/>
    <Drawer title="使用详情" open={selected!==null} onClose={()=>setSelected(null)} width="min(850px, 95vw)">
      {detail.error && <Alert type="error" message={detail.error.message}/>}
      {detail.data && !detail.error && !detail.isFetching && <Space direction="vertical" style={{width:'100%'}} size="large">
        <Descriptions column={2} bordered items={[
          {key:'user',label:'用户',children:detail.data.request.user_id},{key:'department',label:'部门',children:detail.data.request.user_department||'未知部门'},
          {key:'session',label:'会话ID',children:detail.data.request.session_id},{key:'request',label:'调用ID',children:detail.data.request.request_id||'—'},
          {key:'time',label:'开始时间',children:formatTime(detail.data.request.created_at)},{key:'end',label:'完成时间',children:formatTime(detail.data.request.completed_at)},
          {key:'cache',label:'缓存',children:cacheLabels[detail.data.request.cache_status]},{key:'state',label:'结果',children:statusLabels[detail.data.request.execution_status]},
          {key:'mode',label:'模式',children:detail.data.request.is_stream===null?'未知':detail.data.request.is_stream?'流式':'非流式'},
          {key:'duration',label:'耗时(ms)',children:detail.data.request.duration_ms??'—'},
        ]}/>
        {detail.data.request.error_summary && <Alert type="warning" message={detail.data.request.error_code} description={detail.data.request.error_summary}/>}
        <Typography.Title level={5}>提问</Typography.Title><div style={{whiteSpace:'pre-wrap'}}>{detail.data.request.content}</div>
        <Typography.Title level={5}>回答</Typography.Title>{detail.data.answers.length?detail.data.answers.map(a=><div key={a.id} style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{a.content||'（空回答）'}</div>):<Typography.Text type="secondary">没有已保存的回答</Typography.Text>}
      </Space>}
    </Drawer>
  </section>;
}
