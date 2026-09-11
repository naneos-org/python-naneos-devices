import nox

# Use uv to create the session environments.
nox.options.default_venv_backend = "uv"


@nox.session(python=["3.11", "3.12", "3.13", "3.14"])
def tests(session):
    """Run the hardware-free test suite. Hardware tests: `uv run pytest -m hardware`."""
    session.install(".", "pytest", "pytest-timeout")
    session.run("pytest")
