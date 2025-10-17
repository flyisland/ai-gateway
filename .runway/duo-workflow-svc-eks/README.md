# Duo Workflow Service AWS EKS Deployment

This directory contains the configuration files for deploying the Duo Workflow Service on AWS EKS (Elastic Kubernetes Service) using GitLab's Runway platform.

## Overview

The Duo Workflow Service EKS deployment provides an AWS-based alternative to the existing GCP Cloud Run deployment, enabling GitLab to serve Duo Workflow functionality from AWS infrastructure.

## Architecture

```
Internet → ALB → EKS Cluster → Duo Workflow Service Pods
                              ↓
                         CloudWatch Logs
                              ↓
                         Prometheus Metrics
```

## Files Structure

```
.runway/duo-workflow-svc-eks/
├── README.md                    # This documentation
├── default-values.yaml          # Main Runway service configuration
├── eks-service-staging.yaml     # Staging environment deployment
├── eks-service-production.yaml  # Production environment deployment
├── env-staging.yml              # Staging environment variables
├── env-production.yml           # Production environment variables
├── resource-specs.yaml          # Resource specifications and limits
├── aws-env-vars.yaml           # AWS-specific environment variables
├── network-config.yaml         # Network, ingress, and load balancer config
├── security-config.yaml        # Security policies and IAM configurations
├── monitoring-config.yaml      # Monitoring and observability setup
└── operational-runbook.md      # Operations and troubleshooting guide
```

## Prerequisites

1. **AWS Infrastructure**: EKS cluster must be provisioned and configured
2. **Runway Access**: Service must be registered in Runway platform
3. **IAM Roles**: Appropriate IAM roles and policies must be created
4. **Secrets**: Required secrets must be stored in AWS Secrets Manager or Kubernetes secrets
5. **DNS**: DNS records must be configured for the service endpoints

## Configuration

### Environment Variables

The service uses environment variables from multiple sources:
- **Base Configuration**: Defined in `default-values.yaml`
- **Environment-Specific**: Defined in `env-staging.yml` and `env-production.yml`
- **AWS-Specific**: Defined in `aws-env-vars.yaml`

### Resource Specifications

Resource limits are configured to match the GCP Cloud Run deployment:
- **CPU**: 500m request, 2000m limit (2 cores)
- **Memory**: 2Gi request, 8Gi limit
- **Scaling**: 1-8 replicas (staging), 8-16 replicas (production)

### Networking

- **Ingress**: Application Load Balancer (ALB) with SSL termination
- **Service**: LoadBalancer type service exposing ports 8000 (HTTP) and 8082 (metrics)
- **Endpoints**: 
  - Staging: `duo-workflow.aws.staging.gitlab.com`
  - Production: `duo-workflow.aws.gitlab.com`

## Deployment Process

### 1. Infrastructure Setup

Ensure the following AWS resources are available:
- EKS cluster with appropriate node groups
- VPC with public and private subnets
- Security groups allowing traffic on ports 8000 and 8082
- IAM roles for service account and pod execution
- ACM certificate for SSL termination

### 2. Secrets Configuration

Create the required secrets in Kubernetes:
```bash
# GCP service account (for compatibility)
kubectl create secret generic gcp-service-account \
  --from-file=credentials.json=path/to/gcp-credentials.json

# Environment variables secret
kubectl create secret generic env-vars \
  --from-env-file=path/to/env-vars.env
```

### 3. Deploy via GitLab CI/CD

The deployment is automated through GitLab CI/CD pipeline:
1. Code changes trigger the pipeline
2. Docker image is built and pushed to registry
3. Runway deployment is triggered for EKS
4. Health checks verify successful deployment

### 4. Verification

After deployment, verify the service is running:
```bash
# Check pod status
kubectl get pods -l app=duo-workflow-svc-eks

# Check service endpoints
kubectl get svc duo-workflow-svc-eks-service

# Check ingress
kubectl get ingress duo-workflow-svc-eks-ingress

# Test health endpoint
curl https://duo-workflow.aws.staging.gitlab.com/health
```

## Monitoring

### CloudWatch Integration

- **Logs**: Application logs are sent to CloudWatch Logs group `/aws/eks/duo-workflow-svc`
- **Metrics**: Custom metrics are published to CloudWatch namespace `DuoWorkflowService/EKS`
- **Container Insights**: Provides cluster-level metrics and insights

### Prometheus Metrics

The service exposes Prometheus metrics on port 8082:
- HTTP request metrics
- Application-specific metrics
- Resource utilization metrics

### Alerting

Prometheus alerting rules are configured for:
- Service availability
- High error rates
- High latency
- Resource utilization

## Security

### IAM Integration

- Service account is annotated with IAM role ARN
- Pod security policies restrict container capabilities
- Network policies control ingress/egress traffic

### Secrets Management

- Sensitive configuration stored in Kubernetes secrets
- GCP service account key mounted as volume
- Environment variables injected from secrets

## Differences from GCP Deployment

| Aspect | GCP Cloud Run | AWS EKS |
|--------|---------------|---------|
| Platform | Serverless | Kubernetes |
| Scaling | Automatic | HPA-based |
| Load Balancer | Google LB | AWS ALB |
| Logging | Cloud Logging | CloudWatch |
| Metrics | Cloud Monitoring | CloudWatch + Prometheus |
| Networking | VPC Connector | VPC + Security Groups |
| SSL | Google-managed | ACM certificates |

## Troubleshooting

### Common Issues

1. **Pod Startup Issues**
   - Check resource limits and requests
   - Verify secrets are properly mounted
   - Review startup probe configuration

2. **Network Connectivity**
   - Verify security group rules
   - Check ingress controller status
   - Validate DNS resolution

3. **Performance Issues**
   - Monitor resource utilization
   - Check HPA scaling behavior
   - Review application logs

### Useful Commands

```bash
# View pod logs
kubectl logs -l app=duo-workflow-svc-eks -f

# Describe pod for events
kubectl describe pod <pod-name>

# Check HPA status
kubectl get hpa

# View ingress details
kubectl describe ingress duo-workflow-svc-eks-ingress
```

## Support

For issues related to:
- **Infrastructure**: Contact Platform Engineering team
- **Application**: Contact Duo Workflow Service team
- **Runway**: Contact Runway platform team

## References

- [Runway Documentation](https://gitlab-com.gitlab.io/gl-infra/platform/runway/)
- [AWS EKS Documentation](https://docs.aws.amazon.com/eks/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [GitLab CI/CD Documentation](https://docs.gitlab.com/ee/ci/)