"""SportPredict AI API."""
import os

# Bound native BLAS thread pools in API/worker processes. Celery supplies process
# parallelism; unlimited native threads multiply memory use on large hosts.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
