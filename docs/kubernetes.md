# Kubernetes lab validation

The recorded validation used kind 0.33.0 with Kubernetes 1.37.0 in Docker on an ARM64 host. It created a separate `opspilot-validation` cluster using an explicit temporary kubeconfig. The validator checks the context name before creating a namespace. It never uses the ambient Kubernetes context.

Prerequisites: Docker, trusted `kind` and `kubectl` binaries, and the Python development environment. Follow the [official kind installation instructions](https://kind.sigs.k8s.io/docs/user/quick-start/) and verify the release checksum before executing a downloaded binary.

```sh
kind create cluster --name opspilot-validation --kubeconfig /tmp/opspilot-validation-kubeconfig --wait 120s
KUBECONFIG=/tmp/opspilot-validation-kubeconfig .venv/bin/python -m scripts.kubernetes_validate
kind delete cluster --name opspilot-validation --kubeconfig /tmp/opspilot-validation-kubeconfig
```

The validator creates a namespace, introduces a BusyBox deployment which exits unsuccessfully, waits until an actual restart is observed, and checks that OpsPilot reports unready pods and unavailable replicas. It collects node conditions without inducing node failure. It then deletes the failing deployment, starts a healthy deployment, waits for rollout, and requires a healthy diagnostic result. The namespace is deleted in a finally block. Delete the entire disposable cluster even if validation fails.

[Structured evidence](kubernetes-validation.json) includes both failing and healthy outcomes. [Validation output](kubernetes-tests.txt) records the rollout result. [Cleanup evidence](kubernetes-cleanup.txt) records removal of the disposable cluster. No Kubernetes remediation, production cluster mutation, or node-failure recovery is claimed. Node failure conditions are covered with fixtures.

The runtime collector follows the diagnostic pattern described by [Kubernetes troubleshooting documentation](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/): inspect readiness, state, restarts, and resource status before choosing an action. It projects status evidence and excludes workload specifications which may contain inline credentials.
