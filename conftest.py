import os

# Default test environment configuration for pytest runs
os.environ.setdefault("USE_MEMORY_BUS_ONLY", "true")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("VMS_SECRET_KEY", "test_jwt_secret_key_for_unit_tests_32_chars_min")
