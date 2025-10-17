# Duo Workflow Service EKS Operational Runbook

This runbook provides operational procedures for managing the Duo Workflow Service deployment on AWS EKS.

## Table of Contents

1. [Service Overview](#service-overview)
2. [Monitoring and Alerting](#monitoring-and-alerting)
3. [Deployment Operations](#deployment-operations)
4. [Scaling Operations](#scaling-operations)
5. [Troubleshooting](#troubleshooting)
6. [Incident Response](#incident-response)
7. [Maintenance Procedures](#maintenance-procedures)
8. [Emergency Procedures](#emergency-procedures)

## Service Overview

### Service Details
- **Service Name**: Duo Workflow Service EKS
- **Namespace**: default
- **Cluster**: runway-eks-cluster
- **Region**: us-east-1
- **Endpoints**:
  - Production: `https://duo-workflow.aws.gitlab.com`
  - Staging: `https://duo-workflow.aws.staging.gitlab.com`

### Key Components
- **Deployment**: duo-workflow-svc-eks
- **Service**: duo-workflow-svc-eks-service
- **Ingress**: duo-workflow-svc-eks-ingress
- **HPA**: duo-workflow-svc-eks-hpa
- **ServiceAccount**: duo-workflow-svc-eks-sa

## Monitoring and Alerting

### Health Checks

#### Service Health
```bash
# Check service health endpoint
curl -f https://duo-workflow.aws.gitlab.com/health

# Expected response: HTTP 200 with health status
```

#### Pod Health
```bash
# Check pod status
kubectl get pods -l app=duo-workflow-svc-eks

# Check pod readiness
kubectl get pods -l app=duo-workflow-svc-eks -o wide
```

### Key Metrics to Monitor

1. **Availability**
   - Service uptime: `up{job="duo-workflow-svc-eks"}`
   - Pod readiness: `kube_pod_status_ready`

2. **Performance**
   - Request rate: `rate(http_requests_total[5m])`
   - Response time: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
   - Error rate: `rate(http_requests_total{status=~"5.."}[5m])`

3. **Resources**
   - CPU usage: `rate(container_cpu_usage_seconds_total[5m])`
   - Memory usage: `container_memory_usage_bytes`
   - Pod count: `kube_deployment_status_replicas`

### Alert Thresholds

| Alert | Threshold | Duration | Severity |
|-------|-----------|----------|----------|
| Service Down | up == 0 | 1m | Critical |
| High Error Rate | error_rate > 10% | 5m | Warning |
| High Latency | p95 > 2s | 5m | Warning |
| High CPU | cpu > 80% | 5m | Warning |
| High Memory | memory > 80% | 5m | Warning |

## Deployment Operations

### Standard Deployment

Deployments are automated through GitLab CI/CD:

1. **Trigger Deployment**
   ```bash
   # Manual deployment trigger (if needed)
   curl -X POST \
     -F token=$CI_JOB_TOKEN \
     -F ref=main \
     https://gitlab.com/api/v4/projects/39903947/trigger/pipeline
   ```

2. **Monitor Deployment**
   ```bash
   # Watch rollout status
   kubectl rollout status deployment/duo-workflow-svc-eks
   
   # Check deployment history
   kubectl rollout history deployment/duo-workflow-svc-eks
   ```

### Rollback Procedures

#### Quick Rollback
```bash
# Rollback to previous version
kubectl rollout undo deployment/duo-workflow-svc-eks

# Rollback to specific revision
kubectl rollout undo deployment/duo-workflow-svc-eks --to-revision=2
```

#### Verify Rollback
```bash
# Check rollout status
kubectl rollout status deployment/duo-workflow-svc-eks

# Verify service health
curl -f https://duo-workflow.aws.gitlab.com/health
```

## Scaling Operations

### Manual Scaling

#### Scale Replicas
```bash
# Scale to specific number of replicas
kubectl scale deployment duo-workflow-svc-eks --replicas=10

# Check scaling status
kubectl get deployment duo-workflow-svc-eks
```

#### Update HPA
```bash
# Edit HPA configuration
kubectl edit hpa duo-workflow-svc-eks-hpa

# Check HPA status
kubectl get hpa duo-workflow-svc-eks-hpa
```

### Auto-scaling Configuration

#### Current Settings
- **Staging**: 1-8 replicas, 70% CPU target
- **Production**: 8-16 replicas, 70% CPU target

#### Modify Scaling
```bash
# Update minimum replicas
kubectl patch hpa duo-workflow-svc-eks-hpa -p '{"spec":{"minReplicas":5}}'

# Update maximum replicas
kubectl patch hpa duo-workflow-svc-eks-hpa -p '{"spec":{"maxReplicas":20}}'

# Update CPU target
kubectl patch hpa duo-workflow-svc-eks-hpa -p '{"spec":{"targetCPUUtilizationPercentage":60}}'
```

## Troubleshooting

### Common Issues

#### 1. Pod Startup Failures

**Symptoms**: Pods stuck in `Pending`, `CrashLoopBackOff`, or `ImagePullBackOff`

**Investigation**:
```bash
# Check pod events
kubectl describe pod <pod-name>

# Check pod logs
kubectl logs <pod-name> --previous

# Check resource availability
kubectl describe nodes
```

**Common Causes**:
- Insufficient cluster resources
- Image pull failures
- Configuration errors
- Secret mounting issues

#### 2. Service Unavailable

**Symptoms**: HTTP 503 errors, connection timeouts

**Investigation**:
```bash
# Check service endpoints
kubectl get endpoints duo-workflow-svc-eks-service

# Check ingress status
kubectl describe ingress duo-workflow-svc-eks-ingress

# Check ALB target groups (AWS Console)
```

**Common Causes**:
- No healthy pods
- Ingress controller issues
- ALB configuration problems
- Security group restrictions

#### 3. High Latency

**Symptoms**: Slow response times, timeout errors

**Investigation**:
```bash
# Check resource utilization
kubectl top pods -l app=duo-workflow-svc-eks

# Check HPA status
kubectl get hpa

# Review application logs
kubectl logs -l app=duo-workflow-svc-eks --tail=100
```

**Common Causes**:
- Resource constraints
- Database connection issues
- External service dependencies
- Insufficient scaling

### Diagnostic Commands

```bash
# Pod diagnostics
kubectl get pods -l app=duo-workflow-svc-eks -o wide
kubectl describe pod <pod-name>
kubectl logs <pod-name> -f

# Service diagnostics
kubectl get svc duo-workflow-svc-eks-service -o yaml
kubectl describe svc duo-workflow-svc-eks-service

# Ingress diagnostics
kubectl get ingress duo-workflow-svc-eks-ingress -o yaml
kubectl describe ingress duo-workflow-svc-eks-ingress

# HPA diagnostics
kubectl get hpa duo-workflow-svc-eks-hpa
kubectl describe hpa duo-workflow-svc-eks-hpa

# Node diagnostics
kubectl get nodes
kubectl describe node <node-name>
kubectl top nodes
```

## Incident Response

### Severity Levels

#### P1 - Critical (Service Down)
- **Response Time**: 15 minutes
- **Actions**:
  1. Acknowledge alert
  2. Check service health endpoints
  3. Verify pod status and logs
  4. Escalate to on-call engineer
  5. Consider rollback if recent deployment

#### P2 - High (Performance Degradation)
- **Response Time**: 30 minutes
- **Actions**:
  1. Investigate metrics and logs
  2. Check resource utilization
  3. Scale if necessary
  4. Monitor for improvement

#### P3 - Medium (Non-critical Issues)
- **Response Time**: 2 hours
- **Actions**:
  1. Create issue for tracking
  2. Investigate during business hours
  3. Plan fix for next maintenance window

### Escalation Path

1. **Primary**: Duo Workflow Service team
2. **Secondary**: Platform Engineering team
3. **Tertiary**: Infrastructure team

### Communication

- **Status Page**: Update GitLab status page for user-facing issues
- **Slack**: #duo-workflow-service channel
- **PagerDuty**: For critical alerts

## Maintenance Procedures

### Planned Maintenance

#### Pre-maintenance Checklist
- [ ] Schedule maintenance window
- [ ] Notify stakeholders
- [ ] Prepare rollback plan
- [ ] Verify backup procedures

#### During Maintenance
- [ ] Monitor service metrics
- [ ] Verify each step before proceeding
- [ ] Document any issues encountered
- [ ] Test service functionality

#### Post-maintenance Checklist
- [ ] Verify service health
- [ ] Monitor for 30 minutes
- [ ] Update documentation
- [ ] Close maintenance window

### Configuration Updates

#### Environment Variables
```bash
# Update ConfigMap
kubectl edit configmap duo-workflow-svc-eks-config

# Restart deployment to pick up changes
kubectl rollout restart deployment/duo-workflow-svc-eks
```

#### Secrets
```bash
# Update secret
kubectl create secret generic env-vars \
  --from-env-file=new-env-vars.env \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart deployment
kubectl rollout restart deployment/duo-workflow-svc-eks
```

## Emergency Procedures

### Complete Service Outage

1. **Immediate Actions**
   ```bash
   # Check cluster status
   kubectl get nodes
   kubectl get pods --all-namespaces
   
   # Check AWS EKS cluster health (AWS Console)
   # Check ALB status (AWS Console)
   ```

2. **Recovery Steps**
   ```bash
   # Scale up replicas
   kubectl scale deployment duo-workflow-svc-eks --replicas=16
   
   # Force pod recreation
   kubectl delete pods -l app=duo-workflow-svc-eks
   
   # Check ingress controller
   kubectl get pods -n kube-system -l app=aws-load-balancer-controller
   ```

### Data Center Failover

1. **Assess Impact**
   - Check AWS region status
   - Verify multi-AZ deployment
   - Assess data replication status

2. **Failover Actions**
   - Update DNS to point to backup region (if available)
   - Scale up in alternate availability zones
   - Verify data consistency

### Security Incident

1. **Immediate Response**
   ```bash
   # Isolate affected pods
   kubectl label pod <pod-name> quarantine=true
   
   # Update network policies to restrict access
   kubectl apply -f emergency-network-policy.yaml
   
   # Scale down to minimum replicas
   kubectl scale deployment duo-workflow-svc-eks --replicas=1
   ```

2. **Investigation**
   - Collect logs and metrics
   - Preserve evidence
   - Coordinate with security team

## Contact Information

### Teams
- **Duo Workflow Service**: @duo-workflow-team
- **Platform Engineering**: @platform-engineering
- **Infrastructure**: @infrastructure-team
- **Security**: @security-team

### Emergency Contacts
- **On-call Engineer**: PagerDuty escalation
- **Team Lead**: [Contact information]
- **Manager**: [Contact information]

### Resources
- **Runbooks**: [Link to runbook repository]
- **Documentation**: [Link to service documentation]
- **Monitoring**: [Link to monitoring dashboards]
- **Logs**: [Link to log aggregation system]