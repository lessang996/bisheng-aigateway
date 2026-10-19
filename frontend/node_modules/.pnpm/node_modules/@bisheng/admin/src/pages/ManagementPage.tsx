import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { apiClient } from '@bisheng/api';
import { tokenStore } from '@bisheng/auth';

type Resource = 'users' | 'roles' | 'permissions' | 'menus';
type Row = { id: number; username?: string; name?: string; code?: string; email?: string; department?: string; employee_id?: string; is_active?: boolean; is_builtin?: boolean; local_login_enabled?: boolean; role_ids?: number[]; permission_ids?: number[]; menu_ids?: number[]; data_scope?: string; kind?: string; path?: string; parent_id?: number; icon?: string; sort_order?: number; permission_code?: string };
type Options = { roles: Row[]; permissions: Row[]; menus: Row[]; pages: { path: string; name: string; permission_code: string }[] };
const titles: Record<Resource, string> = { users: '用户管理', roles: '角色管理', permissions: '权限管理', menus: '菜单管理' };
const scopeNames: Record<string,string> = {self:'本人',department:'本部门',all:'全部'};

export default function ManagementPage({ resource }: { resource: Resource }) {
  const token = tokenStore.get();
  const [page, setPage] = useState(1), [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();
  const query = useQuery({ queryKey: ['management', token, resource, page, search], queryFn: () => apiClient.json<{items: Row[]; total: number}>(`/admin/${resource}?page=${page}&q=${encodeURIComponent(search)}`) });
  const options = useQuery({queryKey: ['rbac-options', token], queryFn: () => apiClient.json<Options>('/admin/rbac-options')});
  const kind = Form.useWatch('kind', form);
  const localLogin = Form.useWatch('local_login_enabled', form);
  const choices = (rows?: Row[]) => (rows || []).map(r => ({ value: r.id, label: r.name || r.username || r.code }));
  const refresh = async () => { await queryClient.invalidateQueries({queryKey:['management']}); await queryClient.invalidateQueries({queryKey:['rbac-options']}); await queryClient.invalidateQueries({queryKey:['identity']}); };
  const open = (row: Row | null) => {
    setEditing(row); form.resetFields();
    form.setFieldsValue(row ? {...row, password: undefined} : {is_active:true, local_login_enabled: true, data_scope:'self', kind:'page', sort_order:0, permission_ids:[], menu_ids:[]});
  };
  const save = async () => {
    let values;
    try { values = await form.validateFields(); } catch { return; }
    if (resource === 'users') {
      for (const key of ['department', 'employee_id']) values[key] = values[key] || null;
      if (!values.email) delete values.email;
    }
    if (resource === 'menus') {
      values.parent_id = values.parent_id ?? null;
      values.permission_code = values.permission_code ?? null;
      values.icon = values.icon || '';
    }
    if (!values.password) delete values.password;
    if (resource === 'menus' && values.kind === 'directory') values.path = null;
    setSaving(true);
    try {
      await apiClient.json(`/admin/${resource}${editing ? '/' + editing.id : ''}`, {method:editing ? 'PUT':'POST', body:JSON.stringify(values)});
      setEditing(undefined); await refresh(); messageApi.success('已保存');
    } catch (error) { messageApi.error(error instanceof Error ? error.message : '保存失败'); }
    finally { setSaving(false); }
  };
  const remove = async (row: Row) => {
    try { await apiClient.json(`/admin/${resource}/${row.id}`, {method:'DELETE'}); await refresh(); }
    catch(error) { messageApi.error(error instanceof Error ? error.message : '操作失败'); }
  };
  const columns = [
    {title:'ID', dataIndex:'id', width:70},
    {title: resource === 'users' ? '用户名':'名称', dataIndex:resource === 'users'?'username':'name'},
    ...(resource === 'users' ? [{title:'部门',dataIndex:'department'},{title:'邮箱',dataIndex:'email'},{title:'角色',render:(_:unknown,r:Row)=>(r.role_ids||[]).map(id=><Tag key={id}>{options.data?.roles.find(x=>x.id===id)?.name || id}</Tag>)}]
      : [{title:'编码',dataIndex:'code'}]),
    ...(resource === 'roles' ? [{title:'数据范围',dataIndex:'data_scope',render:(v:string)=>scopeNames[v]}] : []),
    ...(resource === 'menus' ? [{title:'类型',dataIndex:'kind'},{title:'地址',dataIndex:'path'},{title:'排序',dataIndex:'sort_order'}] : []),
    ...(resource !== 'permissions' ? [{title:'状态',dataIndex:'is_active',render:(v:boolean)=><Tag color={v?'green':'default'}>{v?'启用':'停用'}</Tag>}] : []),
    {title:'操作',render:(_:unknown,r:Row)=><Space><Button size="small" onClick={()=>open(r)}>编辑</Button>{!r.is_builtin && <Popconfirm title={resource==='users'?'确认停用此用户？':'确认删除？'} onConfirm={()=>remove(r)}><Button danger size="small">{resource==='users'?'停用':'删除'}</Button></Popconfirm>}</Space>},
  ];
  return <section className="panel">{contextHolder}<Typography.Title level={3}>{titles[resource]}</Typography.Title>
    {resource==='permissions' && <Alert type="info" showIcon message="新增权限编码需在前后端业务检查点接入后生效。" style={{marginBottom:16}}/>}
    {resource==='menus' && <Alert type="info" showIcon message="菜单支持已注册页面和 HTTP/HTTPS 外链；新业务页面仍需开发。" style={{marginBottom:16}}/>}
    <Space style={{marginBottom:16}}><Input.Search placeholder="搜索名称" allowClear onSearch={value=>{setSearch(value);setPage(1);}}/><Button type="primary" onClick={()=>open(null)}>新增</Button><Button onClick={()=>void refresh()}>刷新</Button></Space>
    {query.error && <Alert type="error" message={query.error.message}/>}
    {options.error && <Alert type="error" message={options.error.message}/>}
    <Table rowKey="id" loading={query.isFetching} dataSource={query.error ? [] : query.data?.items} columns={columns} scroll={{x:900}} pagination={{current:page,total:query.data?.total,pageSize:20,onChange:setPage,showSizeChanger:false}}/>
    <Modal title={`${editing?'编辑':'新增'}${titles[resource]}`} open={editing!==undefined} onCancel={()=>setEditing(undefined)} onOk={()=>void save()} confirmLoading={saving} width={680} destroyOnClose>
      <Form form={form} layout="vertical" preserve={false}>
        {resource==='users' ? <>
          <Form.Item name="username" label="用户名（外部 userNo）" rules={[{required:true}]}><Input disabled={!!editing} maxLength={100}/></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{type:'email'}]}><Input maxLength={255}/></Form.Item>
          <Form.Item name="department" label="部门"><Input maxLength={100}/></Form.Item>
          <Form.Item name="employee_id" label="工号"><Input maxLength={50}/></Form.Item>
          <Form.Item name="local_login_enabled" label="允许密码登录" valuePropName="checked"><Switch/></Form.Item>
          <Form.Item name="password" label={editing?'重置密码（留空保留原密码）':'密码'} rules={[{required:!!localLogin && (!editing || !editing.local_login_enabled),min:8,max:72}]}><Input.Password autoComplete="new-password"/></Form.Item>
          <Form.Item name="role_ids" label="角色（新建留空使用普通用户）"><Select mode="multiple" options={choices(options.data?.roles)}/></Form.Item>
        </> : <>
          <Form.Item name="name" label="名称" rules={[{required:true}]}><Input maxLength={100}/></Form.Item>
          <Form.Item name="code" label="编码" rules={[{required:true},{pattern:/^[a-z][a-z0-9:_-]*$/,message:'使用小写字母、数字、冒号、下划线或短横线'}]}><Input disabled={!!editing?.is_builtin}/></Form.Item>
        </>}
        {resource==='roles' && <>
          <Form.Item name="data_scope" label="数据范围" rules={[{required:true}]}><Select options={Object.entries(scopeNames).map(([value,label])=>({value,label}))}/></Form.Item>
          <Form.Item name="permission_ids" label="接口与操作权限"><Select mode="multiple" options={choices(options.data?.permissions)}/></Form.Item>
          <Form.Item name="menu_ids" label="菜单授权"><Select mode="multiple" options={choices(options.data?.menus)}/></Form.Item>
        </>}
        {resource==='menus' && <>
          <Form.Item name="kind" label="类型" rules={[{required:true}]}><Select options={[{value:'directory',label:'目录'},{value:'page',label:'已有页面'},{value:'external',label:'外链'}]}/></Form.Item>
          <Form.Item name="parent_id" label="父目录"><Select allowClear options={choices(options.data?.menus.filter(m=>m.kind==='directory' && m.id!==editing?.id))}/></Form.Item>
          {kind==='page' && <Form.Item name="path" label="页面" rules={[{required:true}]}><Select options={options.data?.pages.map(p=>({value:p.path,label:`${p.name} (${p.path})`}))}/></Form.Item>}
          {kind==='external' && <Form.Item name="path" label="外链地址" rules={[{required:true},{type:'url'}]}><Input/></Form.Item>}
          {kind!=='page' && <Form.Item name="permission_code" label="附加权限（可选）"><Select allowClear options={options.data?.permissions.map(p=>({value:p.code,label:p.name}))}/></Form.Item>}
          <Form.Item name="icon" label="图标文字或符号"><Input maxLength={64}/></Form.Item>
          <Form.Item name="sort_order" label="排序"><InputNumber/></Form.Item>
        </>}
        {resource!=='permissions' && <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch/></Form.Item>}
      </Form>
    </Modal>
  </section>;
}
