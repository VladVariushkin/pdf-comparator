import os

# Required so that importing api/tasks/config in tests doesn't raise RuntimeError.
# Tests that need a real Redis connection must set up their own mocks.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
