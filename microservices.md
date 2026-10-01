# Architectural Blueprint: Decomposing into Auth & RAG Microservices on Kubernetes

This document provides a complete architectural design and a step-by-step implementation guide to decompose the current FastAPI application into two decoupled, independently scalable microservices running on Kubernetes:

1. **`auth-service`**: Identity provider, user authentication, RBAC management, and token lifecycle.
2. **`rag-service`**: Document ingestion, parsing, embedding generation, vector/keyword hybrid retrieval, reranking, and guardrail pipelines.

---

## 1. Architectural Overview & Boundary Separation

```
                       ┌─────────────────────────────────────────┐
                       │       Kubernetes Ingress / Gateway      │
                       │          (e.g., ingress-nginx)          │
                       └────────────────────┬────────────────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │                                               │
      Route: `/api/v1/auth/**`                         Route: `/api/v1/documents/**`
      Route: `/api/v1/users/**`                        Route: `/api/v1/rag/**`
                    │                                               │
                    ▼                                               ▼
         ┌─────────────────────┐                         ┌─────────────────────┐
         │    auth-service     │                         │     rag-service     │
         │  (FastAPI - 2+ rep) │                         │ (FastAPI + ML Model)│
         └──────────┬──────────┘                         └──────────┬──────────┘
                    │                                               │
        ┌───────────┴───────────┐                       ┌───────────┴───────────┐
        ▼                       ▼                       ▼           ▼           ▼
  ┌───────────┐           ┌───────────┐           ┌───────────┐ ┌───────┐ ┌───────────┐
  │  Auth DB  │           │   Redis   │           │ RAG DB    │ │ S3 /  │ │ ML Model  │
  │ (Postgres)│           │  (Tokens) │           │ (pgvector)│ │ MinIO │ │    PVC    │
  └───────────┘           └───────────┘           └───────────┘ └───────┘ └───────────┘
```

### Key Separation of Concerns

| Dimension | `auth-service` | `rag-service` |
| :--- | :--- | :--- |
| **Primary Responsibility** | User identity, password verification, RS256 token issuance & refresh. | Multimodal document parsing, chunking, embedding generation, hybrid search, reranking, guardrails. |
| **Data Storage** | PostgreSQL (`users`, `refresh_tokens`) + Redis (rate limiting & token blocklist). | PostgreSQL with `pgvector` (`documents`, `chunks`) + S3/MinIO for file blobs. |
| **Compute Profile** | CPU-light, I/O-bound, ultra-low latency (< 50ms). | CPU/GPU-intensive (SentenceTransformers, CrossEncoder reranking, Docling parsing). |
| **Scaling Trigger** | Concurrency, login requests per second. | Search throughput, heavy ingestion batches, embedding matrix calculations. |
| **Auth Verification** | Issues JWTs signed by RSA Private Key (`jwt-private.pem`). | Validates JWTs locally via RSA Public Key (`jwt-public.pem`) without inter-service RPCs. Checks `rag:query` and `rag:ingest` scopes. |

---

## 2. Stateless Authentication & Inter-Service Security

To avoid high-latency synchronous calls where every RAG search calls the Auth service, leverage **asymmetric RS256 JWTs**:

1. **`auth-service`** holds the **Private Key** (in a K8s Secret) to sign access tokens containing:
   - `sub`: User ID
   - `scopes`: e.g. `["rag:query", "rag:ingest"]`
   - `exp`: Expiration timestamp
2. **`rag-service`** mounts only the **Public Key** (or fetches it from `auth-service/.well-known/jwks.json` at startup).
3. When a client sends `Authorization: Bearer <token>` to `/api/v1/documents/search`, `rag-service` verifies the signature cryptographically in-process.

---

## 3. Step-by-Step Implementation Roadmap

### Phase 1: Codebase Refactoring & Decoupling

1. **Adopt a Monorepo Structure or Split Repositories**:
   * Suggested layout within monorepo:
     ```
     services/
       ├── auth/
       │   ├── app/
       │   │   ├── api/v1/endpoints/{auth.py, users.py}
       │   │   ├── core/{config.py, security.py}
       │   │   ├── db/
       │   │   ├── models/{user.py, token.py}
       │   │   └── services/{auth_service.py, user_service.py}
       │   ├── Dockerfile
       │   └── pyproject.toml
       └── rag/
           ├── app/
           │   ├── api/v1/endpoints/{documents.py, search.py}
           │   ├── rag/{ingestion, retrieval, models}
           │   ├── guardrails/
           │   ├── models/{document.py, chunk.py}
           │   └── repositories/{chunk_repository.py, document_repository.py}
           ├── Dockerfile
           └── pyproject.toml
     ```
2. **Eliminate Cross-Domain Imports**:
   - `rag-service` replaces `from app.models.user import User` with a lightweight `AuthPrincipal(id=str, scopes=list[str])` populated from the verified JWT claims.

---

### Phase 2: Database & Storage Decoupling

1. **Database-per-Service Pattern**:
   - Split database schemas/instances into `auth_db` and `rag_db`.
   - `rag_db` requires PostgreSQL with `pgvector` enabled (`vector` and `tsvector` columns).
2. **Decouple File Uploads**:
   - Migrate `LocalFileStorage` from local disk volume mounts to an S3-compatible object store (AWS S3, Google Cloud Storage, or MinIO on K8s).

---

### Phase 3: Dockerization

Create dedicated container images:

1. **`services/auth/Dockerfile`**:
   - Minimal Python slim image running `uvicorn app.main:app`.
2. **`services/rag/Dockerfile`**:
   - Includes PyTorch/SentenceTransformers and PyTorch runtime dependencies.
   - Pre-downloads or mounts huggingface cache weights.

---

### Phase 4: Kubernetes Deployment Manifests

Below are the production-grade Kubernetes resource definitions.

#### 1. Ingress Configuration (`ingress.yaml`)
Routes incoming HTTP traffic to the appropriate microservice based on URL path.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: platform-ingress
  namespace: rag-platform
  annotations:
    kubernetes.io/ingress.class: "nginx"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m" # Supports large file ingestion
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
spec:
  rules:
  - http:
      paths:
      # Route Auth & Users to auth-service
      - path: /api/v1/auth
        pathType: Prefix
        backend:
          service:
            name: auth-service
            port:
              number: 8000
      - path: /api/v1/users
        pathType: Prefix
        backend:
          service:
            name: auth-service
            port:
              number: 8000
      # Route Documents & Search to rag-service
      - path: /api/v1/documents
        pathType: Prefix
        backend:
          service:
            name: rag-service
            port:
              number: 8000
```

---

#### 2. Auth Service Deployment & Service (`auth-deployment.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-service
  namespace: rag-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: auth-service
  template:
    metadata:
      labels:
        app: auth-service
    spec:
      containers:
      - name: auth-service
        image: ghcr.io/your-org/auth-service:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: auth-secrets
              key: database-url
        - name: JWT_PRIVATE_KEY_PATH
          value: "/secrets/jwt-private.pem"
        - name: JWT_PUBLIC_KEY_PATH
          value: "/secrets/jwt-public.pem"
        volumeMounts:
        - name: jwt-keys
          mountPath: "/secrets"
          readOnly: true
        resources:
          requests:
            cpu: "250m"
            memory: "512Mi"
          limits:
            cpu: "1000m"
            memory: "1Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: jwt-keys
        secret:
          secretName: jwt-keypair-secret
---
apiVersion: v1
kind: Service
metadata:
  name: auth-service
  namespace: rag-platform
spec:
  selector:
    app: auth-service
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
```

---

#### 3. RAG Service Deployment & Service (`rag-deployment.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rag-service
  namespace: rag-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: rag-service
  template:
    metadata:
      labels:
        app: rag-service
    spec:
      containers:
      - name: rag-service
        image: ghcr.io/your-org/rag-service:v1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: rag-secrets
              key: database-url
        - name: JWT_PUBLIC_KEY_PATH
          value: "/secrets/jwt-public.pem"
        - name: S3_ENDPOINT_URL
          value: "http://minio-service:9000"
        - name: S3_BUCKET_NAME
          value: "rag-documents"
        - name: MODELS_DIR
          value: "/models"
        volumeMounts:
        - name: jwt-public-key
          mountPath: "/secrets"
          readOnly: true
        - name: model-weights
          mountPath: "/models"
        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
          limits:
            cpu: "4000m"
            memory: "8Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 15
      volumes:
      - name: jwt-public-key
        secret:
          secretName: jwt-public-secret
      - name: model-weights
        persistentVolumeClaim:
          claimName: rag-models-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: rag-service
  namespace: rag-platform
spec:
  selector:
    app: rag-service
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
```

---

#### 4. Persistent Volume Claim for Shared ML Models (`pvc-models.yaml`)

To avoid each RAG pod downloading sentence transformers and reranker models on boot, use a shared `ReadWriteMany` volume populated by an initialization Job or shared storage.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: rag-models-pvc
  namespace: rag-platform
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 20Gi
```

---

## 5. Autoscaling Strategy (HPA)

Because Auth and RAG have vastly different bottleneck profiles:

```yaml
# RAG Autoscaler: Scales based on CPU/Memory or custom GPU metrics
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: rag-service-hpa
  namespace: rag-platform
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: rag-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 75
```

---

## 6. Summary Checklist for Migration

1. **Auth Key Management**: Store the RSA keypair in Kubernetes Secrets (`jwt-keypair-secret` for Auth, `jwt-public-secret` for RAG).
2. **Database Separation**: Provision separate DB users/databases (`auth_db` and `rag_db` with `pgvector`).
3. **Storage Abstraction**: Replace local storage with S3/MinIO for raw uploaded files.
4. **Model Caching**: Use a Kubernetes PVC or pre-baked image layers for HuggingFace/SentenceTransformers embeddings.
5. **Gateway Routing**: Apply the Ingress resource to route traffic cleanly to both services under a single domain.
