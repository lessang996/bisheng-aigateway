# Kubernetes 生产部署

`k8s/gateway.yaml` 提供 ConfigMap、Secret、Deployment、Service、PDB 和 HPA。部署前将镜像推送到集群可访问的仓库并替换 Secret 占位符；生产建议使用 External Secrets 或云 Secret Manager。

```bash
kubectl create namespace bisheng --dry-run=client -o yaml | kubectl apply -f -
kubectl -n bisheng apply -f k8s/gateway.yaml
kubectl -n bisheng rollout status deployment/bisheng-gateway
```

数据库迁移应作为发布流水线中的一次性 Job 执行成功后再滚动更新 Deployment。清单不会创建数据库或 Redis。Ingress、TLS、域名和网络策略按集群标准配置；SSE 入口需关闭代理缓冲并延长读取超时。
